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

Stripe acts as an intermediary clearing account. Set up a **Bank Account** in ERPNext (e.g. "Stripe") with a dedicated GL account and configure it as the **Stripe Bank Account** in ERPNext Stripe Settings. This should represent your Stripe balance, not the real bank account that receives Stripe payouts.

**Automated by this app:**

When a customer payment succeeds (`charge.succeeded`), the app imports the linked Stripe balance transaction as a **Bank Transaction** against the configured Stripe Bank Account. Existing Stripe balance transactions can also be imported from **ERPNext Stripe Settings** via **Import > Balance Transactions** for a selected date range.

Use ERPNext's bank reconciliation flow to reconcile those Bank Transactions against Sales Invoices and other accounting documents. This creates the accounting entry that clears Accounts Receivable and leaves unreconciled Stripe balance movements visible for manual recovery if automatic matching or posting fails.

Imported charge balance transactions use Stripe's gross transaction amount and do not book the nested Stripe processing fee. Stripe fee balance transactions are imported separately as Bank Transactions and can later be reconciled against Stripe's fee invoices.

**Handled manually:**

When Stripe pays out to your real bank account, reconcile the imported payout Bank Transaction against the corresponding real-bank transaction or create a Journal Entry:

| Account | Debit | Credit |
|---|---|---|
| Real Bank Account | payout amount | |
| Stripe Bank Account | | payout amount |

When Stripe charges fees (deducted from your balance), create a Journal Entry:

| Account | Debit | Credit |
|---|---|---|
| Stripe Fees (Expense) | fee amount | |
| Stripe Bank Account | | fee amount |

The Stripe Bank Account balance in ERPNext should match your actual Stripe balance.

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
