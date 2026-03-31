# Copyright (c) 2025, ALYF GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ERPNextStripeSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext_stripe.erpnext_stripe.doctype.erpnext_stripe_tax_config.erpnext_stripe_tax_config import (
			ERPNextStripeTaxConfig,
		)

		api_key: DF.Password
		endpoint_url: DF.Data | None
		stripe_bank_account: DF.Link | None
		tax_configurations: DF.Table[ERPNextStripeTaxConfig]
		webhook_secret: DF.Password | None
	# end: auto-generated types
	def validate(self):
		self.set_endpoint_url()

	def set_endpoint_url(self):
		self.endpoint_url = f"{frappe.utils.get_url()}/api/method/erpnext_stripe.webhook.handler"
