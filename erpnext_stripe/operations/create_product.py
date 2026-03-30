from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from erpnext.stock.doctype.item.item import Item
	from stripe import Product


import frappe


def run(product: "Product"):
	if frappe.db.exists("Item", {"stripe_id": product.id}):
		return

	item_doc: Item = frappe.new_doc("Item")
	item_doc.stripe_id = product.id
	item_doc.name = product.name
	item_doc.description = product.description
	if product.images:
		item_doc.image = product.images[0]
	item_doc.save()
