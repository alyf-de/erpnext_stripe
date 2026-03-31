from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from erpnext.selling.doctype.customer.customer import Customer as ErpnextCustomer
	from stripe import Customer as StripeCustomer


import frappe
import stripe

from erpnext_stripe.utils import (
	get_country_name_by_code,
	get_stripe_customer_address,
	get_stripe_customer_contact_name,
	get_stripe_customer_language,
	get_stripe_customer_name,
	get_stripe_customer_phone,
	get_valid_contact_email,
	log_skipped_contact_email,
)


def run(
	stripe_customer: "StripeCustomer",
	ignore_permissions: bool = False,
	lead_name: str | None = None,
):
	if frappe.db.exists("Customer", {"stripe_id": stripe_customer.id}):
		return

	customer_name = get_stripe_customer_name(stripe_customer) or stripe_customer.id
	customer_address = get_stripe_customer_address(stripe_customer)
	contact_name = get_stripe_customer_contact_name(stripe_customer)
	contact_phone = get_stripe_customer_phone(stripe_customer)
	valid_email = get_valid_contact_email(stripe_customer.email)
	if stripe_customer.email and not valid_email:
		log_skipped_contact_email(stripe_customer.email, stripe_customer.id)

	customer_doc: ErpnextCustomer = frappe.new_doc("Customer")
	customer_doc.stripe_id = stripe_customer.id
	customer_doc.customer_name = customer_name

	if lead_name:
		customer_doc.lead_name = lead_name

	if hasattr(stripe_customer, "business_name") and stripe_customer.business_name:
		customer_doc.customer_type = "Company"
	else:
		customer_doc.customer_type = "Individual"

	if stripe_customer.currency:
		customer_doc.default_currency = stripe_customer.currency.upper()

	if language := get_stripe_customer_language(stripe_customer):
		customer_doc.language = language

	try:
		tax_ids = stripe_customer.list_tax_ids(stripe_customer.id)
		if tax_ids.data:
			customer_doc.tax_id = tax_ids.data[0].value
	except stripe.InvalidRequestError:
		pass

	customer_doc.save(ignore_permissions=ignore_permissions)

	if customer_address:
		address_doc = frappe.new_doc("Address")
		address_doc.address_line1 = customer_address.line1
		address_doc.address_line2 = customer_address.line2
		address_doc.city = customer_address.city
		address_doc.state = customer_address.state
		address_doc.pincode = customer_address.postal_code
		address_doc.country = get_country_name_by_code(customer_address.country)
		address_doc.append("links", {"link_doctype": "Customer", "link_name": customer_doc.name})
		address_doc.save(ignore_permissions=ignore_permissions)

	if valid_email or contact_phone:
		contact_doc = frappe.new_doc("Contact")
		contact_doc.company_name = customer_doc.customer_name
		if contact_name:
			contact_doc.first_name = contact_name
		if valid_email:
			contact_doc.append("email_ids", {"email_id": valid_email, "is_primary": 1})
		if contact_phone:
			contact_doc.append("phone_nos", {"phone": contact_phone, "is_primary_phone": 1})
		contact_doc.append("links", {"link_doctype": "Customer", "link_name": customer_doc.name})
		contact_doc.save(ignore_permissions=ignore_permissions)
