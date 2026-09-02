# Project Context Report - Presupuestos Semanales AP (Sucursales)

Last regenerated: 2026-09-02
Repo: https://github.com/javierviniegra/presupuestos_semanales_AP_FAR
Local path: `C:\Users\JavierViniegra\Desktop\AnalisisRestaurantesBI\ControlPresupuestos_AP`

Master continuity document. Regenerate FULLY (never as a patch) when: asked
explicitly, a major step closes, the conversation gets long, context usage
passes ~70%, or a new chat is needed. This file is pushed to GitHub, so it
stays in English even though working conversation with the user is Spanish.

---

## 1. What this project is

Web application to control weekly branch (sucursal) budgets against actual
spend, for Fonda Argentina's Accounts Payable team.

```text
Pull paid vendor bills per branch from Odoo (one or several branches selectable).
Administrator enters weekly budgets per branch, optionally broken down by
  tipo de gasto (expense type) or as one lump sum ("everything else").
Home page (dashboard): two tables, overall and by tipo de gasto, plus a
  per-sucursal trend chart (gasto real / presupuesto / linear trend).
Each row links to a week-detail drill-down: KPIs, budget-vs-actual chart by
  tipo de gasto, top providers chart, full invoice list for that week.
Cross-branch provider report: total spend by provider across every
  selected+active sucursal, grouped by proveedor/semana/sucursal.
Pending/partial invoices report: live Odoo query (not the daily sync) of
  not-yet-fully-paid bills, grouped by purchase order, using amount_residual.
Executive PDF export: KPI summary + narrative + top-variance table + charts
  (as static images) + detailed appendix tables. Respects current dashboard filter.
```

Deferred to a later phase (not started): branches not on Odoo will read
their data from an Excel file in SharePoint. Format/source not discussed yet.

## 2. Architecture

```text
Backend:      Django 4.2.30 (pinned <5.0 - MariaDB dev/prod are 10.4.x,
              Django 5.0+ needs 10.5+)
Frontend:     Django server-side templates + Chart.js 4.5.1 (interactive)
              + matplotlib (Agg backend, static PNGs embedded in the PDF)
Database:     MySQL/MariaDB via mysqlclient. Dev = XAMPP MySQL on THIS PC
              (localhost:3306, NOT a remote host - unlike Wansoft's pattern).
              Prod = 187.251.203.223 (not yet deployed there).
PDF export:   xhtml2pdf (pure Python, no system deps - WeasyPrint needs
              GTK3, painful on Windows)
Odoo:         XML-RPC, same instance/credentials as the Wansoft project
Numbers:      django.contrib.humanize (intcomma) everywhere - dashboard,
              PDF, admin
```

### Dev/prod boundary (confirmed once)

```text
Dev = this PC (XAMPP MySQL, localhost:3306). Prod = 187.251.203.223.
Only deploy/push actions to the real server need confirmation each time.
Local/dev changes don't.
```

### Known environment quirk: XAMPP MySQL needs manual start

The dev DB is XAMPP's MySQL, **not a Windows service** (user explicitly
rejected making it one - see memory `feedback_mysql_dev_no_windows_service`).
After a machine restart/reboot it must be started by hand via the XAMPP
control panel, and it is prone to Aria-engine corruption on an unclean
shutdown (`Cannot find checkpoint record`, `Table '.\mysql\db' is marked as
crashed`). Fix used successfully once already: delete
`C:\xampp\mysql\data\aria_log.*` + `aria_log_control`, then if a specific
system table (e.g. `mysql\db`) is still marked crashed, repair it with
`C:\xampp\mysql\bin\aria_chk.exe -r <path-to-table-without-extension>`
(mysqld must not be running during the repair). Both steps are safe -
they don't touch the actual InnoDB data in `presupuestos_ap`/`wansoft`/
`zenput` (separate storage engine, separate files).

### Recurring dev-environment bug: stale runserver process

Multiple times this session, editing a template/view and reloading the
browser kept showing OLD content, even with DEBUG=True (no cached
template loader configured) and even after using the port-based
`Get-NetTCPConnection | Stop-Process` kill loop. Root cause never fully
identified. **What reliably works**: kill by process path, not port -
`Get-Process python | Where-Object { $_.Path -like "*ControlPresupuestos_AP*" } | Stop-Process -Force`
- then start fresh. Do this after every template/view/model edit before
re-testing, don't trust a "still running" server to have picked up changes.

