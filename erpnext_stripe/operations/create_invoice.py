from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
	from stripe import Invoice as StripeInvoice


import frappe
import requests
import stripe
from frappe.utils.data import flt, today

from erpnext_stripe.operations.create_customer import run as create_customer
from erpnext_stripe.operations.create_lead import run as create_lead
from erpnext_stripe.operations.create_product import run as create_product


def run(invoice: "StripeInvoice", ignore_permissions: bool = False):
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
			create_lead(stripe_customer, ignore_permissions=ignore_permissions)
		return

	_ensure_customer(invoice.customer, ignore_permissions=ignore_permissions)

	settings = frappe.get_single("ERPNext Stripe Settings")
	tax_config = _get_tax_config(settings)

	invoice_doc: SalesInvoice = frappe.new_doc("Sales Invoice")
	invoice_doc.stripe_id = invoice.id
	if invoice.number:
		invoice_doc.name = invoice.number
		invoice_doc.flags.name_set = True
	invoice_doc.due_date = invoice.due_date or today()
	invoice_doc.customer = frappe.db.get_value("Customer", {"stripe_id": invoice.customer})
	invoice_doc.project = settings.project
	invoice_doc.selling_price_list = settings.price_list

	for line in invoice.lines.data:
		product_id = _get_product_id(line)
		if not frappe.db.exists("Item", {"stripe_id": product_id}):
			try:
				stripe_product = stripe.Product.retrieve(product_id)
			except stripe.InvalidRequestError:
				stripe_product = None

			if stripe_product:
				create_product(stripe_product, ignore_permissions=ignore_permissions)
			else:
				_create_minimal_item(product_id, line, ignore_permissions=ignore_permissions)

		item_code = frappe.db.get_value("Item", {"stripe_id": product_id})
		quantity = _get_quantity(line)
		rate = _get_rate(line, quantity)

		invoice_doc.append("items", {
			"item_code": item_code,
			"qty": quantity,
			"rate": rate,
		})

	for tax in getattr(invoice, "total_tax_amounts", None) or []:
		if not tax.amount:
			continue

		tax_rate_id = _get_tax_rate_id(tax)
		if not tax_rate_id:
			continue

		config = tax_config.get(tax_rate_id)
		if not config:
			frappe.throw(
				f"No tax configuration found for Stripe tax rate {tax_rate_id}. "
				"Please import it in ERPNext Stripe Settings."
			)

		invoice_doc.append("taxes", {
			"charge_type": "Actual",
			"account_head": config.account,
			"tax_amount": tax.amount / 100,
			"description": config.region or tax_rate_id,
			"cost_center": "",
		})

	invoice_doc.set_missing_values()
	invoice_doc.save(ignore_permissions=ignore_permissions)

	try:
		invoice_doc.flags.ignore_permissions = ignore_permissions
		invoice_doc.submit()
	except Exception:
		frappe.log_error(title="Stripe Invoice: Submit Error")

	_attach_invoice_pdf(invoice, invoice_doc)


def _get_product_id(line) -> str:
	price_details = getattr(getattr(line, "pricing", None), "price_details", None)
	if product_id := getattr(price_details, "product", None):
		return product_id

	price = getattr(line, "price", None)
	if product_id := getattr(price, "product", None):
		return product_id

	frappe.throw(f"Stripe invoice line {line.id} has no product in its pricing data.")


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
		return flt(unit_amount_decimal / 100)

	price = getattr(line, "price", None)
	unit_amount = getattr(price, "unit_amount", None)
	if unit_amount is not None:
		return flt(unit_amount / 100)

	frappe.throw(f"Stripe invoice line {line.id} has no unit amount in its pricing data.")


def _ensure_customer(stripe_customer_id: str, ignore_permissions: bool = False):
	"""Ensure a Customer exists for the given Stripe customer ID, promoting from Lead if needed."""
	if frappe.db.exists("Customer", {"stripe_id": stripe_customer_id}):
		return

	try:
		stripe_customer = stripe.Customer.retrieve(stripe_customer_id)
	except stripe.InvalidRequestError:
		frappe.throw(f"Customer {stripe_customer_id} not found in Stripe")

	lead_name = frappe.db.get_value("Lead", {"stripe_id": stripe_customer_id})
	if lead_name:
		# Promote Lead to Customer: create Customer with lead_name link
		create_customer(stripe_customer, ignore_permissions=ignore_permissions, lead_name=lead_name)
	else:
		create_customer(stripe_customer, ignore_permissions=ignore_permissions)


def _get_tax_config(settings) -> dict:
	return {row.stripe_id: row for row in settings.tax_configurations if row.stripe_id}


def _get_tax_rate_id(tax) -> str | None:
	"""Extract the tax rate ID from a total_tax_amounts entry."""
	# total_tax_amounts[].tax_rate is the tax rate ID string or object
	tax_rate = getattr(tax, "tax_rate", None)
	if not tax_rate:
		return None

	if isinstance(tax_rate, str):
		return tax_rate

	return getattr(tax_rate, "id", None)


def _create_minimal_item(product_id: str, line, ignore_permissions: bool = False):
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
	item_doc.save(ignore_permissions=ignore_permissions)


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
	file_doc.save(ignore_permissions=True)
