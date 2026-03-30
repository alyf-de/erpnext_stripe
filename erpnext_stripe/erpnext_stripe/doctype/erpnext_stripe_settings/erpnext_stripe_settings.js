// Copyright (c) 2025, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("ERPNext Stripe Settings", {
	refresh(frm) {
		if (frm.doc.api_key) {
			frm.add_custom_button(
				__("Customers"),
				() => {
					frm.trigger("import_customers");
				},
				__("Import")
			);
			frm.add_custom_button(
				__("Products"),
				() => {
					frm.trigger("import_products");
				},
				__("Import")
			);
		}
	},

	import_customers() {
		open_import_dialog({
			title: __("Stripe Customers"),
			loading_message: __("Loading customers..."),
			importing_message: __("Importing customers..."),
			empty_message: __("No unimported Stripe customers found."),
			error_message: __("Error importing customers"),
			success_message: __("Customers imported successfully"),
			table_fieldname: "customers",
			id_fieldname: "stripe_id",
			list_method: "erpnext_stripe.api.list_customers",
			import_method: "erpnext_stripe.api.import_customers",
			rows_arg_name: "customers",
			existing_fieldname: "existing_customer",
			fields: [
				{
					fieldname: "stripe_id",
					label: __("Stripe ID"),
					fieldtype: "Data",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "name",
					label: __("Name"),
					fieldtype: "Data",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "email",
					label: __("Email"),
					fieldtype: "Data",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "currency",
					label: __("Currency"),
					fieldtype: "Link",
					options: "Currency",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "existing_customer",
					label: __("Existing Customer"),
					fieldtype: "Link",
					options: "Customer",
					in_list_view: 1,
					change() {
						mark_row_as_selected(this);
					},
					get_query: () => ({
						filters: {
							stripe_id: ["is", "not set"],
						},
					}),
				},
			],
		});
	},

	import_products() {
		open_import_dialog({
			title: __("Stripe Products"),
			loading_message: __("Loading products..."),
			importing_message: __("Importing products..."),
			empty_message: __("No unimported Stripe products found."),
			error_message: __("Error importing products"),
			success_message: __("Products imported successfully"),
			table_fieldname: "products",
			id_fieldname: "stripe_id",
			list_method: "erpnext_stripe.api.list_products",
			import_method: "erpnext_stripe.api.import_products",
			rows_arg_name: "products",
			existing_fieldname: "existing_item",
			fields: [
				{
					fieldname: "stripe_id",
					label: __("Stripe ID"),
					fieldtype: "Data",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "name",
					label: __("Name"),
					fieldtype: "Data",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "type",
					label: __("Type"),
					fieldtype: "Data",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "active",
					label: __("Active"),
					fieldtype: "Check",
					in_list_view: 1,
					read_only: 1,
				},
				{
					fieldname: "description",
					label: __("Description"),
					fieldtype: "Small Text",
					read_only: 1,
				},
				{
					fieldname: "existing_item",
					label: __("Existing Item"),
					fieldtype: "Link",
					options: "Item",
					in_list_view: 1,
					change() {
						mark_row_as_selected(this);
					},
					get_query: () => ({
						filters: {
							stripe_id: ["is", "not set"],
						},
					}),
				},
			],
		});
	},
});

function open_import_dialog(options) {
	frappe.dom.freeze(options.loading_message);
	frappe
		.xcall(options.list_method)
		.then((rows) => {
			if (!rows?.length) {
				frappe.msgprint(options.empty_message);
				return;
			}

			const dialog = new frappe.ui.Dialog({
				size: "extra-large",
				title: options.title,
				fields: [
					{
						fieldname: options.table_fieldname,
						fieldtype: "Table",
						cannot_add_rows: true,
						cannot_delete_rows: true,
						get_data: () => rows,
						fields: options.fields,
					},
				],
				primary_action_label: __("Import"),
				primary_action: () => {
					const values = dialog.get_values() || {};
					const selected_rows = (values[options.table_fieldname] || [])
						.filter((row) => row?.__checked == 1)
						.map((row) => ({
							[options.id_fieldname]: row[options.id_fieldname],
							[options.existing_fieldname]: row[options.existing_fieldname] || null,
						}));

					if (!selected_rows.length) {
						frappe.msgprint(__("Please select at least one row to import."));
						return;
					}

					frappe.dom.freeze(options.importing_message);
					frappe
						.xcall(options.import_method, {
							[options.rows_arg_name]: selected_rows,
						})
						.then(() => {
							frappe.show_alert({
								message: options.success_message,
								indicator: "green",
							});
							dialog.hide();
						})
						.catch(() => {
							frappe.show_alert({
								message: options.error_message,
								indicator: "red",
							});
						})
						.finally(() => {
							frappe.dom.unfreeze();
						});
				},
			});

			dialog.show();
		})
		.finally(() => {
			frappe.dom.unfreeze();
		});
}

function mark_row_as_selected(field) {
	if (!field?.doc || !field.get_value()) {
		return;
	}

	field.doc.__checked = 1;
	field.grid?.refresh();
}
