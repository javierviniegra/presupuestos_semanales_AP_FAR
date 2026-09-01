# scripts/classify_odoo_catalog.py
#
# Read-only from Odoo, writes only to the local mapping tables (never to
# Odoo, never to GastoReal/Presupuesto). Pulls every product.category and
# every distinct non-GRNI expense account actually used on paid/in_payment
# vendor-bill lines, and best-guess classifies each into an existing
# TipoGasto by name keywords. Idempotent and safe to re-run: never
# overwrites a tipo_gasto a human already set (via admin or otherwise),
# only fills rows that are new or still unclassified (tipo_gasto is null).

import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from presupuestos.models import CategoriaProductoTipoGasto, CuentaContableTipoGasto, TipoGasto  # noqa: E402

from core.database.odoo import get_odoo_connection  # noqa: E402


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return text.lower()


# Keyword -> TipoGasto name. Checked in order; first match wins. Keywords are
# matched against the normalized (lowercase, accent-stripped) name.
CATEGORY_RULES = [
    (["material de empaque", "mat. de empaque", "mat de empaque", "jarcieria", "quimicos",
      "higienicos desechables", "eq. seguridad e higiene", "botiquin", "cristaleria", "loza",
      "utensilios", "uniformes"], "Empaque y Limpieza"),
    (["cerveza", "vino", "licor", "brandy", "cognac", "ginebra", "mezcal", "ron", "tequila",
      "vodka", "whisky", "refresco", "jugo", "agua", "cafe y te", "bebidas con alcohol",
      "bebidas sin alcohol", "con alcohol", "sin alcohol", "aperitivos"], "Bebidas"),
    (["abarrotes", "aceite", "aderezo", "aves", "carne", "concentrados", "cordero", "dulces",
      "embutidos", "empanadas", "endulcorantes", "enlatados", "frutas y verduras", "guisados",
      "helados", "hielo", "lacteos", "mariscos", "materia prima", "pan", "pastas", "pasteleria",
      "pasteles", "pescados", "postres", "puerco", "queso", "salsas", "semillas", "especias",
      "condimentos", "tapas preparados", "tortilla", "verduras", "merma carne", "quesos y lacteos",
      "carbon"], "Alimentos"),
    (["papeleria y articulos de oficina", "papeleria y art"], "Administrativo y Oficina"),
]

ACCOUNT_RULES = [
    (["material de empaque", "mat. de empaque", "mat de empaque", "mat. de empaque", "empaque",
      "jarcieria", "articulos de limpieza", "art. de limpieza", "quimicos",
      "higienicos desechables", "equipo de seguridad e higiene", "equipo de proteccion",
      "botiquin", "articulos para botiquin", "cristaleria", "loza", "utensilios de cocina",
      "manteletas"], "Empaque y Limpieza"),
    (["bebidas con alcohol", "bebidas sin alcohol", "con alcohol", "sin alcohol"], "Bebidas"),
    (["abarrotes", "carnes", "embutidos", "empanadas", "frutas y verduras", "pan", "postres",
      "quesos y lacteos", "hielo", "tortilla", "carbon"], "Alimentos"),
    (["mtto", "mantenimiento", "materiales para mantenimiento", "equipo de restaurante",
      "equipo de computo", "equipo de comunicacion", "mobiliario y equipo de oficina",
      "equipo menor", "renta de equipo", "fumigacion", "gastos de instalacion"], "Mantenimiento"),
    (["arrendamiento", "renta de oficina", "unirrenta"], "Renta y Arrendamiento"),
    (["suministro de personal", "prevision social", "vales de despensa", "despensa",
      "asimilados a salarios", "impuesto sobre nomina", "comida personal"], "Nomina y Personal"),
    (["combustibles", "lubricantes", "casetas y estacionamiento", "flete", "peaje", "transporte",
      "equipo de transporte", "mtto eq de transporte", "valet parking", "viaticos", "pasajes"],
     "Combustibles y Transporte"),
    (["energia electrica", "suministro de agua", "telefono", "internet", "gas "], "Servicios Publicos"),
    (["asesorias", "honorarios", "cursos y capacitacion", "soporte tecnico", "auditoria",
      "analisis bacteriologicos", "analisis clinicos", "analisis toxicologicos", "pruebas"],
     "Servicios Profesionales"),
    (["papeleria", "licencias", "programas y software", "cuotas y suscripciones", "seguros",
      "management administrativo", "uniformes", "uniforme"], "Administrativo y Oficina"),
    (["publicidad", "propaganda", "atencion a clientes", "atencion al cliente"],
     "Publicidad y Marketing"),
    (["comisiones bancarias", "comisiones", "no deducibles", "other overheads", "otros impuestos",
      "other taxes", "recargos, multas", "vigilancia y seguridad", "recoleccion de basura",
      "donativos", "gastos fin de a", "gastos de venta", "servicios de log", "mensajeria y paqueteria",
      "advance to national suppliers", "advance payment to foreign suppliers", "banorte", "efectivo",
      "cash difference", "cost of sales", "deferred expenses", "deudores diversos",
      "devoluciones y descuentos", "recibos pendientes", "returns, discounts", "taxable cash flow",
      "taxes withheld", "intereses moratorios", "gastos aduanales", "ingresos por servicios",
      "impuestos retenidos", "raw materials and materials", "production in progress",
      "provision of wages", "variaciones de inventario", "patentes y marcas"],
     "Otros / Sin Clasificar"),
]


