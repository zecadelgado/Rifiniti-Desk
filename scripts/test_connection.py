from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.config_db import get_connection  # noqa: E402
from backend.database.db_compat import ensure_runtime_schema  # noqa: E402


def test_connection() -> bool:
    print("=" * 70)
    print("TESTE DE CONEXAO - PostgreSQL/Supabase")
    print("=" * 70)

    try:
        connection = get_connection()
        ensure_runtime_schema(connection)
        cursor = connection.cursor()

        cursor.execute("SELECT current_database(), current_user, inet_server_addr(), inet_server_port()")
        database, user, server_addr, server_port = cursor.fetchone()
        print("Conexao com PostgreSQL bem-sucedida.")
        print(f"Banco: {database}")
        print(f"Usuario: {user}")
        print(f"Servidor: {server_addr}:{server_port}")

        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tabelas encontradas: {len(tables)}")
        for table in tables:
            print(f" - {table}")

        cursor.close()
        connection.close()
        return True
    except Exception as exc:
        print(f"ERRO: {exc}")
        return False


if __name__ == "__main__":
    raise SystemExit(0 if test_connection() else 1)
