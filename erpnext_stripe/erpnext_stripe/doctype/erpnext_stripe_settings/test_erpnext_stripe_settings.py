# Copyright (c) 2025, ALYF GmbH and Contributors
# See license.txt

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from erpnext_stripe import api


class TestERPNextStripeSettings(FrappeTestCase):
	def test_import_progress_is_scoped_to_settings_document(self):
		with patch("erpnext_stripe.api.frappe.publish_progress") as publish_progress:
			api._publish_import_progress(2, 4, "Importing Stripe Customers")

		publish_progress.assert_called_once_with(
			50.0,
			title="Importing Stripe Customers",
			description="Processed 2 of 4",
			doctype="ERPNext Stripe Settings",
			docname="ERPNext Stripe Settings",
		)

	def test_import_progress_ignores_empty_totals(self):
		with patch("erpnext_stripe.api.frappe.publish_progress") as publish_progress:
			api._publish_import_progress(0, 0, "Importing Stripe Customers")

		publish_progress.assert_not_called()
