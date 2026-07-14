from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableView,
    QTextEdit,
    QWidget,
)

from backend.database.database_manager import DatabaseManager
from backend.database.postgres_driver import DatabaseError


@dataclass
class _ColumnConfig:
    name: str
    header: str
    visible: bool = True


class CentroCustoController:
    def __init__(self, widget: QWidget, db_manager, current_user=None):
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user
        self.current_id: Optional[int] = None
        self._ready = False
        self._table_rows: List[Dict] = []
        self._table_headers: List[_ColumnConfig] = []
        self._table_model: Optional[QStandardItemModel] = None

        self.btn_novo: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_novo")
        self.btn_salvar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_salvar")
        self.btn_excluir: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_excluir")
        self.btn_buscar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_buscar")
        self.txt_buscar: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_buscar")

        self.tab_widget: Optional[QTabWidget] = self.widget.findChild(QTabWidget, "tab_widget")
        self.tab_form: Optional[QWidget] = self.widget.findChild(QWidget, "tab_dados")

        self._line_edits: Dict[str, Optional[QLineEdit]] = {
            "codigo": self.widget.findChild(QLineEdit, "txt_codigo"),
            "nome": self.widget.findChild(QLineEdit, "txt_nome"),
            "responsavel": self.widget.findChild(QLineEdit, "txt_responsavel"),
        }
        self._chk_ativo: Optional[QCheckBox] = self.widget.findChild(QCheckBox, "chk_ativo")
        self._txt_observacoes: Optional[QTextEdit] = self.widget.findChild(QTextEdit, "txt_observacoes")
        self._table_view: Optional[QTableView] = self.widget.findChild(QTableView, "tbl_centro_custo")

        self._columns: Dict[str, Optional[str]] = {}
        self._columns_meta: Dict[str, Dict[str, Optional[str]]] = {}
        self._enum_ativo_values: List[str] = []

        self._discover_columns()
        self._setup_table_model()
        self._apply_column_availability()
        self._connect_signals()
        self._set_buttons_state()

        if self._ready:
            self.refresh()

                                                                          
                   
    def _discover_columns(self):
        self._ready = False
        cursor = None
        try:
            conn = self._ensure_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable, NULL, column_default, NULL
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("centro_custo",),
            )
            rows = cursor.fetchall()
        except DatabaseError as err:
            QMessageBox.critical(self.widget, "Centro de Custo", f"Não foi possível ler as colunas de centro_custo.\n{err}")
            return
        finally:
            if cursor:
                cursor.close()

        available = []
        self._columns_meta.clear()
        for field, col_type, is_null, key, default, extra in rows:
            available.append(field)
            self._columns_meta[field] = {
                "type": col_type,
                "nullable": is_null == "YES",
                "default": default,
            }

        def pick(*candidates, default=None):
            for candidate in candidates:
                if candidate in available:
                    return candidate
            return default

        self._columns = {
            "id": pick("id_centro_custo", "id"),
            "codigo": pick("codigo", "cod_centro", "cod", "codigo_centro"),
            "nome": pick("nome_centro", "nome"),
            "responsavel": pick("responsavel", "nome_responsavel"),
            "ativo": pick("ativo", "situacao", "status", "is_ativo"),
            "observacoes": pick("observacoes", "descricao", "obs", "detalhes"),
        }

        if not self._columns["id"] or not self._columns["nome"]:
            QMessageBox.critical(
                self.widget,
                "Centro de Custo",
                "Estrutura da tabela 'centro_custo' não possui colunas obrigatórias (id/nome).",
            )
            return

        ativo_col = self._columns.get("ativo")
        if ativo_col:
            meta = self._columns_meta.get(ativo_col) or {}
            col_type = (meta.get("type") or "").lower()
            if col_type.startswith("enum("):
                enumerators = col_type[5:-1]
                options = [opt.strip().strip("'") for opt in enumerators.split(",")]
                self._enum_ativo_values = [opt for opt in options if opt]

        self._table_headers = [
            _ColumnConfig(self._columns["id"], "ID", visible=False),
        ]
        if self._columns.get("codigo"):
            self._table_headers.append(_ColumnConfig(self._columns["codigo"], "Código"))
        self._table_headers.append(_ColumnConfig(self._columns["nome"], "Centro de Custo"))
        if self._columns.get("responsavel"):
            self._table_headers.append(_ColumnConfig(self._columns["responsavel"], "Responsável"))
        if self._columns.get("ativo"):
            self._table_headers.append(_ColumnConfig(self._columns["ativo"], "Ativo"))

        self._ready = True

    def _setup_table_model(self):
        if not self._table_view:
            return
        self._table_model = QStandardItemModel(self._table_view)
        headers = [config.header for config in self._table_headers]
        self._table_model.setHorizontalHeaderLabels(headers)
        self._table_view.setModel(self._table_model)
        for index, config in enumerate(self._table_headers):
            self._table_view.setColumnHidden(index, not config.visible)
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)

    def _apply_column_availability(self):
        unavailable_hint = "Campo indisponível porque a coluna equivalente não existe na base de dados."
        for key, widget in self._line_edits.items():
            if widget is None:
                continue
            column_exists = bool(self._columns.get(key))
            widget.setEnabled(column_exists)
            widget.setToolTip("" if column_exists else unavailable_hint)
        if self._chk_ativo:
            column_exists = bool(self._columns.get("ativo"))
            self._chk_ativo.setEnabled(column_exists)
            self._chk_ativo.setToolTip("" if column_exists else unavailable_hint)
        if self._txt_observacoes:
            column_exists = bool(self._columns.get("observacoes"))
            self._txt_observacoes.setEnabled(column_exists)
            self._txt_observacoes.setToolTip("" if column_exists else unavailable_hint)

    def _connect_signals(self):
        if self.btn_novo:
            self.btn_novo.clicked.connect(self._handle_novo)
        if self.btn_salvar:
            self.btn_salvar.clicked.connect(self._handle_salvar)
        if self.btn_excluir:
            self.btn_excluir.clicked.connect(self._handle_excluir)
        if self.btn_buscar:
            self.btn_buscar.clicked.connect(self._handle_buscar)
        if self.txt_buscar:
            self.txt_buscar.returnPressed.connect(self._handle_buscar)
        if self._table_view:
            self._table_view.clicked.connect(self._table_row_clicked)
            self._table_view.doubleClicked.connect(self._table_row_double_clicked)

                                                                          
                    
    def _handle_novo(self):
        if not self._ready:
            return
        self.current_id = None
        self._clear_form()
        if self._table_view:
            self._table_view.clearSelection()
        nome_widget = self._line_edits.get("nome")
        if nome_widget:
            nome_widget.setFocus()
        self._switch_to_form()
        self._set_buttons_state()

    def _handle_salvar(self):
        if not self._ready:
            return
        payload, error = self._collect_form_data()
        if error:
            QMessageBox.warning(self.widget, "Centro de Custo", error)
            return
        if payload is None:
            return

        cursor = None
        conn = None
        try:
            conn = self._ensure_connection()
            cursor = conn.cursor()
            if self.current_id is None:
                columns_fragment = ", ".join(f'"{col}"' for col in payload.keys())
                placeholders = ", ".join(["%s"] * len(payload))
                sql = f"INSERT INTO centro_custo ({columns_fragment}) VALUES ({placeholders})"
                cursor.execute(sql, tuple(payload.values()))
                conn.commit()
                self.current_id = cursor.lastrowid
                QMessageBox.information(self.widget, "Centro de Custo", "Centro de custo cadastrado com sucesso.")
            else:
                set_fragment = ", ".join(f'"{col}" = %s' for col in payload.keys())
                sql = f"UPDATE centro_custo SET {set_fragment} WHERE \"{self._columns['id']}\" = %s"
                params = list(payload.values())
                params.append(self.current_id)
                cursor.execute(sql, tuple(params))
                conn.commit()
                QMessageBox.information(self.widget, "Centro de Custo", "Centro de custo atualizado com sucesso.")
        except DatabaseError as err:
            if conn:
                conn.rollback()
            QMessageBox.critical(self.widget, "Centro de Custo", f"Erro ao salvar centro de custo.\n{err}")
            return
        finally:
            if cursor:
                cursor.close()

        self.refresh()
        self._switch_to_form()
        self._set_buttons_state()

    def _handle_excluir(self):
        # Verificar permissão de admin/master
        if not DatabaseManager.has_admin_privileges(self.current_user):
            QMessageBox.warning(
                self.widget,
                "Centro de Custo",
                "Ação permitida apenas para administradores ou usuários master.",
            )
            return
        
        if not self._ready or not self.current_id:
            QMessageBox.warning(self.widget, "Centro de Custo", "Selecione um centro de custo para excluir.")
            return

        resp = QMessageBox.question(
            self.widget,
            "Excluir centro de custo",
            "Deseja realmente excluir o centro de custo selecionado?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        cursor = None
        conn = None
        try:
            conn = self._ensure_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM centro_custo WHERE \"{self._columns['id']}\" = %s",
                (self.current_id,),
            )
            conn.commit()
            QMessageBox.information(self.widget, "Centro de Custo", "Centro de custo excluído com sucesso.")
        except DatabaseError as err:
            if conn:
                conn.rollback()
            QMessageBox.critical(self.widget, "Centro de Custo", f"Erro ao excluir centro de custo.\n{err}")
            return
        finally:
            if cursor:
                cursor.close()

        self.current_id = None
        self._clear_form()
        self.refresh()
        self._set_buttons_state()

    def _handle_buscar(self):
        if not self._ready:
            return
        termo = self.txt_buscar.text().strip() if self.txt_buscar else ""
        self.refresh(termo)

    def _table_row_clicked(self, index):
        if not self._ready:
            return
        self._load_row(index.row(), focus_form=False)

    def _table_row_double_clicked(self, index):
        if not self._ready:
            return
        self._load_row(index.row(), focus_form=True)

                                                                          
                     
    def refresh(self, search_term: Optional[str] = None):
        if not self._ready:
            return

        if search_term is None and self.txt_buscar:
            search_term = self.txt_buscar.text().strip()

        rows = self._fetch_rows(search_term)
        self._table_rows = rows
        if not self._table_model:
            return

        self._table_model.setRowCount(0)
        for row in rows:
            items: List[QStandardItem] = []
            for config in self._table_headers:
                raw_value = row.get(config.name)
                if config.name == self._columns.get("ativo"):
                    text = self._format_checkbox_display(raw_value)
                else:
                    text = "" if raw_value is None else str(raw_value)
                item = QStandardItem(text)
                if config.name == self._columns["id"]:
                    item.setData(row.get(config.name), Qt.UserRole)
                items.append(item)
            self._table_model.appendRow(items)

        if self._table_view:
            self._table_view.resizeColumnsToContents()

        self._restore_selection()
        self._set_buttons_state()

    def _fetch_rows(self, search_term: Optional[str]) -> List[Dict]:
        columns_fragment = ", ".join(f'"{config.name}"' for config in self._table_headers)
        sql = f"SELECT {columns_fragment} FROM centro_custo"
        params: List[str] = []
        filters: List[str] = []
        if search_term:
            like = f"%{search_term}%"
            filters.append(f"\"{self._columns['nome']}\" LIKE %s")
            params.append(like)
            codigo_col = self._columns.get("codigo")
            if codigo_col:
                filters.append(f'"{codigo_col}" LIKE %s')
                params.append(like)
        if filters:
            sql += " WHERE " + " OR ".join(filters)
        sql += f" ORDER BY \"{self._columns['nome']}\""
        param_tuple = tuple(params) if params else None
        return self.db_manager.fetch_all(sql, param_tuple)

    def _load_row(self, row_index: int, focus_form: bool):
        if row_index < 0 or row_index >= len(self._table_rows):
            return
        record = self._table_rows[row_index]
        record_id = record.get(self._columns["id"])
        if record_id is None:
            return

        detalhes = self._fetch_by_id(record_id)
        if not detalhes:
            QMessageBox.warning(self.widget, "Centro de Custo", "Não foi possível obter os dados selecionados.")
            return

        self.current_id = record_id
        self._populate_form(detalhes)
        self._set_buttons_state()
        if focus_form:
            self._switch_to_form()

    def _fetch_by_id(self, record_id: int) -> Optional[Dict]:
        cursor = None
        conn = None
        try:
            conn = self._ensure_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                f"SELECT * FROM centro_custo WHERE \"{self._columns['id']}\" = %s",
                (record_id,),
            )
            return cursor.fetchone()
        except DatabaseError as err:
            QMessageBox.critical(self.widget, "Centro de Custo", f"Erro ao consultar dados do centro de custo.\n{err}")
            return None
        finally:
            if cursor:
                cursor.close()

                                                                          
                  
    def _collect_form_data(self):
        data: Dict[str, Optional[str]] = {}

        nome_widget = self._line_edits.get("nome")
        column_nome = self._columns.get("nome")
        nome_valor = nome_widget.text().strip() if nome_widget else ""
        if column_nome:
            if not nome_valor:
                return None, "Informe o nome do centro de custo."
            data[column_nome] = nome_valor

        codigo_col = self._columns.get("codigo")
        codigo_widget = self._line_edits.get("codigo")
        if codigo_col and codigo_widget:
            valor = codigo_widget.text().strip()
            if not valor:
                return None, "Informe o código do centro de custo."
            data[codigo_col] = valor

        responsavel_col = self._columns.get("responsavel")
        responsavel_widget = self._line_edits.get("responsavel")
        if responsavel_col and responsavel_widget:
            valor = responsavel_widget.text().strip()
            data[responsavel_col] = valor if valor else None

        ativo_col = self._columns.get("ativo")
        if ativo_col:
            checked = self._chk_ativo.isChecked() if self._chk_ativo else True
            data[ativo_col] = self._format_checkbox_value(checked)

        observacoes_col = self._columns.get("observacoes")
        if observacoes_col and self._txt_observacoes:
            texto = self._txt_observacoes.toPlainText().strip()
            data[observacoes_col] = texto if texto else None

        return data, None

    def _populate_form(self, dados: Dict):
        for key, widget in self._line_edits.items():
            if widget is None:
                continue
            column = self._columns.get(key)
            valor = dados.get(column) if column else None
            widget.setText("" if valor is None else str(valor))

        ativo_col = self._columns.get("ativo")
        if self._chk_ativo:
            valor = dados.get(ativo_col) if ativo_col else None
            self._chk_ativo.setChecked(self._parse_checkbox_value(valor))

        observacoes_col = self._columns.get("observacoes")
        if self._txt_observacoes:
            valor = dados.get(observacoes_col) if observacoes_col else None
            self._txt_observacoes.setPlainText("" if valor is None else str(valor))

    def _clear_form(self):
        for widget in self._line_edits.values():
            if widget is not None:
                widget.clear()
        if self._chk_ativo:
            self._chk_ativo.setChecked(True)
        if self._txt_observacoes:
            self._txt_observacoes.clear()

    def _restore_selection(self):
        if not self._table_view or self.current_id is None:
            return
        for index, row in enumerate(self._table_rows):
            if str(row.get(self._columns["id"])) == str(self.current_id):
                self._table_view.selectRow(index)
                return

    def _switch_to_form(self):
        if self.tab_widget and self.tab_form:
            self.tab_widget.setCurrentWidget(self.tab_form)

    def _set_buttons_state(self):
        enabled = self._ready
        has_selection = enabled and self.current_id is not None
        if self.btn_novo:
            self.btn_novo.setEnabled(enabled)
        if self.btn_salvar:
            self.btn_salvar.setEnabled(enabled)
        if self.btn_excluir:
            self.btn_excluir.setEnabled(has_selection)

                                                                          
                      
    def _format_checkbox_value(self, checked: bool):
        ativo_col = self._columns.get("ativo")
        if not ativo_col:
            return None
        meta = self._columns_meta.get(ativo_col) or {}
        col_type = (meta.get("type") or "").lower()
        if col_type.startswith("enum(") and self._enum_ativo_values:
            if len(self._enum_ativo_values) == 1:
                return self._enum_ativo_values[0]
            return self._enum_ativo_values[0] if checked else self._enum_ativo_values[-1]
        if "int" in col_type or "bit" in col_type or "bool" in col_type:
            return 1 if checked else 0
        return "Sim" if checked else "Não"

    def _format_checkbox_display(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Sim" if value else "Não"
        if isinstance(value, (int, float)):
            return "Sim" if float(value) != 0 else "Não"
        text = str(value).strip()
        if not text:
            return ""
        if self._enum_ativo_values:
            if text == self._enum_ativo_values[0]:
                return "Sim"
            if len(self._enum_ativo_values) > 1 and text == self._enum_ativo_values[-1]:
                return "Não"
        lowered = text.lower()
        if lowered in {"1", "true", "sim", "s", "ativo", "yes"}:
            return "Sim"
        if lowered in {"0", "false", "nao", "não", "n", "inativo", "no"}:
            return "Não"
        return text

    def _parse_checkbox_value(self, value) -> bool:
        if value is None:
            return True
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) != 0
        text = str(value).strip().lower()
        if text in {"", "sim", "s", "1", "true", "ativo", "yes"}:
            return True
        if self._enum_ativo_values:
            if value == self._enum_ativo_values[0]:
                return True
            if len(self._enum_ativo_values) > 1 and value == self._enum_ativo_values[-1]:
                return False
        return text not in {"0", "false", "nao", "não", "n", "inativo", "no"}

                                                                          
               
    def _ensure_connection(self):
        conn = self.db_manager.connection
        if not conn or not conn.is_connected():
            if not self.db_manager.connect():
                raise DatabaseError("Nao foi possivel estabelecer conexao com o banco de dados.")
            conn = self.db_manager.connection
        return conn
