# Project Context Report - Presupuestos AP (Sucursales)

Last regenerated: 2026-10-05 (end of day, at the Odoo-budget-mirror handoff)
Repo: https://github.com/javierviniegra/presupuestos_semanales_AP_FAR
Local path (dev PC): `C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\ControlPresupuestos_AP`
(moved here from `C:\Users\JavierViniegra\Desktop\AnalisisRestaurantesBI\ControlPresupuestos_AP`
sometime between 2026-09-10 and 2026-09-17, same OneDrive migration as the
Wansoft project - the old Desktop path no longer exists on this machine.
venv/git/scheduled tasks all work from the new path.)

Master continuity document. Regenerate FULLY (never as a patch) when: asked
explicitly, a major step closes, the conversation gets long, context usage
passes ~70%, or a new chat is needed. This file is pushed to GitHub, so it
stays in English even though the working conversation with the user is Spanish.

Standing handoff rule (applies to every FONDA project): when the owner says
the context is exhausted, ALWAYS (1) regenerate this file in full, (2) write
the handoff prompt, (3) suggest the new chat title in the format
`FONDA (proyecto corto): Paso N[-M]: <short description>`, (4) commit and push
if needed (English message, no secrets), and stop any running dev server.

---

## 0. Where we stand (read this first)

```text
Latest commit on main: 9e089c2 "mirror Odoo's account budgets and use them in
the reports" (pushed). Dev: fully verified. Production: git pull and migrate
(0014) done by the owner on 2026-10-05; `.\deploy\update.ps1` did NOT run
(the owner pasted it glued to the next command) - re-run it ALONE, then
confirm it printed "Server is listening on port 8020", the dashboard shows
the "Presupuesto por cuenta" button, Las Antenas / Puebla / Coyoacan show
Odoo-based budgets, and logs\scheduler.log has a line like
"presupuestos odoo: items=411 filas=402 ...". The owner said "listo" without
pasting the output, so this is UNCONFIRMED.
```

Optional follow-ups, none requested yet (ask before touching any):
1. Store the Odoo account on `GastoReal` to compare actual spend per account
   against the per-account budget (see Section 7).
2. Decide whether `_avance_mensual` should use `fecha_recepcion` for PO lines.
3. Update the manuals for the new screens (Spanish ones are local only).
4. The dashboard "Nomina y Personal" budget runs far above actual, because
   payroll accounts are imported but payroll is not in vendor bills (the
   owner chose "all costs and expenses" knowingly).
5. The owner mentioned a "fase 2" earlier; it has no defined scope yet.

## 1. What this project is

Django web application that controls branch (sucursal) budgets against actual
spend for Fonda Argentina's Accounts Payable team.

```text
Actual spend: paid vendor bills per branch pulled from Odoo (GastoReal), synced
  twice a day by a scheduler.
Budget: for any branch+month that Odoo has a budget for, the app mirrors it
  (per account) and uses it. Otherwise the admin enters a MONTHLY budget per
  branch in Django admin, optionally split by tipo de gasto or as a lump sum
  ("everything else"). Each month's amount is divided evenly across its days;
  a week's budget is the sum of its 7 daily shares (a week spanning two months
  blends both rates). Capture is monthly, measurement is weekly.
Dashboard: two tables (overall, and by tipo de gasto), a "Global" trend chart
  (log y-axis), per-sucursal trend charts, and "Avance mensual" (cumulative
  monthly spend vs budget, reset each month, red when over).
Week-detail drill-down, cross-branch provider report, pending-invoices report
  (live Odoo), executive PDF (respects the dashboard filter), and a new
  "Presupuesto por cuenta" page (Odoo budget by account).
```

Deferred (not started): branches not on Odoo will read data from an Excel file
in SharePoint; format/source not discussed.

## 2. Architecture and environments