### Dev server port: 8010, not the Django default 8000

Standing rule set 2026-09-02: always start with
`python manage.py runserver 8010`, check `http://127.0.0.1:8010/`, not
8000.

### Browser-tool-specific quirks (not real app bugs)

- The sandboxed preview browser blocks `<script src="external">` network
  requests silently (no console error, no network log entry) even though
  `fetch()` to the same URL works fine and a *dynamically appended*
  `<script>` tag also works. Cause not fully understood; workaround was
  always "this is a testing-tool limitation, verify the real user's
  browser separately" - never chase it further.
- Screenshots taken immediately after a scroll sometimes show a visual
  "ghost duplicate" of chart content. Verified via `getBoundingClientRect()`
  and `get_page_text()` on every occurrence that the real DOM has no
  duplication - it's a capture/paint timing artifact of the tool, not a
  layout bug. Don't re-investigate; just verify via DOM/text extraction
  instead of trusting a mid-scroll screenshot.

### Login testing pattern that reliably works

The `find` tool's returned coordinates are sometimes wrong for this app's
centered-card login form (clicks land outside the visible fields). What
works: take a real `computer` screenshot first, read the actual pixel
coordinates from *that* image, then click by `coordinate`, not by `ref`.

## 3. Data model (presupuestos app)

```text
Sucursal            odoo_company_id (unique), nombre, activa (admin can
                     toggle - list_editable + bulk actions "Marcar como
                     activa/inactiva"). 27 synced from Odoo res.company.
Categoria            Costo de Ventas / Gasto Operativo (P&L top level)
TipoGasto             12 seeded, each under a Categoria. Editable via admin.
CuentaContableTipoGasto / CategoriaProductoTipoGasto
                     Hybrid classification: direct-expense Odoo accounts map
                     via CuentaContableTipoGasto; lines routed through the
                     generic "Goods Received" clearing account (PO-matched
                     purchases) map via the product's category instead
                     (CategoriaProductoTipoGasto). Auto-discovered and
                     keyword-classified from real Odoo data by
                     scripts/classify_odoo_catalog.py (idempotent, re-run
                     anytime - never overwrites a human classification).
Presupuesto          sucursal + tipo_gasto (nullable) + semana + monto.
                     tipo_gasto blank = "everything else": that amount
                     splits EVENLY across whichever tipos_gasto (and the
                     "sin clasificar" GastoReal bucket, if that
                     sucursal/semana has any) do NOT have their own
                     explicit Presupuesto row for the same sucursal/semana.
                     See _calcular_contexto_dashboard() in views.py.
GastoReal             One row per Odoo vendor-bill line. Synced daily,
                     read-only, never user-edited. Key fields:
                       fecha_factura  - real invoice date, reference only
                       fecha_pago     - REAL payment date (latest, if >1
                                        payment) - THIS drives `semana`
                       monto          - line amount WITH TAX (price_total)
                       monto_factura  - whole invoice total (amount_total)
                       monto_pagado   - sum of reconciled payments' own
                                        amount - UNRELIABLE, see Section 5
                     tipo_gasto nullable = "sin clasificar" (Odoo mapping
                     gap, not a data-entry choice).
PerfilUsuario         User <-> Sucursal link, only enforced for the
                     "Sucursal" role/group. Groups: Administrador, Usuario,
                     Sucursal (seeded via migration).
```

## 4. Pages / views (presupuestos/views.py)

