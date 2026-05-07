from __future__ import annotations

from typing import Iterable, Optional, Set

import bcrypt
import mysql.connector


def _table_exists(cursor, table: str) -> bool:
    cursor.execute("SHOW TABLES LIKE %s", (table,))
    return cursor.fetchone() is not None


def _columns(cursor, table: str) -> Set[str]:
    if not _table_exists(cursor, table):
        return set()
    cursor.execute(f"SHOW COLUMNS FROM `{table}`")
    return {row[0] for row in cursor.fetchall()}


def _execute(cursor, sql: str) -> None:
    try:
        cursor.execute(sql)
    except mysql.connector.Error as exc:
        print(f"[Compat DB] Ignorado: {exc.msg} | SQL: {sql}")


def _rename_table(cursor, old: str, new: str) -> None:
    if _table_exists(cursor, old) and not _table_exists(cursor, new):
        _execute(cursor, f"RENAME TABLE `{old}` TO `{new}`")


def _rename_column(cursor, table: str, old: str, new: str, definition: str) -> None:
    cols = _columns(cursor, table)
    if old in cols and new not in cols:
        _execute(cursor, f"ALTER TABLE `{table}` CHANGE COLUMN `{old}` `{new}` {definition}")


def _add_column(cursor, table: str, column: str, definition: str) -> None:
    if column not in _columns(cursor, table):
        _execute(cursor, f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")


def _modify_column(cursor, table: str, column: str, definition: str) -> None:
    if column in _columns(cursor, table):
        _execute(cursor, f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {definition}")


def _seed(cursor, table: str, rows: Iterable[tuple[str, str]]) -> None:
    if not _table_exists(cursor, table):
        return
    for codigo, descricao in rows:
        _execute(
            cursor,
            f"INSERT IGNORE INTO `{table}` (`codigo`, `descricao`) "
            f"VALUES ('{codigo}', '{descricao}')",
        )


def _seed_default_admin(cursor) -> None:
    if not _table_exists(cursor, "usuarios"):
        return

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if int(cursor.fetchone()[0] or 0) > 0:
        return

    cols = _columns(cursor, "usuarios")
    password_hash = bcrypt.hashpw("Admin@123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    payload = {
        "nome": "Administrador",
        "email": "admin@ideau.local",
        "senha": password_hash,
        "hash_senha": password_hash,
        "nivel_acesso": "master",
        "ativo": 1,
    }
    payload = {key: value for key, value in payload.items() if key in cols}

    column_names = ", ".join(f"`{key}`" for key in payload.keys())
    placeholders = ", ".join(["%s"] * len(payload))
    cursor.execute(
        f"INSERT INTO usuarios ({column_names}) VALUES ({placeholders})",
        tuple(payload.values()),
    )


def ensure_runtime_schema(connection) -> None:
    """Adjust the normalized data.sql schema to the names used by the app.

    The project still has controllers written for the previous schema. The new
    database/data.sql keeps more normalized lookup tables, so this compatibility
    pass preserves those tables where possible and adds/renames the legacy
    columns needed by the desktop application.
    """

    cursor = connection.cursor()
    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        _rename_table(cursor, "locais", "setores_locais")
        _rename_table(cursor, "centros_custo", "centro_custo")
        _rename_table(cursor, "patrimonio_centro_custo_hist", "patrimonios_centro_custo")
        _rename_table(cursor, "itens_nota", "itens_nota_fiscal")
        _rename_table(cursor, "nota_fiscal_itens", "itens_nota_fiscal")

        _seed(
            cursor,
            "status_patrimonio",
            (
                ("ativo", "Ativo"),
                ("baixado", "Baixado"),
                ("em_manutencao", "Em manutencao"),
                ("desaparecido", "Desaparecido"),
            ),
        )
        _seed(
            cursor,
            "tipos_movimentacao",
            (
                ("entrada", "Entrada"),
                ("saida", "Saida"),
                ("transferencia", "Transferencia"),
                ("manutencao", "Manutencao"),
                ("baixa", "Baixa"),
            ),
        )
        _seed(
            cursor,
            "status_manutencao",
            (
                ("pendente", "Pendente"),
                ("em_andamento", "Em andamento"),
                ("concluida", "Concluida"),
                ("cancelada", "Cancelada"),
            ),
        )
        _seed(
            cursor,
            "tipos_manutencao",
            (
                ("preventiva", "Preventiva"),
                ("corretiva", "Corretiva"),
                ("preditiva", "Preditiva"),
            ),
        )

        if _table_exists(cursor, "usuarios"):
            _modify_column(cursor, "usuarios", "hash_senha", "VARCHAR(255) NULL")
            _add_column(cursor, "usuarios", "senha", "VARCHAR(255) NULL AFTER nome")
            _add_column(
                cursor,
                "usuarios",
                "nivel_acesso",
                "ENUM('master','admin','user') NOT NULL DEFAULT 'user' AFTER senha",
            )
            _add_column(cursor, "usuarios", "data_criacao", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")

        if _table_exists(cursor, "password_resets"):
            _add_column(cursor, "password_resets", "user_id", "BIGINT NULL AFTER id_reset")
            _add_column(cursor, "password_resets", "created_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
            _modify_column(cursor, "password_resets", "id_usuario", "BIGINT NULL")

        _rename_column(cursor, "categorias", "nome", "nome_categoria", "VARCHAR(255) NOT NULL")
        _rename_column(cursor, "fornecedores", "nome", "nome_fornecedor", "VARCHAR(255) NOT NULL")
        _add_column(cursor, "fornecedores", "contato", "VARCHAR(255) NULL AFTER cnpj")
        _add_column(cursor, "fornecedores", "inscricao_estadual", "VARCHAR(50) NULL AFTER cnpj")
        _add_column(cursor, "fornecedores", "observacoes", "TEXT NULL")
        _modify_column(cursor, "fornecedores", "cnpj", "VARCHAR(18) NULL")

        if _table_exists(cursor, "setores_locais"):
            _rename_column(cursor, "setores_locais", "id_local", "id_setor_local", "INT NOT NULL AUTO_INCREMENT")
            _rename_column(cursor, "setores_locais", "nome", "nome_setor_local", "VARCHAR(255) NOT NULL")
            _add_column(cursor, "setores_locais", "responsavel", "VARCHAR(255) NULL")
            _add_column(cursor, "setores_locais", "capacidade", "INT NULL")
            _add_column(cursor, "setores_locais", "andar", "VARCHAR(50) NULL")

        if _table_exists(cursor, "centro_custo"):
            _rename_column(cursor, "centro_custo", "nome", "nome_centro", "VARCHAR(255) NOT NULL")
            _rename_column(cursor, "centro_custo", "notas", "descricao", "TEXT NULL")
            _modify_column(cursor, "centro_custo", "codigo", "VARCHAR(50) NULL")

        if _table_exists(cursor, "patrimonios"):
            _rename_column(cursor, "patrimonios", "id_local_atual", "id_setor_local", "INT NULL")
            _add_column(cursor, "patrimonios", "quantidade", "INT NOT NULL DEFAULT 1 AFTER valor_compra")
            _add_column(cursor, "patrimonios", "numero_nota", "VARCHAR(50) NULL AFTER quantidade")
            _add_column(cursor, "patrimonios", "data_aquisicao", "DATE NULL AFTER numero_nota")
            _add_column(
                cursor,
                "patrimonios",
                "estado_conservacao",
                "ENUM('novo','bom','regular','ruim') NULL AFTER data_aquisicao",
            )
            _add_column(
                cursor,
                "patrimonios",
                "status",
                "ENUM('ativo','baixado','em_manutencao','desaparecido') NOT NULL DEFAULT 'ativo'",
            )
            _add_column(cursor, "patrimonios", "data_cadastro", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")
            _modify_column(cursor, "patrimonios", "id_status_patrimonio", "TINYINT NOT NULL DEFAULT 1")

        if _table_exists(cursor, "movimentacoes"):
            _add_column(
                cursor,
                "movimentacoes",
                "tipo_movimentacao",
                "ENUM('entrada','saida','transferencia','manutencao','baixa') NULL",
            )
            _add_column(cursor, "movimentacoes", "data_movimentacao", "TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP")
            _add_column(cursor, "movimentacoes", "origem", "VARCHAR(255) NULL")
            _add_column(cursor, "movimentacoes", "destino", "VARCHAR(255) NULL")
            _modify_column(cursor, "movimentacoes", "id_tipo_movimentacao", "TINYINT NULL")
            _modify_column(cursor, "movimentacoes", "data_mov", "DATETIME NULL DEFAULT CURRENT_TIMESTAMP")
            _modify_column(cursor, "movimentacoes", "event_uuid", "CHAR(36) NULL")

        if _table_exists(cursor, "manutencoes"):
            _add_column(
                cursor,
                "manutencoes",
                "tipo_manutencao",
                "ENUM('preventiva','corretiva','preditiva') NULL",
            )
            _add_column(
                cursor,
                "manutencoes",
                "status",
                "ENUM('pendente','em_andamento','concluida','cancelada') NOT NULL DEFAULT 'pendente'",
            )
            _add_column(cursor, "manutencoes", "responsavel", "VARCHAR(255) NULL")
            _add_column(cursor, "manutencoes", "empresa", "VARCHAR(255) NULL")
            _modify_column(cursor, "manutencoes", "id_tipo_manutencao", "TINYINT NULL")
            _modify_column(cursor, "manutencoes", "id_status_manutencao", "TINYINT NULL")

        if _table_exists(cursor, "depreciacoes"):
            _add_column(cursor, "depreciacoes", "data_depreciacao", "DATE NULL")
            _add_column(cursor, "depreciacoes", "valor_atual", "DECIMAL(12,2) NULL")
            _add_column(cursor, "depreciacoes", "metodo_depreciacao", "VARCHAR(255) NULL")
            _modify_column(cursor, "depreciacoes", "data_ref", "DATE NULL")

        if _table_exists(cursor, "anexos"):
            _add_column(cursor, "anexos", "nome_arquivo", "VARCHAR(255) NULL")
            _add_column(cursor, "anexos", "caminho_arquivo", "VARCHAR(255) NULL")
            _add_column(cursor, "anexos", "tipo_arquivo", "VARCHAR(100) NULL")
            _add_column(cursor, "anexos", "tamanho_arquivo", "BIGINT NULL")
            _add_column(cursor, "anexos", "data_upload", "TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP")
            _modify_column(cursor, "anexos", "nome", "VARCHAR(255) NULL")
            _modify_column(cursor, "anexos", "caminho", "VARCHAR(255) NULL")

        if _table_exists(cursor, "auditorias"):
            _add_column(cursor, "auditorias", "data_auditoria", "TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP")
            _add_column(cursor, "auditorias", "detalhes", "TEXT NULL")

        if _table_exists(cursor, "notas_fiscais"):
            _add_column(cursor, "notas_fiscais", "caminho_arquivo_nf", "VARCHAR(255) NULL")

        if _table_exists(cursor, "itens_nota_fiscal"):
            _add_column(cursor, "itens_nota_fiscal", "descricao", "VARCHAR(255) NULL")
            _add_column(cursor, "itens_nota_fiscal", "id_patrimonio", "BIGINT NULL")
            _add_column(cursor, "itens_nota_fiscal", "ncm", "VARCHAR(20) NULL")
            _add_column(cursor, "itens_nota_fiscal", "cfop", "VARCHAR(20) NULL")
            _modify_column(cursor, "itens_nota_fiscal", "id_patrimonio", "BIGINT NULL")
            _modify_column(cursor, "itens_nota_fiscal", "descricao", "VARCHAR(255) NULL")

        _execute(
            cursor,
            """
            CREATE TABLE IF NOT EXISTS anexos_manutencoes (
                id_anexo BIGINT NOT NULL AUTO_INCREMENT,
                id_manutencao BIGINT NOT NULL,
                nome_arquivo VARCHAR(255) NULL,
                caminho_arquivo VARCHAR(255) NULL,
                tipo_arquivo VARCHAR(100) NULL,
                tamanho_arquivo BIGINT NULL,
                data_upload TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id_anexo)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        )
        _execute(
            cursor,
            """
            CREATE TABLE IF NOT EXISTS anexos_notas_fiscais (
                id_anexo BIGINT NOT NULL AUTO_INCREMENT,
                id_nota_fiscal BIGINT NOT NULL,
                nome_arquivo VARCHAR(255) NULL,
                caminho_arquivo VARCHAR(255) NULL,
                tipo_arquivo VARCHAR(100) NULL,
                tamanho_arquivo BIGINT NULL,
                data_upload TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id_anexo)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        )

        _seed_default_admin(cursor)

        connection.commit()
    except mysql.connector.Error:
        connection.rollback()
        raise
    finally:
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        except mysql.connector.Error:
            pass
        cursor.close()
