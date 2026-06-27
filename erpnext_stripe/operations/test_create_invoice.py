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


class TestCreateInvoice(unittest.TestCase):
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
