import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from erpnext_stripe.api import import_balance_transactions
from erpnext_stripe.operations.create_bank_transaction import (
	_get_bank_transaction_values,
	_get_legacy_fee_transaction_id,
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

	def test_builds_net_deposit_with_embedded_fee(self):
		balance_transaction = _stripe_object(
			id="txn_with_fee",
			created=1_704_067_200,
			currency="eur",
			amount=1000,
			fee=30,
			net=970,
			type="charge",
			reporting_category="charge",
			description=None,
		)
		frappe = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="Test Company")),
			unscrub=lambda value: "Charge",
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.get_system_timezone", return_value="UTC"
			),
		):
			values = _get_bank_transaction_values(balance_transaction, "Stripe Clearing")

		self.assertEqual(values["deposit"], 9.7)
		self.assertEqual(values["included_fee"], 0.3)
		self.assertNotIn("withdrawal", values)

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

	def test_resolves_payment_source_invoice_number_through_payment_intent(self):
		balance_transaction = _stripe_object(
			id="txn_test",
			created=1_704_067_200,
			currency="eur",
			amount=1000,
			type="charge",
			reporting_category="charge",
			description=None,
		)
		payment_source = _stripe_object(id="py_test", payment_intent="pi_test")
		payment_intent = _stripe_object(
			id="pi_test",
			invoice=None,
			payment_details={"order_reference": "in_test"},
		)
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
				"erpnext_stripe.operations.create_bank_transaction.stripe.PaymentIntent.retrieve",
				return_value=payment_intent,
			),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.stripe.Invoice.retrieve",
				return_value=stripe_invoice,
			),
		):
			values = _get_bank_transaction_values(
				balance_transaction,
				"Stripe Clearing",
				source=payment_source,
			)

		self.assertEqual(values["reference_number"], "INV-001")

	def test_falls_back_when_payment_details_invoice_is_missing(self):
		import stripe

		balance_transaction = _stripe_object(
			id="txn_test",
			created=1_704_067_200,
			currency="eur",
			amount=1000,
			type="charge",
			reporting_category="charge",
			description=None,
		)
		payment_source = _stripe_object(id="py_test", payment_intent="pi_test")
		payment_intent = _stripe_object(
			id="pi_test",
			invoice=None,
			payment_details={"order_reference": "in_missing"},
		)
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
				"erpnext_stripe.operations.create_bank_transaction.stripe.PaymentIntent.retrieve",
				return_value=payment_intent,
			),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.stripe.Invoice.retrieve",
				side_effect=stripe.error.InvalidRequestError(
					"No such invoice: 'in_missing'",
					"id",
					code="resource_missing",
				),
			),
		):
			values = _get_bank_transaction_values(
				balance_transaction,
				"Stripe Clearing",
				source=payment_source,
			)

		self.assertEqual(values["reference_number"], "py_test")

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

	def test_sets_supplier_for_non_invoice_non_payout_transactions(self):
		balance_transaction = _stripe_object(
			id="txn_fee",
			created=1_704_067_200,
			currency="eur",
			amount=-42,
			type="stripe_fee",
			reporting_category="fee",
			description="Automatic Taxes",
		)
		frappe = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="Test Company")),
			unscrub=lambda value: value.replace("_", " ").title(),
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.get_system_timezone", return_value="UTC"
			),
		):
			values = _get_bank_transaction_values(
				balance_transaction,
				"Stripe Clearing",
				supplier="Stripe Supplier",
			)

		self.assertEqual(values["party_type"], "Supplier")
		self.assertEqual(values["party"], "Stripe Supplier")

	def test_imports_standalone_stripe_fee_without_synthetic_transaction(self):
		balance_transaction = _stripe_object(
			id="txn_fee",
			created=1_704_067_200,
			currency="eur",
			amount=-42,
			fee=0,
			net=-42,
			type="stripe_fee",
			reporting_category="fee",
			description="Billing - Usage Fee",
		)
		settings = _stripe_object(stripe_bank_account="Stripe Clearing", supplier="Stripe Supplier")
		bank_transaction = Mock()

		def get_value(doctype, *args, **kwargs):
			if doctype == "Bank Transaction":
				return None
			if doctype == "Bank Account":
				return "Test Company"
			raise AssertionError(doctype)

		frappe = SimpleNamespace(
			get_single=Mock(return_value=settings),
			db=SimpleNamespace(get_value=get_value, exists=Mock()),
			new_doc=Mock(return_value=bank_transaction),
			unscrub=lambda value: value.replace("_", " ").title(),
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
			patch(
				"erpnext_stripe.operations.create_bank_transaction.get_system_timezone", return_value="UTC"
			),
		):
			result = run(balance_transaction)

		self.assertIs(result, bank_transaction)
		frappe.new_doc.assert_called_once_with("Bank Transaction")
		frappe.db.exists.assert_not_called()
		values = bank_transaction.update.call_args.args[0]
		self.assertEqual(values["withdrawal"], 0.42)
		self.assertEqual(values["transaction_id"], "txn_fee")
		self.assertEqual(values["transaction_type"], "Stripe Fee")
		self.assertNotIn("included_fee", values)

	def test_does_not_set_supplier_for_payouts(self):
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
			values = _get_bank_transaction_values(
				balance_transaction,
				"Stripe Clearing",
				supplier="Stripe Supplier",
			)

		self.assertNotIn("party_type", values)
		self.assertNotIn("party", values)

	def test_creates_one_fee_withdrawal_for_legacy_gross_deposit(self):
		balance_transaction = _stripe_object(
			id="txn_test",
			amount=1000,
			fee=30,
			net=970,
			currency="eur",
			created=1_704_067_200,
		)
		settings = _stripe_object(stripe_bank_account="Stripe Clearing", supplier="Stripe Supplier")
		existing_bank_transaction = _stripe_object(
			name="ACC-BTN-0001",
			company="Test Company",
			date=datetime.date(2024, 1, 1),
			currency="EUR",
			deposit=10.0,
			withdrawal=0,
			included_fee=0,
		)
		fee_transaction = Mock()
		frappe = SimpleNamespace(
			get_single=Mock(return_value=settings),
			db=SimpleNamespace(
				get_value=Mock(return_value=existing_bank_transaction),
				exists=Mock(side_effect=[False, True]),
			),
			new_doc=Mock(return_value=fee_transaction),
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
		):
			self.assertIs(run(balance_transaction), fee_transaction)
			self.assertIsNone(run(balance_transaction))

		frappe.new_doc.assert_called_once_with("Bank Transaction")
		fee_transaction.insert.assert_called_once_with()
		fee_transaction.submit.assert_called_once_with()
		values = fee_transaction.update.call_args.args[0]
		self.assertEqual(values["bank_account"], "Stripe Clearing")
		self.assertEqual(values["company"], "Test Company")
		self.assertEqual(values["date"], datetime.date(2024, 1, 1))
		self.assertEqual(values["currency"], "EUR")
		self.assertEqual(values["withdrawal"], 0.3)
		self.assertEqual(values["party_type"], "Supplier")
		self.assertEqual(values["party"], "Stripe Supplier")
		self.assertEqual(values["reference_number"], "txn_test")
		self.assertEqual(values["transaction_type"], "Stripe Fee")
		self.assertEqual(values["description"], "Embedded Stripe fee for balance transaction txn_test")
		self.assertEqual(values["transaction_id"], _get_legacy_fee_transaction_id("txn_test"))
		self.assertEqual(existing_bank_transaction.deposit, 10.0)
		self.assertEqual(existing_bank_transaction.included_fee, 0)

	def test_does_not_create_fee_withdrawal_for_correct_net_deposit(self):
		balance_transaction = _stripe_object(
			id="txn_test",
			amount=1000,
			fee=30,
			net=970,
			currency="eur",
			created=1_704_067_200,
		)
		settings = _stripe_object(stripe_bank_account="Stripe Clearing", supplier="Stripe Supplier")
		existing_bank_transaction = _stripe_object(
			name="ACC-BTN-0001",
			company="Test Company",
			date=datetime.date(2024, 1, 1),
			currency="EUR",
			deposit=9.7,
			withdrawal=0,
			included_fee=0.3,
		)
		frappe = SimpleNamespace(
			get_single=Mock(return_value=settings),
			db=SimpleNamespace(
				get_value=Mock(return_value=existing_bank_transaction),
				exists=Mock(),
			),
			new_doc=Mock(),
		)

		with (
			patch("erpnext_stripe.operations.create_bank_transaction.frappe", frappe),
		):
			self.assertIsNone(run(balance_transaction))

		frappe.db.exists.assert_not_called()
		frappe.new_doc.assert_not_called()

	def test_import_count_includes_created_legacy_fee_transaction(self):
		balance_transactions = _stripe_object(
			auto_paging_iter=Mock(
				return_value=iter(
					[
						_stripe_object(id="txn_legacy"),
						_stripe_object(id="txn_retry"),
					]
				)
			)
		)
		created_fee_transaction = Mock()

		with (
			patch("erpnext_stripe.api.frappe.has_permission"),
			patch("erpnext_stripe.api.init_stripe"),
			patch("erpnext_stripe.api._get_created_range", return_value=(1, 2)),
			patch(
				"erpnext_stripe.api.stripe.BalanceTransaction.list",
				return_value=balance_transactions,
			),
			patch(
				"erpnext_stripe.api.create_bank_transaction",
				side_effect=[created_fee_transaction, None],
			),
			patch("erpnext_stripe.api._publish_import_progress"),
		):
			result = import_balance_transactions("2024-01-01", "2024-01-02")

		self.assertEqual(result, {"imported": 1})
