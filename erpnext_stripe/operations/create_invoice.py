from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
	from stripe import Invoice as StripeInvoice


import frappe
import requests
import stripe
from frappe import _
from frappe.utils import get_system_timezone
from frappe.utils.data import flt, getdate, today

from erpnext_stripe.operations.create_customer import run as create_customer
from erpnext_stripe.operations.create_lead import run as create_lead
from erpnext_stripe.operations.create_product import run as create_product
from erpnext_stripe.tax_rates import (
	get_tax_rate_calculation,
	get_tax_rate_percentage,
	get_tax_rate_region,
)


class MissingTaxAccountError(frappe.ValidationError):
	def __init__(self, tax_rate_id: str):
		super().__init__(tax_rate_id)
		self.tax_rate_id = tax_rate_id


def run(invoice: "StripeInvoice") -> "SalesInvoice | None":
	if frappe.db.exists("Sales Invoice", {"stripe_id": invoice.id}):
		return

	is_trial = not invoice.total

	if is_trial:
		# Ensure a Lead exists for this Stripe customer, then skip the invoice
		if not frappe.db.exists("Lead", {"stripe_id": invoice.customer}) and not frappe.db.exists(
			"Customer", {"stripe_id": invoice.customer}
		):
			try:
				stripe_customer = stripe.Customer.retrieve(invoice.customer)
			except stripe.InvalidRequestError:
				frappe.log_error(title=f"Stripe Invoice: Customer {invoice.customer} not found")
				return
			create_lead(stripe_customer)
		return

	_ensure_customer(invoice.customer)

	settings = frappe.get_single("ERPNext Stripe Settings")
	tax_rows = _get_invoice_tax_rows(invoice, settings)

	invoice_doc: SalesInvoice = frappe.new_doc("Sales Invoice")
	invoice_doc.stripe_id = invoice.id
	if invoice.number:
		invoice_doc.name = invoice.number
		invoice_doc.flags.name_set = True
	invoice_doc.due_date = invoice.due_date or today()
	# Stripe has already determined the due date; customer defaults must not shorten it.
	invoice_doc.payment_terms_template = ""
	invoice_doc.ignore_default_payment_terms_template = 1
	invoice_doc.customer = frappe.db.get_value("Customer", {"stripe_id": invoice.customer})
	invoice_doc.project = settings.project
	invoice_doc.selling_price_list = settings.price_list
	_set_posting_datetime(invoice_doc, invoice)
	_set_subscription_period(invoice_doc, invoice)

	for line in invoice.lines.data:
		product_id = _get_product_id(line)
		if not frappe.db.exists("Item", {"stripe_id": product_id}):
			try:
				stripe_product = stripe.Product.retrieve(product_id)
			except stripe.InvalidRequestError:
				stripe_product = None

			if stripe_product:
				create_product(stripe_product)
			else:
				_create_minimal_item(product_id, line)

		item_code = frappe.db.get_value("Item", {"stripe_id": product_id})
		_ensure_sales_item(item_code)
		quantity = _get_quantity(line)
		rate = _get_rate(line, quantity)

		invoice_doc.append(
			"items",
			{
				"item_code": item_code,
				"qty": quantity,
				"rate": rate,
			},
		)

	for tax_rate_id, config in tax_rows:
		invoice_doc.append(
			"taxes",
			{
				"charge_type": "On Net Total",
				"account_head": config.account,
				"rate": flt(config.rate),
				"description": config.region or tax_rate_id,
				"cost_center": "",
			},
		)

	invoice_doc.set_missing_values()
	invoice_doc.payment_terms_template = ""
	invoice_doc.payment_schedule = []
	invoice_doc.save()

	try:
		invoice_doc.submit()
	except Exception:
		frappe.log_error(title="Stripe Invoice: Submit Error")

	_attach_invoice_pdf(invoice, invoice_doc)
	return invoice_doc


def _get_product_id(line) -> str:
	price_details = getattr(getattr(line, "pricing", None), "price_details", None)
	if product_id := getattr(price_details, "product", None):
		return product_id

	price = getattr(line, "price", None)
	if product_id := getattr(price, "product", None):
		return product_id

	frappe.throw(_("Stripe invoice line {0} has no product in its pricing data.").format(line.id))


def _get_quantity(line) -> float:
	quantity = getattr(line, "quantity_decimal", None)
	if quantity is None:
		quantity = getattr(line, "quantity", None)

	return flt(quantity or 1)


