from __future__ import annotations

import json
import mimetypes
import os
import secrets
import smtplib
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from email.message import EmailMessage

import bcrypt

from backend.database.config_db import get_connection
from backend.database.db_compat import ensure_runtime_schema
from backend.database.postgres_driver import DatabaseError, ForeignKeyViolation, UndefinedTable, UniqueViolation
from backend.services.cache_manager import CacheManager
from backend.utils.validators import validar_senha


class DatabaseManager:
    """Encapsula as interações com o banco de dados."""

    VALID_ROLES: Tuple[str, ...] = ("master", "admin", "user")

    _ANEXO_CONFIG: Dict[str, Dict[str, Any]] = {
        "patrimonio": {
            "table": "anexos",
            "pk": "id_anexo",
            "columns": {
                "entidade_id": "id_patrimonio",
                "nome_arquivo": "nome_arquivo",
                "caminho_arquivo": "caminho_arquivo",
                "tipo_arquivo": "tipo_arquivo",
                "tamanho_arquivo": "tamanho_arquivo",
                "data_upload": "data_upload",
            },
            "joins": [
                "INNER JOIN patrimonios p ON p.id_patrimonio = a.id_patrimonio",
            ],
            "extra_select": [
                "p.nome AS nome_entidade",
            ],
            "order_by": "a.data_upload DESC",
        },
        "manutencao": {
            "table": "anexos_manutencoes",
            "pk": "id_anexo",
            "columns": {
                "entidade_id": "id_manutencao",
                "nome_arquivo": "nome_arquivo",
                "caminho_arquivo": "caminho_arquivo",
                "tipo_arquivo": "tipo_arquivo",
                "tamanho_arquivo": "tamanho_arquivo",
                "data_upload": "data_upload",
            },
            "joins": [
                "INNER JOIN manutencoes m ON m.id_manutencao = a.id_manutencao",
            ],
            "extra_select": [
                "m.descricao AS nome_entidade",
            ],
            "order_by": "a.data_upload DESC",
        },
        "nota_fiscal": {
            "table": "anexos_notas_fiscais",
            "pk": "id_anexo",
            "columns": {
                "entidade_id": "id_nota_fiscal",
                "nome_arquivo": "nome_arquivo",
                "caminho_arquivo": "caminho_arquivo",
                "tipo_arquivo": "tipo_arquivo",
                "tamanho_arquivo": "tamanho_arquivo",
                "data_upload": "data_upload",
            },
            "joins": [
                "INNER JOIN notas_fiscais nf ON nf.id_nota_fiscal = a.id_nota_fiscal",
            ],
            "extra_select": [
                "nf.numero_nota AS nome_entidade",
            ],
            "order_by": "a.data_upload DESC",
        },
    }

    def __init__(self):
        self.connection = None
        self.cache = CacheManager()
        self._manutencao_columns: Optional[Set[str]] = None
        self._manutencao_schema_checked: bool = False
        self._password_reset_table_checked: bool = False

    def connect(self):
        try:
            self.connection = get_connection()
            ensure_runtime_schema(self.connection)
            print("Conexao com o banco de dados estabelecida com sucesso!")
            self._document_manutencao_migration_dependency()
            return True
        except DatabaseError as err:
            print(f"Erro ao conectar ao banco de dados: {err}")
            return False

    def disconnect(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("Conexao com o banco de dados encerrada.")

    def _ensure_connection(self):
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                raise DatabaseError("Nao foi possivel conectar ao banco de dados.")

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        if not self.connection or not self.connection.is_connected():
            if not self.connect():
                return None
        cursor = self.connection.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            if query.strip().upper().startswith("SELECT"):
                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                else:
                    result = None
                return result
            else:
                self.connection.commit()
                return cursor.rowcount
        except DatabaseError as err:
            print(f"Erro ao executar a query: {err}")
            self.connection.rollback()
            return None
        finally:
            cursor.close()

    def fetch_all(self, query, params=None) -> List[dict]:
        result = self.execute_query(query, params, fetch_all=True)
        return result if result is not None else []

    def fetch_one(self, query, params=None) -> Optional[dict]:
        return self.execute_query(query, params, fetch_one=True)

    def get_user_by_email(self, email):
        query = "SELECT * FROM usuarios WHERE email = %s"
        return self.execute_query(query, (email,), fetch_one=True)

    def verify_password(self, email, password):
        """Verifica a senha do usuário, suportando tanto hash bcrypt quanto senhas antigas em texto puro."""
        user = self.get_user_by_email(email)
        if not user:
            return None
        
        # Verificar se o usuário está ativo (se a coluna existir)
        if 'ativo' in user and not user['ativo']:
            return None  # Usuário inativo
        
        senha_armazenada = user.get("senha") or user.get("hash_senha")
        
        # Verificar se é um hash bcrypt (começa com $2b$ ou $2a$ ou $2y$)
        if senha_armazenada and senha_armazenada.startswith(('$2b$', '$2a$', '$2y$')):
            # É um hash bcrypt, verificar corretamente
            try:
                if bcrypt.checkpw(password.encode('utf-8'), senha_armazenada.encode('utf-8')):
                    return user
            except Exception as e:
                print(f"[Erro] Falha ao verificar hash bcrypt: {e}")
                return None
        else:
            # Senha antiga em texto puro (compatibilidade temporária)
            if senha_armazenada == password:
                # Autenticação bem-sucedida, mas devemos atualizar para hash
                # Vamos fazer a migração automática aqui
                try:
                    novo_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    self.update_user(user['id_usuario'], {'senha': novo_hash})
                    print(f"[Info] Senha do usuário {email} migrada para hash bcrypt.")
                except Exception as e:
                    print(f"[Aviso] Não foi possível migrar senha para hash: {e}")
                return user
        
        return None

    def get_table_columns(self, table: str) -> List[str]:
        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _document_manutencao_migration_dependency(self):
        if self._manutencao_schema_checked:
            return
        self._manutencao_schema_checked = True
        try:
            columns = set(self.get_table_columns("manutencoes"))
            missing = [col for col in ("tipo_manutencao", "empresa") if col not in columns]
            if missing:
                print(
                    "[Aviso] Estrutura de manutencoes incompleta: "
                    f"faltam as colunas {', '.join(missing)}. "
                    "Execute a migração database/migrations_manutencao.sql para habilitar todos os recursos."
                )
            self._manutencao_columns = columns
        except DatabaseError as err:
            print(
                "[Aviso] Não foi possível validar a estrutura da tabela manutencoes. "
                "Certifique-se de aplicar database/migrations_manutencao.sql. Erro: "
                f"{err}"
            )
            self._manutencao_columns = None

    def _get_manutencao_columns(self) -> Set[str]:
        if self._manutencao_columns is None:
            try:
                self._manutencao_columns = set(self.get_table_columns("manutencoes"))
            except DatabaseError:
                # Em caso de falha na leitura do schema, assumir o conjunto completo para não bloquear a UI
                self._manutencao_columns = {
                    "id_patrimonio",
                    "data_inicio",
                    "data_fim",
                    "descricao",
                    "custo",
                    "responsavel",
                    "status",
                    "tipo_manutencao",
                    "empresa",
                }
        return self._manutencao_columns

    def manutencao_has_extended_columns(self) -> bool:
        """Retorna se o schema de manutenção possui todas as colunas esperadas.

        A verificação reutiliza o cache de :meth:`_get_manutencao_columns` para
        evitar consultas redundantes e serve para habilitar/desabilitar recursos
        que dependem das colunas novas.
        """

        columns = self._get_manutencao_columns()
        required = {"tipo_manutencao", "empresa"}
        return required.issubset(columns)

    def create_user(self, nome, email, password, nivel_acesso: str = "user", ativo: Optional[bool] = None):
        if self.get_user_by_email(email):
            return None

        # Gerar hash da senha usando bcrypt
        senha_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        role = self._normalize_role(nivel_acesso)
        columns = ["nome", "email", "senha", "nivel_acesso"]
        values: List[Any] = [nome, email, senha_hash, role]

        try:
            available = set(self.get_table_columns("usuarios"))
        except DatabaseError:
            available = {"nome", "email", "senha", "nivel_acesso"}

        if "ativo" in available and ativo is not None:
            columns.append("ativo")
            values.append(1 if ativo else 0)

        insert_sql = f"INSERT INTO usuarios ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
        rows = self.execute_query(insert_sql, tuple(values))
        if not rows:
            return None
        return self.get_user_by_email(email)

    def update_user(self, user_id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False

        allowed: Sequence[str]
        try:
            allowed = self.get_table_columns("usuarios")
        except DatabaseError:
            allowed = ("nome", "email", "senha", "nivel_acesso", "ativo")

        updates: List[str] = []
        params: List[Any] = []
        for key, value in data.items():
            if key not in allowed or key == "id_usuario":
                continue
            if key == "nivel_acesso":
                role = self._normalize_role(str(value))
                updates.append('"nivel_acesso" = %s')
                params.append(role)
                continue
            updates.append(f'"{key}" = %s')
            params.append(value)

        if not updates:
            return False

        params.append(user_id)
        sql = f"UPDATE usuarios SET {', '.join(updates)} WHERE id_usuario = %s"
        rows = self.execute_query(sql, tuple(params))
        return bool(rows)

    def _normalize_role(self, nivel_acesso: Optional[str]) -> str:
        if not nivel_acesso:
            return "user"
        role = str(nivel_acesso).strip().lower()
        if role not in self.VALID_ROLES:
            return "user"
        return role

    @staticmethod
    def has_master_privileges(user: Optional[Dict[str, Any]]) -> bool:
        return bool(user and str(user.get("nivel_acesso", "")).lower() == "master")

    @staticmethod
    def has_admin_privileges(user: Optional[Dict[str, Any]]) -> bool:
        role = str(user.get("nivel_acesso", "")).lower() if user else ""
        return role in {"admin", "master"}

    def delete_user(self, user_id: int) -> bool:
        sql = "DELETE FROM usuarios WHERE id_usuario = %s"
        rows = self.execute_query(sql, (user_id,))
        return bool(rows)

    def set_user_active(self, user_id: int, active: bool) -> bool:
        try:
            columns = self.get_table_columns("usuarios")
        except DatabaseError:
            columns = []
        if "ativo" not in columns:
            return False
        sql = "UPDATE usuarios SET ativo = %s WHERE id_usuario = %s"
        rows = self.execute_query(sql, (1 if active else 0, user_id))
        return bool(rows)

    def _ensure_password_reset_table(self) -> None:
        if self._password_reset_table_checked:
            return
        create_sql = """
        CREATE TABLE IF NOT EXISTS password_resets (
            id_reset BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES usuarios(id_usuario),
            token_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ativo SMALLINT NOT NULL DEFAULT 1
        )
        """
        self.execute_query(create_sql)
        self._password_reset_table_checked = True

    def _deactivate_password_reset_tokens(self, user_id: int) -> None:
        self._ensure_password_reset_table()
        self.execute_query(
            "UPDATE password_resets SET ativo = 0 WHERE user_id = %s AND ativo = 1",
            (user_id,),
        )

    def _mark_reset_token_used(self, token_id: int) -> None:
        self._ensure_password_reset_table()
        self.execute_query(
            "UPDATE password_resets SET used_at = %s, ativo = 0 WHERE id_reset = %s",
            (datetime.utcnow(), token_id),
        )

    def _send_password_reset_email(
        self,
        recipient: str,
        token: str,
        expires_at: datetime,
        user_name: str = "",
        expiration_minutes: int = 30,
    ) -> Tuple[bool, str]:
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        if smtp_password:
            smtp_password = smtp_password.replace(" ", "")
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        try:
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
        except (TypeError, ValueError):
            smtp_port = 587

        if not smtp_user or not smtp_password:
            return False, "Configuracao de e-mail ausente."

        subject = "Recuperacao de senha - NeoBenesys"
        expires_info = expires_at.strftime("%d/%m/%Y %H:%M UTC")
        saudacao = f"Ola, {user_name}!" if user_name else "Ola!"
        body = (
            f"{saudacao}\n\n"
            "Recebemos um pedido para redefinir a sua senha.\n"
            f"Use o token abaixo para continuar (expira em {expiration_minutes} minutos, ate {expires_info}):\n\n"
            f"{token}\n\n"
            "Caso nao tenha solicitado, ignore este e-mail."
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = smtp_user
        message["To"] = recipient
        message.set_content(body)

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(message)
            return True, ""
        except Exception as exc:
            print(f"[Erro] Falha ao enviar e-mail de recuperacao: {exc}")
            return False, "Nao foi possivel enviar o e-mail de recuperacao. Tente novamente em instantes."


    def create_password_reset_token(
        self, email: str, expiration_minutes: int = 30
    ) -> Tuple[bool, str]:
        self._ensure_password_reset_table()
        user = self.get_user_by_email(email)
        if not user:
            return False, "Usuario nao encontrado ou inativo."

        if "ativo" in user and not user.get("ativo"):
            return False, "Usuario nao encontrado ou inativo."

        try:
            user_id = int(user.get("id_usuario"))
        except (TypeError, ValueError):
            return False, "Usuario invalido."

        self._deactivate_password_reset_tokens(user_id)

        token = secrets.token_urlsafe(20)
        token_hash = bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        expires_at = datetime.utcnow() + timedelta(minutes=expiration_minutes)

        inserted = self.execute_query(
            "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (user_id, token_hash, expires_at),
        )

        if not inserted:
            return False, "Nao foi possivel gerar um token de recuperacao."

        enviado, msg_erro_email = self._send_password_reset_email(
            recipient=email,
            token=token,
            expires_at=expires_at,
            user_name=user.get("nome") or "",
            expiration_minutes=expiration_minutes,
        )
        if not enviado:
            self._deactivate_password_reset_tokens(user_id)
            return False, msg_erro_email

        return True, "Enviamos um e-mail com o token para redefinir a senha. Verifique a caixa de entrada e o spam."

    def _match_reset_token(self, token: str) -> Tuple[Optional[dict], Optional[str]]:
        self._ensure_password_reset_table()
        now = datetime.utcnow()
        self.execute_query(
            "UPDATE password_resets SET ativo = 0 WHERE expires_at < %s OR used_at IS NOT NULL",
            (now,),
        )
        tokens = self.fetch_all(
            "SELECT * FROM password_resets WHERE ativo = 1 ORDER BY created_at DESC"
        )

        for row in tokens:
            stored_hash = row.get("token_hash")
            if not stored_hash:
                continue
            try:
                if not bcrypt.checkpw(token.encode("utf-8"), stored_hash.encode("utf-8")):
                    continue
            except Exception:
                continue

            if row.get("used_at"):
                return None, "Token já utilizado. Solicite um novo código."

            expires_at = row.get("expires_at")
            if expires_at and expires_at < now:
                self.execute_query(
                    "UPDATE password_resets SET ativo = 0 WHERE id_reset = %s",
                    (row.get("id_reset"),),
                )
                return None, "Token expirado. Solicite um novo código."

            return row, None

        return None, "Token inválido."

    def reset_password_with_token(self, token: str, new_password: str) -> Tuple[bool, str]:
        valido, mensagem = validar_senha(new_password)
        if not valido:
            return False, mensagem

        token_row, token_error = self._match_reset_token(token)
        if not token_row:
            return False, token_error or "Token inválido."

        user_id = token_row.get("user_id")
        if not user_id:
            return False, "Token não está vinculado a um usuário válido."

        senha_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        updated = self.update_user(user_id, {"senha": senha_hash})
        if not updated:
            return False, "Não foi possível atualizar a senha."

        token_id = token_row.get("id_reset")
        if token_id:
            self._mark_reset_token_used(token_id)

        # Invalida eventuais outros tokens ativos do usuário
        self._deactivate_password_reset_tokens(user_id)

        return True, "Senha redefinida com sucesso."

    def ensure_patrimonio_optional_columns(self) -> None:
        try:
            columns = set(self.get_table_columns("patrimonios"))
        except DatabaseError as exc:
            print(f"[DatabaseManager] Nao foi possivel inspecionar a tabela patrimonios: {exc}")
            return

        alter_statements: List[str] = []
        if "numero_patrimonio" not in columns:
            alter_statements.append(
                "ADD COLUMN numero_patrimonio BIGINT UNSIGNED NULL UNIQUE AFTER id_patrimonio"
            )
        if "quantidade" not in columns:
            alter_statements.append(
                "ADD COLUMN quantidade INT NOT NULL DEFAULT 1 AFTER valor_compra"
            )
        if "numero_nota" not in columns:
            after_clause = "AFTER quantidade" if "quantidade" in columns or alter_statements else "AFTER valor_compra"
            alter_statements.append(
                f"ADD COLUMN numero_nota VARCHAR(50) NULL {after_clause}"
            )
        if "valor_atual" not in columns:
            alter_statements.append(
                "ADD COLUMN valor_atual DECIMAL(10,2) NULL AFTER valor_compra"
            )

        if not alter_statements:
            return

        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            for stmt in alter_statements:
                cursor.execute(f"ALTER TABLE patrimonios {stmt}")
            self.connection.commit()
            print("[DatabaseManager] Colunas opcionais de patrimonios garantidas com sucesso.")
        except DatabaseError as err:
            self.connection.rollback()
            print(f"[DatabaseManager] Falha ao ajustar colunas opcionais de patrimonios: {err}")
        finally:
            cursor.close()

    def _get_next_patrimonio_numbers(self, cursor, quantidade: int) -> List[int]:
        if quantidade <= 0:
            return []
        cursor.execute("SELECT COALESCE(MAX(numero_patrimonio), 0) FROM patrimonios FOR UPDATE")
        row = cursor.fetchone()
        last = row[0] if row else 0
        try:
            last_int = int(last or 0)
        except (TypeError, ValueError):
            last_int = 0
        # Garanta que a sequência mínima comece em 1200
        base = 1199 if last_int < 1199 else last_int
        return [base + i for i in range(1, quantidade + 1)]

    def create_patrimonio(self, data: Dict[str, Any]) -> int:
        if not data:
            raise ValueError("Dados do patrimonio nao informados.")

        try:
            available_columns = set(self.get_table_columns("patrimonios"))
        except DatabaseError:
            available_columns = {
                "id_patrimonio",
                "nome",
                "descricao",
                "numero_serie",
                "valor_compra",
                "data_aquisicao",
                "estado_conservacao",
                "id_categoria",
                "id_fornecedor",
                "id_setor_local",
                "status",
                "quantidade",
                "numero_nota",
                "valor_atual",
            }

        required_fields = ("nome", "id_categoria", "id_setor_local", "status")
        missing = [field for field in required_fields if not data.get(field)]
        if missing:
            raise ValueError(f"Campos obrigatorios ausentes: {', '.join(missing)}")

        ordered_fields: Sequence[str] = (
            "nome",
            "descricao",
            "numero_serie",
            "valor_compra",
            "data_aquisicao",
            "estado_conservacao",
            "id_categoria",
            "id_fornecedor",
            "id_setor_local",
            "status",
            "quantidade",
            "numero_nota",
            "valor_atual",
        )

        numero_patrimonio_available = "numero_patrimonio" in available_columns
        numero_patrimonio_value = data.get("numero_patrimonio") if numero_patrimonio_available else None
        auto_generate_numero = numero_patrimonio_available and not numero_patrimonio_value

        columns: List[str] = []
        values: List[Any] = []
        for field in ordered_fields:
            if field not in available_columns:
                continue
            if field == "quantidade":
                value = data.get("quantidade", 1)
                if value in (None, ""):
                    value = 1
            elif field == "numero_nota":
                value = data.get("numero_nota") or None
            elif field == "valor_atual":
                bruto = data.get("valor_atual")
                if bruto in (None, ""):
                    bruto = data.get("valor_compra")
                value = bruto
            else:
                value = data.get(field)
            columns.append(field)
            values.append(value)

        if not columns:
            raise ValueError("Nenhuma coluna valida para inserir patrimonio.")

        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            if hasattr(self.connection, "start_transaction") and not getattr(self.connection, "in_transaction", False):
                self.connection.start_transaction()
            if numero_patrimonio_available:
                if auto_generate_numero:
                    seq_values = self._get_next_patrimonio_numbers(cursor, 1)
                    numero_patrimonio_value = seq_values[0] if seq_values else None
                columns.append("numero_patrimonio")
                values.append(numero_patrimonio_value)

            placeholders = ", ".join(["%s"] * len(columns))
            columns_clause = ", ".join(f'"{col}"' for col in columns)

            cursor.execute(
                f"INSERT INTO patrimonios ({columns_clause}) VALUES ({placeholders})",
                tuple(values),
            )
            self.connection.commit()
            return cursor.lastrowid
        except DatabaseError as err:
            self.connection.rollback()
            raise err
        finally:
            cursor.close()

    def create_patrimonios_bulk(
        self,
        data: Dict[str, Any],
        quantidade: int,
        numero_series: Optional[Sequence[str]] = None,
        enforce_unique_serial: bool = False
    ) -> List[int]:
        if not data:
            raise ValueError("Dados do patrimonio nao informados.")
        try:
            qtd = int(quantidade)
        except Exception:
            raise ValueError("Quantidade invalida.")
        if qtd <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")

        # Descobrir colunas disponíveis uma vez
        try:
            available_columns = set(self.get_table_columns("patrimonios"))
        except DatabaseError:
            available_columns = {
                "nome",
                "descricao",
                "numero_serie",
                "valor_compra",
                "data_aquisicao",
                "estado_conservacao",
                "id_categoria",
                "id_fornecedor",
                "id_setor_local",
                "status",
                "quantidade",
                "numero_nota",
                "valor_atual",
            }

        # Base estável de colunas: somente o que foi passado em `data` e existe na tabela
        base_columns = [
            k
            for k in data.keys()
            if k in available_columns and k not in ("id_patrimonio", "quantidade")
        ]
        include_numero_patrimonio = "numero_patrimonio" in available_columns
        if include_numero_patrimonio and "numero_patrimonio" not in base_columns:
            base_columns.append("numero_patrimonio")
        # Se a tabela tiver 'quantidade', vamos inserir 1 para cada linha
        include_quantidade = ("quantidade" in available_columns)
        if include_quantidade:
            columns_for_insert = base_columns + ["quantidade"]
        else:
            columns_for_insert = base_columns

        if not columns_for_insert:
            raise ValueError("Nenhuma coluna valida para inserir patrimonio.")

        placeholders = ", ".join(["%s"] * len(columns_for_insert))
        columns_clause = ", ".join(f'"{c}"' for c in columns_for_insert)

        self._ensure_connection()
        cursor = self.connection.cursor()
        inserted_ids: List[int] = []
        try:
            # Transação única
            if hasattr(self.connection, "start_transaction") and not getattr(self.connection, "in_transaction", False):
                self.connection.start_transaction()
            seq_numbers: List[int] = []
            if include_numero_patrimonio:
                seq_numbers = self._get_next_patrimonio_numbers(cursor, qtd)

            for idx in range(qtd):
                row = dict(data)  # cópia

                # Numero de série por-item (lista fornecida)
                if numero_series and len(numero_series) == qtd:
                    row["numero_serie"] = numero_series[idx]
                # Geração opcional de série única com sufixo
                elif enforce_unique_serial:
                    base_value = row.get("numero_serie")
                    if base_value is not None:
                        base = str(base_value).strip()
                        if base:
                            row["numero_serie"] = f"{base}-{idx+1:03d}"
                        else:
                            row["numero_serie"] = None

                if include_numero_patrimonio:
                    row["numero_patrimonio"] = seq_numbers[idx]

                if include_quantidade:
                    row["quantidade"] = 1

                values = [row.get(col) for col in base_columns]
                if include_quantidade:
                    values.append(1)

                cursor.execute(
                    f"INSERT INTO patrimonios ({columns_clause}) VALUES ({placeholders})",
                    tuple(values)
                )
                inserted_ids.append(cursor.lastrowid)

            self.connection.commit()
            return inserted_ids
        except DatabaseError as err:
            self.connection.rollback()
            raise err
        finally:
            cursor.close()

    def list_centros_custo_por_patrimonio(self, patrimonio_id: int) -> List[Dict[str, Any]]:
        try:
            centro_cols = set(self.get_table_columns("centro_custo"))
        except DatabaseError:
            centro_cols = set()
        has_ativo = "ativo" in centro_cols

        select_fields = ["pcc.id_centro_custo", "cc.nome_centro"]
        if has_ativo:
            select_fields.append("cc.ativo")

        query = f"""
            SELECT {', '.join(select_fields)}
            FROM patrimonios_centro_custo pcc
            INNER JOIN centro_custo cc ON cc.id_centro_custo = pcc.id_centro_custo
            WHERE pcc.id_patrimonio = %s
            ORDER BY cc.nome_centro
        """
        try:
            return self.fetch_all(query, (patrimonio_id,))
        except UndefinedTable:
            return []
        except DatabaseError:
            raise

    def set_patrimonio_centros_custo(self, patrimonio_id: int, centros_ids: Sequence[int]) -> None:
        normalized_ids: List[int] = []
        for cid in centros_ids:
            try:
                parsed = int(cid)
            except (TypeError, ValueError):
                continue
            if parsed <= 0:
                continue
            if parsed not in normalized_ids:
                normalized_ids.append(parsed)

        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM patrimonios_centro_custo WHERE id_patrimonio = %s",
                (patrimonio_id,),
            )
            if normalized_ids:
                values = [(patrimonio_id, cid) for cid in normalized_ids]
                cursor.executemany(
                    "INSERT INTO patrimonios_centro_custo (id_patrimonio, id_centro_custo) VALUES (%s, %s)",
                    values,
                )
            self.connection.commit()
        except UndefinedTable:
            self.connection.rollback()
            return
        except DatabaseError as err:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def get_patrimonio_codigos(self, ids: Sequence[int]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        placeholders = ", ".join(["%s"] * len(ids))
        query = f"""
            SELECT id_patrimonio, numero_patrimonio
            FROM patrimonios
            WHERE id_patrimonio IN ({placeholders})
            ORDER BY numero_patrimonio ASC
        """
        return self.fetch_all(query, tuple(ids))

    def update_patrimonio(self, patrimonio_id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False

        try:
            allowed = set(self.get_table_columns("patrimonios"))
        except DatabaseError:
            allowed = {
                "nome",
                "descricao",
                "numero_serie",
                "valor_compra",
                "data_aquisicao",
                "estado_conservacao",
                "id_categoria",
                "id_fornecedor",
                "id_setor_local",
                "status",
                "quantidade",
                "numero_nota",
                "valor_atual",
            }

        assignments: List[str] = []
        params: List[Any] = []
        for key, value in data.items():
            if key not in allowed or key == "id_patrimonio":
                continue
            assignments.append(f'"{key}" = %s')
            params.append(value if key != "numero_nota" else (value or None))

        if not assignments:
            return False

        params.append(patrimonio_id)
        sql = f"UPDATE patrimonios SET {', '.join(assignments)} WHERE id_patrimonio = %s"
        rows = self.execute_query(sql, tuple(params))
        return bool(rows)

    def get_patrimonio_dependencies(self, patrimonio_id: int) -> Dict[str, int]:
        """Retorna um mapa de vínculos ativos do patrimônio com contagem por entidade."""
        self._ensure_connection()
        cursor = self.connection.cursor(dictionary=True)
        relationships = {
            "patrimonios_centro_custo": ("id_patrimonio", "centros de custo"),
            "movimentacoes": ("id_patrimonio", "movimentações"),
            "manutencoes": ("id_patrimonio", "manutenções"),
            "depreciacoes": ("id_patrimonio", "depreciações"),
            "anexos": ("id_patrimonio", "anexos"),
            "itens_nota_fiscal": ("id_patrimonio", "itens de nota fiscal"),
            "garantias": ("id_patrimonio", "garantias"),
            "baixas": ("id_patrimonio", "baixas"),
        }

        dependencies: Dict[str, int] = {}
        try:
            for table, (column, label) in relationships.items():
                try:
                    cursor.execute(
                        f"SELECT COUNT(*) AS total FROM {table} WHERE {column} = %s",
                        (patrimonio_id,),
                    )
                    result = cursor.fetchone() or {}
                    total = int(result.get("total", 0))
                    if total > 0:
                        dependencies[label] = total
                except UndefinedTable:
                    continue
                except DatabaseError:
                    raise
        finally:
            cursor.close()

        return dependencies

    def delete_patrimonio(self, patrimonio_id: int) -> bool:
        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            dependencies = self.get_patrimonio_dependencies(patrimonio_id)
            if dependencies:
                details = ", ".join(f"{label} ({count})" for label, count in dependencies.items())
                raise ValueError(
                    "Nao e possivel excluir o patrimonio porque existem registros relacionados: "
                    + details
                )
            query = "DELETE FROM patrimonios WHERE id_patrimonio = %s"
            cursor.execute(query, (patrimonio_id,))
            self.connection.commit()
            return cursor.rowcount > 0
        except ForeignKeyViolation as err:
            self.connection.rollback()
            raise ValueError("Nao e possivel excluir o patrimonio porque existem registros relacionados.") from err
        except DatabaseError as err:
            self.connection.rollback()
            raise err
        finally:
            cursor.close()

    def delete_patrimonio_force(self, patrimonio_id: int) -> bool:
        """Remove patrimonio e dependencias forçadas (uso exclusivo de master)."""
        dependents = (
            "movimentacoes",
            "depreciacoes",
            "anexos",
            "itens_nota_fiscal",
            "garantias",
            "baixas",
            "patrimonios_centro_custo",
            "manutencoes",
        )
        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            for table in dependents:
                cursor.execute(f"DELETE FROM {table} WHERE id_patrimonio = %s", (patrimonio_id,))
            cursor.execute("DELETE FROM patrimonios WHERE id_patrimonio = %s", (patrimonio_id,))
            self.connection.commit()
            return cursor.rowcount > 0
        except DatabaseError:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

                                                                             
    @staticmethod
    def _normalize_user_active(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return value != 0
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode().strip()
            except Exception:
                return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            lowered = text.lower()
            truthy = {"1", "true", "t", "sim", "s", "yes", "y", "ativo", "active"}
            falsy = {"0", "false", "f", "nao", "não", "n", "inativo", "inactive"}
            if lowered in truthy:
                return True
            if lowered in falsy:
                return False
            try:
                numeric = Decimal(text)
            except (ArithmeticError, ValueError):
                return None
            return numeric != 0
        return bool(value)

    def list_users(self, search=None):
        try:
            columns = set(self.get_table_columns("usuarios"))
        except DatabaseError:
            columns = set()

        select_fields = [
            "id_usuario",
            "nome",
            "email",
            "nivel_acesso",
        ]
        if "ativo" in columns:
            select_fields.append("ativo")
        else:
            select_fields.append("NULL AS ativo")

        base_query = f"""
            SELECT
                {', '.join(select_fields)}
            FROM usuarios
        """
        params = None
        if search:
            base_query += " WHERE nome LIKE %s OR email LIKE %s"
            like_term = f"%{search}%"
            params = (like_term, like_term)
        base_query += " ORDER BY nome"

        rows = self.fetch_all(base_query, params)
        for row in rows:
            row["ativo"] = self._normalize_user_active(row.get("ativo"))
        return rows

    def list_categorias(self):
        # Tentar obter do cache
        cache_key = 'categorias:list_all'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Buscar do banco e cachear
        query = """
            SELECT id_categoria, nome_categoria, descricao
            FROM categorias
            ORDER BY nome_categoria
        """
        result = self.fetch_all(query)
        self.cache.set(cache_key, result, timeout_seconds=600)  # 10 minutos
        return result

    def ensure_categorias(self, nomes: Sequence[str]) -> Dict[str, int]:
        if not nomes:
            return {}

        placeholders = ", ".join(["%s"] * len(nomes))
        existing_rows = self.fetch_all(
            f"SELECT id_categoria, nome_categoria FROM categorias WHERE nome_categoria IN ({placeholders})",
            tuple(nomes),
        )

        mapping: Dict[str, int] = {}
        if existing_rows:
            for row in existing_rows:
                nome = row.get("nome_categoria")
                categoria_id = row.get("id_categoria")
                if nome and categoria_id is not None:
                    try:
                        mapping[nome] = int(categoria_id)
                    except (TypeError, ValueError):
                        continue

        for nome in nomes:
            if nome in mapping:
                continue

            self._ensure_connection()
            cursor = self.connection.cursor()
            try:
                cursor.execute(
                    "INSERT INTO categorias (nome_categoria, descricao) VALUES (%s, %s)",
                    (nome, f"Categoria fixa {nome.lower()}"),
                )
                self.connection.commit()
                mapping[nome] = int(cursor.lastrowid)
            except DatabaseError as err:
                self.connection.rollback()
                if isinstance(err, UniqueViolation):
                    row = self.fetch_one(
                        "SELECT id_categoria FROM categorias WHERE nome_categoria = %s",
                        (nome,),
                    )
                    if row and row.get("id_categoria") is not None:
                        try:
                            mapping[nome] = int(row["id_categoria"])
                        except (TypeError, ValueError):
                            pass
                else:
                    raise
            finally:
                cursor.close()

        return mapping

    def list_fornecedores(self, search=None):
        # Se tem busca, não usar cache
        if search:
            query = """
                SELECT
                    id_fornecedor,
                    nome_fornecedor,
                    cnpj,
                    contato,
                    telefone,
                    email
                FROM fornecedores
                WHERE nome_fornecedor LIKE %s OR cnpj LIKE %s
                ORDER BY nome_fornecedor
            """
            like = f"%{search}%"
            return self.fetch_all(query, (like, like))
        
        # Tentar obter do cache
        cache_key = 'fornecedores:list_all'
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Buscar do banco e cachear
        query = """
            SELECT
                id_fornecedor,
                nome_fornecedor,
                cnpj,
                contato,
                telefone,
                email
            FROM fornecedores
            ORDER BY nome_fornecedor
        """
        result = self.fetch_all(query, None)
        self.cache.set(cache_key, result, timeout_seconds=300)  # 5 minutos
        return result

    def list_centros_custo(self, search=None, include_inativos: bool = False):
        try:
            columns = set(self.get_table_columns("centro_custo"))
        except DatabaseError:
            columns = set()
        has_ativo = "ativo" in columns

        where_parts: List[str] = []
        params: List[Any] = []
        if search:
            where_parts.append("nome_centro LIKE %s")
            params.append(f"%{search}%")
        if has_ativo and not include_inativos:
            where_parts.append("ativo = 1")

        where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        select_fields = ["id_centro_custo", "nome_centro", "descricao"]
        if has_ativo:
            select_fields.append("ativo")

        query = f"""
            SELECT {', '.join(select_fields)}
            FROM centro_custo{where_clause}
            ORDER BY nome_centro
        """

        return self.fetch_all(query, tuple(params) if params else None)

    def _get_setores_locais_columns(self) -> Set[str]:
        try:
            return set(self.get_table_columns("setores_locais"))
        except DatabaseError:
            return {
                "id_setor_local",
                "nome_setor_local",
                "localizacao",
                "descricao",
                "responsavel",
                "capacidade",
                "andar",
            }

    def list_setores_locais(self, search=None):
        cols = self._get_setores_locais_columns()
        campos = ", ".join(
            col
            for col in (
                "id_setor_local",
                "nome_setor_local",
                "localizacao",
                "descricao",
                "responsavel",
                "capacidade",
                "andar",
            )
            if col in cols
        )

        # Se tem busca, não usar cache
        if search:
            query = f"""
                SELECT {campos}
                FROM setores_locais
                WHERE nome_setor_local LIKE %s
                ORDER BY nome_setor_local
            """
            return self.fetch_all(query, (f"%{search}%",))
        
        # Tentar obter do cache
        cache_key = "setores_locais:list_all"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Buscar do banco e cachear
        query = f"""
            SELECT {campos}
            FROM setores_locais
            ORDER BY nome_setor_local
        """
        result = self.fetch_all(query, None)
        self.cache.set(cache_key, result, timeout_seconds=600)  # 10 minutos
        return result

    def create_setor_local(self, data: Dict[str, Any]) -> int:
        if not data:
            raise ValueError("Dados de setor/local não informados.")
        try:
            allowed = set(self.get_table_columns("setores_locais"))
        except DatabaseError:
            allowed = {
                "nome_setor_local",
                "localizacao",
                "descricao",
                "responsavel",
                "capacidade",
                "andar",
            }
        payload = {k: v for k, v in data.items() if k in allowed and k != "id_setor_local"}
        if not payload:
            raise ValueError("Nenhuma coluna válida para setores/locais.")
        columns = ", ".join(f'"{key}"' for key in payload.keys())
        placeholders = ", ".join(["%s"] * len(payload))
        sql = f"INSERT INTO setores_locais ({columns}) VALUES ({placeholders})"
        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, tuple(payload.values()))
            self.connection.commit()
            new_id = cursor.lastrowid
        except DatabaseError:
            self.connection.rollback()
            raise
        finally:
            cursor.close()
        self.cache.invalidate("setores_locais:list_all")
        return new_id

    def update_setor_local(self, setor_id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        try:
            allowed = set(self.get_table_columns("setores_locais"))
        except DatabaseError:
            allowed = {
                "nome_setor_local",
                "localizacao",
                "descricao",
                "responsavel",
                "capacidade",
                "andar",
            }
        updates: List[str] = []
        params: List[Any] = []
        for key, value in data.items():
            if key not in allowed or key == "id_setor_local":
                continue
            updates.append(f'"{key}" = %s')
            params.append(value)
        if not updates:
            return False
        params.append(setor_id)
        sql = f"UPDATE setores_locais SET {', '.join(updates)} WHERE id_setor_local = %s"
        rows = self.execute_query(sql, tuple(params))
        if rows:
            self.cache.invalidate("setores_locais:list_all")
        return bool(rows)

    def delete_setor_local(self, setor_id: int) -> bool:
        sql = "DELETE FROM setores_locais WHERE id_setor_local = %s"
        rows = self.execute_query(sql, (setor_id,))
        if rows:
            self.cache.invalidate("setores_locais:list_all")
        return bool(rows)

    def list_patrimonios(self, filters: Optional[Dict[str, Any]] = None):
        try:
            columns = set(self.get_table_columns("patrimonios"))
        except DatabaseError:
            columns = {"quantidade", "numero_nota"}

        try:
            centro_cols = set(self.get_table_columns("centro_custo"))
        except DatabaseError:
            centro_cols = set()
        centros_filter = " AND cc.ativo = 1" if "ativo" in centro_cols else ""

        quantidade_expr = "COALESCE(p.quantidade, 1)" if "quantidade" in columns else "1"
        numero_nota_expr = "COALESCE(p.numero_nota, '')" if "numero_nota" in columns else "''"
        valor_atual_expr = "p.valor_atual" if "valor_atual" in columns else "NULL"

        query = [
            "SELECT",
            "    p.id_patrimonio,",
            "    p.numero_patrimonio,",
            "    p.nome AS nome_patrimonio,",
            "    p.descricao,",
            "    p.numero_serie,",
            "    p.valor_compra,",
            f"    {valor_atual_expr} AS valor_atual,",
            "    p.data_aquisicao,",
            "    p.estado_conservacao,",
            "    p.status,",
            "    p.id_categoria,",
            "    p.id_fornecedor,",
            "    p.id_setor_local,",
            f"    {quantidade_expr} AS quantidade,",
            f"    {numero_nota_expr} AS numero_nota,",
            "    cat.nome_categoria,",
            "    forn.nome_fornecedor,",
            "    sl.nome_setor_local,",
            "    (",
            "        SELECT GROUP_CONCAT(DISTINCT cc.nome_centro ORDER BY cc.nome_centro SEPARATOR ', ')",
            "        FROM patrimonios_centro_custo pcc",
            "        INNER JOIN centro_custo cc ON cc.id_centro_custo = pcc.id_centro_custo",
            f"        WHERE pcc.id_patrimonio = p.id_patrimonio{centros_filter}",
            "    ) AS centros_custo",
            "FROM patrimonios p",
            "LEFT JOIN categorias cat ON cat.id_categoria = p.id_categoria",
            "LEFT JOIN fornecedores forn ON forn.id_fornecedor = p.id_fornecedor",
            "LEFT JOIN setores_locais sl ON sl.id_setor_local = p.id_setor_local",
        ]

        conditions: List[str] = []
        params: List[Any] = []
        if filters:
            text = filters.get("texto")
            if text:
                like = f"%{text}%"
                conditions.append(
                    "("
                    "p.nome LIKE %s OR "
                    "p.descricao LIKE %s OR "
                    "p.numero_serie LIKE %s OR "
                    "CAST(p.numero_patrimonio AS CHAR) LIKE %s"
                    ")"
                )
                params.extend([like, like, like, like])
            categoria_id = filters.get("id_categoria")
            if categoria_id:
                conditions.append("p.id_categoria = %s")
                params.append(categoria_id)
            setor_id = filters.get("id_setor_local")
            if setor_id:
                conditions.append("p.id_setor_local = %s")
                params.append(setor_id)
            status = filters.get("status")
            if status:
                conditions.append("p.status = %s")
                params.append(status)

        if conditions:
            query.append("WHERE " + " AND ".join(conditions))

        query.append("ORDER BY p.data_aquisicao DESC, p.id_patrimonio DESC")

        final_query = "\n".join(query)
        return self.fetch_all(final_query, tuple(params) if params else None)

    def get_patrimonio_dashboard_metrics(self) -> Dict[str, Any]:
        try:
            columns = set(self.get_table_columns("patrimonios"))
        except DatabaseError:
            columns = set()

        # Se existir valor_atual, priorizar, mas sempre caindo para valor_compra quando nulo
        if "valor_atual" in columns:
            valor_expr = "COALESCE(p.valor_atual, p.valor_compra, 0)"
        else:
            valor_expr = "COALESCE(p.valor_compra, 0)"

        quantidade_expr = "COALESCE(p.quantidade, 1)" if "quantidade" in columns else "1"

        query = f"""
            SELECT
                SUM(CASE WHEN p.status = 'ativo' THEN 1 ELSE 0 END) AS ativos,
                SUM(CASE WHEN p.status = 'baixado' THEN 1 ELSE 0 END) AS baixados,
                SUM(CASE WHEN p.status = 'em_manutencao' THEN 1 ELSE 0 END) AS manutencao,
                COALESCE(SUM({valor_expr} * {quantidade_expr}), 0) AS total_valor
            FROM patrimonios p
        """
        row = self.fetch_one(query)
        if not row:
            return {"ativos": 0, "baixados": 0, "manutencao": 0, "total_valor": 0.0}
        return {
            "ativos": row.get("ativos", 0) or 0,
            "baixados": row.get("baixados", 0) or 0,
            "manutencao": row.get("manutencao", 0) or 0,
            "total_valor": float(row.get("total_valor") or 0.0),
        }

    def list_manutencoes(self, filters: Optional[Dict[str, Any]] = None):
        base_query = [
            "SELECT",
            "    m.*,",
            "    p.nome AS nome_patrimonio",
            "FROM manutencoes m",
            "INNER JOIN patrimonios p ON p.id_patrimonio = m.id_patrimonio",
        ]
        params: List[Any] = []
        conditions: List[str] = []
        if filters:
            patrimonio_id = filters.get("id_patrimonio")
            if patrimonio_id:
                conditions.append("m.id_patrimonio = %s")
                params.append(patrimonio_id)
            tipo_manutencao = filters.get("tipo_manutencao")
            if tipo_manutencao:
                conditions.append("LOWER(m.tipo_manutencao) = %s")
                params.append(str(tipo_manutencao).strip().lower())
            status = filters.get("status")
            if status:
                conditions.append("m.status = %s")
                params.append(status)
            data_inicio = filters.get("data_inicio")
            if data_inicio:
                conditions.append("m.data_inicio >= %s")
                params.append(data_inicio)
            data_fim = filters.get("data_fim")
            if data_fim:
                conditions.append("m.data_inicio <= %s")
                params.append(data_fim)
            texto = filters.get("texto")
            if texto:
                like = f"%{texto}%"
                conditions.append(
                    "(p.nome LIKE %s OR m.descricao LIKE %s OR m.empresa LIKE %s OR m.responsavel LIKE %s)"
                )
                params.extend([like, like, like, like])
        if conditions:
            base_query.append("WHERE " + " AND ".join(conditions))
        base_query.append("ORDER BY m.data_inicio DESC")
        query = "\n".join(base_query)
        return self.fetch_all(query, tuple(params) if params else None)

    def create_manutencao(self, data: Dict[str, Any]) -> int:
        if not data:
            raise ValueError("Dados de manutenção não informados.")
        allowed = self._get_manutencao_columns()
        payload = {k: v for k, v in data.items() if k in allowed and k != "id_manutencao"}
        if not payload:
            raise ValueError("Nenhuma coluna válida para manutenção.")
        columns = ", ".join(f'"{key}"' for key in payload.keys())
        placeholders = ", ".join(["%s"] * len(payload))
        sql = f"INSERT INTO manutencoes ({columns}) VALUES ({placeholders})"
        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, tuple(payload.values()))
            self.connection.commit()
            return cursor.lastrowid
        except DatabaseError:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def update_manutencao(self, manutencao_id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = self._get_manutencao_columns()
        updates: List[str] = []
        params: List[Any] = []
        for key, value in data.items():
            if key not in allowed or key == "id_manutencao":
                continue
            updates.append(f'"{key}" = %s')
            params.append(value)
        if not updates:
            return False
        params.append(manutencao_id)
        sql = f"UPDATE manutencoes SET {', '.join(updates)} WHERE id_manutencao = %s"
        rows = self.execute_query(sql, tuple(params))
        return bool(rows)

    def delete_manutencao(self, manutencao_id: int) -> bool:
        sql = "DELETE FROM manutencoes WHERE id_manutencao = %s"
        rows = self.execute_query(sql, (manutencao_id,))
        return bool(rows)

    def get_patrimonio(self, patrimonio_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT
                p.*,
                cat.nome_categoria,
                sl.nome_setor_local,
                sl.localizacao
            FROM patrimonios p
            LEFT JOIN categorias cat ON cat.id_categoria = p.id_categoria
            LEFT JOIN setores_locais sl ON sl.id_setor_local = p.id_setor_local
            WHERE p.id_patrimonio = %s
        """
        return self.fetch_one(query, (patrimonio_id,))

    def update_patrimonio_setor_local(self, patrimonio_id: int, setor_local_id: Optional[int]) -> bool:
        sql = "UPDATE patrimonios SET id_setor_local = %s WHERE id_patrimonio = %s"
        rows = self.execute_query(sql, (setor_local_id, patrimonio_id))
        return bool(rows)

    def list_movimentacoes(
        self,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            mov_columns = set(self.get_table_columns("movimentacoes"))
        except DatabaseError:
            mov_columns = set()

        select_fields = [
            "mov.id_movimentacao",
            "mov.data_movimentacao",
            "mov.tipo_movimentacao",
            "mov.origem",
            "mov.destino",
            "mov.observacoes",
        ]
        if "responsavel" in mov_columns:
            select_fields.append("mov.responsavel")
        select_fields.extend(
            [
                "p.nome AS nome_patrimonio",
                "u.nome AS nome_usuario",
            ]
        )
        select_clause = ",\n    ".join(select_fields)

        base_query = [
            "SELECT",
            f"    {select_clause}",
            "FROM movimentacoes mov",
            "INNER JOIN patrimonios p ON p.id_patrimonio = mov.id_patrimonio",
            "INNER JOIN usuarios u ON u.id_usuario = mov.id_usuario",
        ]
        params: List[Any] = []
        conditions: List[str] = []
        if filters:
            patrimonio_id = filters.get("id_patrimonio")
            if patrimonio_id:
                conditions.append("mov.id_patrimonio = %s")
                params.append(patrimonio_id)
            inicio = filters.get("data_inicio")
            if inicio:
                conditions.append("mov.data_movimentacao >= %s")
                params.append(inicio)
            fim = filters.get("data_fim")
            if fim:
                conditions.append("mov.data_movimentacao <= %s")
                params.append(fim)
        if conditions:
            base_query.append("WHERE " + " AND ".join(conditions))
        base_query.append("ORDER BY mov.data_movimentacao DESC")
        base_query.append("LIMIT %s")
        params.append(limit)
        query = "\n".join(base_query)
        return self.fetch_all(query, tuple(params))

    def create_movimentacao(self, data: Dict[str, Any]) -> int:
        if not data:
            raise ValueError("Dados da movimentação não informados.")
        try:
            allowed = set(self.get_table_columns("movimentacoes"))
        except DatabaseError:
            allowed = {
                "id_patrimonio",
                "id_usuario",
                "data_movimentacao",
                "tipo_movimentacao",
                "origem",
                "destino",
                "observacoes",
            }
        payload = {k: v for k, v in data.items() if k in allowed and k != "id_movimentacao"}
        if not payload:
            raise ValueError("Nenhuma coluna válida para movimentação.")
        columns = ", ".join(f'"{key}"' for key in payload.keys())
        placeholders = ", ".join(["%s"] * len(payload))
        sql = f"INSERT INTO movimentacoes ({columns}) VALUES ({placeholders})"
        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, tuple(payload.values()))
            self.connection.commit()
            return cursor.lastrowid
        except DatabaseError:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def list_notas_fiscais(self):
        query = """
            SELECT
                nf.id_nota_fiscal,
                nf.numero_nota,
                nf.data_emissao,
                nf.valor_total,
                nf.caminho_arquivo_nf,
                forn.nome_fornecedor
            FROM notas_fiscais nf
            INNER JOIN fornecedores forn ON forn.id_fornecedor = nf.id_fornecedor
            ORDER BY nf.data_emissao DESC
        """
        return self.fetch_all(query)

    def list_itens_nota(self, id_nota_fiscal):
        query = """
            SELECT
                itens.id_item_nf,
                itens.quantidade,
                itens.valor_unitario,
                p.nome AS nome_patrimonio
            FROM itens_nota_fiscal itens
            LEFT JOIN patrimonios p ON p.id_patrimonio = itens.id_patrimonio
            WHERE itens.id_nota_fiscal = %s
            ORDER BY itens.id_item_nf
        """
        return self.fetch_all(query, (id_nota_fiscal,))

    def _normalize_anexo_entidade(self, entidade: Optional[str]) -> str:
        chave = (entidade or "patrimonio").strip().lower()
        if chave not in self._ANEXO_CONFIG:
            raise ValueError(f"Entidade de anexo '{entidade}' não é suportada.")
        return chave

    def _get_anexo_allowed_columns(self, entidade: str) -> List[str]:
        config = self._ANEXO_CONFIG[entidade]
        try:
            return self.get_table_columns(config["table"])
        except DatabaseError:
            valores = [valor for valor in config["columns"].values() if valor]
            return valores

    def list_anexos(
        self,
        entidade: Optional[str] = None,
        entidade_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        entidade_norm = self._normalize_anexo_entidade(entidade)
        config = self._ANEXO_CONFIG[entidade_norm]

        def _alias(coluna: Optional[str], apelido: str) -> str:
            if coluna:
                return f'a."{coluna}" AS {apelido}'
            return f"NULL AS {apelido}"

        colunas = config["columns"]
        select = [
            _alias(config["pk"], "id_anexo"),
            _alias(colunas.get("entidade_id"), "entidade_id"),
            _alias(colunas.get("nome_arquivo"), "nome_arquivo"),
            _alias(colunas.get("caminho_arquivo"), "caminho_arquivo"),
            _alias(colunas.get("tamanho_arquivo"), "tamanho_arquivo"),
            _alias(colunas.get("tipo_arquivo"), "tipo_arquivo"),
            _alias(colunas.get("data_upload"), "data_upload"),
        ]
        select.extend(config.get("extra_select", []))

        query_parts = ["SELECT", ",\n".join(select), f"FROM {config['table']} a"]
        query_parts.extend(config.get("joins", []))

        params: List[Any] = []
        if entidade_id is not None:
            query_parts.append(f"WHERE a.\"{colunas['entidade_id']}\" = %s")
            params.append(entidade_id)

        order_by = config.get("order_by")
        if order_by:
            query_parts.append(f"ORDER BY {order_by}")

        query = "\n".join(query_parts)
        rows = self.fetch_all(query, tuple(params) if params else None)
        for row in rows:
            row.setdefault("entidade", entidade_norm)
        return rows

    def create_anexo(self, entidade: str, data: Dict[str, Any]) -> int:
        if not data:
            raise ValueError("Dados do anexo não informados.")

        entidade_norm = self._normalize_anexo_entidade(entidade)
        config = self._ANEXO_CONFIG[entidade_norm]
        colunas = config["columns"]

        fk_coluna = colunas.get("entidade_id")
        entidade_id = data.get("entidade_id") or data.get(fk_coluna)
        if not entidade_id:
            raise ValueError("Identificador da entidade não informado.")

        allowed = set(self._get_anexo_allowed_columns(entidade_norm))
        allowed.discard(config["pk"])

        payload: Dict[str, Any] = {}
        for chave_logica, coluna in colunas.items():
            if not coluna or coluna == config["pk"]:
                continue
            valor = data.get(chave_logica)
            if valor is None and chave_logica == coluna:
                valor = data.get(coluna)
            if valor is None and chave_logica == "entidade_id":
                valor = entidade_id
            if valor is None:
                continue
            if coluna in allowed:
                payload[coluna] = valor

        if fk_coluna and fk_coluna not in payload:
            if fk_coluna in allowed:
                payload[fk_coluna] = entidade_id

        if not payload:
            raise ValueError("Nenhuma coluna válida para anexo.")

        columns = ", ".join(f'"{col}"' for col in payload.keys())
        placeholders = ", ".join(["%s"] * len(payload))
        sql = f"INSERT INTO {config['table']} ({columns}) VALUES ({placeholders})"

        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, tuple(payload.values()))
            self.connection.commit()
            return cursor.lastrowid
        except DatabaseError:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def delete_anexo(self, entidade: str, anexo_id: int) -> bool:
        entidade_norm = self._normalize_anexo_entidade(entidade)
        config = self._ANEXO_CONFIG[entidade_norm]
        sql = f"DELETE FROM {config['table']} WHERE \"{config['pk']}\" = %s"
        rows = self.execute_query(sql, (anexo_id,))
        return bool(rows)

    def list_auditorias(self, limit=100):
        query = """
            SELECT
                aud.*,
                usr.nome AS nome_usuario
            FROM auditorias aud
            INNER JOIN usuarios usr ON usr.id_usuario = aud.id_usuario
            ORDER BY aud.data_auditoria DESC
            LIMIT %s
        """
        return self.fetch_all(query, (limit,))

    def create_auditoria(self, data: Dict[str, Any]) -> int:
        if not data.get("id_usuario"):
            raise ValueError("Usuário da auditoria não informado.")
        if not data.get("acao"):
            raise ValueError("Ação da auditoria não informada.")

        payload: Dict[str, Any] = {}
        columns = (
            "id_usuario",
            "data_auditoria",
            "acao",
            "tabela_afetada",
            "id_registro_afetado",
            "detalhes_antigos",
            "detalhes_novos",
        )
        for coluna in columns:
            valor = data.get(coluna)
            if valor is None or valor == "":
                continue
            if coluna == "id_registro_afetado" and (valor == 0 or valor == "0"):
                continue
            if coluna in {"detalhes_antigos", "detalhes_novos"} and isinstance(valor, (dict, list)):
                valor = json.dumps(valor, ensure_ascii=False)
            if coluna == "data_auditoria" and isinstance(valor, datetime):
                valor = valor.strftime("%Y-%m-%d %H:%M:%S")
            payload[coluna] = valor

        if "data_auditoria" not in payload:
            payload["data_auditoria"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        colunas_sql = ", ".join(f'"{col}"' for col in payload.keys())
        placeholders = ", ".join(["%s"] * len(payload))
        sql = f"INSERT INTO auditorias ({colunas_sql}) VALUES ({placeholders})"

        self._ensure_connection()
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, tuple(payload.values()))
            self.connection.commit()
            return cursor.lastrowid
        except DatabaseError:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def update_auditoria(self, auditoria_id: int, data: Dict[str, Any]) -> bool:
        if not auditoria_id:
            raise ValueError("Identificador da auditoria não informado.")
        if not data:
            return False

        allowed = (
            "data_auditoria",
            "acao",
            "tabela_afetada",
            "id_registro_afetado",
            "detalhes_antigos",
            "detalhes_novos",
        )
        updates: List[str] = []
        params: List[Any] = []
        for coluna in allowed:
            if coluna not in data:
                continue
            valor = data[coluna]
            if valor is None or valor == "":
                valor = None
            if coluna == "id_registro_afetado" and valor in (0, "0"):
                valor = None
            if coluna in {"detalhes_antigos", "detalhes_novos"} and isinstance(valor, (dict, list)):
                valor = json.dumps(valor, ensure_ascii=False)
            if coluna == "data_auditoria" and isinstance(valor, datetime):
                valor = valor.strftime("%Y-%m-%d %H:%M:%S")
            updates.append(f'"{coluna}" = %s')
            params.append(valor)

        if not updates:
            return False
        params.append(auditoria_id)
        sql = f"UPDATE auditorias SET {', '.join(updates)} WHERE id_auditoria = %s"
        rows = self.execute_query(sql, tuple(params))
        return bool(rows)

    def list_auditorias_agendadas(self, dias: int = 90) -> List[Dict[str, Any]]:
        query = """
            SELECT
                aud.id_auditoria,
                aud.data_auditoria,
                aud.acao,
                aud.tabela_afetada,
                aud.id_registro_afetado,
                aud.detalhes_novos #>> '{observacoes}' AS observacoes
            FROM auditorias aud
            WHERE aud.detalhes_novos #>> '{status}' = 'agendado'
        """
        params: List[Any] = []
        if dias and dias > 0:
            query += " AND aud.data_auditoria BETWEEN CURRENT_DATE AND CURRENT_DATE + (%s * INTERVAL '1 day')"
            params.append(dias)
        query += " ORDER BY aud.data_auditoria ASC"
        return self.fetch_all(query, tuple(params) if params else None)

    def relatorio_por_setor(self):
        query = """
            SELECT
                sl.nome_setor_local AS setor,
                COALESCE(sl.localizacao, '-') AS localizacao,
                COUNT(p.id_patrimonio) AS quantidade,
                COALESCE(SUM(p.valor_compra), 0) AS valor_total
            FROM setores_locais sl
            LEFT JOIN patrimonios p ON p.id_setor_local = sl.id_setor_local
            GROUP BY sl.id_setor_local, sl.nome_setor_local, sl.localizacao
            ORDER BY sl.nome_setor_local
        """
        return self.fetch_all(query)

    def relatorio_por_categoria(self):
        query = """
            SELECT
                cat.nome_categoria AS categoria,
                COUNT(p.id_patrimonio) AS quantidade,
                COALESCE(SUM(dep.valor_depreciado), 0) AS depreciacao_acumulada
            FROM categorias cat
            LEFT JOIN patrimonios p ON p.id_categoria = cat.id_categoria
            LEFT JOIN depreciacoes dep ON dep.id_patrimonio = p.id_patrimonio
            GROUP BY cat.id_categoria, cat.nome_categoria
            ORDER BY cat.nome_categoria
        """
        return self.fetch_all(query)

    def relatorio_manutencoes(self, limit=100):
        query = """
            SELECT
                m.data_inicio,
                p.nome AS nome_patrimonio,
                COALESCE(m.tipo_manutencao, m.status) AS tipo,
                m.responsavel,
                m.custo,
                m.status
            FROM manutencoes m
            INNER JOIN patrimonios p ON p.id_patrimonio = m.id_patrimonio
            ORDER BY m.data_inicio DESC
            LIMIT %s
        """
        return self.fetch_all(query, (limit,))

    def calcular_depreciacao(self, vida_util_anos: int = 10, filters: Optional[Dict[str, Any]] = None):
        """Calcula os valores de depreciação para os patrimônios cadastrados.

        A função aplica um modelo simples de depreciação linear considerando uma vida útil
        média (em anos). Opcionalmente é possível filtrar os patrimônios pelo mesmo formato
        aceito em :py:meth:`list_patrimonios`.

        Parameters
        ----------
        vida_util_anos: int
            Vida útil média utilizada para o cálculo linear. O padrão é ``10`` anos.
        filters: dict, optional
            Dicionário de filtros, aceitando ``texto`` e ``id_categoria`` entre outros
            campos utilizados por :py:meth:`list_patrimonios`.
        """

        list_filters = filters or {}
        patrimonios = self.list_patrimonios(list_filters if list_filters else None)
        hoje = date.today()
        vida_util_meses = max(int(vida_util_anos) * 12, 1)
        linhas = []

        for item in patrimonios:
            valor = item.get("valor_compra") or Decimal("0")
            if not isinstance(valor, Decimal):
                valor = Decimal(str(valor or "0"))

            aquisicao = item.get("data_aquisicao")
            if isinstance(aquisicao, datetime):
                aquisicao = aquisicao.date()

            if isinstance(aquisicao, date):
                meses_em_uso = max((hoje.year - aquisicao.year) * 12 + (hoje.month - aquisicao.month), 0)
            else:
                meses_em_uso = 0

            depreciacao_mensal = valor / vida_util_meses if vida_util_meses else Decimal("0")
            acumulado = depreciacao_mensal * Decimal(meses_em_uso)
            if acumulado > valor:
                acumulado = valor

            valor_periodo = depreciacao_mensal
            if acumulado >= valor:
                valor_periodo = Decimal("0")
            elif acumulado + depreciacao_mensal > valor:
                valor_periodo = valor - acumulado

            nome_patrimonio = item.get("nome") or item.get("nome_patrimonio") or "-"
            linhas.append(
                {
                    "patrimonio": nome_patrimonio,
                    "categoria": item.get("nome_categoria"),
                    "competencia": hoje.strftime("%Y-%m"),
                    "valor_periodo": float(valor_periodo),
                    "valor_acumulado": float(acumulado),
                }
            )

        return linhas
