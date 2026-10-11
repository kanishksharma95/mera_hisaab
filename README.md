# Mera Hisaab

> **Apni Dukaan, Apna Hisaab.** — A digital hisaab-kitaab partner for every local shop.

Multi-tenant business-management / ERP SaaS for Indian local shops, built with
Django + PostgreSQL + Bootstrap 5 + HTMX.

## Status

Actively built out. The foundation and all core shop-management modules are
**complete and tested** (96 tests, incl. tenant-isolation).

### Done

- **Foundation** — custom email auth, user profiles, business onboarding,
  multi-tenant architecture, branded layout, Super-Admin (Django admin)
- **Dashboard** — real, tenant-scoped KPIs with a period filter (today → year)
- **Catalog** — products with dynamic per-business-type attributes, categories
- **Inventory** — stock tracking; every change logged as a transaction
- **Sales / POS** — billing, invoices, shareable public invoice links, udhaar
- **Customers & Udhaar** — customer ledger with running balances
- **Purchases & Suppliers** — stock-in, supplier ledger, payables
- **Payments** — dynamic per-business payment methods + a cashbook, with
  **Razorpay** integration (online invoice collection + SaaS subscriptions,
  webhook-verified)
- **Expenses** — dynamic per-business expense categories, mirrored to the
  cashbook; feeds net-profit on the dashboard
- **Reports** — P&L, sales trend, top products, tax summary, receivables vs.
  payables

### Not yet built

- Employees / role-based access control (RBAC)
- Full SaaS-plan lifecycle (plan gating, upgrades, dunning)

## Architecture notes

Every module is strictly **tenant-scoped** (`Model.objects.for_business(...)`),
and all money/stock changes flow through service functions inside atomic
transactions, so ledgers, inventory and the cashbook never drift. Dynamic,
per-business config (payment methods, expense categories, business-type
attributes) lives in the database and is editable per shop — not hardcoded.

## Requirements

- Python 3.11+
- PostgreSQL 13+ (production/target DB)

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows (PowerShell)
pip install -r requirements.txt

copy .env.example .env           # then edit values
```

### Database

Target DB is **PostgreSQL** — set `POSTGRES_*` in `.env`. If you don't have a
local Postgres while developing, set `USE_SQLITE=1` in `.env` to use a SQLite
file instead (migrations and tests run identically).

```bash
python manage.py migrate                 # applies schema + seeds business types
python manage.py createsuperuser         # Super Admin for /admin
python manage.py runserver
```

Open http://127.0.0.1:8000/ — you'll be routed to register → onboarding →
dashboard. Super Admin lives at http://127.0.0.1:8000/admin/.

### Razorpay (optional)

Online payments and subscriptions stay disabled until keys are set. Add test
keys (from the Razorpay dashboard, prefixed `rzp_test_`) to `.env`:

```
RAZORPAY_KEY_ID=rzp_test_xxxxx
RAZORPAY_KEY_SECRET=xxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxx     # required in production when Razorpay is on
```

Point a webhook at `/payments/webhook/razorpay/` (events `payment.captured`,
`order.paid`, `subscription.*`). `KEY_ID` is exposed to the browser by design;
the secrets stay server-side. See `.env.example` for all options.

## Settings layout

- `config/settings/base.py` — shared, env-driven config
- `config/settings/dev.py` — local development (default for `manage.py`)
- `config/settings/prod.py` — hardened production (HTTPS, HSTS, SMTP email)

Select with `DJANGO_SETTINGS_MODULE=config.settings.<env>`.

## Tests

```bash
python manage.py test
```

Includes the critical **tenant-isolation** tests proving a user cannot access
or switch into a business they don't belong to.
