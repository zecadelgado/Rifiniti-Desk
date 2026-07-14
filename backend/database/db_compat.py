from __future__ import annotations

import os
from typing import Iterable, Set

import bcrypt

from backend.database.config_db import load_env
from backend.database.postgres_driver import DatabaseError


load_env()


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return cursor.fetchone() is not None


def _columns(cursor, table: str) -> Set[str]:
    if not _table_exists(cursor, table):
        return set()
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {row[0] for row in cursor.fetchall()}


def _execute(cursor, sql: str, params=None) -> None:
    try:
        cursor.execute(sql, params)
    except DatabaseError as exc:
        print(f"[Compat DB] Ignorado: {exc} | SQL: {sql}")


def _add_column(cursor, table: str, column: str, definition: str) -> None:
    if column not in _columns(cursor, table):
        _execute(cursor, f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _seed(cursor, table: str, rows: Iterable[tuple[str, str]]) -> None:
    if not _table_exists(cursor, table):
        return
    for codigo, descricao in rows:
        _execute(
            cursor,
            f'INSERT INTO "{table}" (codigo, descricao) VALUES (%s, %s) ON CONFLICT (codigo) DO NOTHING',
            (codigo, descricao),
        )


def _seed_default_admin(cursor) -> None:
    if not _table_exists(cursor, "usuarios"):
        return

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if int(cursor.fetchone()[0] or 0) > 0:
        return

    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not admin_password:
        print("[Compat DB] INITIAL_ADMIN_PASSWORD nao configurado; usuario admin inicial nao sera criado.")
        return

    cols = _columns(cursor, "usuarios")
    password_hash = bcrypt.hashpw(admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    payload = {
        "nome": os.getenv("INITIAL_ADMIN_NAME", "Administrador"),
        "email": os.getenv("INITIAL_ADMIN_EMAIL", "admin@ideau.local"),
        "senha": password_hash,
        "hash_senha": password_hash,
        "nivel_acesso": "master",
        "ativo": 1,
    }
    payload = {key: value for key, value in payload.items() if key in cols}
    if not payload:
        return

    column_names = ", ".join(f'"{key}"' for key in payload.keys())
    placeholders = ", ".join(["%s"] * len(payload))
    cursor.execute(
        f"INSERT INTO usuarios ({column_names}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def ensure_runtime_schema(connection) -> None:
    cursor = connection.cursor()
    try:
        if _table_exists(cursor, "usuarios"):
            _add_column(cursor, "usuarios", "senha", "VARCHAR(255)")
            _add_column(cursor, "usuarios", "hash_senha", "VARCHAR(255)")
            _add_column(cursor, "usuarios", "nivel_acesso", "VARCHAR(20) NOT NULL DEFAULT 'user'")
            _add_column(cursor, "usuarios", "data_criacao", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

        if _table_exists(cursor, "password_resets"):
            _add_column(cursor, "password_resets", "user_id", "BIGINT REFERENCES usuarios(id_usuario)")
            _add_column(cursor, "password_resets", "created_at", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

        if _table_exists(cursor, "fornecedores"):
            _add_column(cursor, "fornecedores", "nome_fornecedor", "VARCHAR(255)")
            _add_column(cursor, "fornecedores", "contato", "VARCHAR(255)")
            _add_column(cursor, "fornecedores", "inscricao_estadual", "VARCHAR(50)")
            _add_column(cursor, "fornecedores", "observacoes", "TEXT")

        if _table_exists(cursor, "categorias"):
            _add_column(cursor, "categorias", "nome_categoria", "VARCHAR(255)")

        if _table_exists(cursor, "setores_locais"):
            _add_column(cursor, "setores_locais", "nome_setor_local", "VARCHAR(255)")
            _add_column(cursor, "setores_locais", "responsavel", "VARCHAR(255)")
            _add_column(cursor, "setores_locais", "capacidade", "INTEGER")
            _add_column(cursor, "setores_locais", "andar", "VARCHAR(50)")

        if _table_exists(cursor, "centro_custo"):
            _add_column(cursor, "centro_custo", "nome_centro", "VARCHAR(255)")
            _add_column(cursor, "centro_custo", "descricao", "TEXT")

        if _table_exists(cursor, "patrimonios"):
            _add_column(cursor, "patrimonios", "quantidade", "INTEGER NOT NULL DEFAULT 1")
            _add_column(cursor, "patrimonios", "numero_nota", "VARCHAR(50)")
            _add_column(cursor, "patrimonios", "data_aquisicao", "DATE")
            _add_column(cursor, "patrimonios", "estado_conservacao", "VARCHAR(20)")
            _add_column(cursor, "patrimonios", "status", "VARCHAR(20) NOT NULL DEFAULT 'ativo'")
            _add_column(cursor, "patrimonios", "data_cadastro", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

        if _table_exists(cursor, "movimentacoes"):
            _add_column(cursor, "movimentacoes", "tipo_movimentacao", "VARCHAR(20)")
            _add_column(cursor, "movimentacoes", "data_movimentacao", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            _add_column(cursor, "movimentacoes", "origem", "VARCHAR(255)")
            _add_column(cursor, "movimentacoes", "destino", "VARCHAR(255)")
            _add_column(cursor, "movimentacoes", "responsavel", "VARCHAR(255)")

        if _table_exists(cursor, "manutencoes"):
            _add_column(cursor, "manutencoes", "tipo_manutencao", "VARCHAR(20)")
            _add_column(cursor, "manutencoes", "status", "VARCHAR(20) NOT NULL DEFAULT 'pendente'")
            _add_column(cursor, "manutencoes", "responsavel", "VARCHAR(255)")
            _add_column(cursor, "manutencoes", "empresa", "VARCHAR(255)")

        if _table_exists(cursor, "anexos"):
            _add_column(cursor, "anexos", "nome_arquivo", "VARCHAR(255)")
            _add_column(cursor, "anexos", "caminho_arquivo", "VARCHAR(255)")
            _add_column(cursor, "anexos", "tipo_arquivo", "VARCHAR(100)")
            _add_column(cursor, "anexos", "tamanho_arquivo", "BIGINT")
            _add_column(cursor, "anexos", "data_upload", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        _seed(cursor, "status_patrimonio", (("ativo", "Ativo"), ("baixado", "Baixado"), ("em_manutencao", "Em manutencao"), ("desaparecido", "Desaparecido")))
        _seed(cursor, "tipos_movimentacao", (("entrada", "Entrada"), ("saida", "Saida"), ("transferencia", "Transferencia"), ("manutencao", "Manutencao"), ("baixa", "Baixa")))
        _seed(cursor, "status_manutencao", (("pendente", "Pendente"), ("em_andamento", "Em andamento"), ("concluida", "Concluida"), ("cancelada", "Cancelada")))
        _seed(cursor, "tipos_manutencao", (("preventiva", "Preventiva"), ("corretiva", "Corretiva"), ("preditiva", "Preditiva")))
        _seed_default_admin(cursor)
        connection.commit()
    except DatabaseError:
        connection.rollback()
        raise
    finally:
        cursor.close()