def _get_rate(line, quantity: float) -> float:
	amount_excluding_tax = getattr(line, "amount_excluding_tax", None)
	if amount_excluding_tax is not None:
		return flt(amount_excluding_tax / 100 / quantity)

	pricing = getattr(line, "pricing", None)
	unit_amount_decimal = getattr(pricing, "unit_amount_decimal", None)
	if unit_amount_decimal is not None:
		return flt(unit_amount_decimal) / 100

	price = getattr(line, "price", None)
	unit_amount = getattr(price, "unit_amount", None)
	if unit_amount is not None:
		return flt(unit_amount / 100)

	for amount_field in ("subtotal", "amount"):
		amount = getattr(line, amount_field, None)
		if amount is not None:
			return flt(amount / 100 / quantity)

	frappe.throw(_("Stripe invoice line {0} has no unit amount in its pricing data.").format(line.id))


def _set_posting_datetime(invoice_doc: "SalesInvoice", invoice: "StripeInvoice"):
	posting_datetime = _get_invoice_posting_datetime(invoice)
	if not posting_datetime:
		return

	invoice_doc.set_posting_time = 1
	invoice_doc.posting_date = getdate(posting_datetime)
	if invoice_doc.meta.has_field("posting_time"):
		invoice_doc.posting_time = posting_datetime.time().replace(microsecond=0)


def _get_invoice_posting_datetime(invoice: "StripeInvoice") -> datetime | None:
	timestamp = _get_invoice_accounting_timestamp(invoice)
	if timestamp is None:
		return None

	system_timezone = ZoneInfo(get_system_timezone())
	return datetime.fromtimestamp(timestamp, tz=system_timezone)


def _get_invoice_accounting_timestamp(invoice: "StripeInvoice") -> int | None:
	effective_at = getattr(invoice, "effective_at", None)
	if effective_at is not None:
		return effective_at

	status_transitions = getattr(invoice, "status_transitions", None)
	finalized_at = getattr(status_transitions, "finalized_at", None)
	if finalized_at is not None:
		return finalized_at

	return getattr(invoice, "created", None)


def _set_subscription_period(invoice_doc: "SalesInvoice", invoice: "StripeInvoice"):
	period = _get_invoice_line_period(invoice)
	if not period:
		return

	period_start, period_end = period
	invoice_doc.from_date = _get_timestamp_date(period_start)
	invoice_doc.to_date = _get_timestamp_date(period_end - 1)


def _get_invoice_line_period(invoice: "StripeInvoice") -> tuple[int, int] | None:
	periods = []
	for line in invoice.lines.data:
		period = getattr(line, "period", None)
		period_start = getattr(period, "start", None)
		period_end = getattr(period, "end", None)
		if period_start is None or period_end is None or period_end <= period_start:
			continue

		periods.append((period_start, period_end))

	if not periods:
		return None

	return min(period[0] for period in periods), max(period[1] for period in periods)


def _get_timestamp_date(timestamp: int):
	system_timezone = ZoneInfo(get_system_timezone())
	return getdate(datetime.fromtimestamp(timestamp, tz=system_timezone))


def _ensure_customer(stripe_customer_id: str):
	"""Ensure a Customer exists for the given Stripe customer ID, promoting from Lead if needed."""
	if frappe.db.exists("Customer", {"stripe_id": stripe_customer_id}):
		return

	try:
		stripe_customer = stripe.Customer.retrieve(stripe_customer_id)
	except stripe.InvalidRequestError:
		frappe.throw(_("Customer {0} not found in Stripe").format(stripe_customer_id))

	lead_name = frappe.db.get_value("Lead", {"stripe_id": stripe_customer_id})
	if lead_name:
		# Promote Lead to Customer: create Customer with lead_name link
		create_customer(stripe_customer, lead_name=lead_name)
	else:
		create_customer(stripe_customer)


def _get_tax_config(settings) -> dict:
	return {row.stripe_id: row for row in settings.tax_configurations if row.stripe_id}


def _get_invoice_tax_rows(
	invoice: "StripeInvoice",
	settings,
) -> list[tuple[str, object]]:
	"""Resolve invoice tax rates against ERPNext Stripe Settings.

	Unknown Stripe tax rate IDs are imported into `settings.tax_configurations`
	as a side effect (with the account copied from a uniquely matching existing
	row, when available). The settings doc is saved once per imported rate.
	"""
	tax_rows = []
	seen = set()
	tax_config = _get_tax_config(settings)

	for tax in _get_tax_entries(invoice, "total_tax_amounts", "total_taxes"):
		if not tax.amount:
			continue

		tax_rate_id = _get_tax_rate_id(tax)
		if not tax_rate_id or tax_rate_id in seen:
			continue

		config = tax_config.get(tax_rate_id) or _import_tax_config_for_rate(tax_rate_id, settings)
		if not config:
			frappe.throw(
				_(
					"No tax configuration found for Stripe tax rate {0}. "
					"Please import it in ERPNext Stripe Settings."
				).format(tax_rate_id)
			)

		if not config.account:
			raise MissingTaxAccountError(tax_rate_id)

		tax_rows.append((tax_rate_id, config))
		seen.add(tax_rate_id)

	return tax_rows


