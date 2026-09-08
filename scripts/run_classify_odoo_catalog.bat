@echo off
cd /d %~dp0..
.venv\Scripts\python.exe scripts\classify_odoo_catalog.py >> logs\classify_odoo_catalog.log 2>&1