```text
Backend:  Django 4.2.30 (pinned <5.0: MariaDB 10.4.x dev/prod; Django 5 needs 10.5+)
Frontend: server-side templates + Chart.js 4.5.1; matplotlib (Agg) PNGs in the PDF
DB:       MySQL/MariaDB via mysqlclient
PDF:      xhtml2pdf (pure Python)
Excel:    openpyxl (catalog import/export)
Odoo:     XML-RPC via core.database.odoo.get_odoo_connection (same instance and
          credentials as the Wansoft project)
Serving:  Waitress + WhiteNoise in production (no IIS/nginx)
Numbers:  django.contrib.humanize (intcomma) everywhere
```

### Dev (this PC)
- XAMPP MySQL on localhost:3306. It is NOT a Windows service (the owner
  rejected making it one - do not re-suggest); start it by hand from the XAMPP
  panel after every reboot.
- Always `python manage.py runserver 8010` (never 8000).
- Kill stale servers BY PROCESS PATH, not port:
  `Get-Process python | Where-Object { $_.Path -like "*ControlPresupuestos_AP*" } | Stop-Process -Force`
  then start fresh. Do it after every template/view/model edit before testing.
- mysqld crash root cause (fixed 2026-09-07): native-AIO assertion
  (`os0file.cc`), not Aria corruption. Fix is `innodb_use_native_aio=0` under
  `[mysqld]` in `C:\xampp\mysql\bin\my.ini` (outside the repo - re-add if XAMPP
  is reinstalled). If Aria corruption ever recurs: delete
  `C:\xampp\mysql\data\aria_log.*` + `aria_log_control`, then `aria_chk.exe -r`
  on the crashed table with mysqld stopped.

### Production (two machines, no remote access from this session)
```text
App VM "SVR-HIKCENTER" 192.168.100.93, Windows 11, repo at C:\Apps\ControlPresupuestos_AP,
  Waitress on port 8020, started by deploy\update.ps1.
Proxy/DB server 187.251.203.223: MySQL 3306 (db presupuestos_ap, user
  presupuestosusers - the password lives ONLY in the gitignored core\config\.env,
  never print or repeat it) AND an Apache reverse proxy on port 8088 mapping
  /presupuestos_ap/ -> http://192.168.100.93:8020/.
Public URL: http://187.251.203.223:8088/presupuestos_ap/
```
- `DJANGO_FORCE_SCRIPT_NAME=/presupuestos_ap` in the prod `.env`;
  `STATIC_URL = f"{FORCE_SCRIPT_NAME or ''}/static/"`. Apache strips the prefix
  on the way in, Django re-adds it on the way out; WhiteNoise un-prefixes its
  own matching. Testing directly against Waitress WITH the prefix gives
  misleading doubled-prefix results - test unprefixed.
- **Waitress is a plain background process with no auto-reload. After any
  `git pull`, code changes take effect only after `.\deploy\update.ps1`
  restarts it.** (This caused a "I don't see the new columns" report.)
- Windows Scheduled Tasks on prod: Gastos reales AM (5:00), PM (14:00),
  Catalogos mensual (day 1, 04:00), and "Arranque automatico" (AtStartup, runs
  as SYSTEM, runs update.ps1 so a reboot restarts the server). Both dev and
  prod run the full schedule against the same prod DB - deliberate redundancy,
  each sync is an idempotent upsert.
- The owner runs every production command by hand, guided step by step. Any
  production-affecting change needs explicit confirmation first.
- First-time production setup lives in `deploy/PRODUCTION_SETUP.md`.

### Scheduled tasks (dev, prefix "ControlPresupuestos_AP - ")
```text
Gastos reales AM   daily 5:00   scripts/scheduler.py
Gastos reales PM   daily 14:00  scripts/scheduler.py
Catalogos mensual  day 1 04:00  scripts/run_classify_odoo_catalog.bat
                                 = sync_sucursales.py, classify_odoo_catalog.py,
                                   then scheduler.py --full
```
`schtasks /TR` is limited to 261 characters, hence the .bat wrapper. Dev tasks
only fire while the laptop is on, logged in, with MySQL running (the AM task
missed 2026-09-18 because the laptop was off). Outage 2026-09-15..17: all three
tasks pointed at the dead Desktop path (`0x80070002`); re-registered against
the OneDrive path on 2026-09-17. Prod tasks were never affected.

