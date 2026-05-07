"""Controlador responsável pela tela de depreciação."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from backend.database.database_manager import DatabaseManager


class DepreciacaoController:
    """Faz o intermédio entre a UI de depreciação e o banco de dados."""

    TABLE_HEADERS: List[str] = [
        "Patrimônio",
        "Competência",
        "Valor",
        "Acumulado",
    ]

    def __init__(self, widget: QWidget, db_manager: DatabaseManager, current_user=None) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user

        self._table: Optional[QTableWidget] = self.widget.findChild(QTableWidget, "tbl_dep")
        self._search_input: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_patrimonio")
        self._category_combo: Optional[QComboBox] = self.widget.findChild(QComboBox, "cb_categoria")

        self._setup_table()
        self._connect_signals()
        self._populate_categories()
        self.refresh()

                                                                          
                   
    def _setup_table(self) -> None:
        if not self._table:
            print("[DepreciacaoController] Tabela 'tbl_dep' não encontrada na UI.")
            return
        self._table.setColumnCount(len(self.TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)

    def _connect_signals(self) -> None:
        btn_filtrar = self.widget.findChild(QPushButton, "btn_filtrar")
        if btn_filtrar:
            btn_filtrar.clicked.connect(self.apply_filters)

        btn_limpar = self.widget.findChild(QPushButton, "btn_limpar")
        if btn_limpar:
            btn_limpar.clicked.connect(self.clear_filters)

        if self._search_input:
            self._search_input.returnPressed.connect(self.apply_filters)

        if self._category_combo:
            self._category_combo.currentIndexChanged.connect(self.apply_filters)

    def _populate_categories(self) -> None:
        if not self._category_combo:
            return

        try:
            categorias = self.db_manager.list_categorias()
        except Exception as exc:                                        
            QMessageBox.warning(
                self.widget,
                "Depreciação",
                f"Não foi possível carregar as categorias.\n{exc}",
            )
            return

        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        self._category_combo.addItem("Categoria", None)
        for categoria in categorias:
            nome = categoria.get("nome_categoria")
            categoria_id = categoria.get("id_categoria")
            if nome is None or categoria_id is None:
                continue
            self._category_combo.addItem(str(nome), categoria_id)
        self._category_combo.blockSignals(False)
        self._category_combo.setCurrentIndex(0)

                                                                          
                
    def refresh(self) -> None:
        self.apply_filters()

    def apply_filters(self) -> None:
        filters = self._collect_filters()
        try:
            linhas = self.db_manager.calcular_depreciacao(filters=filters)
        except Exception as exc:                                                 
            QMessageBox.warning(
                self.widget,
                "Depreciação",
                f"Não foi possível calcular a depreciação.\n{exc}",
            )
            return

        self._populate_table(linhas)

    def clear_filters(self) -> None:
        if self._search_input:
            self._search_input.clear()
        if self._category_combo:
            self._category_combo.blockSignals(True)
            self._category_combo.setCurrentIndex(0)
            self._category_combo.blockSignals(False)
        self.refresh()

                                                                          
             
    def _collect_filters(self) -> Dict[str, Optional[str]]:
        filters: Dict[str, Optional[str]] = {}
        if self._search_input:
            texto = self._search_input.text().strip()
            if texto:
                filters["texto"] = texto
        if self._category_combo:
            categoria_id = self._category_combo.currentData()
            if categoria_id:
                filters["id_categoria"] = categoria_id
        return filters

    def _populate_table(self, linhas: List[Dict[str, object]]) -> None:
        if not self._table:
            return

        self._table.setRowCount(0)

        if not linhas:
            return

        for row_index, linha in enumerate(linhas):
            self._table.insertRow(row_index)
            patrimonio_item = QTableWidgetItem(str(linha.get("patrimonio", "-")))
            competencia_item = QTableWidgetItem(str(linha.get("competencia", "-")))

            valor_periodo = linha.get("valor_periodo") or 0.0
            valor_item = QTableWidgetItem(f"R$ {float(valor_periodo):.2f}")
            valor_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            acumulado = linha.get("valor_acumulado") or 0.0
            acumulado_item = QTableWidgetItem(f"R$ {float(acumulado):.2f}")
            acumulado_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self._table.setItem(row_index, 0, patrimonio_item)
            self._table.setItem(row_index, 1, competencia_item)
            self._table.setItem(row_index, 2, valor_item)
            self._table.setItem(row_index, 3, acumulado_item)

