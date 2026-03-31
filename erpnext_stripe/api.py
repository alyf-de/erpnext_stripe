import frappe
import stripe

from erpnext_stripe.operations.create_customer import run as create_customer
from erpnext_stripe.operations.create_product import run as create_product


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
			"currency": getattr(customer, "currency", "").upper() or None,
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

	for customer in customers:
		if existing_customer := customer.get("existing_customer"):
			_attach_stripe_id("Customer", existing_customer, customer["stripe_id"])
			continue

		create_customer(stripe.Customer.retrieve(customer["stripe_id"]))


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

	for product in products:
		if existing_item := product.get("existing_item"):
			_attach_stripe_id("Item", existing_item, product["stripe_id"])
			continue

		create_product(stripe.Product.retrieve(product["stripe_id"]))


@frappe.whitelist(methods=["POST"])
def get_tax_rates():
	init_stripe()
	rates = []

	for tax_rate in stripe.TaxRate.list():
		region_parts = [
			getattr(tax_rate, "country", None),
			getattr(tax_rate, "state", None),
			getattr(tax_rate, "jurisdiction", None),
		]
		region = " - ".join(part for part in region_parts if part)

		rates.append({
			"stripe_id": tax_rate.id,
			"region": region or getattr(tax_rate, "display_name", None) or tax_rate.description,
			"description": tax_rate.description,
			"rate": tax_rate.percentage,
			"inclusive": tax_rate.inclusive,
		})

	return rates


def init_stripe():
	frappe.has_permission("ERPNext Stripe Settings", ptype="write", throw=True)

	settings = frappe.get_single("ERPNext Stripe Settings")
	stripe.api_key = settings.get_password("api_key")


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
			raise TypeError(
				f"{label.title()} existing record must be a string, got {type(existing_value)}"
			)

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