### Browser/verification quirks (not app bugs)
- Verification convention: create a throwaway superuser (`_temp_verify`),
  verify in the browser pane, delete the user, close the tab, restart the dev
  server by process path.
- The Browser pane is often 0x0 right after navigation (wait 1-2 s, then
  screenshot). Login coordinates change with the viewport: screenshot first
  and click by `coordinate` from that image, not by `ref`.
- The sandboxed browser silently blocks `<script src="external">`; screenshots
  mid-scroll can show ghost duplicates. Verify via DOM/text, never chase it.
- PowerShell tool: `$home` is a reserved variable; some `Remove-Item` calls
  with path-like values get falsely blocked (split cleanup into separate
  calls); the Bash tool mangles values starting with `/` (MSYS) - use
  PowerShell for such tests.

## 3. Data model (presupuestos app)

```text
Sucursal             odoo_company_id (unique), nombre, activa (toggle in admin).
Categoria / TipoGasto  Costo de Ventas / Gasto Operativo; 12 TipoGasto seeded.
CuentaContableTipoGasto / CategoriaProductoTipoGasto
                     Hybrid classification: direct-expense accounts map via the
                     account; lines through the generic "Goods Received" clearing
                     account (PO purchases) map via the product category.
                     Auto-discovered/keyword-classified by
                     scripts/classify_odoo_catalog.py (idempotent, never
                     overwrites a human choice). Bulk Excel load at
                     /admin/catalogos/ (see below).
ConfiguracionCatalogos  singleton pk=1, permitir_carga_inicial flag (self-disabling).
Presupuesto          sucursal + tipo_gasto (nullable) + mes (first day of the month)
                     + monto. save() normalizes mes to day 1. tipo_gasto is
                     on_delete=PROTECT (blocks the destructive catalog wipe when
                     presupuestos exist). Blank tipo_gasto = "everything else":
                     split evenly across the tipos (and the "sin clasificar"
                     bucket if that sucursal/month has any) with no explicit row.
GastoReal            one row per Odoo vendor-bill line, synced, read-only.
                       fecha_factura, fecha_pago (latest payment), monto
                       (line amount WITH tax, price_total), monto_factura,
                       monto_pagado (UNRELIABLE, see Section 5),
                       orden_compra (Odoo invoice_origin, blank = direct/service),
                       fecha_recepcion (purchase.order.effective_date),
                       semana (see the week rule below), tipo_gasto (SET_NULL,
                       null = sin clasificar).
PresupuestoCuenta    read-only mirror of Odoo budgets: sucursal, mes,
                     cuenta_codigo, cuenta_nombre, monto, odoo_budget_id,
                     sincronizado_en. UniqueConstraint (sucursal, mes,
                     cuenta_codigo). Fully replaced on every sync.
CuentaPresupuestoTipoGasto
                     account code (unique) -> TipoGasto (SET_NULL). Seeded by the
                     sync; never overwrites a human-set tipo.
PerfilUsuario        User <-> Sucursal, enforced only for the "Sucursal" group.
                     Groups: Administrador, Usuario, Sucursal.
```

Migrations: 0011 monthly capture (wipes old weekly Presupuesto), 0012
ConfiguracionCatalogos, 0013 GastoReal.orden_compra/fecha_recepcion, 0014
PresupuestoCuenta + CuentaPresupuestoTipoGasto.

### GastoReal semantics
- `GASTOREAL_SYNC_DESDE = 2026-01-01` is the managed window. Older rows are
  untouched historial (the scheduler never writes or deletes them; the owner:
  "solo necesitamos presupuestos del ultimo anio... dejalos como historial").