```text
/                              Public landing page, links to /dashboard/
/accounts/login/               Branded login
/dashboard/                    Main dashboard: sucursal/semana filter
                                (Odoo-style dropdown, chips, Todas/Ninguna),
                                2 grouped/collapsible tables (Agrupar por:
                                semana/sucursal, +tipo_gasto for table 2),
                                per-sucursal trend chart. Rows in table 1
                                link to detalle_semana.
/dashboard/detalle/<suc>/<semana>/
                                Week-detail: KPIs, budget-vs-actual bar
                                chart by tipo_gasto, top-10 providers bar
                                chart, per-invoice-total table, per-line
                                table. Permission-checked against the
                                viewer's allowed sucursales.
/dashboard/proveedores/        Cross-branch provider report - combines
                                every selected+active sucursal (deliberately,
                                unlike detalle_semana). Top-15 chart +
                                grouped table (proveedor/semana/sucursal).
/dashboard/pendientes/         Live Odoo query (NOT from GastoReal) of
                                not_paid/partial bills as of a cutoff date,
                                grouped by purchase order (invoice_origin),
                                using amount_residual (reliable, unlike
                                monto_pagado - see Section 5).
/dashboard/reporte.pdf         Executive PDF export of the current filter.
/admin/                        Django admin, Fonda Argentina branded
                                (green #035953, logo), Spanish (es-mx),
                                has a "Dashboard" link back.
```

Shared computation lives in `_calcular_contexto_dashboard(request)` -
`dashboard`, `reporte_pdf` both call it. `detalle_semana`, `reporte_proveedores`,
`facturas_pendientes` each have their own focused query (didn't force-fit
the shared helper onto meaningfully different shapes).

## 5. Two real data-accuracy bugs found and fixed this session

Both were caught by the user cross-checking the app against Odoo directly -
neither would have been caught by "the sync ran without errors."

1. **Week was based on invoice date, not payment date.** 87% of sampled
   bills are paid on a different date than invoiced, sometimes a different
   week entirely. Fixed: `semana` now derives from `fecha_pago` (via
   `account.move.reconciled_payment_ids` -> `account.payment.date`, latest
   payment if more than one). `fecha_factura` kept as pure reference.

2. **Line amounts were pre-tax.** Synced `account.move.line.price_subtotal`
   (no IVA) instead of `price_total` (with IVA - verified sums to
   `amount_total` to the cent on real bills). This understated every
   single GastoReal row by the line's tax amount, which defeats the whole
   purpose of the app (tracking real cash paid). Fixed, and the full
   53,301-row history was re-synced, not just new rows going forward.

Both fixes were verified against the user's own manual Odoo cross-check
(Coyoacan semana 34: app now shows $171,224.62, user's Odoo check was
~$170,800, independent recomputation from Odoo gave $171,224.63 - 1 cent
of rounding across 189 lines, not a bug).

**Known remaining gap - `monto_pagado` is unreliable, flagged not fixed:**
it sums `account.payment.amount` for a bill's reconciled payments, but that
field is the payment TRANSACTION's total, which can cover multiple
invoices at once. Sampled: 8,477 of 16,084 invoices show `monto_factura` !=
`monto_pagado` by more than $1, some by over a million pesos (payment
shared across many bills). Documented in `GastoReal`'s docstring rather
than silently trusted. A reliable per-invoice fix would need
`account.partial.reconcile`'s own per-match `amount` field - not
implemented. Multi-payment bills (~4.2% of bills) also use a
simplification: full line amount counts toward the LATEST payment's week,
not proportionally split across payment dates - documented, not fixed
(user confirmed this simplification is fine for now).

## 6. Odoo integration details worth remembering

```text
account.move (vendor bill) reconciled_payment_ids -> account.payment.date
  is the real payment date. payment_ids is usually EMPTY - use
  reconciled_payment_ids or matched_payment_ids instead.
account.move.line.price_total (not price_subtotal) for tax-inclusive amounts.
account.move.amount_residual = reliable per-invoice outstanding balance
  (unlike summing account.payment.amount).
account.move.invoice_origin = purchase order reference, often blank
  (direct-entry bills have none) - fall back to "(Sin orden de compra)".
Odoo's chart of accounts is heavily duplicated per company (513 distinct
  account ids collapse to far fewer real concepts) - classify by NAME
  (normalized/accent-stripped), never by id.
Company IDs used in testing: Coyoacan=36 (Sucursal.id=22), Las Antenas=8,
  Maq=9 in our DB. San Jeronimo/Vallejo/Fonda Argentina still have zero
  Odoo purchase activity (pre-October-migration-wave branches).
```

## 7. Working conventions

