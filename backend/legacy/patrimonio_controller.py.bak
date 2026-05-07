from __future__ import annotations

import datetime
from typing import Optional, Sequence

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database_manager import DatabaseManager


class PatrimonioController(QWidget):
    """Controller responsavel por orquestrar a tela de patrimonio."""

    TABLE_HEADERS: Sequence[str] = (
        "ID",
        "Nome",
        "Descricao",
        "Numero de Serie",
        "Data de Aquisicao",
        "Valor Compra",
        "Valor Atual",
        "Categoria",
        "Fornecedor",
        "Setor/Local",
        "Status",
    )

    STATUS_OPTIONS: Sequence[str] = ("ativo", "baixado", "em_manutencao", "desaparecido")
    ESTADO_CONSERVACAO_OPTIONS: Sequence[str] = ("novo", "bom", "regular", "ruim")

    def __init__(self, ui_widget: QWidget, db_manager: DatabaseManager) -> None:
        super().__init__()
        self.ui = ui_widget
        self.db_manager = db_manager

        self.table: Optional[QTableWidget] = self.ui.findChild(QTableWidget, "tbl_patrimonio")
        self.search_input: Optional[QLineEdit] = self.ui.findChild(QLineEdit, "le_busca")
        self.category_filter: Optional[QComboBox] = self.ui.findChild(QComboBox, "cb_categoria")
        self.sector_filter: Optional[QComboBox] = self.ui.findChild(QComboBox, "cb_setor")
        self.status_filter: Optional[QComboBox] = self.ui.findChild(QComboBox, "cb_status")

        if self.table:
            self.table.setColumnCount(len(self.TABLE_HEADERS))
            self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)

        self.has_valor_atual_column = self._check_valor_atual_column()

        self._setup_ui_connections()
        self.populate_comboboxes()
        self.load_patrimonios()

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #
    def _setup_ui_connections(self) -> None:
        button_map = {
            "btn_novo": self.abrir_cadastro_patrimonio,
            "btn_editar": self.editar_patrimonio,
            "btn_excluir": self.excluir_patrimonio,
            "btn_filtrar": self.load_patrimonios,
            "btn_limpar": self.limpar_filtros,
        }

        for object_name, handler in button_map.items():
            button = self.ui.findChild(QPushButton, object_name)
            if button is None:
                print(f"[PatrimonioController] Botao '{object_name}' nao encontrado na UI.")
                continue
            button.clicked.connect(handler)  # type: ignore[arg-type]

    def _check_valor_atual_column(self) -> bool:
        try:
            result = self.db_manager.fetch_one("SHOW COLUMNS FROM patrimonios LIKE %s", ("valor_atual",))
            return bool(result)
        except Exception as exc:  # pragma: no cover - apenas log de seguranca
            print(f"[PatrimonioController] Falha ao verificar coluna valor_atual: {exc}")
            return False

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
            value = row.get(value_key)
            label = row.get(label_key)
            if value is None or label is None:
                continue
            combo.addItem(str(label), value)

        if current_value is not None:
            index = combo.findData(current_value)
            if index >= 0:
                combo.setCurrentIndex(index)

    @staticmethod
    def _format_currency(value: Optional[float]) -> str:
        try:
            return f"R$ {float(value):.2f}"
        except (TypeError, ValueError):
            return "R$ 0.00"

    @staticmethod
    def _format_date(value: Optional[datetime.date]) -> str:
        if value is None:
            return "-"
        if isinstance(value, datetime.datetime):
            value = value.date()
        return value.strftime("%d/%m/%Y")

    # --------------------------------------------------------------------- #
    # Combos e filtros
    # --------------------------------------------------------------------- #
    def populate_comboboxes(self) -> None:
        if self.category_filter:
            self.category_filter.clear()
            self.category_filter.addItem("Categoria", None)
            for row in self.db_manager.fetch_all("SELECT nome_categoria FROM categorias ORDER BY nome_categoria"):
                nome = row.get("nome_categoria")
                if nome:
                    self.category_filter.addItem(str(nome), nome)

        if self.sector_filter:
            self.sector_filter.clear()
            self.sector_filter.addItem("Setor", None)
            for row in self.db_manager.fetch_all(
                "SELECT nome_setor_local FROM setores_locais ORDER BY nome_setor_local"
            ):
                nome = row.get("nome_setor_local")
                if nome:
                    self.sector_filter.addItem(str(nome), nome)

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

    # --------------------------------------------------------------------- #
    # Carregamento de dados
    # --------------------------------------------------------------------- #
    def load_patrimonios(self) -> None:
        if self.has_valor_atual_column:
            self.atualizar_valores_depreciados()

        if not self.table:
            return

        query_parts = [
            "SELECT",
            "    p.id_patrimonio,",
            "    p.nome AS nome_patrimonio,",
            "    p.descricao,",
            "    p.numero_serie,",
            "    p.data_aquisicao,",
            "    p.valor_compra,",
        ]

        if self.has_valor_atual_column:
            query_parts.append("    p.valor_atual,")
        else:
            query_parts.append("    NULL AS valor_atual,")

        query_parts.extend(
            [
                "    c.nome_categoria,",
                "    f.nome_fornecedor,",
                "    sl.nome_setor_local,",
                "    p.status",
                "FROM patrimonios p",
                "LEFT JOIN categorias c ON p.id_categoria = c.id_categoria",
                "LEFT JOIN fornecedores f ON p.id_fornecedor = f.id_fornecedor",
                "LEFT JOIN setores_locais sl ON p.id_setor_local = sl.id_setor_local",
                "WHERE 1=1",
            ]
        )

        params: list[object] = []

        if self.search_input:
            busca = self.search_input.text().strip()
            if busca:
                query_parts.append(
                    "  AND (p.nome LIKE %s OR p.descricao LIKE %s OR p.numero_serie LIKE %s)"
                )
                wildcard = f"%{busca}%"
                params.extend([wildcard, wildcard, wildcard])

        if self.category_filter:
            categoria = self.category_filter.currentText()
            if categoria and categoria not in ("", "Categoria"):
                query_parts.append("  AND c.nome_categoria = %s")
                params.append(categoria)

        if self.sector_filter:
            setor = self.sector_filter.currentText()
            if setor and setor not in ("", "Setor"):
                query_parts.append("  AND sl.nome_setor_local = %s")
                params.append(setor)

        if self.status_filter:
            status = self.status_filter.currentText()
            if status and status not in ("", "Status"):
                query_parts.append("  AND p.status = %s")
                params.append(status)

        query_parts.append("ORDER BY p.nome ASC")
        query = "\n".join(query_parts)

        patrimonios = self.db_manager.fetch_all(query, tuple(params) if params else None)

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

            table_values = [
                item.get("id_patrimonio"),
                item.get("nome_patrimonio"),
                item.get("descricao"),
                item.get("numero_serie"),
                self._format_date(data_aquisicao),
                self._format_currency(valor_compra),
                self._format_currency(valor_atual),
                item.get("nome_categoria") or "-",
                item.get("nome_fornecedor") or "-",
                item.get("nome_setor_local") or "-",
                item.get("status") or "-",
            ]

            for column, value in enumerate(table_values):
                text = "" if value is None else str(value)
                self.table.setItem(row_index, column, QTableWidgetItem(text))

        self.table.resizeColumnsToContents()

    # --------------------------------------------------------------------- #
    # Dialogo de cadastro
    # --------------------------------------------------------------------- #
    def abrir_cadastro_patrimonio(self) -> None:
        dialog = QDialog(self.ui)
        dialog.setWindowTitle("Cadastrar novo patrimonio")

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.nome_input = QLineEdit()
        self.descricao_input = QLineEdit()
        self.numero_serie_input = QLineEdit()

        self.data_aquisicao_input = QDateEdit(QDate.currentDate())
        self.data_aquisicao_input.setCalendarPopup(True)

        self.valor_compra_input = QDoubleSpinBox()
        self.valor_compra_input.setPrefix("R$ ")
        self.valor_compra_input.setDecimals(2)
        self.valor_compra_input.setMaximum(999_999_999.99)

        self.estado_conservacao_input = QComboBox()
        self.estado_conservacao_input.addItems(self.ESTADO_CONSERVACAO_OPTIONS)

        self.categoria_combo = QComboBox()
        self.fornecedor_combo = QComboBox()
        self.setor_local_combo = QComboBox()
        self.status_combo = QComboBox()
        self.status_combo.addItems(self.STATUS_OPTIONS)

        self._populate_fk_combo(
            self.categoria_combo,
            "Selecione uma Categoria",
            "SELECT id_categoria, nome_categoria FROM categorias ORDER BY nome_categoria",
            "id_categoria",
            "nome_categoria",
        )
        self._populate_fk_combo(
            self.fornecedor_combo,
            "Selecione um Fornecedor",
            "SELECT id_fornecedor, nome_fornecedor FROM fornecedores ORDER BY nome_fornecedor",
            "id_fornecedor",
            "nome_fornecedor",
        )
        self._populate_fk_combo(
            self.setor_local_combo,
            "Selecione um Setor/Local",
            "SELECT id_setor_local, nome_setor_local FROM setores_locais ORDER BY nome_setor_local",
            "id_setor_local",
            "nome_setor_local",
        )

        form_layout.addRow("Nome:", self.nome_input)
        form_layout.addRow("Descricao:", self.descricao_input)
        form_layout.addRow("Numero de Serie:", self.numero_serie_input)
        form_layout.addRow("Data de Aquisicao:", self.data_aquisicao_input)
        form_layout.addRow("Valor de Compra:", self.valor_compra_input)
        form_layout.addRow("Estado de Conservacao:", self.estado_conservacao_input)
        form_layout.addRow("Categoria:", self.categoria_combo)
        form_layout.addRow("Fornecedor:", self.fornecedor_combo)
        form_layout.addRow("Setor/Local:", self.setor_local_combo)
        form_layout.addRow("Status:", self.status_combo)

        btn_salvar = QPushButton("Salvar")
        btn_salvar.clicked.connect(lambda: self.salvar_patrimonio(dialog))  # type: ignore[arg-type]

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
        id_categoria = self.categoria_combo.currentData()
        id_fornecedor = self.fornecedor_combo.currentData()
        id_setor_local = self.setor_local_combo.currentData()
        status = self.status_combo.currentText()

        if not all([nome, numero_serie, id_categoria, id_setor_local, status]):
            QMessageBox.warning(dialog, "Cadastro", "Preencha os campos obrigatorios.")
            return

        valor_atual = valor_compra

        columns = [
            "nome",
            "descricao",
            "numero_serie",
            "data_aquisicao",
            "valor_compra",
            "estado_conservacao",
            "id_categoria",
            "id_fornecedor",
            "id_setor_local",
            "status",
        ]
        params: list[object] = [
            nome,
            descricao or None,
            numero_serie,
            data_aquisicao,
            valor_compra,
            estado_conservacao,
            id_categoria,
            id_fornecedor,
            id_setor_local,
            status,
        ]

        if self.has_valor_atual_column:
            columns.insert(5, "valor_atual")
            params.insert(5, valor_atual)

        placeholders = ", ".join(["%s"] * len(columns))
        columns_sql = ", ".join(columns)

        query = f"INSERT INTO patrimonios ({columns_sql}) VALUES ({placeholders})"

        if self.db_manager.execute_query(query, tuple(params)):
            QMessageBox.information(dialog, "Cadastro", "Patrimonio cadastrado com sucesso.")
            dialog.accept()
            self.load_patrimonios()
        else:
            QMessageBox.critical(
                dialog,
                "Cadastro",
                "Falha ao cadastrar patrimonio. Verifique se o numero de serie ja existe.",
            )

    # --------------------------------------------------------------------- #
    # Dialogo de edicao
    # --------------------------------------------------------------------- #
    def editar_patrimonio(self) -> None:
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

        patrimonio = self.db_manager.fetch_one(
            """
            SELECT nome, descricao, numero_serie, data_aquisicao, valor_compra,
                   estado_conservacao, id_categoria, id_fornecedor, id_setor_local, status
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
        self.status_combo = QComboBox()
        self.status_combo.addItems(self.STATUS_OPTIONS)

        status_atual = patrimonio.get("status")
        if status_atual:
            index_status = self.status_combo.findText(str(status_atual))
            if index_status >= 0:
                self.status_combo.setCurrentIndex(index_status)

        self._populate_fk_combo(
            self.categoria_combo,
            "Selecione uma Categoria",
            "SELECT id_categoria, nome_categoria FROM categorias ORDER BY nome_categoria",
            "id_categoria",
            "nome_categoria",
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

        form_layout.addRow("Nome:", self.nome_input)
        form_layout.addRow("Descricao:", self.descricao_input)
        form_layout.addRow("Numero de Serie:", self.numero_serie_input)
        form_layout.addRow("Data de Aquisicao:", self.data_aquisicao_input)
        form_layout.addRow("Valor de Compra:", self.valor_compra_input)
        form_layout.addRow("Estado de Conservacao:", self.estado_conservacao_input)
        form_layout.addRow("Categoria:", self.categoria_combo)
        form_layout.addRow("Fornecedor:", self.fornecedor_combo)
        form_layout.addRow("Setor/Local:", self.setor_local_combo)
        form_layout.addRow("Status:", self.status_combo)

        btn_salvar = QPushButton("Salvar alteracoes")
        btn_salvar.clicked.connect(lambda: self.atualizar_patrimonio(dialog, id_patrimonio))  # type: ignore[arg-type]

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
        id_categoria = self.categoria_combo.currentData()
        id_fornecedor = self.fornecedor_combo.currentData()
        id_setor_local = self.setor_local_combo.currentData()
        status = self.status_combo.currentText()

        if not all([nome, numero_serie, id_categoria, id_setor_local, status]):
            QMessageBox.warning(dialog, "Edicao", "Preencha os campos obrigatorios.")
            return

        set_parts = [
            "nome = %s",
            "descricao = %s",
            "numero_serie = %s",
            "data_aquisicao = %s",
            "valor_compra = %s",
            "estado_conservacao = %s",
            "id_categoria = %s",
            "id_fornecedor = %s",
            "id_setor_local = %s",
            "status = %s",
        ]
        params: list[object] = [
            nome,
            descricao or None,
            numero_serie,
            data_aquisicao,
            valor_compra,
            estado_conservacao,
            id_categoria,
            id_fornecedor,
            id_setor_local,
            status,
        ]

        if self.has_valor_atual_column:
            set_parts.append("valor_atual = %s")
            params.append(valor_compra)

        params.append(id_patrimonio)

        query = f"UPDATE patrimonios SET {', '.join(set_parts)} WHERE id_patrimonio = %s"

        if self.db_manager.execute_query(query, tuple(params)):
            QMessageBox.information(dialog, "Edicao", "Patrimonio atualizado com sucesso.")
            dialog.accept()
            self.load_patrimonios()
        else:
            QMessageBox.critical(
                dialog,
                "Edicao",
                "Falha ao atualizar patrimonio. Verifique se o numero de serie ja existe.",
            )

    # --------------------------------------------------------------------- #
    # Exclusao (baixa)
    # --------------------------------------------------------------------- #
    def registrar_movimentacao(
        self,
        id_patrimonio: int,
        tipo: str,
        origem: Optional[str],
        destino: Optional[str],
        observacoes: str = "",
    ) -> bool:
        id_usuario = 1  # TODO: recuperar usuario logado quando houver contexto
        query = (
            "INSERT INTO movimentacoes (id_patrimonio, id_usuario, tipo_movimentacao, origem, destino, observacoes) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        params = (id_patrimonio, id_usuario, tipo, origem, destino, observacoes)
        return bool(self.db_manager.execute_query(query, params))

    def excluir_patrimonio(self) -> None:
        if not self.table:
            return

        selected_rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not selected_rows:
            QMessageBox.warning(self.ui, "Baixa", "Selecione um patrimonio para baixar.")
            return

        row_index = selected_rows[0].row()
        id_item = self.table.item(row_index, 0)
        nome_item = self.table.item(row_index, 1)
        local_item = self.table.item(row_index, 9)

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

        resposta = QMessageBox.question(
            self.ui,
            "Confirmacao",
            f"Deseja realmente baixar o patrimonio '{nome_patrimonio}' (ID: {id_patrimonio})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if resposta != QMessageBox.Yes:
            return

        query = "UPDATE patrimonios SET status = %s, data_baixa = %s WHERE id_patrimonio = %s"
        params = ("baixado", QDate.currentDate().toString("yyyy-MM-dd"), id_patrimonio)

        if not self.db_manager.execute_query(query, params):
            QMessageBox.critical(self.ui, "Baixa", "Falha ao atualizar status do patrimonio.")
            return

        if self.registrar_movimentacao(
            id_patrimonio,
            "baixa",
            local_atual,
            "Baixado",
            f"Baixa automatica do patrimonio {nome_patrimonio}",
        ):
            QMessageBox.information(self.ui, "Baixa", "Patrimonio baixado com sucesso.")
        else:
            QMessageBox.warning(
                self.ui,
                "Baixa",
                "Patrimonio baixado, mas nao foi possivel registrar a movimentacao.",
            )

        self.load_patrimonios()

    # --------------------------------------------------------------------- #
    # Depreciacao
    # --------------------------------------------------------------------- #
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

    # --------------------------------------------------------------------- #
    # Interface publica
    # --------------------------------------------------------------------- #
    def refresh(self) -> None:
        self.populate_comboboxes()
        self.load_patrimonios()
