@echo off
rem Monthly Odoo reference-data refresh, all under one .bat/one scheduled
rem task ("ControlPresupuestos_AP - Catalogos mensual"):
rem   1. New branches (Sucursal) - scheduler.py skips any line whose
rem      company has no matching Sucursal yet, so this must run first.
rem   2. Expense-account/category classification.
rem   3. A FULL GastoReal reconciliation (scheduler.py --full) - the
rem      twice-daily runs are incremental (last 30 days only, for speed -
rem      see scheduler.py's own header comment) and can miss a
rem      cancellation/reversal on something paid more than 30 days ago;
rem      this monthly full pass is the safety net that eventually catches it.
cd /d %~dp0..
.venv\Scripts\python.exe scripts\sync_sucursales.py >> logs\classify_odoo_catalog.log 2>&1
.venv\Scripts\python.exe scripts\classify_odoo_catalog.py >> logs\classify_odoo_catalog.log 2>&1
.venv\Scripts\python.exe scripts\scheduler.py --full
