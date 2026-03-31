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

Subscribe to the following webhook events in the Stripe Dashboard:

- `customer.created`
- `customer.updated`
- `invoice.finalized`
- `invoice.paid`

### Setup

1. Open **ERPNext Stripe Settings** and enter your Stripe API key.
2. Click **Import > Tax Rates** to fetch your Stripe tax rates. Set the ERPNext **Account** for each rate and save.
3. Click **Import > Products** to import your Stripe products as ERPNext Items.
4. Click **Import > Customers** to import existing Stripe customers as ERPNext Customers.
5. Configure the webhook in Stripe Dashboard (the endpoint URL is shown in the settings form). Copy the webhook signing secret into **Webhook Secret** and save.

### Payment Reconciliation

Stripe acts as an intermediary bank account. Set up a **Bank Account** in ERPNext (e.g. "Stripe") with a dedicated GL account and configure it as the **Stripe Bank Account** in ERPNext Stripe Settings.

**Automated by this app:**

When a customer pays a Stripe invoice (`invoice.paid`), the app creates a Payment Entry:
- Debit: Stripe Bank Account
- Credit: Accounts Receivable

**Handled manually:**

When Stripe pays out to your real bank account, create a Journal Entry:

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