- **Week rule (2026-09-17)**: a PO-linked line has `semana` = Monday of
  `fecha_recepcion`; a PO line whose PO has no receipt yet is skipped
  (`skipped_po_sin_recepcion`); a line with no PO uses `fecha_pago`. The
  pre-cutoff check still uses `fecha_pago`.
- Weeks are ISO weeks: Monday to Sunday.

### Catalog Excel tool (`/admin/catalogos/`)
`presupuestos/catalogos_excel.py`, `views_catalogos.py`,
`templates/presupuestos/catalogos_admin.html`. 4 related sheets with Excel
dropdowns. While `permitir_carga_inicial` is True, an import WIPES the 4
catalog tables plus GastoReal within the managed window (pre-cutoff historial
untouched) and reloads from the file, then flips the flag off; while False it
only upserts. A ProtectedError from Presupuesto aborts the transaction and
leaves the flag on. After a wipe, the next scheduler run reclassifies GastoReal.

## 4. Pages (presupuestos/views.py, config/urls.py)

```text
/                                  public landing page
/accounts/login/                   branded login
/dashboard/                        main dashboard. Sucursal selection is persisted in
                                   request.session["dashboard_sucursales"]; the main
                                   table (g_agrupar) defaults to grouping by sucursal;
                                   t_agrupar still defaults to tipo_gasto
/dashboard/detalle/<suc>/<semana>/ week detail: KPIs, budget-vs-actual by tipo,
                                   top providers, per-invoice tables with Orden de
                                   compra, Fecha de factura, Fecha de recepcion,
                                   Fecha de pago, Estado
/dashboard/proveedores/            cross-branch provider report
/dashboard/pendientes/             live Odoo unpaid/partial invoices by PO
/dashboard/presupuesto-cuentas/    Odoo budget by sucursal > month > tipo > account
/dashboard/reporte.pdf             executive PDF of the current filter
/admin/catalogos/ (+2 routes)      Excel catalog tool
/admin/                            Django admin, Fonda branded, es-mx
```
Shared computation: `_calcular_contexto_dashboard(request)` (dashboard and PDF).
Budget math: `_resolver_presupuestos_mensuales`, `_prorratear_por_dias`,
`_avance_mensual`. `_avance_mensual` buckets actual spend by `fecha_pago` day
and intentionally does not reconcile 1:1 with the weekly tables.

## 5. Data-accuracy bugs found by the owner cross-checking Odoo

1. Week used invoice date instead of payment date -> now uses real payment date
   (`reconciled_payment_ids` -> `account.payment.date`, latest payment).
2. Line amounts were pre-tax -> now `price_total` (sums to `amount_total` to
   the cent). Whole history was re-synced.
3. Dashboard showed invoices dated before the week's Monday (Coyoacan,
   31 Aug): not a grouping bug - `semana` followed payment date. The week
   detail now shows both fecha de factura and fecha de pago.
4. Production had zero Sucursal rows (only sync_sucursales.py creates them) so
   the scheduler silently skipped every line -> now run in update.ps1 and in
   the monthly .bat.
5. Naive date filtering of the scheduler would have deleted ~25k historical
   rows via stale cleanup -> caught before shipping; cleanup is scoped to the
   managed window.
6. I forgot the `fecha_recepcion` column in detalle_semana; the owner caught it;
   fixed in c4953c5.

Known gaps flagged, not fixed: `monto_pagado` is unreliable (payment totals can
cover many invoices; a fix would use `account.partial.reconcile`); multi-payment
bills (~4.2%) attribute the full line to the latest payment's week
(simplification the owner accepted).

## 6. Odoo integration notes