```text
Git identity: Javier Viniegra <javier.viniegra@fondaargentina.com>
Branch: main. Explicit files only, never `git add .`; never amend; push
  only when asked (has been asked, and granted, every time so far this
  session - still ask each time per the user's standing rule).
Every feature this session: build -> verify with a temp throwaway Django
  superuser account (created, tested, deleted) or direct DB/RequestFactory
  checks -> commit with a detailed message including what was verified ->
  ask "hago push?" -> push -> restart the dev server for the user.
Real user-facing text in Spanish; commit messages, this report, code
  comments all in English.
Colors: Fonda Argentina green #035953 (verified from the real website,
  not guessed) + orange #eb6834 (documented CVD-safe pairing) + muted gray
  #898781 for trend/analytical overlays. Could not run the project's
  formal palette validator (no Node.js on this machine) - informed
  convention, not machine-verified; said so honestly rather than claiming
  full validation.
```

## 8. Git history (most recent first)

```text
9bd9963  Sync tax-inclusive line amounts (price_total), not pre-tax
74aeaeb  Add pending/partial invoices report, grouped by purchase order
5506009  Use real payment date, not invoice date, for GastoReal's semana
91fe600  Add cross-branch provider report
c8c5c7c  Add a per-invoice total list above the per-line breakdown
6a8fccc  Add week-detail drill-down page
a1517a9  Format money with thousand separators everywhere
ab3707d  Include "sin clasificar" in the remainder budget split
3bb1b2a  Spread blank-tipo_gasto Presupuesto across unspecified tipos
f9dc85f  Restructure PDF into a real executive report
6182a20  Add executive PDF export
5f109c2  Allow lump-sum Presupuesto without tipo_gasto
bae9c16  Add per-sucursal line chart
3869273  ISO week number + Dashboard link from admin
a2527c6  Fix "Ninguna" deselect-all bug
cc2bb54  Add logging system
434c5a3  Odoo-style filter dropdown + group-by
9b549b1  Add login and dashboard
(older: scaffolding, Django 4.2 pin, branding, Odoo sync/classification -
 see git log for full history, ~35 commits total)
```

All pushed to `origin/main` as of 2026-09-02.

## 9. Step numbering and progress

```text
Paso 1: Scaffolding (Django, MySQL/Odoo connections, branding) - CLOSED 2026-09-01
Paso 2: Data model, Odoo sync, main interface (dashboard, 3 reports, PDF,
        budget entry with smart splitting, 2 critical data-accuracy fixes)
        - substantially complete as of this report. Propose closing it
        here given the scope covered; confirm with user.
Paso 3: not started - candidates below.
```

## 10. Open questions / next step candidates (not yet decided with the user)

```text
- Confirm closing Paso 2 and the Paso 3 scope/numbering.
- monto_pagado reliability (Section 5) - fix via account.partial.reconcile,
  or leave as a documented gap?
- Multi-payment bill week-splitting (Section 5) - still fine as a
  simplification, or worth the complexity now that tax/date bugs are fixed?
- Production deployment to 187.251.203.223 (not started).
- SharePoint/Excel integration for non-Odoo branches (deferred phase,
  no details yet).
- Should scheduler.py actually be scheduled (Windows Task Scheduler,
  ~5am) now that it's been manually re-run several times this session?
- User-role testing: Administrador/Usuario/Sucursal groups exist and are
  enforced in code, but never tested end-to-end with a real
  Sucursal-restricted user account.
```

## 11. How to resume work in a new session

1. Read this file first.
2. `cd` into `C:\Users\JavierViniegra\Desktop\AnalisisRestaurantesBI\ControlPresupuestos_AP`.
3. **Check XAMPP MySQL is running first** (`Get-NetTCPConnection -LocalPort 3306 -State Listen`) -
   it is NOT a Windows service and will not survive a reboot. See Section 2's
   "Known environment quirk" for the corruption-recovery steps if it won't start.
4. Kill any stale server by PROCESS PATH before starting a fresh one (Section 2).
5. `git log --oneline` / `git status` against Section 8 to confirm nothing
   changed outside this report's knowledge.
6. `.venv/Scripts/python.exe manage.py check` before doing anything else.
