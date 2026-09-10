# scripts/scheduler.py
#
# Sync: Odoo paid/in_payment vendor-bill lines -> GastoReal in MySQL.
# Read-only on the Odoo side; writes only to GastoReal. Two modes,
# selected by the --full CLI flag:
#
#   Incremental (default - the twice-daily 5am/2pm Scheduled Tasks): only
#   asks Odoo for bills with write_date >= RECENT_WINDOW_DAYS ago, so a
#   routine run only costs what actually changed instead of re-processing
#   the whole managed history every time (was taking 4-7 minutes for
#   ~53k lines with almost nothing to show for it - see PROJECT_CONTEXT_
#   REPORT.md 2026-09-10). Its stale-cleanup is scoped to GastoReal rows
#   whose OWN fecha_pago also falls in that same recent window - a bill
#   cancelled/reverted long after being paid won't be caught until the
#   next full run, by design (see below); a bill cancelled shortly after
#   being paid will be, since both its write_date and fecha_pago are
#   recent.
#
#   Full (--full - the monthly "Catalogos mensual" Scheduled Task, see
#   scripts/run_classify_odoo_catalog.bat): no write_date filter, and
#   stale-cleanup covers the entire managed window. This is the safety
#   net that eventually catches a cancellation/reversal too old for an
#   incremental run to have noticed.
#
# Both modes: every line currently paid/in_payment in Odoo (within
# whichever window applies) with fecha_pago >= GASTOREAL_SYNC_DESDE
# (models.py) is upserted (touches sincronizado_en via auto_now).
# Afterward, any in-scope GastoReal row NOT touched in this run - because
# its invoice was cancelled, its payment was reverted, or the line no
# longer exists - is deleted. This is how cancelled/un-paid invoices get
# removed automatically, without a separate cancellation-handling path.
# Anything with fecha_pago before GASTOREAL_SYNC_DESDE is never touched
# by either mode - deliberately kept as untouched historical record
# (business decision 2026-09-10).
#
# semana is based on fecha_pago (real payment date via account.payment,
# through account.move.reconciled_payment_ids), not the invoice date -
# sampled 87% of bills are paid on a different date than invoiced, the
# whole point of this app is tracking cash paid per week. See GastoReal's
# docstring in models.py for the multi-payment simplification and the
# monto_factura/monto_pagado audit fields.

import datetime
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.utils import timezone  # noqa: E402

# Own log file, separate from Django's own logs/django.log, since this runs
# unattended (~5am) and needs a dedicated, easy-to-check history of runs.
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    _file_handler = logging.FileHandler(LOGS_DIR / "scheduler.log", encoding="utf-8")
    _file_handler.setFormatter(_formatter)
    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)
    logger.addHandler(_console_handler)
    logger.propagate = False

from presupuestos.models import (  # noqa: E402
    GASTOREAL_SYNC_DESDE,
    CategoriaProductoTipoGasto,
    CuentaContableTipoGasto,
    GastoReal,
    Sucursal,
)

from core.database.odoo import get_odoo_connection  # noqa: E402

PAID_STATES = ["paid", "in_payment"]
CHUNK = 500
RECENT_WINDOW_DAYS = 30


def iso_week_monday(d):
    return d - datetime.timedelta(days=d.weekday())


def resolve_tipo_gasto(account, product_id, prod_categ, account_map, category_map):
    if not account:
        return None
    if "Goods Received" in account[1]:
        if not product_id:
            return None
        categ_id = prod_categ.get(product_id[0])
        return category_map.get(categ_id) if categ_id else None
    return account_map.get(account[0])


