import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from erpnext_stripe.operations.create_bank_transaction import (
	_get_bank_transaction_values,
	run,
)


def _stripe_object(**values):
	for key, value in values.items():
		if isinstance(value, dict):
			values[key] = _stripe_object(**value)

	return SimpleNamespace(**values)


class TestCreateBankTransaction(unittest.TestCase):
	def test_builds_deposit_from_positive_balance_transaction(self):
		balance_transaction = _stripe_object(
			id="txn_test",
			created=1_704_067_200,
			currency="eur",
			amount=1000,
			type="charge",
			reporting_category="charge",
			description=None,
		)
		charge = _stripe_object(id="ch_test", customer="cus_test", invoice="in_test")
		invoice = _stripe_object(id="in_test", number="INV-001", customer="cus_test")

		def get_value(doctype, name_or_filters, fieldname=None):
			if doctype == "Bank Account":
				return "Test Company"
			if doctype == "Customer":
				return "Test Customer"
			raise AssertionError(doctype)

		frappe = SimpleNamespace(db=SimpleNamespace(get_value=get_value), unscrub=lambda value: "Charge")

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.get_system_timezone", return_value="UTC"
			),
		):
			values = _get_bank_transaction_values(
				balance_transaction,
				"Stripe Clearing",
				source=charge,
				invoice=invoice,
			)

		self.assertEqual(values["bank_account"], "Stripe Clearing")
		self.assertEqual(values["company"], "Test Company")
		self.assertEqual(values["date"], datetime.date(2024, 1, 1))
		self.assertEqual(values["deposit"], 10.0)
		self.assertNotIn("withdrawal", values)
		self.assertNotIn("included_fee", values)
		self.assertEqual(values["currency"], "EUR")
		self.assertEqual(values["reference_number"], "INV-001")
		self.assertEqual(values["transaction_id"], "txn_test")
		self.assertEqual(values["transaction_type"], "Stripe Charge")
		self.assertEqual(values["party_type"], "Customer")
		self.assertEqual(values["party"], "Test Customer")

	def test_uses_source_invoice_as_reference_number(self):
		balance_transaction = _stripe_object(
			id="txn_test",
			created=1_704_067_200,
			currency="eur",
			amount=1000,
			type="charge",
			reporting_category="charge",
			description=None,
		)
		charge = _stripe_object(id="ch_test", invoice="in_test")
		stripe_invoice = _stripe_object(id="in_test", number="INV-001")
		frappe = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="Test Company")),
			unscrub=lambda value: "Charge",
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.get_system_timezone", return_value="UTC"
			),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.stripe.Invoice.retrieve",
				return_value=stripe_invoice,
			),
		):
			values = _get_bank_transaction_values(
				balance_transaction,
				"Stripe Clearing",
				source=charge,
			)

		self.assertEqual(values["reference_number"], "INV-001")

	def test_builds_withdrawal_from_negative_balance_transaction(self):
		balance_transaction = _stripe_object(
			id="txn_payout",
			created=1_704_067_200,
			currency="eur",
			amount=-2500,
			type="payout",
			reporting_category="payout",
			description="STRIPE PAYOUT",
		)
		frappe = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="Test Company")),
			unscrub=lambda value: "Payout",
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.get_system_timezone", return_value="UTC"
			),
		):
			values = _get_bank_transaction_values(balance_transaction, "Stripe Clearing")

		self.assertEqual(values["withdrawal"], 25.0)
		self.assertNotIn("deposit", values)
		self.assertEqual(values["description"], "STRIPE PAYOUT")
		self.assertNotIn("reference_number", values)
		self.assertEqual(values["transaction_type"], "Stripe Payout")

	def test_skips_existing_bank_transaction(self):
		balance_transaction = _stripe_object(
			id="txn_test",
			amount=1000,
			currency="eur",
			created=1_704_067_200,
		)
		settings = _stripe_object(stripe_bank_account="Stripe Clearing")
		frappe = SimpleNamespace(
			get_single=Mock(return_value=settings),
			db=SimpleNamespace(exists=Mock(return_value=True)),
			new_doc=Mock(),
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
		):
			self.assertIsNone(run(balance_transaction))

		frappe.new_doc.assert_not_called()
