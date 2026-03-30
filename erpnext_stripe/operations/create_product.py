from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from erpnext.stock.doctype.item.item import Item
	from stripe import Product


import frappe
import stripe


def run(product: "Product", ignore_permissions: bool = False):
	if frappe.db.exists("Item", {"stripe_id": product.id}):
		return

	native_uom = _resolve_uom_name(getattr(product, "unit_label", None))
	stock_uom = native_uom or _resolve_stock_uom()

	item_doc: Item = frappe.new_doc("Item")
	item_doc.stripe_id = product.id
	item_doc.item_code = product.id
	item_doc.item_name = product.name or item_doc.item_code
	item_doc.description = _build_description(product)
	item_doc.disabled = 0 if getattr(product, "active", True) else 1

	if item_group := _resolve_item_group():
		item_doc.item_group = item_group

	if stock_uom:
		item_doc.stock_uom = stock_uom

	if native_uom:
		item_doc.sales_uom = native_uom

	product_type = getattr(product, "type", None)
	shippable = getattr(product, "shippable", None)
	if product_type == "service":
		item_doc.is_stock_item = 0
	elif shippable is not None:
		item_doc.is_stock_item = 1 if shippable else 0
	elif product_type == "good":
		item_doc.is_stock_item = 1

	if product.images:
		item_doc.image = product.images[0]

	standard_rate = _get_standard_rate(product)
	if standard_rate is not None:
		item_doc.standard_rate = standard_rate

	_apply_package_weight(item_doc, product)

	item_doc.save(ignore_permissions=ignore_permissions)


def _build_description(product: "Product") -> str:
	description_parts = []
	if product.description:
		description_parts.append(product.description.strip())

	feature_names = [
		feature.name.strip()
		for feature in getattr(product, "marketing_features", []) or []
		if getattr(feature, "name", None)
	]
	if feature_names:
		description_parts.append(
			"Features:\n" + "\n".join(f"- {feature_name}" for feature_name in feature_names)
		)

	if statement_descriptor := getattr(product, "statement_descriptor", None):
		description_parts.append(f"Statement descriptor: {statement_descriptor}")

	if product_url := getattr(product, "url", None):
		description_parts.append(f"Stripe URL: {product_url}")

	package_dimensions = getattr(product, "package_dimensions", None)
	if package_dimensions and all(
		getattr(package_dimensions, fieldname, None) is not None
		for fieldname in ("length", "width", "height")
	):
		description_parts.append(
			"Package dimensions (in): "
			f"{package_dimensions.length:g} x {package_dimensions.width:g} x {package_dimensions.height:g}"
		)

	return "\n\n".join(description_parts) or product.name or product.id


def _resolve_item_group() -> str | None:
	return frappe.db.get_single_value("Stock Settings", "item_group") or _resolve_docname(
		"Item Group", "All Item Groups", "item_group_name"
	)


def _resolve_stock_uom() -> str | None:
	for candidate in (
		frappe.db.get_single_value("Stock Settings", "stock_uom"),
		"Nos",
	):
		if uom := _resolve_uom_name(candidate):
			return uom

	return None


def _resolve_uom_name(value: str | None) -> str | None:
	if not value:
		return None

	for candidate in dict.fromkeys((value, value.upper(), value.title())):
		if uom := _resolve_docname("UOM", candidate, "uom_name"):
			return uom

	return None


def _resolve_docname(doctype: str, value: str | None, fieldname: str) -> str | None:
	if not value:
		return None

	return frappe.db.exists(doctype, value) or frappe.db.get_value(doctype, {fieldname: value}, "name")


def _get_standard_rate(product: "Product") -> float | None:
	price = _get_default_price(product)
	if not price:
		return None

	unit_amount_decimal = getattr(price, "unit_amount_decimal", None)
	if unit_amount_decimal is not None:
		return float(unit_amount_decimal) / 100

	unit_amount = getattr(price, "unit_amount", None)
	if unit_amount is not None:
		return unit_amount / 100

	return None


def _get_default_price(product: "Product"):
	default_price = getattr(product, "default_price", None)
	if not default_price:
		return None

	if hasattr(default_price, "unit_amount") or hasattr(default_price, "unit_amount_decimal"):
		return default_price

	try:
		return stripe.Price.retrieve(default_price)
	except Exception:
		return None


def _apply_package_weight(item_doc: "Item", product: "Product"):
	package_dimensions = getattr(product, "package_dimensions", None)
	if not package_dimensions or getattr(package_dimensions, "weight", None) is None:
		return

	weight_in_ounces = package_dimensions.weight
	if weight_uom := _resolve_uom_name("Kg"):
		item_doc.weight_per_unit = round(weight_in_ounces * 0.028349523125, 6)
		item_doc.weight_uom = weight_uom
		return

	if weight_uom := _resolve_uom_name("Gram"):
		item_doc.weight_per_unit = round(weight_in_ounces * 28.349523125, 3)
		item_doc.weight_uom = weight_uom
		return

	for candidate in ("Ounce", "Oz", "oz"):
		if weight_uom := _resolve_uom_name(candidate):
			item_doc.weight_per_unit = weight_in_ounces
			item_doc.weight_uom = weight_uom
			return
