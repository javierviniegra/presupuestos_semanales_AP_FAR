# presupuestos/presupuestos_odoo.py
#
# Mirrors Odoo's own budgets (account.report.budget + its .item lines, the
# "Presupuesto 2026" screens under Contabilidad > Reportes) into
# PresupuestoCuenta, one row per sucursal / month / account code. Read-only
# on the Odoo side. Called by scripts/scheduler.py after every GastoReal sync
# (so twice a day) and by scripts/sync_presupuestos_odoo.py for a manual run.
#
# Why account CODE and not account id: every company has its own account ids
# for the same chart-of-accounts line ("Carnes" is 4922 / 8870 / 10021 in three
# companies, always code 501.01.03), so the code is the only key stable across
# sucursales. Codes are read per company (account.account's `code` is a
# per-company computed field, it comes back False without that company in the
# context).
#
# Scope decisions (user, 2026-10-05): keep the per-account detail; import every
# cost/expense account (including payroll); never import revenue (4xx - the
# "Ventas" line, negative amounts); zero-amount lines are skipped as noise.

import datetime
import logging
from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from core.database.odoo import get_odoo_connection

from .models import CuentaPresupuestoTipoGasto, PresupuestoCuenta, Sucursal, TipoGasto

logger = logging.getLogger("scheduler")

# Known account code -> TipoGasto name, built from the 69 codes found in the
# three budgets that existed on 2026-10-05, following the same conventions
# scripts/classify_odoo_catalog.py already applies to vendor-bill accounts.
# Only a seed: a tipo_gasto edited by a human in the admin is never overwritten.
TIPO_POR_CODIGO = {
    "113.08.03": "Nomina y Personal",  # PTU
    "501.01.12": "Bebidas",  # Con Alcohol
    "501.01.13": "Bebidas",  # Sin Alcohol
    "504.01.02": "Empaque y Limpieza",  # Cristaleria y Loza
    "504.01.03": "Empaque y Limpieza",  # Utensilios de Cocina
    "504.01.04": "Empaque y Limpieza",  # Mat. de Empaque
    "504.01.05": "Alimentos",  # Carbon
    "504.01.06": "Servicios Publicos",  # Gas
    "504.01.08": "Empaque y Limpieza",  # Art. de Limpieza
    "504.01.09": "Empaque y Limpieza",  # Manteletas
    "504.01.10": "Alimentos",  # Hielo
    "504.01.12": "Alimentos",  # Gastos de Salon (salsas, aderezos...)
    "504.01.13": "Otros / Sin Clasificar",  # Comisiones Plataformas
    "601.38.01": "Servicios Profesionales",  # Honorarios PM
    "601.45.01": "Renta y Arrendamiento",  # Arrendamiento PF
    "601.46.01": "Renta y Arrendamiento",  # Arrendamiento PM
    "601.49.01": "Combustibles y Transporte",  # Viaticos y Gastos de Viaje
    "601.50.01": "Servicios Publicos",  # Telefono
    "601.51.01": "Servicios Publicos",  # Suministro de Agua
    "601.52.01": "Servicios Publicos",  # Energia Electrica
    "601.53.01": "Otros / Sin Clasificar",  # Vigilancia y Seguridad
    "601.55.01": "Administrativo y Oficina",  # Papeleria y Art. de Oficina
    "601.56.01": "Mantenimiento",  # Mtto del Local
    "601.56.05": "Mantenimiento",  # Mantenimiento ABR
    "601.57.01": "Administrativo y Oficina",  # Seguros
    "601.58.01": "Otros / Sin Clasificar",  # Other taxes and duties
    "601.61.01": "Publicidad y Marketing",  # Publicidad y Propaganda
    "601.62.01": "Servicios Profesionales",  # Cursos y Capacitaciones
    "601.72.02": "Combustibles y Transporte",  # Fletes PM
    "601.77.01": "Administrativo y Oficina",  # Uniformes
    "601.83.01": "Otros / Sin Clasificar",  # No deducibles
    "601.84.02": "Mantenimiento",  # Renta de Equipo
    "601.84.03": "Mantenimiento",  # Fumigaciones
    "601.84.04": "Administrativo y Oficina",  # Licencias, Programas y Software
    "601.84.06": "Otros / Sin Clasificar",  # Recoleccion de basura
    "601.84.07": "Combustibles y Transporte",  # Servicios de Valet Parking
    "601.84.09": "Empaque y Limpieza",  # Botiquin
    "601.84.10": "Mantenimiento",  # Equipo Menor
    "601.84.11": "Publicidad y Marketing",  # Atencion al Cliente
    "601.84.13": "Nomina y Personal",  # Suministro de Personal
    "601.84.15": "Nomina y Personal",  # Vales de despensa
    "601.84.16": "Administrativo y Oficina",  # Management Administrativo
    "601.84.22": "Servicios Profesionales",  # Analisis Bacteriologicos
    "601.84.25": "Nomina y Personal",  # Comida personal
    "701.10.01": "Otros / Sin Clasificar",  # Comisiones Bancarias
}


def _nombre_tipo_por_defecto(codigo):
    if codigo in TIPO_POR_CODIGO:
        return TIPO_POR_CODIGO[codigo]
    # A code not seen on 2026-10-05: fall back to the account family so it
    # still lands somewhere sensible instead of silently "sin clasificar".
    if codigo.startswith("501."):
        return "Alimentos"
    if codigo.startswith("504."):
        return "Empaque y Limpieza"
    if codigo.startswith("601.") and codigo[4:6].isdigit() and int(codigo[4:6]) <= 29:
        return "Nomina y Personal"  # 601.01-601.29 is the payroll block
    return None


