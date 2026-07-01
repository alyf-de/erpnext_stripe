from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import frappe
import stripe
from frappe import _
from frappe.utils import get_system_timezone, getdate

from erpnext_stripe.operations.create_bank_transaction import run as create_bank_transaction
from erpnext_stripe.operations.create_customer import run as create_customer
from erpnext_stripe.operations.create_invoice import (
	MissingTaxAccountError,
)
from erpnext_stripe.operations.create_invoice import (
	run as create_invoice,
)
from erpnext_stripe.operations.create_product import run as create_product
from erpnext_stripe.tax_rates import get_tax_rate_data
from erpnext_stripe.utils import configure_stripe

SETTINGS_DOCTYPE = "ERPNext Stripe Settings"


@frappe.whitelist(methods=["POST"])
def list_customers():
	frappe.has_permission("Customer", throw=True)

	init_stripe()
	customers = list(stripe.Customer.list(limit=100).auto_paging_iter())
	existing_customer_ids = _get_existing_stripe_ids("Customer", [customer.id for customer in customers])
	customers = [customer for customer in customers if customer.id not in existing_customer_ids]

	return [
		{
			"stripe_id": customer.id,
			"name": getattr(customer, "name", None) or getattr(customer, "email", None) or customer.id,
			"email": getattr(customer, "email", None),
			"currency": (getattr(customer, "currency", None) or "").upper() or None,
			"existing_customer": None,
		}
		for customer in customers
	]


@frappe.whitelist(methods=["POST"])
def import_customers(customer_ids: str | None = None, customers: str | None = None):
	frappe.has_permission("Customer", ptype="create", throw=True)

	init_stripe()
	customers = _parse_import_rows(
		rows=customers,
		stripe_ids=customer_ids,
		label="customer",
		existing_fieldname="existing_customer",
	)

	total = len(customers)
	for count, customer in enumerate(customers, start=1):
		try:
			if existing_customer := customer.get("existing_customer"):
				_attach_stripe_id("Customer", existing_customer, customer["stripe_id"])
				continue

			create_customer(stripe.Customer.retrieve(customer["stripe_id"]))
		finally:
			_publish_import_progress(count, total, _("Importing Stripe Customers"))


@frappe.whitelist(methods=["POST"])
def list_products():
	frappe.has_permission("Item", throw=True)

	init_stripe()
	products = list(stripe.Product.list(limit=100).auto_paging_iter())
	existing_product_ids = _get_existing_stripe_ids("Item", [product.id for product in products])
	products = [product for product in products if product.id not in existing_product_ids]

	return [
		{
			"stripe_id": product.id,
			"name": getattr(product, "name", None) or product.id,
			"description": getattr(product, "description", None),
			"active": 1 if getattr(product, "active", False) else 0,
			"type": getattr(product, "type", None),
			"existing_item": None,
		}
		for product in products
	]


@frappe.whitelist(methods=["POST"])
def import_products(product_ids: str | None = None, products: str | None = None):
	frappe.has_permission("Item", ptype="create", throw=True)

	init_stripe()
	products = _parse_import_rows(
		rows=products,
		stripe_ids=product_ids,
		label="product",
		existing_fieldname="existing_item",
	)

	total = len(products)
	for count, product in enumerate(products, start=1):
		try:
			if existing_item := product.get("existing_item"):
				_attach_stripe_id("Item", existing_item, product["stripe_id"])
				continue

			create_product(stripe.Product.retrieve(product["stripe_id"]))
		finally:
			_publish_import_progress(count, total, _("Importing Stripe Products"))


@frappe.whitelist(methods=["POST"])
def import_invoices(from_date: str, to_date: str):
	frappe.has_permission("Sales Invoice", ptype="create", throw=True)

	init_stripe()
	from_timestamp, to_timestamp = _get_created_range(from_date, to_date)
	imported = 0
	skipped = []
	invoices = list(
		stripe.Invoice.list(
			limit=100,
			created={"gte": from_timestamp, "lt": to_timestamp},
		).auto_paging_iter()
	)
	total = len(invoices)

	for count, invoice in enumerate(invoices, start=1):
		try:
			if getattr(invoice, "status", None) == "draft":
				continue

			if frappe.db.exists("Sales Invoice", {"stripe_id": invoice.id}):
				continue

			try:
				invoice_doc = create_invoice(invoice)
			except MissingTaxAccountError as e:
				skipped.append(
					{
						"stripe_id": invoice.id,
						"reason": "missing_tax_account",
						"tax_rate_id": e.tax_rate_id,
					}
				)
				continue

			if invoice_doc:
				imported += 1
		finally:
			_publish_import_progress(count, total, _("Importing Stripe Invoices"))

	return {"imported": imported, "skipped": len(skipped), "skipped_invoices": skipped}


