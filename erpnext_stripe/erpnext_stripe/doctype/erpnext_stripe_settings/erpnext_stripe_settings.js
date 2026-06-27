// Copyright (c) 2025, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("ERPNext Stripe Settings", {
	refresh(frm) {
		if (frm.doc.api_key) {
			add_import_button(frm, __("Customers"), "import_customers");
			add_import_button(frm, __("Products"), "import_products");
			add_import_button(frm, __("Tax Rates"), "import_tax_rates");
			add_import_button(frm, __("Invoices"), "import_invoices");
			add_import_button(frm, __("Balance Transactions"), "import_balance_transactions");
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

	import_tax_rates(frm) {
		frappe.dom.freeze(__("Loading tax rates..."));
		frappe
			.xcall("erpnext_stripe.api.get_tax_rates")
			.then((rates) => {
				if (!rates?.length) {
					frappe.msgprint(__("No tax rates found in Stripe."));
					return;
				}

				const existing_ids = new Set(
					(frm.doc.tax_configurations || []).map((row) => row.stripe_id)
				);

				let added = 0;
				for (const rate of rates) {
					if (existing_ids.has(rate.stripe_id)) {
						continue;
					}
					const row = frm.add_child("tax_configurations");
					row.stripe_id = rate.stripe_id;
					row.region = rate.region;
					row.rate = rate.rate;
					row.calculation = rate.inclusive ? "Inclusive" : "Exclusive";
					added++;
				}

				if (added === 0) {
					frappe.msgprint(__("All Stripe tax rates are already imported."));
					return;
				}

				frm.refresh_field("tax_configurations");
				frm.dirty();
				frappe.show_alert({
					message: __("{0} tax rate(s) added. Set the Account for each and save.", [
						added,
					]),
					indicator: "green",
				});
			})
			.catch(() => {
				frappe.show_alert({
					message: __("Error fetching tax rates"),
					indicator: "red",
				});
			})
			.finally(() => {
				frappe.dom.unfreeze();
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

	import_invoices() {
		open_date_range_import_dialog({
			title: __("Stripe Invoices"),
			importing_message: __("Importing invoices..."),
			error_message: __("Error importing invoices"),
			success_message: get_invoice_import_message,
			import_method: "erpnext_stripe.api.import_invoices",
		});
	},

	import_balance_transactions() {
		open_date_range_import_dialog({
			title: __("Stripe Balance Transactions"),
			importing_message: __("Importing balance transactions..."),
			error_message: __("Error importing balance transactions"),
			success_message: get_balance_transaction_import_message,
			import_method: "erpnext_stripe.api.import_balance_transactions",
		});
	},
});

function add_import_button(frm, label, trigger) {
	frm.add_custom_button(
		label,
		() => {
			frm.trigger(trigger);
		},
		__("Import")
	);
}

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

					run_import(dialog, options, {
						[options.rows_arg_name]: selected_rows,
					});
				},
			});

			dialog.show();
		})
		.finally(() => {
			frappe.dom.unfreeze();
		});
}

function open_date_range_import_dialog(options) {
	const dialog = new frappe.ui.Dialog({
		title: options.title,
		fields: [
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				reqd: 1,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				reqd: 1,
			},
		],
		primary_action_label: __("Import"),
		primary_action: () => {
			const values = dialog.get_values();
			if (!values) {
				return;
			}

			run_import(dialog, options, {
				from_date: values.from_date,
				to_date: values.to_date,
			});
		},
	});

	dialog.show();
}

function run_import(dialog, options, args) {
	frappe.dom.freeze(options.importing_message);
	frappe
		.xcall(options.import_method, args)
		.then((result) => {
			frappe.show_alert({
				message:
					typeof options.success_message === "function"
						? options.success_message(result)
						: options.success_message,
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
}

function get_invoice_import_message(result) {
	const imported = result?.imported || 0;
	const skipped = result?.skipped || 0;

	if (skipped) {
		return __("{0} invoice(s) imported. {1} skipped; check tax configuration.", [
			imported,
			skipped,
		]);
	}

	return __("{0} invoice(s) imported.", [imported]);
}

function get_balance_transaction_import_message(result) {
	const imported = result?.imported || 0;

	return __("{0} balance transaction(s) imported as Bank Transaction(s).", [imported]);
}

function mark_row_as_selected(field) {
	if (!field?.doc || !field.get_value()) {
		return;
	}

	field.doc.__checked = 1;
	field.grid?.refresh();
}
