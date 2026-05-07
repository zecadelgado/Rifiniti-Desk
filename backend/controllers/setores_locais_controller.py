from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QListView,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QTextEdit,
    QLineEdit,
    QWidget,
)

from backend.database.database_manager import DatabaseManager


class SetoresLocaisController:
    """Gerencia cadastros de setores/locais."""

    def __init__(self, widget: QWidget, db_manager: DatabaseManager, current_user=None) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user

        self.list_view: Optional[QListView] = self.widget.findChild(QListView, "list_setores")
        self.table: Optional[QTableView] = self.widget.findChild(QTableView, "tbl_locais")

        self.txt_setor_nome: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_setor_nome")
        self.txt_setor_responsavel: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_setor_responsavel")
        self.txt_setor_descricao: Optional[QTextEdit] = self.widget.findChild(QTextEdit, "txt_setor_descricao")

        self.txt_local_nome: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_local_nome")
        self.txt_local_andar: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_local_andar")
        self.spin_local_capacidade: Optional[QSpinBox] = self.widget.findChild(QSpinBox, "spin_local_capacidade")
        self.txt_local_descricao: Optional[QTextEdit] = self.widget.findChild(QTextEdit, "txt_local_descricao")

        self.btn_novo_setor: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_novo_setor")
        self.btn_editar_setor: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_editar_setor")
        self.btn_excluir_setor: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_excluir_setor")
        self.btn_salvar_setor: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_salvar_setor")

        self.btn_novo_local: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_novo_local")
        self.btn_editar_local: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_editar_local")
        self.btn_excluir_local: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_excluir_local")
        self.btn_salvar_local: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_salvar_local")

        self._list_model = QStandardItemModel(self.list_view)
        if self.list_view:
            self.list_view.setModel(self._list_model)

        self._table_model = QStandardItemModel(self.table)
        if self.table:
            self.table.setModel(self._table_model)
            self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)

        self._registros: List[Dict[str, object]] = []
        self._columns: List[str] = self._descobrir_colunas()
        self._current_id: Optional[int] = None

        self._connect_signals()
        self.refresh()

                                                                          
    def _descobrir_colunas(self) -> List[str]:
        try:
            return self.db_manager.get_table_columns("setores_locais")
        except Exception:
            return [
                "id_setor_local",
                "nome_setor_local",
                "localizacao",
                "descricao",
                "responsavel",
                "capacidade",
                "andar",
            ]

    def _connect_signals(self) -> None:
        if self.btn_novo_setor:
            self.btn_novo_setor.clicked.connect(self._novo)
        if self.btn_editar_setor:
            self.btn_editar_setor.clicked.connect(self._editar_selecionado)
        if self.btn_excluir_setor:
            self.btn_excluir_setor.clicked.connect(self._excluir)
        if self.btn_salvar_setor:
            self.btn_salvar_setor.clicked.connect(self._salvar)
        if self.btn_novo_local:
            self.btn_novo_local.clicked.connect(self._novo)
        if self.btn_editar_local:
            self.btn_editar_local.clicked.connect(self._editar_selecionado)
        if self.btn_excluir_local:
            self.btn_excluir_local.clicked.connect(self._excluir)
        if self.btn_salvar_local:
            self.btn_salvar_local.clicked.connect(self._salvar)
        if self.list_view and self.list_view.selectionModel():
            self.list_view.selectionModel().currentChanged.connect(self._on_list_changed)
        if self.table and self.table.selectionModel():
            self.table.selectionModel().currentChanged.connect(self._on_table_changed)

                                                                          
    def refresh(self) -> None:
        try:
            rows = self.db_manager.list_setores_locais()
        except Exception as exc:                                       
            QMessageBox.critical(
                self.widget,
                "Setores/Locais",
                f"Não foi possível carregar os setores/locais.\n{exc}",
            )
            rows = []
        self._registros = rows
        self._popular_modelos()
        if self._registros:
            self._select_by_id(self._registros[0].get("id_setor_local"))
        else:
            self._clear_form()

                                                                          
    def _popular_modelos(self) -> None:
        self._list_model.clear()
        for registro in self._registros:
            nome = str(registro.get("nome_setor_local") or "(sem nome)")
            item = QStandardItem(nome)
            item.setEditable(False)
            item.setData(int(registro.get("id_setor_local")), Qt.ItemDataRole.UserRole)
            self._list_model.appendRow(item)

        headers = [
            ("ID", "id_setor_local"),
            ("Nome", "nome_setor_local"),
            ("Localização", "localizacao"),
            ("Responsável", "responsavel"),
            ("Capacidade", "capacidade"),
            ("Descrição", "descricao"),
        ]

        keys_disponiveis = {k for registro in self._registros for k in registro.keys()}
        colunas = [item for item in headers if item[1] in keys_disponiveis]
        self._table_model.clear()
        self._table_model.setColumnCount(len(colunas))
        self._table_model.setHorizontalHeaderLabels([label for label, _ in colunas])
        for registro in self._registros:
            linha = []
            for _, chave in colunas:
                valor = registro.get(chave)
                if chave == "capacidade" and valor is not None:
                    valor = str(valor)
                linha.append(str(valor or "-"))
            items = [QStandardItem(valor) for valor in linha]
            for item in items:
                item.setEditable(False)
            self._table_model.appendRow(items)

                                                                          
    def _novo(self) -> None:
        self._current_id = None
        if self.list_view:
            self.list_view.clearSelection()
        if self.table:
            self.table.clearSelection()
        self._clear_form()

    def _editar_selecionado(self) -> None:
        registro = self._registro_selecionado()
        if not registro:
            QMessageBox.information(self.widget, "Setores/Locais", "Selecione um registro para editar.")
            return
        self._current_id = int(registro.get("id_setor_local"))
        self._popular_formulario(registro)

    def _excluir(self) -> None:
        # Verificar permissão de admin/master
        if not DatabaseManager.has_admin_privileges(self.current_user):
            QMessageBox.warning(
                self.widget,
                "Setores/Locais",
                "Ação permitida apenas para administradores ou usuários master.",
            )
            return
        
        registro = self._registro_selecionado()
        if not registro:
            QMessageBox.information(self.widget, "Setores/Locais", "Selecione um registro para excluir.")
            return
        resposta = QMessageBox.question(
            self.widget,
            "Setores/Locais",
            "Deseja realmente remover este registro?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db_manager.delete_setor_local(int(registro.get("id_setor_local")))
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Setores/Locais", f"Não foi possível remover.\n{exc}")
            return
        self.refresh()

    def _salvar(self) -> None:
        dados = self._coletar_dados_formulario()
        if not dados:
            return
        try:
            if self._current_id is None:
                self.db_manager.create_setor_local(dados)
            else:
                self.db_manager.update_setor_local(self._current_id, dados)
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Setores/Locais", f"Não foi possível salvar.\n{exc}")
            return
        QMessageBox.information(self.widget, "Setores/Locais", "Registro salvo com sucesso.")
        self.refresh()

                                                                          
    def _registro_selecionado(self) -> Optional[Dict[str, object]]:
        if self.list_view and self.list_view.selectionModel():
            indexes = self.list_view.selectionModel().selectedIndexes()
            if indexes:
                registro = self._registros[indexes[0].row()]
                return registro
        if self.table and self.table.selectionModel():
            indexes = self.table.selectionModel().selectedRows()
            if indexes:
                registro = self._registros[indexes[0].row()]
                return registro
        return None

    def _select_by_id(self, registro_id: Optional[object]) -> None:
        if registro_id is None:
            return
        registro_id = int(registro_id)
        for row, registro in enumerate(self._registros):
            if int(registro.get("id_setor_local")) == registro_id:
                if self.list_view and self.list_view.model().rowCount() > row:
                    index = self.list_view.model().index(row, 0)
                    self.list_view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                if self.table and self.table.model().rowCount() > row:
                    index = self.table.model().index(row, 0)
                    self.table.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                self._current_id = registro_id
                self._popular_formulario(registro)
                break

    def _on_list_changed(self, current, _previous) -> None:
        if not current.isValid():
            return
        registro = self._registros[current.row()]
        self._current_id = int(registro.get("id_setor_local"))
        self._popular_formulario(registro)

    def _on_table_changed(self, current, _previous) -> None:
        if not current.isValid():
            return
        registro = self._registros[current.row()]
        self._current_id = int(registro.get("id_setor_local"))
        self._popular_formulario(registro)

                                                                          
    def _popular_formulario(self, registro: Dict[str, object]) -> None:
        if self.txt_setor_nome:
            self.txt_setor_nome.setText(str(registro.get("nome_setor_local") or ""))
        if self.txt_setor_responsavel:
            self.txt_setor_responsavel.setText(str(registro.get("responsavel") or ""))
        descricao = str(registro.get("descricao") or "")
        if self.txt_setor_descricao:
            self.txt_setor_descricao.setPlainText(descricao)
        if self.txt_local_nome:
            self.txt_local_nome.setText(str(registro.get("localizacao") or ""))
        if self.txt_local_andar:
            self.txt_local_andar.setText(str(registro.get("andar") or ""))
        if self.spin_local_capacidade:
            valor = registro.get("capacidade")
            if valor is not None:
                try:
                    self.spin_local_capacidade.setValue(int(valor))
                except (TypeError, ValueError):
                    pass
            else:
                self.spin_local_capacidade.setValue(self.spin_local_capacidade.minimum())
        if self.txt_local_descricao:
            self.txt_local_descricao.setPlainText(descricao)

    def _clear_form(self) -> None:
        if self.txt_setor_nome:
            self.txt_setor_nome.clear()
        if self.txt_setor_responsavel:
            self.txt_setor_responsavel.clear()
        if self.txt_setor_descricao:
            self.txt_setor_descricao.clear()
        if self.txt_local_nome:
            self.txt_local_nome.clear()
        if self.txt_local_andar:
            self.txt_local_andar.clear()
        if self.spin_local_capacidade:
            self.spin_local_capacidade.setValue(self.spin_local_capacidade.minimum())
        if self.txt_local_descricao:
            self.txt_local_descricao.clear()

    def _coletar_dados_formulario(self) -> Optional[Dict[str, object]]:
        nome = self.txt_setor_nome.text().strip() if self.txt_setor_nome else ""
        if not nome:
            QMessageBox.warning(self.widget, "Setores/Locais", "Informe o nome do setor/local.")
            return None
        dados: Dict[str, object] = {"nome_setor_local": nome}
        if self.txt_setor_responsavel and self.txt_setor_responsavel.text().strip():
            dados["responsavel"] = self.txt_setor_responsavel.text().strip()
        descricao = ""
        if self.txt_local_descricao and self.txt_local_descricao.toPlainText().strip():
            descricao = self.txt_local_descricao.toPlainText().strip()
        elif self.txt_setor_descricao and self.txt_setor_descricao.toPlainText().strip():
            descricao = self.txt_setor_descricao.toPlainText().strip()
        if descricao:
            dados["descricao"] = descricao
        if self.txt_local_nome and self.txt_local_nome.text().strip():
            dados["localizacao"] = self.txt_local_nome.text().strip()
        if self.txt_local_andar and self.txt_local_andar.text().strip():
            dados["andar"] = self.txt_local_andar.text().strip()
        if self.spin_local_capacidade:
            dados["capacidade"] = self.spin_local_capacidade.value()

                                          
        dados_filtrados = {k: v for k, v in dados.items() if k in self._columns}
        if not dados_filtrados:
            QMessageBox.warning(
                self.widget,
                "Setores/Locais",
                "Nenhum campo corresponde às colunas disponíveis na tabela.",
            )
            return None
        return dados_filtrados
