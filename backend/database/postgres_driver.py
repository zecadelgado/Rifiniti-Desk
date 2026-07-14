from __future__ import annotations

import re
from typing import Any, Optional

import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor


DatabaseError = psycopg2.Error
IntegrityError = psycopg2.IntegrityError
UniqueViolation = errors.UniqueViolation
ForeignKeyViolation = errors.ForeignKeyViolation
UndefinedTable = errors.UndefinedTable
UndefinedColumn = errors.UndefinedColumn

UNIQUE_VIOLATION = errors.UniqueViolation
FOREIGN_KEY_VIOLATION = errors.ForeignKeyViolation
UNDEFINED_TABLE = errors.UndefinedTable
UNDEFINED_COLUMN = errors.UndefinedColumn


PRIMARY_KEYS = {
    "anexos": "id_anexo",
    "anexos_manutencoes": "id_anexo",
    "anexos_notas_fiscais": "id_anexo",
    "auditorias": "id_auditoria",
    "baixas": "id_baixa",
    "categorias": "id_categoria",
    "centro_custo": "id_centro_custo",
    "depreciacoes": "id_depreciacao",
    "fornecedores": "id_fornecedor",
    "garantias": "id_garantia",
    "itens_nota_fiscal": "id_item_nf",
    "manutencoes": "id_manutencao",
    "movimentacoes": "id_movimentacao",
    "notas_fiscais": "id_nota_fiscal",
    "password_resets": "id_reset",
    "patrimonios": "id_patrimonio",
    "roles": "id_role",
    "setores_locais": "id_setor_local",
    "status_manutencao": "id_status_manutencao",
    "status_patrimonio": "id_status_patrimonio",
    "tipos_manutencao": "id_tipo_manutencao",
    "tipos_movimentacao": "id_tipo_movimentacao",
    "usuarios": "id_usuario",
}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_sql(sql: str) -> str:
    return sql


def _maybe_add_returning(sql: str) -> str:
    if re.search(r"\bRETURNING\b", sql, re.IGNORECASE):
        return sql
    match = re.match(r"\s*INSERT\s+INTO\s+\"?(\w+)\"?", sql, re.IGNORECASE)
    if not match:
        return sql
    pk = PRIMARY_KEYS.get(match.group(1))
    if not pk:
        return sql
    return f"{sql} RETURNING {_quote_identifier(pk)}"


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid: Optional[int] = None

    def execute(self, sql: str, params: Optional[tuple[Any, ...]] = None):
        sql = _maybe_add_returning(_normalize_sql(sql))

        self._cursor.execute(sql, params)
        self.lastrowid = None
        if re.match(r"\s*INSERT\s+", sql, re.IGNORECASE) and self._cursor.description:
            row = self._cursor.fetchone()
            if row is not None:
                self.lastrowid = next(iter(row.values())) if isinstance(row, dict) else row[0]
        return None

    def executemany(self, sql: str, seq_of_params):
        sql = _normalize_sql(sql)
        self._cursor.executemany(sql, seq_of_params)
        self.lastrowid = None
        return None

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description


class PostgresConnection:
    def __init__(self, dsn: str):
        self._connection = psycopg2.connect(dsn)

    def cursor(self, dictionary: bool = False):
        factory = RealDictCursor if dictionary else None
        return PostgresCursor(self._connection.cursor(cursor_factory=factory))

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def is_connected(self) -> bool:
        return self._connection.closed == 0
