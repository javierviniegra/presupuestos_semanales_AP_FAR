# User Guide - Presupuestos AP

Practical guide for the three people who use this app day to day. For
architecture and data model details, see [PROJECT_CONTEXT_REPORT.md](../PROJECT_CONTEXT_REPORT.md).

## 1. Entering the monthly budget (admin)

Budgets are captured **once per month**, not per week. The app then
prorates that amount evenly across the days of the month and compares it
against actual spend week by week.

1. Go to `/admin/` and log in with a staff account.
2. Under **Presupuestos**, click **Add Presupuesto**.
3. Fill in:
   - **Sucursal**: the branch this budget is for.
   - **Tipo de gasto**: an expense type (Alimentos, Bebidas, etc.), or
     leave it **blank** to set a total for "everything else" not covered
     by an explicit row that month. A blank row is split evenly across
     whichever expense types don't already have their own row for that
     branch/month.
   - **Mes**: pick any day inside the target month — it is normalized to
     the 1st automatically on save.
   - **Monto**: the total budget for the whole month (not a weekly amount).
4. Save. Each `(sucursal, tipo_gasto, mes)` combination can only exist
   once — editing an existing row is how you correct a month, there's no
   separate "correction" flow.
5. A week that spans two calendar months (e.g. Aug 31-Sep 6) automatically
   blends both months' daily rates — you don't need to do anything special
   for that; it's handled by the app once both months have a budget entered.

If a branch/month has no budget row at all, that branch/month simply shows
$0 budgeted — the dashboard doesn't guess or carry over a prior month's
number (there is no rollover).

## 2. Reading the dashboard (`/dashboard/`)

1. **Filter panel** (top): check one or more sucursales, pick how many
   weeks back to show (`semanas`), and submit. The rest of the page is
   scoped to that selection.
2. **"Compras por sucursal (comparativo)"**: one line per selected branch,
   actual spend only, on a **logarithmic** y-axis. It exists specifically
   so a small branch's purchase pattern is still visible next to a much
   larger branch — on a normal (linear) axis the small branch would look
   like a flat line near zero. Use it to compare each branch's own
   trend/shape over time, not to compare exact dollar amounts (read those
   from the tables instead).
3. Per-branch cards below that: the same three series (gasto real,
   presupuesto, tendencia) on a normal linear axis, for a closer look at
   one branch at a time.
4. **"Presupuesto vs. gasto real"** table: one row per branch per week,
   budget vs. actual vs. remaining. The `g_agrupar` dropdown controls
   whether rows are grouped by sucursal or by week.
5. **"Por tipo de gasto"** table: same comparison broken down by expense
   type; `t_agrupar` controls its grouping the same way.
6. **"Avance mensual del presupuesto"**: expand a branch to see, per
   month, a running total of that month's actual spend against its
   budget, week by week. **Restante acumulado** turns red once a branch
   has gone over budget for that month; it resets to the full budget at
   the start of the next month (no carryover of over/under spend).
7. Click any week's row to open **detalle_semana** — a breakdown of that
   branch/week's spend by provider and by invoice.

## 3. Generating reports

All three buttons at the top of the filter panel use whatever
sucursal/semanas filter is currently selected:

- **Exportar PDF** (`/dashboard/reporte.pdf`): the executive PDF report.
  Opens in a new tab. Sections, in order:
  - **Anexo A**: always grouped by sucursal with weeks as rows,
    regardless of the dashboard's own `g_agrupar` toggle.
  - **Anexo B**: a chart plus a compact table per branch (the old
    all-rows table was replaced with a chart because it had too much
    detail to read on paper).
  - **Facturas pendientes de pago**: every unpaid invoice as of the
    moment the report was generated, with a pending-total.
  - **Proveedores - todas las sucursales**: top providers by spend across
    *every* branch, independent of the sucursal filter above (this one
    section intentionally ignores the filter, so it always reflects
    company-wide provider spend).
  - **Compras por sucursal (comparativo)**: the same log-scale
    per-branch chart described in section 2.
  - **Avance mensual del presupuesto**: same as the dashboard section,
    one table per branch per month.
- **Reporte por proveedor** (`/dashboard/proveedores/`): a simplified,
  provider-focused view of the same filtered data.
- **Facturas pendientes** (`/dashboard/pendientes/`): just the unpaid-invoice
  list and total, as its own page.

## 4. Known limitations (by design, not bugs)

- **1-cent rounding**: splitting a month's budget across days, or a
  branch's total across weeks, occasionally leaves a 1-cent difference
  between a displayed total and the sum of its parts. This is expected
  rounding behavior, not a data error.
- **Split-invoice weeks**: when Odoo records one invoice paid across two
  different payment dates, the app attributes the whole invoice to the
  week of its *latest* payment. This can make the app's weekly total
  differ slightly from Odoo's own per-payment view for that specific week
  — it is a simplification, not a discrepancy in the underlying data.
