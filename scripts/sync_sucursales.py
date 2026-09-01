# scripts/sync_sucursales.py
#
# Read-only from Odoo. Upserts Sucursal rows from res.company. Never
# deletes - a company disappearing from Odoo doesn't mean the branch
# stopped existing, so removal (if ever needed) stays a manual admin action.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from presupuestos.models import Sucursal  # noqa: E402

from core.database.odoo import get_odoo_connection  # noqa: E402


def run():
    uid, models_proxy, db, password = get_odoo_connection()

    companies = models_proxy.execute_kw(
        db, uid, password, "res.company", "search_read", [[]], {"fields": ["id", "name"]}
    )

    created, updated = 0, 0
    for c in companies:
        obj, was_created = Sucursal.objects.get_or_create(
            odoo_company_id=c["id"], defaults={"nombre": c["name"]}
        )
        if was_created:
            created += 1
        elif obj.nombre != c["name"]:
            obj.nombre = c["name"]
            obj.save()
            updated += 1

    print(f"{len(companies)} companies in Odoo. {created} created, {updated} renamed, "
          f"{len(companies) - created - updated} unchanged.")


if __name__ == "__main__":
    run()