def run(full=False):
    modo = "full" if full else "incremental"
    logger.info("scheduler run started (modo=%s)", modo)
    sync_started_at = timezone.now()

    uid, models, db, password = get_odoo_connection()

    sucursal_by_company = {s.odoo_company_id: s for s in Sucursal.objects.all()}

    domain = [["move_type", "=", "in_invoice"], ["payment_state", "in", PAID_STATES]]
    recent_cutoff_date = (sync_started_at - datetime.timedelta(days=RECENT_WINDOW_DAYS)).date()
    if not full:
        recent_cutoff_dt = sync_started_at - datetime.timedelta(days=RECENT_WINDOW_DAYS)
        domain.append(["write_date", ">=", recent_cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")])

    bills = models.execute_kw(
        db, uid, password, "account.move", "search_read",
        [domain],
        {
            "fields": [
                "id", "name", "invoice_date", "partner_id", "company_id", "payment_state",
                "amount_total", "reconciled_payment_ids",
            ],
            "limit": 50000,
        },
    )
    bill_by_id = {b["id"]: b for b in bills}
    bill_ids = list(bill_by_id.keys())

    payment_ids = list({pid for b in bills for pid in b["reconciled_payment_ids"]})
    payment_by_id = {}
    for i in range(0, len(payment_ids), CHUNK):
        chunk = payment_ids[i:i + CHUNK]
        payments = models.execute_kw(
            db, uid, password, "account.payment", "read", [chunk], {"fields": ["id", "date", "amount"]}
        )
        for p in payments:
            payment_by_id[p["id"]] = p

    for bill in bills:
        pagos = [payment_by_id[pid] for pid in bill["reconciled_payment_ids"] if pid in payment_by_id]
        fechas_pago = [p["date"] for p in pagos if p["date"]]
        bill["fecha_pago"] = max(fechas_pago) if fechas_pago else bill["invoice_date"]
        bill["monto_pagado"] = sum((p["amount"] for p in pagos), 0)

    all_lines = []
    for i in range(0, len(bill_ids), CHUNK):
        chunk = bill_ids[i:i + CHUNK]
        lines = models.execute_kw(
            db, uid, password, "account.move.line", "search_read",
            [[["move_id", "in", chunk], ["display_type", "=", "product"]]],
            {"fields": ["id", "move_id", "account_id", "product_id", "price_total"]},
        )
        all_lines.extend(lines)

    product_ids = list({l["product_id"][0] for l in all_lines if l["product_id"]})
    prod_categ = {}
    for i in range(0, len(product_ids), CHUNK):
        chunk = product_ids[i:i + CHUNK]
        prods = models.execute_kw(db, uid, password, "product.product", "read", [chunk], {"fields": ["id", "categ_id"]})
        for p in prods:
            prod_categ[p["id"]] = p["categ_id"][0] if p["categ_id"] else None

    account_map = {m.odoo_account_id: m.tipo_gasto_id for m in CuentaContableTipoGasto.objects.all()}
    category_map = {m.odoo_category_id: m.tipo_gasto_id for m in CategoriaProductoTipoGasto.objects.all()}

    created, updated, skipped_no_sucursal, skipped_no_date, skipped_pre_cutoff = 0, 0, 0, 0, 0

    for line in all_lines:
        bill = bill_by_id[line["move_id"][0]]
        company = bill["company_id"]
        sucursal = sucursal_by_company.get(company[0]) if company else None
        if not sucursal:
            skipped_no_sucursal += 1
            continue

        if not bill["invoice_date"]:
            skipped_no_date += 1
            continue
        fecha_factura = datetime.date.fromisoformat(bill["invoice_date"])
        fecha_pago = datetime.date.fromisoformat(bill["fecha_pago"]) if bill["fecha_pago"] else fecha_factura

        if fecha_pago < GASTOREAL_SYNC_DESDE:
            # Older than the managed window (see GASTOREAL_SYNC_DESDE's
            # docstring in models.py) - deliberately left alone, not
            # created/updated, and excluded from the stale-cleanup query
            # below too.
            skipped_pre_cutoff += 1
            continue

        semana = iso_week_monday(fecha_pago)

        tipo_gasto_id = resolve_tipo_gasto(
            line["account_id"], line["product_id"], prod_categ, account_map, category_map
        )

        defaults = dict(
            sucursal=sucursal,
            tipo_gasto_id=tipo_gasto_id,
            odoo_move_id=bill["id"],
            factura_numero=bill["name"] or "",
            proveedor_odoo_id=bill["partner_id"][0] if bill["partner_id"] else None,
            proveedor_nombre=bill["partner_id"][1] if bill["partner_id"] else "",
            fecha_factura=fecha_factura,
            fecha_pago=fecha_pago,
            semana=semana,
            monto=Decimal(str(line["price_total"])),
            monto_factura=Decimal(str(bill["amount_total"])),
            monto_pagado=Decimal(str(bill["monto_pagado"])),
            payment_state=bill["payment_state"],
        )
        _, was_created = GastoReal.objects.update_or_create(odoo_move_line_id=line["id"], defaults=defaults)
        if was_created:
            created += 1
        else:
            updated += 1

    # Full mode: scoped to the whole managed window (fecha_pago >=
    # GASTOREAL_SYNC_DESDE) - the periodic safety net that reconciles
    # anything an incremental run couldn't have safely caught.
    # Incremental mode: scoped further, to fecha_pago >= recent_cutoff_date
    # too - a row paid outside the recent window simply wasn't re-fetched
    # this run (not necessarily invalid), so it must never be treated as
    # stale here. Only a recently-paid row absent from this run's result
    # is real evidence of a cancellation/reversal.
    stale = GastoReal.objects.filter(sincronizado_en__lt=sync_started_at, fecha_pago__gte=GASTOREAL_SYNC_DESDE)
    if not full:
        stale = stale.filter(fecha_pago__gte=recent_cutoff_date)
    deleted_count = stale.count()
    stale.delete()

    logger.info(
        "modo=%s bills=%s lines=%s created=%s updated=%s deleted_stale=%s "
        "skipped_no_sucursal=%s skipped_no_date=%s skipped_pre_cutoff=%s",
        modo, len(bills), len(all_lines), created, updated, deleted_count,
        skipped_no_sucursal, skipped_no_date, skipped_pre_cutoff,
    )


if __name__ == "__main__":
    try:
        run(full="--full" in sys.argv)
    except Exception:
        logger.exception("scheduler run failed")
        raise
