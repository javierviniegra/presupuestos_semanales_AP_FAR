# scripts/test_odoo_connection.py
#
# Read-only connectivity check: authenticates and reads the server version.
# No data is read or written.

from core.database.odoo import get_odoo_connection


def test():
    uid, models, db, password = get_odoo_connection()

    if not uid:
        print("Authentication failed (no uid returned). Check ODOO_* credentials.")
        return

    print("UID:", uid)
    print("Connection OK")


if __name__ == "__main__":
    test()
