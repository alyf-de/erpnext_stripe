import frappe
import stripe

from erpnext_stripe.operations.create_customer import run as create_customer
from erpnext_stripe.operations.create_product import run as create_product


@frappe.whitelist(methods=["POST"])
def import_customers():
	init_stripe()

	for customer in stripe.Customer.list():
		create_customer(customer)


@frappe.whitelist(methods=["POST"])
def import_products():
	init_stripe()

	for product in stripe.Product.list():
		create_product(product)


@frappe.whitelist(methods=["GET"])
def get_tax_rates():
	init_stripe()
	rates = []

	for tax_rate in stripe.TaxRate.list():
		rates.append({
			"stripe_id": tax_rate.id,
			"country": tax_rate.country,
			"description": tax_rate.description,
			"rate": tax_rate.percentage,
		})

	return rates


def init_stripe():
	frappe.has_permission("ERPNext Stripe Settings", ptype="write", throw=True)

	settings = frappe.get_single("ERPNext Stripe Settings")
	stripe.api_key = settings.get_password("api_key")
