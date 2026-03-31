# Copyright (c) 2026, ALYF GmbH and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ERPNextStripeTaxConfig(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		account: DF.Link | None
		calculation: DF.Literal["Exclusive", "Inclusive"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		rate: DF.Percent
		region: DF.Data | None
		stripe_id: DF.Data | None
	# end: auto-generated types
	pass
