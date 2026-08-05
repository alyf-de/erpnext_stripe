from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
	from stripe import BalanceTransaction, Charge
	from stripe import Invoice as StripeInvoice


import frappe
import stripe
from frappe import _
from frappe.utils import get_system_timezone
from frappe.utils.data import flt, getdate


def run_for_invoice(invoice: "StripeInvoice"):
	charge = _get_charge(invoice)
	if not charge:
		return None

	return run_for_charge(charge, invoice=invoice)


def run_for_charge(
	charge: "Charge",
	invoice: "StripeInvoice | None" = None,
):
	balance_transaction = _get_charge_balance_transaction(charge)
	if not balance_transaction:
		return None

	return run(balance_transaction, source=charge, invoice=invoice)


def run(
	balance_transaction: "BalanceTransaction",
	source=None,
	invoice: "StripeInvoice | None" = None,
):
	if not getattr(balance_transaction, "id", None):
		return None

	amount = getattr(balance_transaction, "amount", 0)
	if not amount:
		return None

	settings = frappe.get_single("ERPNext Stripe Settings")
	if not settings.stripe_bank_account:
		frappe.throw(_("Please configure Stripe Bank Account in ERPNext Stripe Settings."))

	if frappe.db.exists(
		"Bank Transaction",
		{
			"bank_account": settings.stripe_bank_account,
			"transaction_id": balance_transaction.id,
		},
	):
		return None

	source = _get_source(balance_transaction, source)
	bank_transaction = frappe.new_doc("Bank Transaction")
	bank_transaction.update(
		_get_bank_transaction_values(
			balance_transaction,
			settings.stripe_bank_account,
			source=source,
			invoice=invoice,
			supplier=settings.supplier,
		)
	)
	bank_transaction.insert()
	bank_transaction.submit()
	return bank_transaction


def _get_source(balance_transaction: "BalanceTransaction", source=None):
	if source:
		return source

	source = getattr(balance_transaction, "source", None)
	if isinstance(source, str):
		return None

	return source


def _get_bank_transaction_values(
	balance_transaction: "BalanceTransaction",
	bank_account: str,
	source=None,
	invoice: "StripeInvoice | None" = None,
	supplier: str | None = None,
) -> dict:
	amount = _get_amount(balance_transaction.amount)
	reference_number = _get_reference_number(balance_transaction, source=source, invoice=invoice)
	values = {
		"bank_account": bank_account,
		"company": frappe.db.get_value("Bank Account", bank_account, "company"),
		"date": _get_transaction_date(balance_transaction),
		"currency": balance_transaction.currency.upper(),
		"description": _get_description(balance_transaction, source=source, invoice=invoice),
		"transaction_id": balance_transaction.id,
		"transaction_type": _get_transaction_type(balance_transaction),
	}

	if reference_number:
		values["reference_number"] = reference_number

	if amount > 0:
		values["deposit"] = amount
	else:
		values["withdrawal"] = abs(amount)

	if party := _get_party(balance_transaction, source=source, invoice=invoice, supplier=supplier):
		values.update(party)

	return values


def _get_charge(invoice: "StripeInvoice"):
	charge = getattr(invoice, "charge", None)
	if charge:
		return charge

	payment_intent = getattr(invoice, "payment_intent", None)
	if not payment_intent:
		return None

	payment_intent_id = payment_intent if isinstance(payment_intent, str) else payment_intent.id
	payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["latest_charge"])
	return getattr(payment_intent, "latest_charge", None)


def _get_charge_balance_transaction(charge: "Charge"):
	if isinstance(charge, str):
		charge = stripe.Charge.retrieve(charge, expand=["balance_transaction"])

	balance_transaction = getattr(charge, "balance_transaction", None)
	if isinstance(balance_transaction, str):
		return stripe.BalanceTransaction.retrieve(balance_transaction)

	return balance_transaction


def _get_amount(amount: int) -> float:
	return flt(amount / 100)


def _get_transaction_date(balance_transaction: "BalanceTransaction"):
	system_timezone = ZoneInfo(get_system_timezone())
	return getdate(datetime.fromtimestamp(balance_transaction.created, tz=system_timezone))


