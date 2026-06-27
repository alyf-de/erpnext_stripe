from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


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


def handle(event: "Event", ignore_permissions: bool = False):
	stripe_customer = event.data.object

	if frappe.db.exists("Customer", {"stripe_id": stripe_customer.id}):
		_update_customer(stripe_customer, ignore_permissions=ignore_permissions)
	elif frappe.db.exists("Lead", {"stripe_id": stripe_customer.id}):
		_update_lead(stripe_customer, ignore_permissions=ignore_permissions)


def _update_lead(stripe_customer, ignore_permissions: bool = False):
	customer_address = get_stripe_customer_address(stripe_customer)
	contact_phone = get_stripe_customer_phone(stripe_customer)
	valid_email = get_valid_contact_email(stripe_customer.email)
	if stripe_customer.email and not valid_email:
		log_skipped_contact_email(stripe_customer.email, stripe_customer.id)

	lead_name = frappe.db.get_value("Lead", {"stripe_id": stripe_customer.id})
	lead_doc = frappe.get_doc("Lead", lead_name)

	if resolved_name := get_stripe_customer_name(stripe_customer, fallback_to_identifier=False):
		lead_doc.lead_name = resolved_name

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


def _update_customer(stripe_customer, ignore_permissions: bool = False):
	customer_address = get_stripe_customer_address(stripe_customer)
	contact_display_name = get_stripe_customer_contact_name(stripe_customer)
	contact_phone = get_stripe_customer_phone(stripe_customer)
	valid_email = get_valid_contact_email(stripe_customer.email)
	if stripe_customer.email and not valid_email:
		log_skipped_contact_email(stripe_customer.email, stripe_customer.id)

	customer_name = frappe.db.get_value("Customer", {"stripe_id": stripe_customer.id})
	customer_doc = frappe.get_doc("Customer", customer_name)

	if resolved_customer_name := get_stripe_customer_name(stripe_customer, fallback_to_identifier=False):
		customer_doc.customer_name = resolved_customer_name

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
		address_name = frappe.db.get_value(
			"Dynamic Link",
			{"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Address"},
			"parent",
		)
		if address_name:
			address_doc = frappe.get_doc("Address", address_name)
		else:
			address_doc = frappe.new_doc("Address")
			address_doc.append("links", {"link_doctype": "Customer", "link_name": customer_name})

		address_doc.address_line1 = customer_address.line1
		address_doc.address_line2 = customer_address.line2
		address_doc.city = customer_address.city
		address_doc.state = customer_address.state
		address_doc.pincode = customer_address.postal_code
		address_doc.country = get_country_name_by_code(customer_address.country)
		address_doc.save(ignore_permissions=ignore_permissions)

	if valid_email or contact_phone:
		contact_docname = frappe.db.get_value(
			"Dynamic Link",
			{"link_doctype": "Customer", "link_name": customer_name, "parenttype": "Contact"},
			"parent",
		)
		if contact_docname:
			contact_doc = frappe.get_doc("Contact", contact_docname)
		else:
			contact_doc = frappe.new_doc("Contact")
			contact_doc.append("links", {"link_doctype": "Customer", "link_name": customer_name})

		contact_doc.company_name = customer_doc.customer_name
		if contact_display_name:
			contact_doc.first_name = contact_display_name

		if valid_email:
			existing_email = next((e for e in contact_doc.email_ids if e.email_id == valid_email), None)
			if not existing_email:
				contact_doc.append("email_ids", {"email_id": valid_email, "is_primary": 1})

		if contact_phone:
			existing_phone = next((p for p in contact_doc.phone_nos if p.phone == contact_phone), None)
			if not existing_phone:
				contact_doc.append("phone_nos", {"phone": contact_phone, "is_primary_phone": 1})

		contact_doc.save(ignore_permissions=ignore_permissions)