```text
reconciled_payment_ids / matched_payment_ids (payment_ids is usually empty).
price_total, not price_subtotal. amount_residual is the reliable outstanding
balance. invoice_origin = PO reference (blank for direct bills).
purchase.order.effective_date == stock.picking.date_done (verified live).
Chart of accounts is duplicated per company -> classify by NAME or CODE, not id.
Budgets: account.report.budget (name, company_id; one per company) and
  account.report.budget.item (budget_id, account_id, amount, date).
  Account ids differ per company (Carnes = 4922/8870/10021) but the CODE is
  stable (501.01.03). account.account.code is per-company: read it only with
  context={'allowed_company_ids': [company_id]}.
  On 2026-10-05: Las Antenas (company 9, Jan-May), Puebla (34, Aug-Sep),
  Coyoacan (36, Aug).
```

## 7. Odoo budget mirror (built 2026-10-05, commit 9e089c2)

Owner decisions: keep per-account detail; import every cost/expense account
(payroll included); skip revenue (codes starting "4"); Odoo replaces what was
captured manually; sync daily.

- `presupuestos/presupuestos_odoo.py` `sincronizar_presupuestos_odoo()`: reads
  budgets and items; if two budgets of one company cover the same month the
  highest id wins; skips revenue, zero amounts and unmapped companies; sums
  duplicates per (sucursal, mes, code); seeds `CuentaPresupuestoTipoGasto`
  (explicit `TIPO_POR_CODIGO` table for the 69 known codes plus prefix
  fallbacks, never overwrites a human tipo); then inside `transaction.atomic`
  replaces all `PresupuestoCuenta` rows. Never wipes if Odoo returns nothing.
- It runs at the end of every `scripts/scheduler.py` run as an independent step
  (failure -> exit code 1, but the GastoReal sync result is kept), via
  `scripts/sync_presupuestos_odoo.py` manually, and inside `deploy/update.ps1`.
- `_resolver_presupuestos_mensuales` overrides, per (sucursal, mes) covered by
  `PresupuestoCuenta`, both the general total and the per-tipo dict. Manual
  `Presupuesto` rows stay in the DB but are ignored there (so a month dropped
  from Odoo falls back to the manual figure). Dashboard, PDF, detalle_semana
  and avance mensual all inherit this.
- Verified in dev: sync output "items=411 filas=402 sucursales=3
  cuentas_nuevas_en_mapeo=68 omitidos_ingreso=8"; Coyoacan Aug = 1,288,759.05
  (equals Odoo to the cent), per-tipo breakdown sums to the same figure; the
  31/08 week blends 1 Aug day (Odoo) with 6 Sep days (manual) = 241,572.87;
  end-to-end scheduler run OK; the sync is idempotent; the page and button
  verified in the browser.
