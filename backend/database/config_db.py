import os
from pathlib import Path
from urllib.parse import quote

from backend.database.postgres_driver import PostgresConnection


def load_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = os.getenv("POSTGRES_HOST", "").strip()
    port = os.getenv("POSTGRES_PORT", "5432").strip()
    database = os.getenv("POSTGRES_DB", "postgres").strip()
    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "")

    if not host or not user or not password:
        raise RuntimeError("Configure DATABASE_URL ou POSTGRES_HOST, POSTGRES_USER e POSTGRES_PASSWORD no .env.")

    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{database}?sslmode=require"


def get_db_config(include_database: bool = True):
    return {
        "host": os.getenv("POSTGRES_HOST", ""),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "database": os.getenv("POSTGRES_DB", "postgres") if include_database else "",
        "user": os.getenv("POSTGRES_USER", ""),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "database_url": get_database_url(),
    }


def get_connection():
    return PostgresConnection(get_database_url())
