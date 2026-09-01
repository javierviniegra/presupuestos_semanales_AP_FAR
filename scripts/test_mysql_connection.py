# scripts/test_mysql_connection.py
#
# Read-only connectivity check: connects and runs SELECT VERSION(). No
# writes, no migrate. Usage: python scripts/test_mysql_connection.py [dev|prod]

import sys

from core.database.mysql import get_mysql_connection


def test(env):
    conn = get_mysql_connection(env=env)
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    version = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"[{env}] Connection OK. Server version: {version}")


if __name__ == "__main__":
    env = sys.argv[1] if len(sys.argv) > 1 else "dev"
    test(env)
