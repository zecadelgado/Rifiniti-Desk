from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from backend.database.database_manager import DatabaseManager


class AnexosController:
    """Controlador da tela de anexos."""

    TABLE_HEADERS: List[str] = [
        "Entidade",
        "ID",
        "Nome",
        "Caminho",
        "Tamanho",
        "MIME",
        "Criado em",
    ]

    def __init__(self, widget: QWidget, db_manager: DatabaseManager, current_user=None) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user

        self.cb_entidade: Optional[QComboBox] = self.widget.findChild(QComboBox, "cb_entidade")
        self.sb_entidade_id: Optional[QSpinBox] = self.widget.findChild(QSpinBox, "sb_entidade_id")
        self.le_arquivo: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_arquivo")
        self.table: Optional[QTableWidget] = self.widget.findChild(QTableWidget, "tbl_anexos")

        self.btn_add: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_add")
        self.btn_remover: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_remover")
        self.btn_atualizar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_atualizar")

        self._setup_table()
        self._connect_signals()
        self.refresh()

                                                                          
    def _setup_table(self) -> None:
        if not self.table:
            return
        self.table.setColumnCount(len(self.TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        header = self.table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)
        vheader = self.table.verticalHeader()
        if vheader:
            vheader.setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

    def _connect_signals(self) -> None:
        if self.cb_entidade:
            self.cb_entidade.currentTextChanged.connect(self._on_entidade_changed)
        if self.btn_add:
            self.btn_add.clicked.connect(self._adicionar_anexo)
        if self.btn_remover:
            self.btn_remover.clicked.connect(self._remover_anexo)
        if self.btn_atualizar:
            self.btn_atualizar.clicked.connect(self.refresh)
        if self.sb_entidade_id:
            self.sb_entidade_id.valueChanged.connect(self.refresh)

                                                                          
    def refresh(self) -> None:
        self._carregar_anexos()

    def _carregar_anexos(self) -> None:
        if not self.table:
            return
        entidade = self._current_entidade()
        patrimonio_id = self.sb_entidade_id.value() if self.sb_entidade_id else 0
        rows = []
        mensagem: Optional[str] = None
        if patrimonio_id > 0:
            try:
                rows = self.db_manager.list_anexos(entidade, patrimonio_id)
            except Exception as exc:                                       
                QMessageBox.critical(
                    self.widget,
                    "Anexos",
                    f"Não foi possível carregar os anexos.\n{exc}",
                )
                mensagem = "Não foi possível carregar os anexos."
            if not rows and mensagem is None:
                mensagem = "Nenhum anexo encontrado para o patrimônio informado."
        else:
            mensagem = "Informe o ID do patrimônio para visualizar os anexos."

        self._preencher_tabela(rows, mensagem)

    def _preencher_tabela(
        self, rows: List[dict], mensagem: Optional[str] = None
    ) -> None:
        if not self.table:
            return
        self.table.setRowCount(0)
        if not rows:
            self.table.setRowCount(1)
            texto = mensagem or "Nenhum anexo encontrado."
            self._set_item(0, 0, texto)
            for column in range(1, len(self.TABLE_HEADERS)):
                self._set_item(0, column, "")
            self.table.resizeColumnsToContents()
            return

        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            entidade_row = row.get("entidade") or self._current_entidade()
            entidade_id_row = (
                row.get("entidade_id")
                or row.get("id_patrimonio")
                or row.get("id_manutencao")
                or row.get("id_nota_fiscal")
            )
            nome = row.get("nome_arquivo") or row.get("nome") or row.get("arquivo")
            caminho = (
                row.get("caminho_arquivo")
                or row.get("caminho")
                or row.get("caminho_arquivo_nf")
            )
            tamanho = row.get("tamanho_arquivo") or row.get("tamanho")
            mime = row.get("tipo_arquivo") or row.get("mime")
            criado = row.get("data_upload") or row.get("data_criacao")

            metadata = {
                "id_anexo": row.get("id_anexo"),
                "entidade": entidade_row,
                "entidade_id": entidade_id_row,
            }

            self._set_item(row_index, 0, entidade_row, metadata=metadata)
            self._set_item(row_index, 1, str(entidade_id_row or "-"))
            self._set_item(row_index, 2, str(nome or "-"))
            self._set_item(row_index, 3, str(caminho or "-"))
            self._set_item(row_index, 4, self._formatar_tamanho(tamanho))
            self._set_item(row_index, 5, str(mime or "-"))
            self._set_item(row_index, 6, str(criado or "-"))
        self.table.resizeColumnsToContents()

    def _set_item(
        self,
        row: int,
        column: int,
        text: str,
        metadata: Optional[dict] = None,
    ) -> None:
        if not self.table:
            return
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if metadata is not None:
            item.setData(Qt.ItemDataRole.UserRole, metadata)
        self.table.setItem(row, column, item)

                                                                          
    def _adicionar_anexo(self) -> None:
        entidade = self._current_entidade()
        if not self.sb_entidade_id:
            return
        entidade_id = self.sb_entidade_id.value()
        if entidade_id <= 0:
            QMessageBox.warning(self.widget, "Anexos", "Informe o ID da entidade.")
            return
        arquivo_path = self.le_arquivo.text().strip() if self.le_arquivo else ""
        if not arquivo_path:
            arquivo_path, _ = QFileDialog.getOpenFileName(
                self.widget,
                "Selecionar arquivo",
                str(Path.home()),
            )
            if not arquivo_path:
                return
            if self.le_arquivo:
                self.le_arquivo.setText(arquivo_path)
        path = Path(arquivo_path)
        if not path.exists() or not path.is_file():
            QMessageBox.warning(
                self.widget,
                "Anexos",
                "Arquivo inválido selecionado.",
            )
            return
        tamanho = path.stat().st_size
        mime, _ = mimetypes.guess_type(str(path))

        dados = {
            "entidade_id": entidade_id,
            "nome_arquivo": path.name,
            "caminho_arquivo": str(path),
            "tipo_arquivo": mime or "application/octet-stream",
            "tamanho_arquivo": tamanho,
        }
        try:
            self.db_manager.create_anexo(entidade, dados)
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Anexos", f"Não foi possível salvar o anexo.\n{exc}")
            return
        QMessageBox.information(self.widget, "Anexos", "Anexo salvo com sucesso.")
        self.refresh()

    def _remover_anexo(self) -> None:
        # Verificar permissão de admin/master
        if not DatabaseManager.has_admin_privileges(self.current_user):
            QMessageBox.warning(
                self.widget,
                "Anexos",
                "Ação permitida apenas para administradores ou usuários master.",
            )
            return
        
        if not self.table:
            return
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self.widget, "Anexos", "Selecione um anexo para remover.")
            return
        item = selected[0]
        metadata = item.data(Qt.ItemDataRole.UserRole) or {}
        anexo_id = metadata.get("id_anexo")
        entidade = metadata.get("entidade") or self._current_entidade()
        if not anexo_id or not entidade:
            QMessageBox.warning(self.widget, "Anexos", "Não foi possível identificar o anexo.")
            return
        resposta = QMessageBox.question(
            self.widget,
            "Anexos",
            "Deseja realmente remover o anexo selecionado?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db_manager.delete_anexo(str(entidade), int(anexo_id))
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Anexos", f"Não foi possível remover o anexo.\n{exc}")
            return
        self.refresh()

                                                                          
    @staticmethod
    def _formatar_tamanho(tamanho: Optional[object]) -> str:
        try:
            valor = float(tamanho)
        except (TypeError, ValueError):
            return "-"
        unidades = ["B", "KB", "MB", "GB"]
        indice = 0
        while valor >= 1024 and indice < len(unidades) - 1:
            valor /= 1024
            indice += 1
        return f"{valor:.2f} {unidades[indice]}"

    def _current_entidade(self) -> str:
        if self.cb_entidade:
            texto = self.cb_entidade.currentText().strip().lower()
            if texto:
                return texto
        return "patrimonio"

    def _on_entidade_changed(self) -> None:
        if self.le_arquivo:
            self.le_arquivo.clear()
        self.refresh()
