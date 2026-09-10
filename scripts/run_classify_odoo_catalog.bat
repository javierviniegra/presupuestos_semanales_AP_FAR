@echo off
rem Monthly Odoo reference-data refresh: new branches (Sucursal) and the
rem expense-account/category classification. Kept in one .bat/one
rem scheduled task ("ControlPresupuestos_AP - Catalogos mensual") since
rem both are low-frequency, Odoo-sourced reference data - scheduler.py
rem (GastoReal, twice daily) explicitly skips any line whose company has
rem no matching Sucursal yet, so this must run before GastoReal sync can
rem pick up a brand-new branch.
cd /d %~dp0..
.venv\Scripts\python.exe scripts\sync_sucursales.py >> logs\classify_odoo_catalog.log 2>&1
.venv\Scripts\python.exe scripts\classify_odoo_catalog.py >> logs\classify_odoo_catalog.log 2>&1
