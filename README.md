### ERPNext Stripe

Sync Customers, Items and Invoices from Stripe to ERPNext

> [!WARNING]
> This app is still in development and not ready for production use.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app erpnext_stripe
```

### Stripe API Key Permissions

This app only reads from Stripe. When using a restricted API key, enable **Read** access for:

- Customers
- Products
- Prices
- Tax Rates
- Invoices
- Payment Intents
- Balance
- Balance Transaction Sources
- Charges and Refunds
- Payouts

Subscribe to the following webhook events in the Stripe Dashboard:

- `charge.succeeded`
- `customer.created`
- `customer.updated`
- `invoice.finalized`

### Setup

1. Open **ERPNext Stripe Settings** and enter your Stripe API key.
2. Click **Import > Tax Rates** to fetch your Stripe tax rates. Set the ERPNext **Account** for each rate and save.
3. Click **Import > Products** to import your Stripe products as ERPNext Items.
4. Click **Import > Customers** to import existing Stripe customers as ERPNext Customers.
5. Configure the webhook in Stripe Dashboard (the endpoint URL is shown in the settings form). Copy the webhook signing secret into **Webhook Secret** and save.

### Payment Reconciliation

Stripe acts as an intermediary clearing account. Create a dedicated **Bank Account** for the Stripe balance.
Do not use the real bank account that receives Stripe payouts.

In **ERPNext Stripe Settings**, set the _Stripe Bank Account_ (`stripe_bank_account`).
Also set the Stripe _Supplier_ (`supplier`) when you use Stripe supplier invoices.

When a customer payment succeeds, the app imports the linked Stripe balance transaction as a
**Bank Transaction**. You can also use **Import > Balance Transactions** for a selected date range.

#### Standalone Stripe fees

Stripe can report a fee as a separate balance transaction. Examples include usage fees and automatic tax fees.
These rows have a negative amount, a zero fee, and a net amount equal to the negative amount.

The app imports each row as one **Bank Transaction** with a _Withdrawal_ (`withdrawal`).
It does not create another fee transaction. Reconcile the withdrawal against the matching Stripe supplier
**Purchase Invoice** in **Bank Reconciliation Tool Beta**.

#### New charges with an embedded processing fee

For a positive Stripe balance transaction with an embedded fee, Stripe reports gross amount, fee, and net.
The app imports the net as _Deposit_ (`deposit`). It imports the fee as _Included Fee_ (`included_fee`).
It does not use the gross amount as the deposit.

To reconcile this **Bank Transaction**:

1. Enable _Enable Automatic Journal Entries for Bank Fees_
   (`enable_automatic_journal_entries_for_bank_fees`) in **Banking Settings**.
2. Set the _Bank Fee Account_ (`bank_fee_account`) on the Stripe **Bank Account**.
3. In **Bank Reconciliation Tool Beta**, select the charge and all matching **Sales Invoices**.
4. Reconcile the full gross invoice amount in one step.

The tool posts only the net amount to the Stripe bank account. It posts the included fee to the configured
bank fee account. Partial or follow-up reconciliation is not supported for an included fee.

**Bank Reconciliation Tool Beta** cannot use the included fee to settle a Stripe supplier
**Purchase Invoice** directly. The tool posts the included fee without party data.

The _Bank Fee Account_ only permits accounts with the "Expense" root type. Do not use the Stripe supplier
payable account as the _Bank Fee Account_. Create a separate "Stripe Fee Clearing" expense account in the
same currency as the Stripe bank account.

Use this manual clearing process:

1. Set the Stripe _Bank Fee Account_ to the "Stripe Fee Clearing" expense account.
2. Submit the Stripe supplier **Purchase Invoice** with its normal fee expense and payable accounts.
3. Reconcile each net Stripe deposit and included fee against the matching gross **Sales Invoice**.
4. Wait until the **Purchase Invoice** and all matching charge reconciliations are submitted.
5. Calculate the part of the **Purchase Invoice** that covers embedded card and payment processing fees.
6. Create one **Journal Entry** for this embedded-fee amount.
7. Debit the Stripe supplier payable account.
8. Set _Party Type_ (`party_type`) to "Supplier" on the payable row.
9. Set the Stripe Supplier and the **Purchase Invoice** reference on the payable row.
10. Credit the "Stripe Fee Clearing" expense account.
11. Leave the party fields empty on the clearing row.
12. Submit the **Journal Entry**.

Reconcile standalone and synthetic fee withdrawals directly against the remaining **Purchase Invoice**
outstanding amount. Do not include these fees in the manual clearing **Journal Entry**.

This process clears the supplier invoice and the temporary clearing account. The **Purchase Invoice**
books the fee expense once. The clearing entries do not book a second expense.

If you do not need a supplier invoice, the _Bank Fee Account_ can be the fee expense account.
In that case, do not create a **Purchase Invoice** for the same fee.

The tool exposes deposit-side included fees only when the Stripe bank account uses the company currency.
For other currency combinations, post and reconcile the fee manually with an appropriate **Journal Entry**.

#### Legacy gross deposits

Older imports can contain the gross charge as _Deposit_ with no _Included Fee_.
The app does not change these submitted or reconciled transactions.

On a repeat import, the app creates one separate fee **Bank Transaction** when all these conditions match:

- The Stripe transaction is positive and has a positive embedded fee.
- The existing transaction is an exact gross deposit.
- The existing transaction has no included fee.

The separate transaction uses a deterministic synthetic transaction ID and the Stripe supplier.
It has the same bank account, company, date, and currency as the original transaction.
Repeated imports and webhook retries do not create another transaction.

Reconcile the legacy gross deposit against the gross **Sales Invoice**.
Reconcile the synthetic fee withdrawal against the matching Stripe supplier **Purchase Invoice**.
Do not add an included fee to the legacy deposit.

The app does not create synthetic fee rows for negative transactions, adjustments, or nonstandard legacy
amounts. Review these cases manually.

#### Prevent double booking

- Never use both an included fee and a synthetic fee withdrawal for the same embedded fee.
- Keep standalone Stripe fee rows as separate withdrawals. Their zero `fee` value does not mean the row is free.
- In the Beta tool, reconcile a supplier **Purchase Invoice** only against a standalone or synthetic withdrawal.
- For a new included fee, use the clearing-account workflow when a supplier invoice is required.
- Treat a Stripe contribution as a separate movement. Do not include it in a processing-fee invoice.

#### Payouts

When Stripe pays out to the real bank account, reconcile the Stripe withdrawal against the corresponding
real-bank deposit. You can also use a **Journal Entry** through a money-in-transit account.

The Stripe **Bank Account** balance in ERPNext should match the actual Stripe balance.

### Local testing

Copy _Endpoint URL_ from **ERPNext Stripe Settings** and use it as the **Forward URL** in the Stripe CLI:

```bash
stripe login
stripe listen --forward-to http://127.0.0.1:8006/api/method/erpnext_stripe.webhook.handler
stripe trigger customer.created
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/erpnext_stripe
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

gpl-3.0
