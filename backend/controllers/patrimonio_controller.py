from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Callable, Dict, Optional, Sequence, Set

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.database.database_manager import DatabaseManager
from backend.controllers.quick_create_dialogs import QuickCreateFornecedorDialog, QuickCreateNotaFiscalDialog


class PatrimonioController(QWidget):
    """Controller responsavel por orquestrar a tela de patrimonio."""

    TABLE_HEADERS: Sequence[str] = (
        "ID",
        "Número Patrimonial",
        "Nome",
        "Descricao",
        "Numero de Serie",
        "Data de Aquisicao",
        "Valor Compra",
        "Valor Atual",
        "Quantidade",
        "Numero Nota",
        "Categoria",
        "Fornecedor",
        "Setor/Local",
        "Status",
    )

    STATUS_OPTIONS: Sequence[str] = ("ativo", "baixado", "em_manutencao", "desaparecido")
    ESTADO_CONSERVACAO_OPTIONS: Sequence[str] = ("novo", "bom", "regular", "ruim")
    FIXED_CATEGORIES: Sequence[str] = ("Eletronico", "Imobilizado", "Movel", "Utilitarios")

    def __init__(self, ui_widget: QWidget, db_manager: DatabaseManager, current_user=None) -> None:
        super().__init__()
        self.ui = ui_widget
        self.db_manager = db_manager
        self.current_user = current_user
        self._dashboard_updater: Optional[Callable[[], None]] = None
        self._fixed_category_map: Dict[str, int] = {}
        self._selection_connected: bool = False

        self.table: Optional[QTableWidget] = self.ui.findChild(QTableWidget, "tbl_patrimonio")
        self.search_input: Optional[QLineEdit] = self.ui.findChild(QLineEdit, "le_busca")
        self.category_filter: Optional[QComboBox] = self.ui.findChild(QComboBox, "cb_categoria")
        self.sector_filter: Optional[QComboBox] = self.ui.findChild(QComboBox, "cb_setor")
        self.status_filter: Optional[QComboBox] = self.ui.findChild(QComboBox, "cb_status")

        if self.table:
            self.table.setColumnCount(len(self.TABLE_HEADERS))
            self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)

        self.has_valor_atual_column = self._check_valor_atual_column()
        self.has_quantidade_column = False
        self.has_numero_nota_column = False
        self._refresh_optional_columns()

        self._setup_ui_connections()
        self._connect_table_selection()
        self._update_buttons_state()
        self.populate_comboboxes()
        self.load_patrimonios()

    def _setup_ui_connections(self) -> None:
        button_map = {
            "btn_novo": self.abrir_cadastro_patrimonio,
            "btn_editar": self.editar_patrimonio,
            "btn_excluir": self.excluir_patrimonio,
            "btn_filtrar": self.load_patrimonios,
            "btn_limpar": self.limpar_filtros,
            "btn_importar": self.abrir_importacao_massa,
        }

        for object_name, handler in button_map.items():
            button = self.ui.findChild(QPushButton, object_name)
            if button is None:
                print(f"[PatrimonioController] Botao '{object_name}' nao encontrado na UI.")
                continue
            button.clicked.connect(handler)

    def _connect_table_selection(self) -> None:
        if not self.table or not self.table.selectionModel():
            return
        if self._selection_connected:
            return
        self.table.selectionModel().selectionChanged.connect(self._update_buttons_state)
        self._selection_connected = True

    def _check_valor_atual_column(self) -> bool:
        try:
            result = self.db_manager.fetch_one(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'patrimonios' AND column_name = %s
                """,
                ("valor_atual",),
            )
            return bool(result)
        except Exception as exc:                                              
            print(f"[PatrimonioController] Falha ao verificar coluna valor_atual: {exc}")
            return False

    def _refresh_optional_columns(self) -> Set[str]:
        try:
            columns = set(self.db_manager.get_table_columns("patrimonios"))
        except Exception:
            columns = set()
        self.has_quantidade_column = "quantidade" in columns
        self.has_numero_nota_column = "numero_nota" in columns
        return columns

    def _populate_fk_combo(
        self,
        combo: QComboBox,
        placeholder: str,
        query: str,
        value_key: str,
        label_key: str,
        current_value: Optional[int] = None,
    ) -> None:
        combo.clear()
        combo.addItem(placeholder, None)

        rows = self.db_manager.fetch_all(query)
        for row in rows:
            value = self._normalize_id(row.get(value_key))
            label = row.get(label_key)
            if value is None or label is None:
                continue
            combo.addItem(str(label), value)

        normalized_current = self._normalize_id(current_value)
        if normalized_current is not None:
            index = combo.findData(normalized_current)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _populate_centros_custo_combo(
        self,
        combo: QComboBox,
        placeholder: str,
        current_value: Optional[int] = None,
        include_inativos: bool = False,
    ) -> None:
        combo.clear()
        combo.addItem(placeholder, None)
        try:
            centros = self.db_manager.list_centros_custo(include_inativos=include_inativos)
        except Exception as exc:  # pragma: no cover - feedback user-facing
            QMessageBox.warning(
                self.ui,
                "Patrimonio",
                f"Nao foi possivel carregar os centros de custo.\n{exc}",
            )
            centros = []

        normalized_current = self._normalize_id(current_value)
        for centro in centros:
            centro_id = self._normalize_id(centro.get("id_centro_custo"))
            nome = str(centro.get("nome_centro") or "-")
            ativo_flag = centro.get("ativo")
            label = nome if ativo_flag in (None, True, 1, "1", "True") else f"{nome} (Inativo)"
            combo.addItem(label, centro_id)

        if normalized_current is not None:
            index = combo.findData(normalized_current)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _ensure_fixed_category_map(self) -> Dict[str, int]:
        raw_map = self.db_manager.ensure_categorias(self.FIXED_CATEGORIES)
        normalized_map: Dict[str, int] = {}
        for nome, identificador in raw_map.items():
            normalized = self._normalize_id(identificador)
            if normalized is not None:
                normalized_map[nome] = normalized
        self._fixed_category_map = normalized_map
        return self._fixed_category_map

    def _populate_categoria_combo(
        self,
        combo: QComboBox,
        placeholder: str,
        current_value: Optional[int] = None,
    ) -> None:
        category_map = self._ensure_fixed_category_map()
        combo.clear()
        combo.addItem(placeholder, None)
        for nome in self.FIXED_CATEGORIES:
            categoria_id = category_map.get(nome)
            if categoria_id is None:
                continue
            combo.addItem(nome, categoria_id)

        normalized_current = self._normalize_id(current_value)
        if normalized_current is not None:
            index = combo.findData(normalized_current)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _has_management_privileges(self) -> bool:
        return DatabaseManager.has_admin_privileges(self.current_user)

    def _ensure_management_privileges(self) -> bool:
        if self._has_management_privileges():
            return True
        QMessageBox.warning(
            self.ui,
            "Patrimônio",
            "Ação permitida apenas para administradores ou usuários master.",
        )
        return False

    def _update_buttons_state(self) -> None:
        can_manage = self._has_management_privileges()
        has_selection = bool(
            self.table
            and self.table.selectionModel()
            and self.table.selectionModel().hasSelection()
        )

        button_rules = {
            "btn_novo": can_manage,
            "btn_importar": can_manage,
            "btn_editar": can_manage and has_selection,
            "btn_excluir": can_manage and has_selection,
        }

        for object_name, enabled in button_rules.items():
            button = self.ui.findChild(QPushButton, object_name)
            if button:
                button.setEnabled(enabled)

    def set_dashboard_updater(self, callback: Optional[Callable[[], None]]) -> None:
        self._dashboard_updater = callback

    def _trigger_dashboard_update(self) -> None:
        if callable(self._dashboard_updater):
            try:
                self._dashboard_updater()
            except Exception as exc:  # pragma: no cover - log but do not disrupt flow
                print(f"[PatrimonioController] Falha ao atualizar cards do dashboard: {exc}")

    def _persistir_centros_custo(
        self,
        patrimonio_ids: Sequence[int],
        centro_custo_id: Optional[int],
        parent_dialog: QDialog,
    ) -> None:
        if not patrimonio_ids:
            return
        centros = [centro_custo_id] if centro_custo_id is not None else []
        try:
            for patrimonio_id in patrimonio_ids:
                self.db_manager.set_patrimonio_centros_custo(patrimonio_id, centros)
        except Exception as exc:  # pragma: no cover - feedback user-facing
            QMessageBox.warning(
                parent_dialog,
                "Centro de Custo",
                f"Nao foi possivel atualizar o vinculo de centro de custo.\n{exc}",
            )

    @staticmethod
    def _normalize_id(value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, Decimal):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(stripped)
            except ValueError:
                return None
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_currency(value: Optional[float]) -> str:
        try:
            return f"R$ {float(value):.2f}"
        except (TypeError, ValueError):
            return "R$ 0.00"

    @staticmethod
    def _format_codigo(value: Optional[object]) -> str:
        if value in (None, "", 0):
            return "-"
        return str(value)

    @staticmethod
    def _format_date(value: Optional[datetime.date]) -> str:
        if value is None:
            return "-"
        if isinstance(value, datetime.datetime):
            value = value.date()
        return value.strftime("%d/%m/%Y")

                                                                             
                      
                                                                             
    def populate_comboboxes(self) -> None:
        category_map = self._ensure_fixed_category_map()

        if self.category_filter:
            self.category_filter.clear()
            self.category_filter.addItem("Categoria", None)
            for nome in self.FIXED_CATEGORIES:
                categoria_id = category_map.get(nome)
                self.category_filter.addItem(nome, categoria_id)

        if self.sector_filter:
            self.sector_filter.clear()
            self.sector_filter.addItem("Setor", None)
            try:
                setores = self.db_manager.list_setores_locais()
            except Exception as exc:  # pragma: no cover - feedback user-facing
                QMessageBox.warning(
                    self.ui,
                    "Patrimonio",
                    f"Nao foi possivel carregar os setores/locais.\n{exc}",
                )
                setores = []
            for row in setores:
                setor_id = self._normalize_id(row.get("id_setor_local"))
                nome = row.get("nome_setor_local")
                if setor_id is None or not nome:
                    continue
                self.sector_filter.addItem(str(nome), setor_id)

        if self.status_filter:
            self.status_filter.clear()
            self.status_filter.addItem("Status", None)
            self.status_filter.addItems(self.STATUS_OPTIONS)

    def limpar_filtros(self) -> None:
        if self.search_input:
            self.search_input.clear()
        if self.category_filter:
            self.category_filter.setCurrentIndex(0)
        if self.sector_filter:
            self.sector_filter.setCurrentIndex(0)
        if self.status_filter:
            self.status_filter.setCurrentIndex(0)
        self.load_patrimonios()

                                                                             
                           
                                                                             
    def load_patrimonios(self) -> None:
        self._refresh_optional_columns()
        if self.has_valor_atual_column:
            self.atualizar_valores_depreciados()

        if not self.table:
            return

        filtros: Dict[str, object] = {}
        if self.search_input:
            busca = self.search_input.text().strip()
            if busca:
                filtros["texto"] = busca
        if self.category_filter:
            categoria_id = self._normalize_id(self.category_filter.currentData())
            if categoria_id is not None:
                filtros["id_categoria"] = categoria_id
        if self.sector_filter:
            setor_id = self._normalize_id(self.sector_filter.currentData())
            if setor_id is not None:
                filtros["id_setor_local"] = setor_id
        if self.status_filter:
            status = self.status_filter.currentText()
            if status and status not in ("", "Status"):
                filtros["status"] = status

        patrimonios = self.db_manager.list_patrimonios(filtros if filtros else None)

        self.table.setRowCount(0)
        self.table.setRowCount(len(patrimonios))

        for row_index, item in enumerate(patrimonios):
            valor_compra = item.get("valor_compra")
            valor_compra = float(valor_compra) if valor_compra is not None else 0.0

            data_aquisicao = item.get("data_aquisicao")
            valor_atual_registrado = item.get("valor_atual")

            if valor_atual_registrado is not None:
                valor_atual = float(valor_atual_registrado)
            else:
                valor_atual = self.calcular_depreciacao(data_aquisicao, valor_compra)

            quantidade_value = item.get("quantidade")
            if quantidade_value is None:
                quantidade_display = "1"
            else:
                try:
                    quantidade_display = str(int(quantidade_value))
                except (TypeError, ValueError):
                    quantidade_display = str(quantidade_value)

            numero_nota_value = item.get("numero_nota")
            numero_nota_display = numero_nota_value if numero_nota_value else "-"

            table_values = [
                item.get("id_patrimonio"),
                self._format_codigo(item.get("numero_patrimonio")),
                item.get("nome_patrimonio"),
                item.get("descricao"),
                item.get("numero_serie"),
                self._format_date(data_aquisicao),
                self._format_currency(valor_compra),
                self._format_currency(valor_atual),
                quantidade_display,
                numero_nota_display,
                item.get("nome_categoria") or "-",
                item.get("nome_fornecedor") or "-",
                item.get("nome_setor_local") or "-",
                item.get("status") or "-",
            ]

            for column, value in enumerate(table_values):
                text = "" if value is None else str(value)
                self.table.setItem(row_index, column, QTableWidgetItem(text))

        self.table.resizeColumnsToContents()
        self._connect_table_selection()
        # Seleciona a primeira linha para habilitar edi��o r�pida
        if self.table.rowCount() > 0 and not self.table.selectionModel().hasSelection():
            self.table.selectRow(0)
        self._update_buttons_state()

                                                                             
                         
                                                                             
    def abrir_cadastro_patrimonio(self) -> None:
        if not self._ensure_management_privileges():
            return

        dialog = QDialog(self.ui)
        dialog.setWindowTitle("Cadastrar novo patrimonio")

        self._refresh_optional_columns()

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        codigo_hint = QLabel("Será gerado automaticamente ao salvar.")
        codigo_hint.setStyleSheet("color: #666666; font-style: italic;")
        form_layout.addRow("Número patrimonial:", codigo_hint)

        self.nome_input = QLineEdit()
        self.descricao_input = QLineEdit()
        self.numero_serie_input = QLineEdit()

        self.data_aquisicao_input = QDateEdit(QDate.currentDate())
        self.data_aquisicao_input.setCalendarPopup(True)

        self.valor_compra_input = QDoubleSpinBox()
        self.valor_compra_input.setPrefix("R$ ")
        self.valor_compra_input.setDecimals(2)
        self.valor_compra_input.setMaximum(999_999_999.99)
        self.valor_compra_input.setValue(0.0)

        self.quantidade_input = QSpinBox()
        self.quantidade_input.setMinimum(1)
        self.quantidade_input.setMaximum(1_000_000)
        self.quantidade_input.setValue(1)
        if not self.has_quantidade_column:
            self.quantidade_input.setToolTip(
                "Coluna 'quantidade' nao disponivel na tabela patrimonios (valor nao sera salvo)."
            )

        self.numero_nota_input = QLineEdit()
        self.numero_nota_input.setMaxLength(50)
        if not self.has_numero_nota_column:
            self.numero_nota_input.setToolTip(
                "Coluna 'numero_nota' nao disponivel na tabela patrimonios (valor nao sera salvo)."
            )

        self.estado_conservacao_input = QComboBox()
        self.estado_conservacao_input.addItems(self.ESTADO_CONSERVACAO_OPTIONS)

        self.categoria_combo = QComboBox()
        self.fornecedor_combo = QComboBox()
        self.setor_local_combo = QComboBox()
        self.centro_custo_combo = QComboBox()
        self.status_combo = QComboBox()
        self.status_combo.addItems(self.STATUS_OPTIONS)
        status_default_index = self.status_combo.findText("ativo")
        if status_default_index >= 0:
            self.status_combo.setCurrentIndex(status_default_index)

        self._populate_categoria_combo(
            self.categoria_combo,
            "Selecione uma Categoria",
        )
        self._populate_fk_combo(
            self.fornecedor_combo,
            "Selecione um Fornecedor",
            "SELECT id_fornecedor, nome_fornecedor FROM fornecedores ORDER BY nome_fornecedor",
            "id_fornecedor",
            "nome_fornecedor",
        )
        
        # Botão para cadastro rápido de fornecedor
        btn_novo_fornecedor = QPushButton("+ Novo Fornecedor")
        btn_novo_fornecedor.setMaximumWidth(150)
        btn_novo_fornecedor.clicked.connect(lambda: self._abrir_cadastro_rapido_fornecedor(dialog))
        
        # Layout horizontal para fornecedor
        fornecedor_layout = QHBoxLayout()
        fornecedor_layout.addWidget(self.fornecedor_combo)
        fornecedor_layout.addWidget(btn_novo_fornecedor)
        
        self._populate_fk_combo(
            self.setor_local_combo,
            "Selecione um Setor/Local",
            "SELECT id_setor_local, nome_setor_local FROM setores_locais ORDER BY nome_setor_local",
            "id_setor_local",
            "nome_setor_local",
        )
        self._populate_centros_custo_combo(
            self.centro_custo_combo,
            "Selecione um Centro de Custo",
        )
        
        # Botão para cadastro rápido de nota fiscal
        btn_nova_nota = QPushButton("+ Nova Nota")
        btn_nova_nota.setMaximumWidth(150)
        btn_nova_nota.clicked.connect(lambda: self._abrir_cadastro_rapido_nota(dialog))
        
        # Layout horizontal para nota fiscal
        nota_layout = QHBoxLayout()
        nota_layout.addWidget(self.numero_nota_input)
        nota_layout.addWidget(btn_nova_nota)

        form_layout.addRow("Nome:", self.nome_input)
        form_layout.addRow("Descricao:", self.descricao_input)
        form_layout.addRow("Numero de Serie:", self.numero_serie_input)
        form_layout.addRow("Data de Aquisicao:", self.data_aquisicao_input)
        form_layout.addRow("Valor de Compra:", self.valor_compra_input)
        form_layout.addRow("Quantidade:", self.quantidade_input)
        form_layout.addRow("Numero da Nota:", nota_layout)
        form_layout.addRow("Estado de Conservacao:", self.estado_conservacao_input)
        form_layout.addRow("Categoria:", self.categoria_combo)
        form_layout.addRow("Fornecedor:", fornecedor_layout)
        form_layout.addRow("Setor/Local:", self.setor_local_combo)
        form_layout.addRow("Centro de Custo:", self.centro_custo_combo)
        form_layout.addRow("Status:", self.status_combo)

        btn_salvar = QPushButton("Salvar")
        btn_salvar.clicked.connect(lambda: self.salvar_patrimonio(dialog))                          

        layout.addLayout(form_layout)
        layout.addWidget(btn_salvar)
        dialog.setLayout(layout)
        dialog.exec()

    def salvar_patrimonio(self, dialog: QDialog) -> None:
        nome = self.nome_input.text().strip()
        descricao = self.descricao_input.text().strip()
        numero_serie = self.numero_serie_input.text().strip()
        data_aquisicao = self.data_aquisicao_input.date().toString("yyyy-MM-dd")
        valor_compra = self.valor_compra_input.value()
        estado_conservacao = self.estado_conservacao_input.currentText()
        id_categoria = self._normalize_id(
            self.categoria_combo.currentData() if self.categoria_combo else None
        )
        id_fornecedor = self._normalize_id(
            self.fornecedor_combo.currentData() if self.fornecedor_combo else None
        )
        id_setor_local = self._normalize_id(
            self.setor_local_combo.currentData() if self.setor_local_combo else None
        )
        id_centro_custo = self._normalize_id(
            self.centro_custo_combo.currentData() if self.centro_custo_combo else None
        )
        status = self.status_combo.currentText()

        if not nome or id_categoria is None or id_setor_local is None or not status:
            QMessageBox.warning(dialog, "Cadastro", "Preencha os campos obrigatorios.")
            return

        valor_atual = valor_compra

        available_columns = self._refresh_optional_columns()
        available_columns = set(available_columns)

        quantidade = self.quantidade_input.value() if self.has_quantidade_column and self.quantidade_input else 1
        numero_nota = (self.numero_nota_input.text().strip() if self.has_numero_nota_column and self.numero_nota_input else "")

        if self.has_quantidade_column and quantidade <= 0:
            QMessageBox.warning(dialog, "Cadastro", "Informe uma quantidade valida.")
            return

        dados: Dict[str, object] = {
            "nome": nome,
            "descricao": descricao or None,
            "numero_serie": numero_serie or None,
            "data_aquisicao": data_aquisicao,
            "valor_compra": valor_compra,
            "estado_conservacao": estado_conservacao,
            "id_categoria": id_categoria,
            "id_fornecedor": id_fornecedor,
            "id_setor_local": id_setor_local,
            "status": status,
        }
        if "valor_atual" in available_columns:
            dados["valor_atual"] = valor_atual
        if self.has_quantidade_column and "quantidade" in available_columns:
            dados["quantidade"] = quantidade
        if self.has_numero_nota_column and "numero_nota" in available_columns:
            dados["numero_nota"] = numero_nota or None

        try:
            # Tenta extrair lista de números de série, se houver "a,b,c,..."
            serial_list = None
            cleaned_serial_base: Optional[str] = dados.get("numero_serie") or None
            if numero_serie and ("," in numero_serie):
                parts = [s.strip() for s in numero_serie.split(",") if s.strip()]
                if parts:
                    cleaned_serial_base = parts[0]
                if len(parts) == quantidade and len(set(parts)) == len(parts):
                    serial_list = parts
            dados["numero_serie"] = cleaned_serial_base or None

            enforce_unique_serial = bool(cleaned_serial_base and not serial_list)

            if self.has_quantidade_column and quantidade > 1:
                ids = self.db_manager.create_patrimonios_bulk(
                    dados,
                    quantidade,
                    numero_series=serial_list,
                    enforce_unique_serial=enforce_unique_serial,
                )
                if ids:
                    self._persistir_centros_custo(ids, id_centro_custo, dialog)
                    numeros = self.db_manager.get_patrimonio_codigos(ids)
                    numeros_lista = [
                        self._format_codigo(row.get("numero_patrimonio"))
                        for row in numeros
                        if row.get("numero_patrimonio") not in (None, "")
                    ]
                    detalhe = ""
                    if numeros_lista:
                        if len(numeros_lista) == 1:
                            detalhe = f" Número gerado: {numeros_lista[0]}."
                        else:
                            detalhe = f" Números gerados: {numeros_lista[0]} - {numeros_lista[-1]}."
                    QMessageBox.information(dialog, "Cadastro",
                        f"{len(ids)} patrimônios cadastrados com sucesso.{detalhe}")
                    dialog.accept()
                    self.load_patrimonios()
                    self._trigger_dashboard_update()
                    return
                else:
                    QMessageBox.warning(dialog, "Cadastro",
                        "Nenhum patrimônio foi criado (bulk retornou vazio).")
                    return
            else:
                novo_id = self.db_manager.create_patrimonio(dados)
                if novo_id:
                    self._persistir_centros_custo([novo_id], id_centro_custo, dialog)
                    codigo = self.db_manager.get_patrimonio_codigos([novo_id])
                    numero_texto = ""
                    if codigo and codigo[0].get("numero_patrimonio") not in (None, ""):
                        numero_texto = f" Número gerado: {self._format_codigo(codigo[0].get('numero_patrimonio'))}."
                    QMessageBox.information(dialog, "Cadastro",
                        f"Patrimônio cadastrado com sucesso.{numero_texto}")
                    dialog.accept()
                    self.load_patrimonios()
                    self._trigger_dashboard_update()
                    return
                else:
                    QMessageBox.warning(dialog, "Cadastro",
                        "Não foi possível criar o patrimônio.")
                    return
        except Exception as exc:
            QMessageBox.critical(dialog, "Cadastro",
                f"Falha ao cadastrar patrimônio(s).\n{exc}")
            return

                                                                             
                       
                                                                             
    def editar_patrimonio(self) -> None:
        if not self._ensure_management_privileges():
            return

        if not self.table:
            return

        selected_rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not selected_rows:
            QMessageBox.warning(self.ui, "Edicao", "Selecione um patrimonio para editar.")
            return

        row_index = selected_rows[0].row()
        id_item = self.table.item(row_index, 0)
        if not id_item:
            QMessageBox.critical(self.ui, "Edicao", "Nao foi possivel identificar o patrimonio selecionado.")
            return

        try:
            id_patrimonio = int(id_item.text())
        except (TypeError, ValueError):
            QMessageBox.critical(self.ui, "Edicao", "Identificador de patrimonio invalido.")
            return

        available_columns = self._refresh_optional_columns()

        select_columns = [
            "nome",
            "descricao",
            "numero_serie",
            "numero_patrimonio" if "numero_patrimonio" in available_columns else "NULL AS numero_patrimonio",
            "data_aquisicao",
            "valor_compra",
            "estado_conservacao",
            "id_categoria",
            "id_fornecedor",
            "id_setor_local",
            "status",
        ]
        if self.has_quantidade_column:
            select_columns.append("quantidade")
        else:
            select_columns.append("NULL AS quantidade")
        if self.has_numero_nota_column:
            select_columns.append("numero_nota")
        else:
            select_columns.append("NULL AS numero_nota")

        select_clause = ",\n                ".join(select_columns)

        patrimonio = self.db_manager.fetch_one(
            f"""
            SELECT {select_clause}
            FROM patrimonios
            WHERE id_patrimonio = %s
            """,
            (id_patrimonio,),
        )

        if not patrimonio:
            QMessageBox.critical(self.ui, "Edicao", "Patrimonio nao encontrado.")
            return

        dialog = QDialog(self.ui)
        dialog.setWindowTitle("Editar patrimonio")

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        numero_label = QLabel(self._format_codigo(patrimonio.get("numero_patrimonio")))
        numero_label.setStyleSheet("font-weight: bold;")
        form_layout.addRow("Número patrimonial:", numero_label)

        self.nome_input = QLineEdit(patrimonio.get("nome") or "")
        self.descricao_input = QLineEdit(patrimonio.get("descricao") or "")
        self.numero_serie_input = QLineEdit(patrimonio.get("numero_serie") or "")

        data_original = patrimonio.get("data_aquisicao")
        data_qdate = QDate.currentDate()
        if isinstance(data_original, (datetime.date, datetime.datetime)):
            if isinstance(data_original, datetime.datetime):
                data_original = data_original.date()
            data_qdate = QDate(data_original.year, data_original.month, data_original.day)
        elif isinstance(data_original, str) and data_original:
            try:
                parsed = datetime.datetime.strptime(data_original, "%Y-%m-%d").date()
                data_qdate = QDate(parsed.year, parsed.month, parsed.day)
            except ValueError:
                pass

        self.data_aquisicao_input = QDateEdit(data_qdate)
        self.data_aquisicao_input.setCalendarPopup(True)

        self.valor_compra_input = QDoubleSpinBox()
        self.valor_compra_input.setPrefix("R$ ")
        self.valor_compra_input.setDecimals(2)
        self.valor_compra_input.setMaximum(999_999_999.99)
        valor_compra = patrimonio.get("valor_compra") or 0
        self.valor_compra_input.setValue(float(valor_compra))

        self.estado_conservacao_input = QComboBox()
        self.estado_conservacao_input.addItems(self.ESTADO_CONSERVACAO_OPTIONS)
        estado = patrimonio.get("estado_conservacao")
        if estado:
            index_estado = self.estado_conservacao_input.findText(str(estado))
            if index_estado >= 0:
                self.estado_conservacao_input.setCurrentIndex(index_estado)

        self.categoria_combo = QComboBox()
        self.fornecedor_combo = QComboBox()
        self.setor_local_combo = QComboBox()
        self.centro_custo_combo = QComboBox()
        self.status_combo = QComboBox()
        self.status_combo.addItems(self.STATUS_OPTIONS)

        status_atual = patrimonio.get("status")
        if status_atual:
            index_status = self.status_combo.findText(str(status_atual))
            if index_status >= 0:
                self.status_combo.setCurrentIndex(index_status)

        centro_atual_id: Optional[int] = None
        try:
            centros_do_patrimonio = self.db_manager.list_centros_custo_por_patrimonio(id_patrimonio)
        except Exception as exc:  # pragma: no cover - feedback user-facing
            QMessageBox.warning(
                self.ui,
                "Centro de Custo",
                f"Nao foi possivel carregar os centros de custo vinculados.\n{exc}",
            )
            centros_do_patrimonio = []
        if centros_do_patrimonio:
            preferencia_ativa = next(
                (c for c in centros_do_patrimonio if c.get("ativo") not in (False, 0, "0", "False")),
                centros_do_patrimonio[0],
            )
            centro_atual_id = self._normalize_id(preferencia_ativa.get("id_centro_custo"))

        self._populate_categoria_combo(
            self.categoria_combo,
            "Selecione uma Categoria",
            patrimonio.get("id_categoria"),
        )
        self._populate_fk_combo(
            self.fornecedor_combo,
            "Selecione um Fornecedor",
            "SELECT id_fornecedor, nome_fornecedor FROM fornecedores ORDER BY nome_fornecedor",
            "id_fornecedor",
            "nome_fornecedor",
            patrimonio.get("id_fornecedor"),
        )
        self._populate_fk_combo(
            self.setor_local_combo,
            "Selecione um Setor/Local",
            "SELECT id_setor_local, nome_setor_local FROM setores_locais ORDER BY nome_setor_local",
            "id_setor_local",
            "nome_setor_local",
            patrimonio.get("id_setor_local"),
        )
        self._populate_centros_custo_combo(
            self.centro_custo_combo,
            "Selecione um Centro de Custo",
            centro_atual_id,
            include_inativos=True,
        )

        self.quantidade_input = QSpinBox()
        self.quantidade_input.setMinimum(1)
        self.quantidade_input.setMaximum(1_000_000)
        quantidade_atual = patrimonio.get("quantidade") if self.has_quantidade_column else None
        try:
            quantidade_valor = int(quantidade_atual) if quantidade_atual is not None else 1
        except (TypeError, ValueError):
            quantidade_valor = 1
        if quantidade_valor <= 0:
            quantidade_valor = 1
        self.quantidade_input.setValue(quantidade_valor)
        if not self.has_quantidade_column:
            self.quantidade_input.setToolTip(
                "Coluna 'quantidade' nao disponivel na tabela patrimonios (valor nao sera salvo)."
            )

        numero_nota_atual = patrimonio.get("numero_nota") if self.has_numero_nota_column else None
        self.numero_nota_input = QLineEdit(str(numero_nota_atual or ""))
        self.numero_nota_input.setMaxLength(50)
        if not self.has_numero_nota_column:
            self.numero_nota_input.setToolTip(
                "Coluna 'numero_nota' nao disponivel na tabela patrimonios (valor nao sera salvo)."
            )

        form_layout.addRow("Nome:", self.nome_input)
        form_layout.addRow("Descricao:", self.descricao_input)
        form_layout.addRow("Numero de Serie:", self.numero_serie_input)
        form_layout.addRow("Data de Aquisicao:", self.data_aquisicao_input)
        form_layout.addRow("Valor de Compra:", self.valor_compra_input)
        form_layout.addRow("Quantidade:", self.quantidade_input)
        form_layout.addRow("Numero da Nota:", nota_layout)
        form_layout.addRow("Estado de Conservacao:", self.estado_conservacao_input)
        form_layout.addRow("Categoria:", self.categoria_combo)
        form_layout.addRow("Fornecedor:", fornecedor_layout)
        form_layout.addRow("Setor/Local:", self.setor_local_combo)
        form_layout.addRow("Centro de Custo:", self.centro_custo_combo)
        form_layout.addRow("Status:", self.status_combo)

        btn_salvar = QPushButton("Salvar alteracoes")
        btn_salvar.clicked.connect(lambda: self.atualizar_patrimonio(dialog, id_patrimonio))                          

        layout.addLayout(form_layout)
        layout.addWidget(btn_salvar)
        dialog.setLayout(layout)
        dialog.exec()

    def atualizar_patrimonio(self, dialog: QDialog, id_patrimonio: int) -> None:
        nome = self.nome_input.text().strip()
        descricao = self.descricao_input.text().strip()
        numero_serie = self.numero_serie_input.text().strip()
        data_aquisicao = self.data_aquisicao_input.date().toString("yyyy-MM-dd")
        valor_compra = self.valor_compra_input.value()
        estado_conservacao = self.estado_conservacao_input.currentText()
        id_categoria = self._normalize_id(
            self.categoria_combo.currentData() if self.categoria_combo else None
        )
        id_fornecedor = self._normalize_id(
            self.fornecedor_combo.currentData() if self.fornecedor_combo else None
        )
        id_setor_local = self._normalize_id(
            self.setor_local_combo.currentData() if self.setor_local_combo else None
        )
        id_centro_custo = self._normalize_id(
            self.centro_custo_combo.currentData() if self.centro_custo_combo else None
        )
        status = self.status_combo.currentText()

        if not nome or not numero_serie or id_categoria is None or id_setor_local is None or not status:
            QMessageBox.warning(dialog, "Edicao", "Preencha os campos obrigatorios.")
            return

        available_columns = set(self._refresh_optional_columns())
        quantidade = self.quantidade_input.value() if self.has_quantidade_column and self.quantidade_input else 1
        numero_nota = (self.numero_nota_input.text().strip() if self.has_numero_nota_column and self.numero_nota_input else "")

        if self.has_quantidade_column and quantidade <= 0:
            QMessageBox.warning(dialog, "Edicao", "Informe uma quantidade valida.")
            return

        dados: Dict[str, object] = {
            "nome": nome,
            "descricao": descricao or None,
            "numero_serie": numero_serie or None,
            "data_aquisicao": data_aquisicao,
            "valor_compra": valor_compra,
            "estado_conservacao": estado_conservacao,
            "id_categoria": id_categoria,
            "id_fornecedor": id_fornecedor,
            "id_setor_local": id_setor_local,
            "status": status,
        }
        if "valor_atual" in available_columns:
            dados["valor_atual"] = valor_compra
        if self.has_quantidade_column and "quantidade" in available_columns:
            dados["quantidade"] = quantidade
        if self.has_numero_nota_column and "numero_nota" in available_columns:
            dados["numero_nota"] = numero_nota or None

        try:
            atualizado = self.db_manager.update_patrimonio(id_patrimonio, dados)
        except Exception as exc:
            QMessageBox.critical(dialog, "Edicao", f"Falha ao atualizar patrimonio.\n{exc}")
            return

        if atualizado:
            self._persistir_centros_custo([id_patrimonio], id_centro_custo, dialog)
            QMessageBox.information(dialog, "Edicao", "Patrimonio atualizado com sucesso.")
            dialog.accept()
            self.load_patrimonios()
            self._trigger_dashboard_update()
        else:
            QMessageBox.critical(
                dialog,
                "Edicao",
                "Falha ao atualizar patrimonio. Verifique os dados informados.",
            )

                                                                             
                      
                                                                             
    def registrar_movimentacao(
        self,
        id_patrimonio: int,
        tipo: str,
        origem: Optional[str],
        destino: Optional[str],
        observacoes: str = "",
    ) -> bool:
        id_usuario = 1                                                         
        query = (
            "INSERT INTO movimentacoes (id_patrimonio, id_usuario, tipo_movimentacao, origem, destino, observacoes) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        params = (id_patrimonio, id_usuario, tipo, origem, destino, observacoes)
        return bool(self.db_manager.execute_query(query, params))

    def excluir_patrimonio(self) -> None:
        if not self._ensure_management_privileges():
            self._update_buttons_state()
            return

        if not self.table:
            return

        selected_rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not selected_rows:
            QMessageBox.warning(self.ui, "Baixa", "Selecione um patrimonio para baixar.")
            return

        row_index = selected_rows[0].row()
        id_item = self.table.item(row_index, 0)
        nome_item = self.table.item(row_index, 1)
        local_item = self.table.item(row_index, 11)

        if not id_item or not nome_item:
            QMessageBox.critical(self.ui, "Baixa", "Dados do patrimonio selecionado estao incompletos.")
            return

        try:
            id_patrimonio = int(id_item.text())
        except (TypeError, ValueError):
            QMessageBox.critical(self.ui, "Baixa", "Identificador de patrimonio invalido.")
            return

        nome_patrimonio = nome_item.text()
        local_atual = local_item.text() if local_item else None

        try:
            dependencies = self.db_manager.get_patrimonio_dependencies(id_patrimonio)
        except Exception as exc:
            QMessageBox.critical(
                self.ui,
                "Baixa",
                f"Falha ao verificar vínculos do patrimônio.\n{exc}",
            )
            return

        master_user = DatabaseManager.has_master_privileges(self.current_user)
        if dependencies and not master_user:
            details = "\n".join(
                f"• {label}: {count} registro(s) relacionado(s)" for label, count in dependencies.items()
            )
            QMessageBox.warning(
                self.ui,
                "Baixa",
                "Nao e possivel excluir o patrimonio porque existem vinculos ativos:\n" + details,
            )
            return

        if dependencies and master_user:
            details = "\n".join(
                f"• {label}: {count} registro(s) relacionado(s)" for label, count in dependencies.items()
            )
            confirm_msg = (
                f"O patrimônio '{nome_patrimonio}' possui vínculos:\n{details}\n\n"
                "Deseja remover mesmo assim? Todos os vínculos serão apagados."
            )
        else:
            confirm_msg = f"Deseja realmente baixar o patrimonio '{nome_patrimonio}' (ID: {id_patrimonio})?"

        resposta = QMessageBox.question(
            self.ui,
            "Confirmacao",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if resposta != QMessageBox.Yes:
            self._update_buttons_state()
            return

        try:
            if dependencies and master_user:
                ok = self.db_manager.delete_patrimonio_force(id_patrimonio)
            else:
                ok = self.db_manager.delete_patrimonio(id_patrimonio)
            if not ok:
                QMessageBox.warning(
                    self.ui,
                    "Baixa",
                    "Nao foi possivel excluir o patrimonio. Verifique se existem registros relacionados.",
                )
                return
        except Exception as exc:
            QMessageBox.critical(self.ui, "Baixa", f"Falha ao excluir patrimonio.\n{exc}")
            return

        QMessageBox.information(self.ui, "Baixa", "Patrimonio removido com sucesso.")

        self.load_patrimonios()
        self._trigger_dashboard_update()
        self._update_buttons_state()

                                                                             
                 
                                                                             
    def calcular_depreciacao(self, data_aquisicao: object, valor_compra: float) -> float:
        if not valor_compra:
            return 0.0

        if isinstance(data_aquisicao, datetime.datetime):
            data_base = data_aquisicao.date()
        elif isinstance(data_aquisicao, datetime.date):
            data_base = data_aquisicao
        elif isinstance(data_aquisicao, str) and data_aquisicao:
            try:
                data_base = datetime.datetime.strptime(data_aquisicao, "%Y-%m-%d").date()
            except ValueError:
                return float(valor_compra)
        else:
            return float(valor_compra)

        hoje = datetime.date.today()
        dias_em_uso = (hoje - data_base).days
        if dias_em_uso <= 0:
            return float(valor_compra)

        vida_util_anos = 5
        taxa_anual = 1 / vida_util_anos
        anos_passados = dias_em_uso / 365.25
        depreciacao_acumulada = float(valor_compra) * taxa_anual * anos_passados
        depreciacao_acumulada = min(depreciacao_acumulada, float(valor_compra))
        return max(0.0, float(valor_compra) - depreciacao_acumulada)

    def atualizar_valores_depreciados(self) -> None:
        if not self.has_valor_atual_column:
            return

        patrimonios = self.db_manager.fetch_all(
            "SELECT id_patrimonio, valor_compra, data_aquisicao FROM patrimonios WHERE status = 'ativo'"
        )
        for item in patrimonios:
            id_patrimonio = item.get("id_patrimonio")
            valor_compra = item.get("valor_compra")
            data_aquisicao = item.get("data_aquisicao")

            if id_patrimonio is None or valor_compra is None:
                continue

            valor_atual = self.calcular_depreciacao(data_aquisicao, float(valor_compra))
            self.db_manager.execute_query(
                "UPDATE patrimonios SET valor_atual = %s WHERE id_patrimonio = %s",
                (valor_atual, id_patrimonio),
            )

                                                                             
                       
                                                                             
    def refresh(self) -> None:
        self.populate_comboboxes()
        self.load_patrimonios()

    def _abrir_cadastro_rapido_fornecedor(self, parent_dialog):
        """Abre diálogo de cadastro rápido de fornecedor"""
        dialog = QuickCreateFornecedorDialog(parent_dialog, self.db_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fornecedor_id = dialog.get_fornecedor_id()
            if fornecedor_id:
                # Recarregar combo de fornecedores
                self._populate_fk_combo(
                    self.fornecedor_combo,
                    "Selecione um Fornecedor",
                    "SELECT id_fornecedor, nome_fornecedor FROM fornecedores ORDER BY nome_fornecedor",
                    "id_fornecedor",
                    "nome_fornecedor",
                )
                # Selecionar o fornecedor recém-criado
                for i in range(self.fornecedor_combo.count()):
                    if self.fornecedor_combo.itemData(i) == fornecedor_id:
                        self.fornecedor_combo.setCurrentIndex(i)
                        break
    
    def _abrir_cadastro_rapido_nota(self, parent_dialog):
        """Abre diálogo de cadastro rápido de nota fiscal"""
        dialog = QuickCreateNotaFiscalDialog(parent_dialog, self.db_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            numero_nota = dialog.get_numero_nota()
            if numero_nota:
                # Atualizar campo de número de nota
                self.numero_nota_input.setText(numero_nota)
                QMessageBox.information(
                    parent_dialog,
                    "Nota Fiscal Criada",
                    f"Nota fiscal {numero_nota} criada com sucesso!\n\n"
                    "Os itens da nota poderão ser adicionados depois na tela de Notas Fiscais."
                )

    
    def abrir_importacao_massa(self) -> None:
        """Abre diálogo de importação em massa de patrimônios"""
        from backend.controllers.import_controller import ImportPatrimonioDialog
        
        dialog = ImportPatrimonioDialog(self.db_manager, self.current_user, self.ui)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Recarregar lista de patrimônios
            self.load_patrimonios()
            
            # Atualizar dashboard se disponível
            if self._dashboard_updater:
                self._dashboard_updater()
            
            QMessageBox.information(
                self.ui,
                "Importação Concluída",
                "Patrimônios importados com sucesso!\n\nA lista foi atualizada."
            )
