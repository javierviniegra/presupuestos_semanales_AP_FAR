# Presupuestos Semanales AP - Sucursales

## Overview

Web application to track and control weekly branch (sucursal) budgets against
actual spend. It pulls actual payments per branch from Odoo, lets an
administrator enter weekly budgets, and reports budget vs actual with
drill-down by expense type and by provider.

## Scope

```text
Pull actual payments by branch from Odoo (one or several branches at a time).
Administrator enters weekly budgets per branch.
Home page shows two tables: budget/week/actual/remaining, overall and by expense type.
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
python manage.py runserver
```
