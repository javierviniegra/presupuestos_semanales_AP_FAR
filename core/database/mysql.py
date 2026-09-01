"""
MySQL/MariaDB Connection (Core Infrastructure)
"""

import os
from pathlib import Path

import MySQLdb
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parents[2] / "core" / "config" / ".env"
load_dotenv(dotenv_path=env_path)


def get_mysql_connection(env="dev"):
    """
    env:
        - dev
        - prod
    """
    suffix = "_DEV" if env == "dev" else ""

    return MySQLdb.connect(
        host=os.getenv(f"PRESUPUESTOS_DB_HOST{suffix}"),
        port=int(os.getenv(f"PRESUPUESTOS_DB_PORT{suffix}", "3306")),
        user=os.getenv(f"PRESUPUESTOS_DB_USER{suffix}"),
        passwd=os.getenv(f"PRESUPUESTOS_DB_PASSWORD{suffix}"),
        db=os.getenv(f"PRESUPUESTOS_DB_NAME{suffix}"),
        charset="utf8mb4",
    )
