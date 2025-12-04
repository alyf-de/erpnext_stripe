from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from erpnext.selling.doctype.customer.customer import Customer as ErpnextCustomer
	from stripe._customer import Customer as StripeCustomer


import frappe


def run(stripe_customer: "StripeCustomer"):
	if frappe.db.exists("Customer", {"stripe_id": stripe_customer.id}):
		return

	customer_doc: ErpnextCustomer = frappe.new_doc("Customer")
	customer_doc.stripe_id = stripe_customer.id
	customer_doc.customer_name = stripe_customer.name

	if hasattr(stripe_customer, "business_name") and stripe_customer.business_name:
		customer_doc.customer_type = "Company"
	else:
		customer_doc.customer_type = "Individual"

	if stripe_customer.currency:
		customer_doc.default_currency = stripe_customer.currency.upper()

	tax_ids = stripe_customer.list_tax_ids(stripe_customer.id)
	if tax_ids.data:
		customer_doc.tax_id = tax_ids.data[0].value

	customer_doc.save()

	if stripe_customer.address:
		address_doc = frappe.new_doc("Address")
		address_doc.address_line1 = stripe_customer.address.line1
		address_doc.address_line2 = stripe_customer.address.line2
		address_doc.city = stripe_customer.address.city
		address_doc.state = stripe_customer.address.state
		address_doc.pincode = stripe_customer.address.postal_code
		address_doc.country = frappe.db.get_value(
			"Country", {"code": stripe_customer.address.country.lower()}
		)
		address_doc.append("links", {"link_doctype": "Customer", "link_name": customer_doc.name})
		address_doc.save()

	if stripe_customer.email or stripe_customer.phone:
		contact_doc = frappe.new_doc("Contact")
		contact_doc.company_name = customer_doc.customer_name
		if stripe_customer.email:
			contact_doc.append("email_ids", {"email_id": stripe_customer.email, "is_primary": 1})
		if stripe_customer.phone:
			contact_doc.append("phone_nos", {"phone": stripe_customer.phone, "is_primary_phone": 1})
		contact_doc.append("links", {"link_doctype": "Customer", "link_name": customer_doc.name})
		contact_doc.save()
