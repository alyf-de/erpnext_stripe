// Copyright (c) 2025, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("ERPNext Stripe Settings", {
	refresh(frm) {
		if (frm.doc.api_key) {
			frm.add_custom_button(
				__("Customers"),
				() => {
					frappe.xcall("erpnext_stripe.api.import_customers");
				},
				__("Import")
			);
			frm.add_custom_button(
				__("Products"),
				() => {
					frappe.xcall("erpnext_stripe.api.import_products");
				},
				__("Import")
			);
		}
	},
});