def classify(name, rules):
    n = normalize(name)
    for keywords, tipo_nombre in rules:
        for kw in keywords:
            if normalize(kw) in n:
                return tipo_nombre
    return None


def run():
    tipos = {t.nombre: t for t in TipoGasto.objects.all()}
    uid, models_proxy, db, password = get_odoo_connection()

    # --- product categories ---
    categories = models_proxy.execute_kw(db, uid, password, "product.category", "search_read", [[]], {"fields": ["id", "name"]})

    cat_created, cat_classified, cat_unclassified = 0, 0, []
    for c in categories:
        obj, created = CategoriaProductoTipoGasto.objects.get_or_create(
            odoo_category_id=c["id"], defaults={"odoo_category_name": c["name"]}
        )
        if created:
            cat_created += 1
        if obj.tipo_gasto_id is None:
            tipo_nombre = classify(c["name"], CATEGORY_RULES)
            if tipo_nombre:
                obj.tipo_gasto = tipos[tipo_nombre]
                obj.odoo_category_name = c["name"]
                obj.save()
                cat_classified += 1
            else:
                cat_unclassified.append(c["name"])

    # --- direct-expense accounts (non-GRNI) actually used on paid/in_payment bills ---
    bill_ids = models_proxy.execute_kw(
        db, uid, password, "account.move", "search_read",
        [[["move_type", "=", "in_invoice"], ["payment_state", "in", ["paid", "in_payment"]]]],
        {"fields": ["id"], "limit": 20000},
    )
    ids = [b["id"] for b in bill_ids]

    accounts_seen = {}
    CHUNK = 500
    for i in range(0, len(ids), CHUNK):
        chunk_ids = ids[i:i + CHUNK]
        lines = models_proxy.execute_kw(
            db, uid, password, "account.move.line", "search_read",
            [[["move_id", "in", chunk_ids], ["display_type", "=", "product"]]],
            {"fields": ["account_id"]},
        )
        for l in lines:
            acc = l["account_id"]
            if acc and "Goods Received" not in acc[1]:
                accounts_seen[acc[0]] = acc[1]

    acc_created, acc_classified, acc_unclassified = 0, 0, []
    for acc_id, acc_name in accounts_seen.items():
        obj, created = CuentaContableTipoGasto.objects.get_or_create(
            odoo_account_id=acc_id, defaults={"odoo_account_name": acc_name}
        )
        if created:
            acc_created += 1
        if obj.tipo_gasto_id is None:
            tipo_nombre = classify(acc_name, ACCOUNT_RULES)
            if tipo_nombre:
                obj.tipo_gasto = tipos[tipo_nombre]
                obj.odoo_account_name = acc_name
                obj.save()
                acc_classified += 1
            else:
                acc_unclassified.append(acc_name)

    print(f"Categories: {len(categories)} total, {cat_created} new rows, {cat_classified} auto-classified")
    print(f"Accounts:   {len(accounts_seen)} total, {acc_created} new rows, {acc_classified} auto-classified")

    print(f"\n{len(set(cat_unclassified))} distinct UNCLASSIFIED category names (need manual review in admin):")
    for name in sorted(set(cat_unclassified)):
        print(" -", name)

    print(f"\n{len(set(acc_unclassified))} distinct UNCLASSIFIED account names (need manual review in admin):")
    for name in sorted(set(acc_unclassified)):
        print(" -", name)


if __name__ == "__main__":
    run()