@frappe.whitelist(methods=["POST"])
def import_balance_transactions(from_date: str, to_date: str):
	frappe.has_permission("Bank Transaction", ptype="create", throw=True)

	init_stripe()
	from_timestamp, to_timestamp = _get_created_range(from_date, to_date)
	imported = 0
	balance_transactions = list(
		stripe.BalanceTransaction.list(
			limit=100,
			created={"gte": from_timestamp, "lt": to_timestamp},
			expand=["data.source"],
		).auto_paging_iter()
	)
	total = len(balance_transactions)

	for count, balance_transaction in enumerate(balance_transactions, start=1):
		try:
			if create_bank_transaction(balance_transaction):
				imported += 1
		finally:
			_publish_import_progress(count, total, _("Importing Stripe Balance Transactions"))

	return {"imported": imported}


@frappe.whitelist(methods=["POST"])
def import_payments(from_date: str, to_date: str):
	return import_balance_transactions(from_date, to_date)


@frappe.whitelist(methods=["POST"])
def get_tax_rates():
	init_stripe()

	return [get_tax_rate_data(tax_rate) for tax_rate in stripe.TaxRate.list(limit=100).auto_paging_iter()]


def init_stripe():
	frappe.has_permission("ERPNext Stripe Settings", ptype="write", throw=True)

	settings = frappe.get_single("ERPNext Stripe Settings")
	configure_stripe(settings.get_password("api_key"))


def _publish_import_progress(current: int, total: int, title: str):
	if total <= 0:
		return

	frappe.publish_progress(
		current / total * 100,
		title=title,
		description=_("Processed {0} of {1}").format(current, total),
		doctype=SETTINGS_DOCTYPE,
		docname=SETTINGS_DOCTYPE,
	)


def _get_existing_stripe_ids(doctype: str, stripe_ids: list[str]) -> set[str]:
	if not stripe_ids:
		return set()

	return set(frappe.get_all(doctype, filters={"stripe_id": ["in", stripe_ids]}, pluck="stripe_id"))


def _parse_stripe_ids(stripe_ids: str, label: str) -> list[str]:
	stripe_ids = frappe.parse_json(stripe_ids) or []
	for stripe_id in stripe_ids:
		if not isinstance(stripe_id, str):
			raise TypeError(f"{label.title()} ID must be a string, got {type(stripe_id)}")

	return stripe_ids


def _parse_import_rows(
	rows: str | None,
	stripe_ids: str | None,
	label: str,
	existing_fieldname: str,
) -> list[frappe._dict]:
	if rows is None:
		return [
			frappe._dict({"stripe_id": stripe_id, existing_fieldname: None})
			for stripe_id in _parse_stripe_ids(stripe_ids or "[]", label)
		]

	rows = frappe.parse_json(rows) or []
	if not isinstance(rows, list):
		raise TypeError(f"{label.title()} rows must be a list, got {type(rows)}")

	parsed_rows = []
	selected_existing_records = set()
	for row in rows:
		if not isinstance(row, dict):
			raise TypeError(f"{label.title()} row must be a dict, got {type(row)}")

		stripe_id = row.get("stripe_id")
		if not isinstance(stripe_id, str):
			raise TypeError(f"{label.title()} ID must be a string, got {type(stripe_id)}")

		existing_value = row.get(existing_fieldname) or None
		if existing_value is not None and not isinstance(existing_value, str):
			raise TypeError(f"{label.title()} existing record must be a string, got {type(existing_value)}")

		if existing_value:
			if existing_value in selected_existing_records:
				frappe.throw(
					frappe._("{0} {1} is selected more than once.").format(
						frappe.unscrub(existing_fieldname), frappe.bold(existing_value)
					)
				)
			selected_existing_records.add(existing_value)

		parsed_rows.append(frappe._dict({"stripe_id": stripe_id, existing_fieldname: existing_value}))

	return parsed_rows


def _get_created_range(from_date: str, to_date: str) -> tuple[int, int]:
	from_date = getdate(from_date)
	to_date = getdate(to_date)

	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))

	system_timezone = ZoneInfo(get_system_timezone())
	from_datetime = datetime.combine(from_date, time.min, tzinfo=system_timezone)
	to_datetime = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=system_timezone)
	return int(from_datetime.timestamp()), int(to_datetime.timestamp())


def _attach_stripe_id(doctype: str, docname: str, stripe_id: str):
	doc = frappe.get_doc(doctype, docname)
	doc.check_permission("write")

	current_stripe_id = doc.get("stripe_id")
	if current_stripe_id == stripe_id:
		return

	if current_stripe_id:
		frappe.throw(
			frappe._("{0} {1} is already linked to Stripe ID {2}.").format(
				doctype, frappe.bold(docname), frappe.bold(current_stripe_id)
			)
		)

	if existing_doc := frappe.db.get_value(doctype, {"stripe_id": stripe_id}, "name"):
		if existing_doc != docname:
			frappe.throw(
				frappe._("Stripe ID {0} is already linked to {1} {2}.").format(
					frappe.bold(stripe_id), doctype, frappe.bold(existing_doc)
				)
			)

	frappe.db.set_value(doctype, docname, "stripe_id", stripe_id, update_modified=True)
