"""
Odoo XML-RPC Connection (Core Infrastructure)
"""

import xmlrpc.client
import os
from dotenv import load_dotenv

from pathlib import Path

env_path = Path(__file__).resolve().parents[2] / "core" / "config" / ".env"
load_dotenv(dotenv_path=env_path)


def get_odoo_connection():
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB_NAME")
    username = os.getenv("ODOO_USER")
    password = os.getenv("ODOO_PASSWORD")

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    return uid, models, db, password
