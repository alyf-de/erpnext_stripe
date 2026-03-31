from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from erpnext.crm.doctype.lead.lead import Lead
	from stripe import Customer as StripeCustomer


import frappe

from erpnext_stripe.utils import (
	get_country_name_by_code,
	get_stripe_customer_address,
	get_stripe_customer_language,
	get_stripe_customer_name,
	get_stripe_customer_phone,
	get_valid_contact_email,
	log_skipped_contact_email,
)


def run(stripe_customer: "StripeCustomer", ignore_permissions: bool = False):
	if frappe.db.exists("Lead", {"stripe_id": stripe_customer.id}):
		return

	# If a Customer already exists for this Stripe ID, don't create a Lead
	if frappe.db.exists("Customer", {"stripe_id": stripe_customer.id}):
		return

	customer_name = get_stripe_customer_name(stripe_customer) or stripe_customer.id
	customer_address = get_stripe_customer_address(stripe_customer)
	contact_phone = get_stripe_customer_phone(stripe_customer)
	valid_email = get_valid_contact_email(stripe_customer.email)
	if stripe_customer.email and not valid_email:
		log_skipped_contact_email(stripe_customer.email, stripe_customer.id)

	lead_doc: Lead = frappe.new_doc("Lead")
	lead_doc.stripe_id = stripe_customer.id
	lead_doc.lead_name = customer_name

	if hasattr(stripe_customer, "business_name") and stripe_customer.business_name:
		lead_doc.company_name = stripe_customer.business_name

	if valid_email:
		lead_doc.email_id = valid_email

	if contact_phone:
		lead_doc.phone = contact_phone

	if language := get_stripe_customer_language(stripe_customer):
		lead_doc.language = language

	if customer_address:
		lead_doc.city = customer_address.city
		lead_doc.state = customer_address.state
		lead_doc.country = get_country_name_by_code(customer_address.country)

	lead_doc.save(ignore_permissions=ignore_permissions)