def _get_description(
	balance_transaction: "BalanceTransaction",
	source=None,
	invoice: "StripeInvoice | None" = None,
) -> str:
	description = getattr(balance_transaction, "description", None)
	if description:
		return description

	description = f"Stripe {balance_transaction.type} {balance_transaction.id}"
	if invoice_reference := _get_invoice_reference(invoice):
		description = f"{description} for invoice {invoice_reference}"

	return description


def _get_reference_number(
	balance_transaction: "BalanceTransaction",
	source=None,
	invoice: "StripeInvoice | None" = None,
) -> str:
	reference_number = (
		_get_invoice_reference(invoice)
		or _get_source_invoice_reference(source)
		or getattr(source, "id", None)
		or balance_transaction.id
	)
	if reference_number == balance_transaction.id:
		return None

	return reference_number


def _get_transaction_type(balance_transaction: "BalanceTransaction") -> str:
	transaction_type = getattr(balance_transaction, "reporting_category", None) or balance_transaction.type
	return f"Stripe {frappe.unscrub(transaction_type)}"


def _get_invoice_reference(invoice: "StripeInvoice | None") -> str | None:
	if not invoice:
		return None

	return getattr(invoice, "number", None)


def _get_source_invoice_reference(source) -> str | None:
	if not source:
		return None

	invoice = getattr(source, "invoice", None)
	if invoice_reference := _get_invoice_reference(_get_invoice(invoice)):
		return invoice_reference

	if invoice_reference := _get_payment_details_invoice_reference(source):
		return invoice_reference

	payment_intent = getattr(source, "payment_intent", None)
	if payment_intent_reference := _get_payment_intent_invoice_reference(payment_intent):
		return payment_intent_reference

	charge = getattr(source, "charge", None)
	if charge_reference := _get_charge_invoice_reference(charge):
		return charge_reference

	return None


def _get_invoice(invoice):
	if not invoice:
		return None

	if isinstance(invoice, str):
		try:
			return stripe.Invoice.retrieve(invoice)
		except stripe.InvalidRequestError:
			return None

	return invoice


def _get_payment_intent_invoice_reference(payment_intent) -> str | None:
	if not payment_intent:
		return None

	if isinstance(payment_intent, str):
		payment_intent = stripe.PaymentIntent.retrieve(payment_intent, expand=["invoice"])

	return _get_invoice_reference(_get_invoice(getattr(payment_intent, "invoice", None))) or (
		_get_payment_details_invoice_reference(payment_intent)
	)


def _get_payment_details_invoice_reference(source) -> str | None:
	payment_details = getattr(source, "payment_details", None)
	invoice_id = getattr(payment_details, "order_reference", None) if payment_details else None
	return _get_invoice_reference(_get_invoice(invoice_id))


def _get_charge_invoice_reference(charge) -> str | None:
	if not charge:
		return None

	if isinstance(charge, str):
		charge = stripe.Charge.retrieve(charge, expand=["payment_intent.invoice"])

	return _get_source_invoice_reference(charge)


def _get_party(
	balance_transaction: "BalanceTransaction",
	source=None,
	invoice: "StripeInvoice | None" = None,
	supplier: str | None = None,
) -> dict | None:
	if _is_invoice_transaction(source, invoice):
		if customer := _get_customer_party(source, invoice):
			return {
				"party_type": "Customer",
				"party": customer,
			}

		return None

	if supplier and not _is_payout(balance_transaction):
		return {
			"party_type": "Supplier",
			"party": supplier,
		}

	return None


def _is_invoice_transaction(source=None, invoice: "StripeInvoice | None" = None) -> bool:
	return bool(_get_invoice_reference(invoice) or _get_source_invoice_reference(source))


def _is_payout(balance_transaction: "BalanceTransaction") -> bool:
	reporting_category = getattr(balance_transaction, "reporting_category", None) or ""
	transaction_type = getattr(balance_transaction, "type", None) or ""
	return reporting_category == "payout" or transaction_type.startswith("payout")


def _get_customer_party(
	source=None,
	invoice: "StripeInvoice | None" = None,
) -> str | None:
	stripe_customer_id = getattr(invoice, "customer", None) if invoice else None
	stripe_customer_id = stripe_customer_id or getattr(source, "customer", None)
	if not stripe_customer_id:
		return None

	return frappe.db.get_value("Customer", {"stripe_id": stripe_customer_id})
