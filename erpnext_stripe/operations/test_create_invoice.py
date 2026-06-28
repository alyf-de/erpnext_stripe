import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import stripe

from erpnext_stripe.operations.create_invoice import (
	MissingTaxAccountError,
	_get_invoice_tax_rows,
	_get_product_id,
	_get_quantity,
	_get_rate,
	_get_tax_rate_id,
	_set_posting_datetime,
	run,
)


def _line_item(**values):
	return stripe.InvoiceLineItem.construct_from(
		{
			"id": "il_test",
			"object": "line_item",
			"period": {"start": 1, "end": 1},
			**values,
		},
		None,
	)


def _stripe_object(**values):
	for key, value in values.items():
		if isinstance(value, dict):
			values[key] = _stripe_object(**value)
		elif isinstance(value, list):
			values[key] = [_stripe_object(**entry) if isinstance(entry, dict) else entry for entry in value]

	return SimpleNamespace(**values)


def _invoice_doc(has_posting_time=True):
	return SimpleNamespace(
		meta=SimpleNamespace(
			has_field=lambda fieldname: has_posting_time if fieldname == "posting_time" else False
		)
	)


class _Settings:
	def __init__(self, tax_configurations=None):
		self.tax_configurations = tax_configurations or []
		self.saved = False
		self.ignore_permissions = False

	def append(self, fieldname, value):
		assert fieldname == "tax_configurations", fieldname
		row = _stripe_object(**value)
		self.tax_configurations.append(row)
		return row

	def save(self, ignore_permissions=False):
		self.saved = True
		self.ignore_permissions = ignore_permissions


class _SalesInvoiceDoc:
	def __init__(self):
		self.flags = SimpleNamespace()
		self.meta = SimpleNamespace(has_field=lambda fieldname: False)
		self.items = []
		self.taxes = []
		self.payment_schedule = []

	def append(self, fieldname, value):
		row = _stripe_object(**value)
		getattr(self, fieldname).append(row)
		return row

	def set_missing_values(self):
		self.payment_terms_template_before_missing = self.payment_terms_template
		self.payment_terms_template = "Default Customer Terms"
		self.payment_schedule = [_stripe_object(due_date="2026-06-14")]

	def save(self, ignore_permissions=False):
		self.saved_ignore_permissions = ignore_permissions
		self.saved_due_date = self.due_date
		self.saved_payment_terms_template = self.payment_terms_template
		self.saved_payment_schedule = self.payment_schedule

	def submit(self):
		self.submitted = True


