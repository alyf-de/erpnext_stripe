from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


import frappe

from erpnext_stripe.operations.create_bank_transaction import run_for_invoice as create_bank_transaction


def handle(event: "Event", ignore_permissions: bool = False):
	stripe_invoice = event.data.object

	invoice_name = frappe.db.get_value("Sales Invoice", {"stripe_id": stripe_invoice.id})
	if invoice_name:
		invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)

		if invoice_doc.docstatus == 0:
			invoice_doc.flags.ignore_permissions = ignore_permissions
			invoice_doc.submit()

	create_bank_transaction(stripe_invoice, ignore_permissions=ignore_permissions)
