# Presupuestos AP - Sucursales

## Overview

Web application to track and control branch (sucursal) budgets against
actual spend. Budgets are captured monthly per branch (prorated evenly
across the days of the month) but measured weekly. It pulls actual
payments per branch from Odoo, lets an administrator enter monthly
budgets, and reports budget vs actual with drill-down by expense type
and by provider.

## Scope

```text
Pull actual payments by branch from Odoo (one or several branches at a time).
Administrator enters monthly budgets per branch (optionally split by expense type).
A month's budget is prorated evenly across its calendar days; a week spanning
two months blends the daily rate from each month.
Home page shows: budget/week/actual/remaining (overall and by expense type),
a per-branch purchase comparison chart (logarithmic scale), and a monthly
running-balance view that resets each month and flags overspend.
Each budget row links to a detail report: payments broken down by provider, charts,
export to Excel or an executive PDF report for Direccion General.
Expense type is resolved from a provider -> expense-type mapping dictionary
(loaded from Excel for now; a future module may manage it directly).
```

Not in scope yet: branches that are not on Odoo will be read from an Excel
file in SharePoint in a later phase. That source is not wired up yet.

## Stack

```text
Backend: Django 6.1
Frontend: Django templates (server-side) + Chart.js for charts
Database: MySQL (mysqlclient), same host/credentials boundary pattern as
          the Wansoft project (ENV=dev/prod, *_DEV suffixed vars)
Odoo integration: XML-RPC, same Odoo instance/credentials as the Wansoft project
Excel export: openpyxl
```

## Environments

```text
Dev: local machine, test MySQL database.
Prod: deployed at http://187.251.203.223/, real MySQL database, deployed via
      GitHub pull (same pattern as Chatbot_FAR).
```

Only actions that touch the production server or the production database
require explicit confirmation before running. Local/dev changes do not.

## Project layout

```text
config/            Django project settings, URLs, WSGI/ASGI entrypoints
presupuestos/       Main Django app (budgets, expenses, reports)
core/config/.env    Local environment file (gitignored, never committed)
core/config/.env.example  Template listing every expected environment variable
manage.py
requirements.txt
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp core/config/.env.example core/config/.env
# fill in core/config/.env with real dev DB and Odoo credentials
python manage.py migrate
python manage.py runserver 8010
```

Port 8010 is used instead of Django's default 8000 because 8000 is already taken by XAMPP on this machine.

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md): how to enter monthly budgets,
  read the dashboard, and generate the PDF/provider/pending-invoice reports.
- [docs/Configuration_Manual_Presupuestos_AP.pdf](docs/Configuration_Manual_Presupuestos_AP.pdf)
  (source: [docs/configuration_manual.html](docs/configuration_manual.html)):
  initial setup from scratch - credentials, syncing branches from Odoo, the
  expense-type catalog, and the account/category -> expense-type mapping.
  A Spanish version for the operations team is generated the same way but
  kept out of the repo (English-only content policy for this repo).
- [PROJECT_CONTEXT_REPORT.md](PROJECT_CONTEXT_REPORT.md): architecture and
  data model reference, kept up to date for session handoffs.