def _import_tax_config_for_rate(tax_rate_id: str, settings):
	try:
		tax_rate = stripe.TaxRate.retrieve(tax_rate_id)
	except stripe.InvalidRequestError:
		return None

	matching_config = _get_matching_tax_config(settings.tax_configurations, tax_rate)
	account = matching_config.account if matching_config else None
	return _import_tax_config(settings, tax_rate, account=account)


def _get_matching_tax_config(configs, tax_rate):
	matches = [config for config in configs if _tax_config_matches_tax_rate(config, tax_rate)]
	if len(matches) == 1:
		return matches[0]


def _import_tax_config(settings, tax_rate, account: str | None = None):
	config = settings.append(
		"tax_configurations",
		{
			"stripe_id": tax_rate.id,
			"region": get_tax_rate_region(tax_rate),
			"rate": get_tax_rate_percentage(tax_rate),
			"calculation": get_tax_rate_calculation(tax_rate),
			"account": account,
		},
	)
	settings.save()
	return config


def _tax_config_matches_tax_rate(config, tax_rate) -> bool:
	return (
		(config.region or None) == get_tax_rate_region(tax_rate)
		and flt(config.rate) == get_tax_rate_percentage(tax_rate)
		and config.calculation == get_tax_rate_calculation(tax_rate)
	)


def _get_tax_entries(source, *fieldnames: str):
	for fieldname in fieldnames:
		if entries := getattr(source, fieldname, None):
			return entries

	return []


def _get_tax_rate_id(tax) -> str | None:
	"""Extract the tax rate ID from current and legacy Stripe tax entry shapes."""
	tax_rate = getattr(tax, "tax_rate", None)
	if not tax_rate:
		tax_rate_details = getattr(tax, "tax_rate_details", None)
		tax_rate = getattr(tax_rate_details, "tax_rate", None)

	if isinstance(tax_rate, str):
		return tax_rate

	return getattr(tax_rate, "id", None)


def _create_minimal_item(product_id: str, line):
	"""Create a minimal Item from invoice line data when the product can't be fetched from Stripe."""
	from erpnext_stripe.operations.create_product import _resolve_item_group, _resolve_stock_uom

	item_doc = frappe.new_doc("Item")
	item_doc.stripe_id = product_id
	item_doc.item_code = product_id
	item_doc.item_name = getattr(line, "description", None) or product_id

	if item_group := _resolve_item_group():
		item_doc.item_group = item_group

	if stock_uom := _resolve_stock_uom():
		item_doc.stock_uom = stock_uom

	item_doc.is_stock_item = 0
	item_doc.is_sales_item = 1
	item_doc.save()


def _ensure_sales_item(item_code: str):
	"""Any Item linked to a Stripe product must be a sales item, since it appears on Stripe invoices.

	This corrects existing Items that were linked (e.g. manually) without the flag set.
	"""
	if frappe.db.get_value("Item", item_code, "is_sales_item"):
		return

	item_doc = frappe.get_doc("Item", item_code)
	item_doc.is_sales_item = 1
	item_doc.save()


def _attach_invoice_pdf(invoice: "StripeInvoice", invoice_doc: "SalesInvoice"):
	"""Download the Stripe invoice PDF and attach it to the Sales Invoice."""
	invoice_pdf_url = getattr(invoice, "invoice_pdf", None)
	if not invoice_pdf_url:
		return

	try:
		response = requests.get(invoice_pdf_url, timeout=30)
		response.raise_for_status()
	except Exception:
		frappe.log_error(title="Stripe Invoice: PDF Download Error")
		return

	filename = f"{invoice.number or invoice.id}.pdf"

	file_doc = frappe.new_doc("File")
	file_doc.file_name = filename
	file_doc.content = response.content
	file_doc.attached_to_doctype = "Sales Invoice"
	file_doc.attached_to_name = invoice_doc.name
	file_doc.is_private = 1
	file_doc.save()
