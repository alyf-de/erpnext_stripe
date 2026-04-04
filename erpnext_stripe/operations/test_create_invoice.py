import unittest

import stripe

from erpnext_stripe.operations.create_invoice import _get_product_id, _get_quantity, _get_rate


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