class TestCreateInvoice(unittest.TestCase):
	def test_preserves_stripe_due_date_without_customer_payment_terms(self):
		invoice_doc = _SalesInvoiceDoc()
		stripe_due_date = "2026-06-30"
		invoice = _stripe_object(
			id="in_test",
			number="SI-STRIPE-TEST",
			total=1000,
			due_date=stripe_due_date,
			customer="cus_test",
			lines={
				"data": [
					{
						"id": "il_test",
						"pricing": {
							"price_details": {"product": "prod_test"},
							"unit_amount_decimal": "1000",
						},
						"quantity": 1,
					}
				]
			},
		)

		def exists(doctype, filters):
			return doctype == "Item"

		def get_value(doctype, filters, *args, **kwargs):
			if doctype == "Customer":
				return "CUST-001"
			if doctype == "Item":
				return "ITEM-001"

		db = SimpleNamespace(exists=exists, get_value=get_value)

		with (
			patch("erpnext_stripe.operations.create_invoice._ensure_customer"),
			patch("erpnext_stripe.operations.create_invoice._ensure_sales_item"),
			patch("erpnext_stripe.operations.create_invoice._get_invoice_tax_rows", return_value=[]),
			patch(
				"erpnext_stripe.operations.create_invoice.frappe.get_single",
				return_value=_stripe_object(project="Stripe Project", price_list="Standard Selling"),
			),
			patch("erpnext_stripe.operations.create_invoice.frappe.new_doc", return_value=invoice_doc),
			patch("erpnext_stripe.operations.create_invoice.frappe.db", db),
		):
			result = run(invoice, ignore_permissions=True)

		self.assertEqual(result, invoice_doc)
		self.assertEqual(invoice_doc.payment_terms_template_before_missing, "")
		self.assertEqual(invoice_doc.saved_due_date, stripe_due_date)
		self.assertEqual(invoice_doc.saved_payment_terms_template, "")
		self.assertEqual(invoice_doc.saved_payment_schedule, [])
		self.assertEqual(invoice_doc.ignore_default_payment_terms_template, 1)
		self.assertTrue(invoice_doc.saved_ignore_permissions)

	def test_sets_posting_datetime_from_effective_at_in_system_timezone(self):
		invoice = _stripe_object(
			effective_at=1_704_067_199,
			status_transitions={"finalized_at": 1_704_067_200},
			created=1_704_067_201,
		)
		invoice_doc = _invoice_doc()

		with patch(
			"erpnext_stripe.operations.create_invoice.get_system_timezone", return_value="Europe/Berlin"
		):
			_set_posting_datetime(invoice_doc, invoice)

		self.assertEqual(invoice_doc.set_posting_time, 1)
		self.assertEqual(invoice_doc.posting_date, datetime.date(2024, 1, 1))
		self.assertEqual(invoice_doc.posting_time, datetime.time(0, 59, 59))

	def test_falls_back_to_finalized_at_then_created_for_posting_datetime(self):
		invoice = _stripe_object(
			effective_at=None,
			status_transitions={"finalized_at": 1_704_067_200},
			created=1_704_153_600,
		)
		invoice_doc = _invoice_doc()

		with patch("erpnext_stripe.operations.create_invoice.get_system_timezone", return_value="UTC"):
			_set_posting_datetime(invoice_doc, invoice)

		self.assertEqual(invoice_doc.posting_date, datetime.date(2024, 1, 1))
		self.assertEqual(invoice_doc.posting_time, datetime.time(0, 0))

		invoice.status_transitions.finalized_at = None
		invoice_doc = _invoice_doc()
		with patch("erpnext_stripe.operations.create_invoice.get_system_timezone", return_value="UTC"):
			_set_posting_datetime(invoice_doc, invoice)

		self.assertEqual(invoice_doc.posting_date, datetime.date(2024, 1, 2))
		self.assertEqual(invoice_doc.posting_time, datetime.time(0, 0))

	def test_skips_posting_time_when_field_is_not_supported(self):
		invoice = _stripe_object(effective_at=1_704_067_200)
		invoice_doc = _invoice_doc(has_posting_time=False)

		with patch("erpnext_stripe.operations.create_invoice.get_system_timezone", return_value="UTC"):
			_set_posting_datetime(invoice_doc, invoice)

		self.assertEqual(invoice_doc.set_posting_time, 1)
		self.assertEqual(invoice_doc.posting_date, datetime.date(2024, 1, 1))
		self.assertFalse(hasattr(invoice_doc, "posting_time"))

	def test_reads_current_pricing_shape(self):
		line = _line_item(
			pricing={
				"price_details": {
					"price": "price_current",
					"product": "prod_current",
				},
				"type": "price_details",
				"unit_amount_decimal": "995",
			},
			quantity_decimal="1.5",
		)

		quantity = _get_quantity(line)

		self.assertEqual(_get_product_id(line), "prod_current")
		self.assertAlmostEqual(quantity, 1.5)
		self.assertAlmostEqual(_get_rate(line, quantity), 9.95)

	def test_falls_back_to_legacy_price_shape(self):
		line = _line_item(
			price={
				"id": "price_legacy",
				"product": "prod_legacy",
				"unit_amount": 2975,
			},
			quantity=2,
		)

		quantity = _get_quantity(line)

		self.assertEqual(_get_product_id(line), "prod_legacy")
		self.assertAlmostEqual(quantity, 2)
		self.assertAlmostEqual(_get_rate(line, quantity), 29.75)

	def test_uses_decimal_quantity_for_amount_excluding_tax(self):
		line = _line_item(
			amount_excluding_tax=1492,
			pricing={
				"price_details": {
					"price": "price_current",
					"product": "prod_current",
				},
				"type": "price_details",
				"unit_amount_decimal": "2984",
			},
			quantity_decimal="0.5",
		)

		quantity = _get_quantity(line)

		self.assertAlmostEqual(quantity, 0.5)
		self.assertAlmostEqual(_get_rate(line, quantity), 29.84)

	def test_derives_negative_proration_rate_from_subtotal(self):
		line = _line_item(
			amount=-1702,
			subtotal=-1702,
			pricing={
				"price_details": {
					"price": "price_current",
					"product": "prod_current",
				},
				"type": "price_details",
				"unit_amount_decimal": None,
			},
			parent={"subscription_item_details": {"proration": True}},
			quantity=1,
		)

		quantity = _get_quantity(line)

		self.assertAlmostEqual(quantity, 1)
		self.assertAlmostEqual(_get_rate(line, quantity), -17.02)

	def test_derives_positive_proration_rate_from_amount(self):
		line = _line_item(
			amount=3405,
			pricing={
				"price_details": {
					"price": "price_current",
					"product": "prod_current",
				},
				"type": "price_details",
				"unit_amount_decimal": None,
			},
			parent={"subscription_item_details": {"proration": True}},
			quantity=2,
		)

		quantity = _get_quantity(line)

		self.assertAlmostEqual(quantity, 2)
		self.assertAlmostEqual(_get_rate(line, quantity), 17.025)

	def test_reads_current_total_tax_shape(self):
		tax = _stripe_object(
			amount=475,
			tax_rate_details={"tax_rate": "txr_current"},
		)

		self.assertEqual(_get_tax_rate_id(tax), "txr_current")

	def test_builds_tax_rows_from_total_taxes(self):
		invoice = _stripe_object(
			total_taxes=[
				{
					"amount": 475,
					"tax_rate_details": {"tax_rate": "txr_19"},
				}
			]
		)
		config = _stripe_object(account="VAT 19", rate=19, region="DE", stripe_id="txr_19")
		settings = _Settings([config])

		self.assertEqual(_get_invoice_tax_rows(invoice, settings), [("txr_19", config)])

	def test_imports_unknown_tax_rate_with_matching_account(self):
		invoice = _stripe_object(
			total_taxes=[
				{
					"amount": 475,
					"tax_rate_details": {"tax_rate": "txr_new_19"},
				}
			]
		)
		old_config = _stripe_object(
			stripe_id="txr_old_19",
			account="VAT 19",
			calculation="Exclusive",
			rate=19,
			region="DE",
		)
		tax_rate = _stripe_object(
			id="txr_new_19",
			country="DE",
			state=None,
			jurisdiction="DE",
			percentage=19,
			inclusive=False,
		)
		settings = _Settings([old_config])

		with patch(
			"erpnext_stripe.operations.create_invoice.stripe.TaxRate.retrieve",
			return_value=tax_rate,
		):
			tax_rows = _get_invoice_tax_rows(
				invoice,
				settings=settings,
				ignore_permissions=True,
			)

		self.assertTrue(settings.saved)
		self.assertTrue(settings.ignore_permissions)
		imported_config = settings.tax_configurations[-1]
		self.assertEqual(imported_config.stripe_id, "txr_new_19")
		self.assertEqual(imported_config.account, "VAT 19")
		self.assertEqual(tax_rows, [("txr_new_19", imported_config)])

	def test_imports_unknown_tax_rate_before_throwing_for_missing_account(self):
		invoice = _stripe_object(
			total_taxes=[
				{
					"amount": 475,
					"tax_rate_details": {"tax_rate": "txr_new_19"},
				}
			]
		)
		tax_rate = _stripe_object(
			id="txr_new_19",
			country="DE",
			state=None,
			jurisdiction="DE",
			percentage=19,
			inclusive=False,
		)
		settings = _Settings()

		with patch(
			"erpnext_stripe.operations.create_invoice.stripe.TaxRate.retrieve",
			return_value=tax_rate,
		):
			with self.assertRaises(MissingTaxAccountError) as cm:
				_get_invoice_tax_rows(
					invoice,
					settings=settings,
					ignore_permissions=True,
				)

		self.assertEqual(cm.exception.tax_rate_id, "txr_new_19")
		self.assertTrue(settings.saved)
		self.assertEqual(settings.tax_configurations[0].stripe_id, "txr_new_19")
		self.assertIsNone(settings.tax_configurations[0].account)
