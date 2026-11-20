import frappe
import stripe
from frappe.tests import IntegrationTestCase

from erpnext_stripe.handlers.customer_updated import handle
from erpnext_stripe.operations.create_lead import run as create_lead


def _stripe_customer(**values):
	return stripe.Customer.construct_from(
		{"id": "cus_test_lead_update", "object": "customer", "email": None, **values},
		None,
	)


class TestCustomerUpdated(IntegrationTestCase):
	def test_updates_lead_name(self):
		create_lead(_stripe_customer(name="Old Name"))

		event = stripe.Event.construct_from(
			{"data": {"object": _stripe_customer(name="Jane Middle Doe")}},
			None,
		)
		handle(event)

		lead = frappe.get_doc("Lead", {"stripe_id": "cus_test_lead_update"})
		self.assertEqual(lead.lead_name, "Jane Middle Doe")
