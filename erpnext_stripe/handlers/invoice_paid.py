from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


import frappe
from frappe.utils.data import today


def handle(event: "Event", ignore_permissions: bool = False):
	stripe_invoice = event.data.object

	invoice_name = frappe.db.get_value("Sales Invoice", {"stripe_id": stripe_invoice.id})
	if not invoice_name:
		return

	invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)

	if invoice_doc.docstatus == 0:
		invoice_doc.flags.ignore_permissions = ignore_permissions
		invoice_doc.submit()

	if frappe.db.exists("Payment Entry", {"reference_no": stripe_invoice.payment_intent}):
		return

	settings = frappe.get_single("ERPNext Stripe Settings")

	payment_entry = frappe.new_doc("Payment Entry")
	payment_entry.payment_type = "Receive"
	payment_entry.posting_date = today()
	payment_entry.party_type = "Customer"
	payment_entry.party = invoice_doc.customer
	payment_entry.paid_amount = stripe_invoice.amount_paid / 100
	payment_entry.received_amount = stripe_invoice.amount_paid / 100
	payment_entry.target_exchange_rate = 1
	payment_entry.reference_no = stripe_invoice.payment_intent
	payment_entry.reference_date = today()

	if settings.stripe_bank_account:
		payment_entry.paid_to = frappe.db.get_value(
			"Bank Account", settings.stripe_bank_account, "account"
		)

	payment_entry.append(
		"references",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice_name,
			"allocated_amount": stripe_invoice.amount_paid / 100,
		},
	)

	payment_entry.save(ignore_permissions=ignore_permissions)
	payment_entry.flags.ignore_permissions = ignore_permissions
	payment_entry.submit()
