import json

import frappe
import stripe

EVENT_HANDLERS = {
	"customer.created": "customer_created",
	"customer.updated": "customer_updated",
	"invoice.finalized": "invoice_finalized",
	"invoice.paid": "invoice_paid",
}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handler():
	event = None
	payload = frappe.request.data

	try:
		event = json.loads(payload)
	except json.JSONDecodeError:
		frappe.log_error(title="Stripe Webhook: JSON Decode Error")
		return {"success": False}

	settings = frappe.get_single("ERPNext Stripe Settings")
	api_key = settings.get_password("api_key")
	webhook_secret = settings.get_password("webhook_secret")

	stripe.api_key = api_key
	if webhook_secret:
		sig_header = frappe.request.headers.get("stripe-signature")
		try:
			event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
		except stripe.error.SignatureVerificationError:
			frappe.log_error(title="Stripe Webhook: Signature Verification Error")
			return {"success": False}

	if not event or event["type"] not in EVENT_HANDLERS:
		frappe.log_error(title=f"Stripe Webhook: Unhandled Event Type {event['type'] if event else 'None'}")
		return {"success": False}

	handler_file = EVENT_HANDLERS[event["type"]]
	handler = frappe.get_attr(f"erpnext_stripe.handlers.{handler_file}.handle")

	try:
		handler(event, ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Stripe Webhook: Handler Error")
		return {"success": False}

	return {"success": True}