def _sembrar_mapeo(codigos_nombres):
    """
    Create a CuentaPresupuestoTipoGasto row for every code not seen before,
    and fill the tipo_gasto of any existing row that's still null (e.g. after
    a catalog reload nulled it). Never overwrites a non-null tipo_gasto.
    """
    tipos = {t.nombre: t for t in TipoGasto.objects.all()}
    existentes = {c.codigo: c for c in CuentaPresupuestoTipoGasto.objects.all()}
    creados = 0
    for codigo, nombre in codigos_nombres.items():
        fila = existentes.get(codigo)
        tipo_defecto = tipos.get(_nombre_tipo_por_defecto(codigo) or "")
        if fila is None:
            CuentaPresupuestoTipoGasto.objects.create(codigo=codigo, nombre=nombre, tipo_gasto=tipo_defecto)
            creados += 1
        elif fila.tipo_gasto_id is None and tipo_defecto is not None:
            fila.tipo_gasto = tipo_defecto
            fila.save()
    return creados


def sincronizar_presupuestos_odoo():
    """
    Full replace of PresupuestoCuenta from Odoo's current budgets. Returns a
    summary dict. Never wipes the table if Odoo returned nothing usable (an
    empty answer is far more likely an outage/permission problem than every
    budget having been deleted).
    """
    uid, models_proxy, db, password = get_odoo_connection()

    def ejecutar(modelo, metodo, args, kwargs=None):
        return models_proxy.execute_kw(db, uid, password, modelo, metodo, args, kwargs or {})

    sucursal_por_company = {s.odoo_company_id: s for s in Sucursal.objects.all()}

    presupuestos = ejecutar("account.report.budget", "search_read", [[]], {"fields": ["id", "name", "company_id"]})
    company_de_presupuesto = {p["id"]: (p["company_id"][0] if p["company_id"] else None) for p in presupuestos}

    items = ejecutar(
        "account.report.budget.item", "search_read", [[]], {"fields": ["budget_id", "account_id", "amount", "date"]}
    )
    if not items:
        logger.warning("presupuestos odoo: no budget items returned - leaving PresupuestoCuenta untouched")
        return {"items": 0, "filas": 0, "reemplazado": False}

    # If two budgets of the same company cover the same month (a duplicated
    # budget), the one with the highest id wins - never both, which would
    # double the month.
    presupuesto_ganador = {}
    for it in items:
        bid = it["budget_id"][0]
        company_id = company_de_presupuesto.get(bid)
        clave = (company_id, it["date"])
        if clave not in presupuesto_ganador or bid > presupuesto_ganador[clave]:
            presupuesto_ganador[clave] = bid

    # Account code/name, read per company (see the module header).
    cuentas_por_company = defaultdict(set)
    for it in items:
        cuentas_por_company[company_de_presupuesto.get(it["budget_id"][0])].add(it["account_id"][0])
    info_cuenta = {}  # (company_id, account_id) -> (codigo, nombre)
    for company_id, ids in cuentas_por_company.items():
        if company_id is None:
            continue
        leidas = ejecutar(
            "account.account", "read", [sorted(ids)],
            {"fields": ["code", "name"], "context": {"allowed_company_ids": [company_id]}},
        )
        for a in leidas:
            info_cuenta[(company_id, a["id"])] = (a["code"] or "", a["name"])

    acumulado = {}  # (sucursal_id, mes, codigo) -> [nombre, monto, budget_id]
    omitidos_sin_sucursal = set()
    omitidos_ingreso = 0
    for it in items:
        bid = it["budget_id"][0]
        company_id = company_de_presupuesto.get(bid)
        if presupuesto_ganador.get((company_id, it["date"])) != bid:
            continue
        sucursal = sucursal_por_company.get(company_id)
        if sucursal is None:
            omitidos_sin_sucursal.add(company_id)
            continue
        codigo, nombre = info_cuenta.get((company_id, it["account_id"][0]), ("", it["account_id"][1]))
        if not codigo:
            logger.warning("presupuestos odoo: account %s has no code, skipped", it["account_id"])
            continue
        if codigo.startswith("4"):
            omitidos_ingreso += 1
            continue
        monto = Decimal(str(it["amount"]))
        if monto == 0:
            continue
        mes = datetime.date.fromisoformat(it["date"])
        clave = (sucursal.id, mes, codigo)
        if clave in acumulado:
            acumulado[clave][1] += monto
        else:
            acumulado[clave] = [nombre, monto, bid]

    if not acumulado:
        logger.warning("presupuestos odoo: nothing importable after filtering - leaving PresupuestoCuenta untouched")
        return {"items": len(items), "filas": 0, "reemplazado": False}

    codigos_nombres = {}
    for (_, _, codigo), (nombre, _, _) in acumulado.items():
        codigos_nombres.setdefault(codigo, nombre)
    cuentas_nuevas = _sembrar_mapeo(codigos_nombres)

    filas = [
        PresupuestoCuenta(
            sucursal_id=suc_id, mes=mes, cuenta_codigo=codigo, cuenta_nombre=nombre, monto=monto, odoo_budget_id=bid
        )
        for (suc_id, mes, codigo), (nombre, monto, bid) in acumulado.items()
    ]
    with transaction.atomic():
        PresupuestoCuenta.objects.all().delete()
        PresupuestoCuenta.objects.bulk_create(filas)

    logger.info(
        "presupuestos odoo: items=%s filas=%s sucursales=%s cuentas_nuevas_en_mapeo=%s omitidos_ingreso=%s "
        "companies_sin_sucursal=%s",
        len(items), len(filas), len({f.sucursal_id for f in filas}), cuentas_nuevas, omitidos_ingreso,
        sorted(c for c in omitidos_sin_sucursal if c),
    )
    return {"items": len(items), "filas": len(filas), "reemplazado": True, "cuentas_nuevas": cuentas_nuevas}
