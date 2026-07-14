from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.config_db import get_connection  # noqa: E402
from backend.database.db_compat import ensure_runtime_schema  # noqa: E402


def _split_sql(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    line_comment = False

    i = 0
    while i < len(script):
        ch = script[i]
        nxt = script[i + 1] if i + 1 < len(script) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
                current.append(ch)
            i += 1
            continue

        if not in_single and not in_double and ch == "-" and nxt == "-":
            line_comment = True
            i += 2
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double

        if ch == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _reset_public_schema(connection) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        for row in cursor.fetchall():
            cursor.execute(f'DROP TABLE IF EXISTS "{row[0]}" CASCADE')
        connection.commit()
    finally:
        cursor.close()


def import_data_sql(reset: bool = False) -> None:
    data_sql = PROJECT_ROOT / "database" / "data.sql"
    if not data_sql.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {data_sql}")

    connection = get_connection()
    cursor = connection.cursor()
    try:
        if reset:
            _reset_public_schema(connection)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        table_count = int(cursor.fetchone()[0])

        if table_count == 0:
            for statement in _split_sql(data_sql.read_text(encoding="utf-8")):
                cursor.execute(statement)
            connection.commit()
        else:
            print(f"Schema public ja possui {table_count} tabelas; mantendo dados existentes.")

        ensure_runtime_schema(connection)
    finally:
        cursor.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara o banco PostgreSQL do NeoBenesys.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove as tabelas do schema public antes de importar database/data.sql.",
    )
    args = parser.parse_args()

    import_data_sql(reset=args.reset)
    print("Banco PostgreSQL preparado com database/data.sql e compatibilidade aplicada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