- NOT done: comparing actual spend per account (GastoReal stores only the
  resolved tipo_gasto, not the account; for PO lines it would be the product
  category's expense account, stored at sync time).

## 8. scheduler.py (GastoReal sync)

- Incremental by default: Odoo query adds `write_date >= now - 30 days`, and
  stale cleanup is scoped to GastoReal rows whose own `fecha_pago` is in that
  window (2m2s instead of 4-7 min).
- `--full`: no write_date filter; stale cleanup covers the whole managed
  window; runs monthly via the .bat.
- PO/receipt logic via `po_effective_date` (batched `purchase.order`
  search_read on `invoice_origin`). Counters in the log line include
  `skipped_pre_cutoff` and `skipped_po_sin_recepcion`.
- Production recompute of the PO-week rule was done 2026-09-18 (wipe of 13,950
  in-window rows, then `--full`: created=31871 skipped_pre_cutoff=25301
  skipped_po_sin_recepcion=61). Categorias/TipoGasto/mappings/Presupuesto/
  Sucursal were never touched.

## 9. Working conventions

```text
Git identity: Javier Viniegra <javier.viniegra@fondaargentina.com>. Branch main.
Explicit files only, never `git add .`; never amend. Commit/push when asked.
All GitHub content (commits, this report, docs, code comments) in English;
chat and user-facing UI text in Spanish.
Spanish manuals stay LOCAL and are never committed: docs/manual_configuracion.html,
docs/manual_modulos_admin.html and their PDFs (Manual_de_Configuracion_...,
Manual_Modulos_Admin_...). English ones are committed.
.env is gitignored; never print or repeat any credential.
Colors: Fonda green #035953, orange #eb6834, muted gray #898781.
Every feature: build -> verify (temp superuser or direct DB/RequestFactory) ->
commit with what was verified -> push -> restart the dev server.
```

Docs in the repo: `README.md`, `docs/USER_GUIDE.md` (3 usage profiles; notes
that Odoo budgets override manual ones), English configuration and admin-module
manuals (HTML + PDF) with `docs/screenshots/`, `deploy/PRODUCTION_SETUP.md`.
Not yet covering the Odoo budget mirror: the Spanish manuals and the English
admin-modules manual (no `PresupuestoCuenta` / `CuentaPresupuestoTipoGasto`
screens, no "Presupuesto por cuenta" page).

## 10. Git history (most recent first, all pushed)

```text
9e089c2  feat(presupuestos): mirror Odoo's account budgets and use them in the reports
c4953c5  fix(detalle_semana): actually show the fecha_recepcion column
726807f  feat(dashboard): remember sucursal filter, default the main table to sucursal grouping
940ebfc  docs(project): mark the PO-receipt-week production fix as done
023ab3b  feat(gastoreal): week for PO-linked lines follows goods-receipt date
018951f  docs(project): log dev Scheduled Tasks outage from the OneDrive path move
6d70922  docs(project): update local path after OneDrive move, log fecha de pago fix
c3520b1  fix(detalle_semana): show fecha de pago alongside fecha de factura
8f43b45  perf(scheduler): incremental sync by default, full reconciliation monthly
0c437e9  feat(gastoreal): add a 2026-01-01 sync cutoff, wipe that window on catalog reload
e71565c  fix(deploy): sync sucursales on every deploy, not just once manually
8eaab89  docs(project): record production reboot-survival task and Odoo sync decision
cd80d06  docs(project): mark production deployment as live
101ca39  feat(deploy): add production deployment tooling (Waitress + WhiteNoise)
a732a7e  feat(catalogos): add Excel bulk import/export for catalog tables
a96b6f9  docs: add initial configuration manual (PDF + HTML source)
f06df98  docs: add usability guide for admins, dashboard users, and reporting
e700019  docs(readme): update overview for monthly budget capture
42a5fae  feat(presupuestos): switch budget capture to monthly with weekly tracking
8d70251  Expand executive PDF report
(older: scaffolding, Django 4.2 pin, branding, Odoo sync/classification)
```

## 11. Step numbering

```text
Paso 1: Scaffolding - CLOSED 2026-09-01.
Paso 2: Data model, Odoo sync, dashboard, reports, PDF, budget capture, data-accuracy
        fixes - closed in practice.
Paso 3: Monthly capture, docs, catalog Excel tool, production deployment, scheduler
        performance, PO-receipt week rule, dashboard memory - done.
Paso 4: Odoo budgets by account (this handoff) - built and pushed; production
        verification pending.
```
Step numbers are tentative; the owner keeps their own count in the chat titles.

## 12. Open questions (not decided with the owner)

- The "fase 2" scope.
- Whether `_avance_mensual` should bucket PO lines by receipt date.
- Per-account actual-vs-budget comparison (needs the account on GastoReal).
- `monto_pagado` reliability and multi-payment week splitting.
- Sucursal-restricted user accounts have never been tested end to end.
- Update the manuals for the new screens.

## 13. How to resume work in a new session

1. Read this file first.
2. `cd` into the dev path at the top of this file (NOT the old Desktop path).
3. Check XAMPP MySQL is running (`Get-NetTCPConnection -LocalPort 3306 -State Listen`);
   it is not a Windows service and does not survive a reboot.
4. Kill any stale Django server by PROCESS PATH, then start
   `python manage.py runserver 8010`.
5. `git log --oneline` and `git status` against Section 10.
6. `.venv\Scripts\python.exe manage.py check`.
7. Then resolve the pending production confirmation in Section 0.
