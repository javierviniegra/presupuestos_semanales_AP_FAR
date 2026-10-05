# scripts/sync_presupuestos_odoo.py
#
# Manual run of the Odoo budget mirror (see presupuestos/presupuestos_odoo.py).
# The same function also runs automatically at the end of every
# scripts/scheduler.py run (twice a day), so this is only needed to refresh on
# demand or to seed a brand-new environment right away.

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from presupuestos.presupuestos_odoo import sincronizar_presupuestos_odoo  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("scheduler").setLevel(logging.INFO)

if __name__ == "__main__":
    print(sincronizar_presupuestos_odoo())
