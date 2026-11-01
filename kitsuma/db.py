"""One connection configuration for local PostgreSQL or Supabase."""
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent.parent


class KitsumaError(Exception):
    pass


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def connect():
    load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise KitsumaError("Set DATABASE_URL in .env (see .env.example).")
    conn = psycopg2.connect(url, connect_timeout=10, cursor_factory=RealDictCursor)
    # Supabase commonly installs pgcrypto in extensions; local PostgreSQL uses public.
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT set_config('search_path', current_setting('search_path') || ', extensions', false)")
        return conn
    except Exception:
        conn.close()
        raise


def initialize():
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('users') AS users, to_regclass('kitsuma_schema') AS version")
            tables = cur.fetchone()
            if tables["users"] and not tables["version"]:
                raise KitsumaError("Old prototype database detected. Export it and use a fresh database; db-init will not overwrite it.")
            if tables["version"]:
                cur.execute("SELECT version FROM kitsuma_schema")
                if [r["version"] for r in cur.fetchall()] != [1]:
                    raise KitsumaError("Unsupported schema version.")
            cur.execute((ROOT / "kitsumadb.sql").read_text(encoding="utf-8"))
    finally:
        conn.close()
