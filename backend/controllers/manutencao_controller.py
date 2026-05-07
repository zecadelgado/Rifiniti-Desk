from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from backend.database.database_manager import DatabaseManager
from backend.utils.validators import validar_valor_positivo
from backend.services.audit_helper import registrar_auditoria


@dataclass
class _ManutencaoRecord:
    id_manutencao: int
    id_patrimonio: int
    nome_patrimonio: str
    data_inicio: Optional[datetime.date]
    data_fim: Optional[datetime.date]
    tipo: Optional[str]
    custo: Optional[float]
    empresa: Optional[str]
    descricao: Optional[str]
    status: Optional[str]


class ManutencaoController:
    """Controla a tela de manutenções."""

    def __init__(self, widget: QWidget, db_manager: DatabaseManager, current_user=None) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user

        self.cb_patrimonio: Optional[QComboBox] = self.widget.findChild(QComboBox, "cb_patrimonio")
        self.cb_tipo: Optional[QComboBox] = self.widget.findChild(QComboBox, "cb_tipo")
        self.de_inicio: Optional[QDateEdit] = self.widget.findChild(QDateEdit, "de_inicio")
        self.de_fim: Optional[QDateEdit] = self.widget.findChild(QDateEdit, "de_fim")
        self.dsb_custo: Optional[QDoubleSpinBox] = self.widget.findChild(QDoubleSpinBox, "dsb_custo")
        self.le_empresa: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_empresa")
        self.pte_descricao: Optional[QPlainTextEdit] = self.widget.findChild(QPlainTextEdit, "pte_descricao")
        self.table: Optional[QTableWidget] = self.widget.findChild(QTableWidget, "tbl_manutencoes")

        self.btn_novo: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_novo")
        self.btn_editar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_editar")
        self.btn_excluir: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_excluir")
        self.btn_salvar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_salvar")
        self.btn_cancelar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_cancelar")

        self._manutencoes: List[_ManutencaoRecord] = []
        self._current_id: Optional[int] = None
        self._edit_mode = False
        self._schema_ready = True
        self._schema_warning_shown = False

        self._setup_table()
        self._connect_signals()
        self.refresh()

                                                                          
                   
    def _setup_table(self) -> None:
        if not self.table:
            return
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Início", "Patrimônio", "Tipo", "Custo", "Empresa", "Descrição"]
        )
        header = self.table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)
        vheader = self.table.verticalHeader()
        if vheader:
            vheader.setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

    def _connect_signals(self) -> None:
        if self.btn_novo:
            self.btn_novo.clicked.connect(self._start_new)
        if self.btn_editar:
            self.btn_editar.clicked.connect(self._start_edit)
        if self.btn_excluir:
            self.btn_excluir.clicked.connect(self._delete_selected)
        if self.btn_salvar:
            self.btn_salvar.clicked.connect(self._save)
        if self.btn_cancelar:
            self.btn_cancelar.clicked.connect(self._cancel_edit)
        if self.table:
            self.table.itemSelectionChanged.connect(self._on_selection_changed)

                                                                          
                
    def refresh(self) -> None:
        self._schema_ready = self.db_manager.manutencao_has_extended_columns()
        if not self._schema_ready and not self._schema_warning_shown:
            QMessageBox.warning(
                self.widget,
                "Manutenções",
                (
                    "A tabela 'manutencoes' está incompleta. Execute o script "
                    "database/migrations_manutencao.sql para habilitar todos os recursos."
                ),
            )
            self._schema_warning_shown = True
        # Manter a tela funcional mesmo que faltem colunas; apenas desabilitar campos dependentes
        self._set_dependent_fields_enabled(self._schema_ready)

        self._populate_patrimonios()
        self._populate_tipos()
        self._load_manutencoes()
        self._clear_form()
        self._current_id = None
        self._set_edit_mode(True)

    def _populate_patrimonios(self) -> None:
        if not self.cb_patrimonio:
            return
        self.cb_patrimonio.clear()
        self.cb_patrimonio.addItem("Selecione", None)
        try:
            patrimonios = self.db_manager.list_patrimonios()
        except Exception as exc:                                       
            QMessageBox.warning(
                self.widget,
                "Manutenções",
                f"Não foi possível carregar os patrimônios.\n{exc}",
            )
            return
        for item in patrimonios:
            nome = item.get("nome") or item.get("nome_patrimonio")
            patrimonio_id = item.get("id_patrimonio")
            if nome and patrimonio_id is not None:
                self.cb_patrimonio.addItem(str(nome), int(patrimonio_id))
    
    def _populate_tipos(self) -> None:
        """Popula o combo de tipos de manutenção"""
        if not self.cb_tipo:
            return
        current_text = self.cb_tipo.currentText()
        self.cb_tipo.clear()
        self.cb_tipo.addItem("Selecione o tipo", None)
        tipos = [
            "Preventiva",
            "Corretiva",
            "Preditiva",
            "Emergencial",
            "Garantia",
            "Outro"
        ]
        for tipo in tipos:
            self.cb_tipo.addItem(tipo)
        # Restaurar seleção anterior se existir
        if current_text:
            index = self.cb_tipo.findText(current_text, Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                self.cb_tipo.setCurrentIndex(index)

    def _load_manutencoes(self, filters: Optional[Dict[str, object]] = None) -> None:
        try:
            rows = self.db_manager.list_manutencoes(filters or None)
        except Exception as exc:                                       
            QMessageBox.critical(
                self.widget,
                "Manutenções",
                f"Não foi possível carregar as manutenções.\n{exc}",
            )
            rows = []
        self._manutencoes = []
        for row in rows:
            self._manutencoes.append(
                _ManutencaoRecord(
                    id_manutencao=int(row.get("id_manutencao")),
                    id_patrimonio=int(row.get("id_patrimonio")),
                    nome_patrimonio=str(row.get("nome_patrimonio", "-")),
                    data_inicio=self._to_date(row.get("data_inicio")),
                    data_fim=self._to_date(row.get("data_fim")),
                    tipo=row.get("tipo_manutencao") or row.get("tipo") or row.get("status"),
                    custo=self._to_float(row.get("custo")),
                    empresa=row.get("empresa") or row.get("responsavel"),
                    descricao=row.get("descricao"),
                    status=row.get("status"),
                )
            )
        self._populate_table()

    def _populate_table(self) -> None:
        if not self.table:
            return
        self.table.setRowCount(len(self._manutencoes))
        for row_index, record in enumerate(self._manutencoes):
            self._set_item(row_index, 0, self._format_date(record.data_inicio))
            self._set_item(row_index, 1, record.nome_patrimonio)
            self._set_item(row_index, 2, record.tipo or "-")
            custo_text = f"R$ {record.custo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if record.custo else "R$ 0,00"
            self._set_item(row_index, 3, custo_text, align_right=True)
            self._set_item(row_index, 4, record.empresa or "-")
            self._set_item(row_index, 5, record.descricao or "-")
        self.table.resizeColumnsToContents()

    def _set_item(self, row: int, column: int, text: str, align_right: bool = False) -> None:
        if not self.table:
            return
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        alignment = Qt.AlignmentFlag.AlignVCenter
        alignment |= Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
        item.setTextAlignment(int(alignment))
        self.table.setItem(row, column, item)

                                                                          
                  
    def _start_new(self) -> None:
        self._current_id = None
        self._clear_form()
        self._set_edit_mode(True)

    def _start_edit(self) -> None:
        record = self._selected_record()
        if not record:
            QMessageBox.information(self.widget, "Manutenções", "Selecione uma manutenção para editar.")
            return
        self._current_id = record.id_manutencao
        self._populate_form(record)
        self._set_edit_mode(True)

    def _delete_selected(self) -> None:
        # Verificar permissão de admin/master
        if not DatabaseManager.has_admin_privileges(self.current_user):
            QMessageBox.warning(
                self.widget,
                "Manutenções",
                "Ação permitida apenas para administradores ou usuários master.",
            )
            return
        
        record = self._selected_record()
        if not record:
            QMessageBox.information(self.widget, "Manutenções", "Selecione uma manutenção para excluir.")
            return
        resposta = QMessageBox.question(
            self.widget,
            "Manutenções",
            "Deseja realmente excluir esta manutenção?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db_manager.delete_manutencao(record.id_manutencao)
            
            # Registrar auditoria
            if self.current_user:
                registrar_auditoria(
                    self.db_manager,
                    self.current_user,
                    "manutencoes",
                    record.id_manutencao,
                    "DELETE",
                    f"Manutenção {record.tipo or 'N/A'} - Patrimônio: {record.nome_patrimonio}"
                )
            
            QMessageBox.information(
                self.widget,
                "Manutenções",
                "Manutenção excluída com sucesso!"
            )
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Manutenções", f"Não foi possível excluir.\n{exc}")
            return
        self.refresh()

    def _save(self) -> None:
        if not self._edit_mode:
            QMessageBox.information(self.widget, "Manutenções", "Nenhuma alteração para salvar.")
            return
        dados = self._collect_form_data()
        if not dados:
            return
        
        # Validar custo
        custo = dados.get("custo", 0.0)
        valido_custo, msg_custo = validar_valor_positivo(custo, "Custo")
        if not valido_custo:
            QMessageBox.warning(
                self.widget,
                "Manutenções",
                msg_custo
            )
            return
        
        try:
            if self._current_id is None:
                auditoria_registro_id = self.db_manager.create_manutencao(dados)
                acao = "CREATE"
                QMessageBox.information(
                    self.widget,
                    "Manutenções",
                    "Manutenção cadastrada com sucesso!"
                )
            else:
                self.db_manager.update_manutencao(self._current_id, dados)
                auditoria_registro_id = self._current_id
                acao = "UPDATE"
                QMessageBox.information(
                    self.widget,
                    "Manutenções",
                    "Manutenção atualizada com sucesso!"
                )
            
            # Registrar auditoria
            if self.current_user:
                patrimonio_nome = self.cb_patrimonio.currentText() if self.cb_patrimonio else "N/A"
                tipo = dados.get("tipo_manutencao", "N/A")
                registrar_auditoria(
                    self.db_manager,
                    self.current_user,
                    "manutencoes",
                    auditoria_registro_id,
                    acao,
                    f"Manutenção {tipo} - Patrimônio: {patrimonio_nome}"
                )
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Manutenções", f"Não foi possível salvar.\n{exc}")
            return
        self.refresh()

    def _cancel_edit(self) -> None:
        self._set_edit_mode(False)
        self._clear_form()
        if self.table:
            self.table.clearSelection()

                                                                          
                  
    def _set_edit_mode(self, enabled: bool) -> None:
        # Permitir edição mesmo se campos extras estiverem ausentes; os campos dependentes já são tratados separadamente
        effective_enabled = enabled
        self._edit_mode = effective_enabled
        widgets = [
            self.cb_patrimonio,
            self.cb_tipo,
            self.de_inicio,
            self.de_fim,
            self.dsb_custo,
            self.le_empresa,
            self.pte_descricao,
        ]
        for widget in widgets:
            if widget:
                requires_extended = widget in {self.cb_tipo, self.le_empresa}
                widget.setEnabled(effective_enabled and (self._schema_ready or not requires_extended))
        buttons = [self.btn_novo, self.btn_editar, self.btn_excluir, self.btn_salvar, self.btn_cancelar]
        for button in buttons:
            if button:
                button.setEnabled(True)

    def _set_dependent_fields_enabled(self, enabled: bool) -> None:
        for widget in (self.cb_tipo, self.le_empresa):
            if widget:
                widget.setEnabled(enabled)

    def _clear_form(self) -> None:
        today = datetime.date.today()
        if self.cb_patrimonio:
            self.cb_patrimonio.setCurrentIndex(0)
        if self.cb_tipo:
            self.cb_tipo.setCurrentIndex(0)
        if self.de_inicio:
            self.de_inicio.setDate(self._from_date(today))
        if self.de_fim:
            self.de_fim.setSpecialValueText("")
            self.de_fim.setDate(QDate())
        if self.dsb_custo:
            self.dsb_custo.setValue(0.0)
        if self.le_empresa:
            self.le_empresa.clear()
        if self.pte_descricao:
            self.pte_descricao.clear()

    def _populate_form(self, record: _ManutencaoRecord) -> None:
        if self.cb_patrimonio:
            index = self.cb_patrimonio.findData(record.id_patrimonio)
            if index >= 0:
                self.cb_patrimonio.setCurrentIndex(index)
        if self.cb_tipo:
            index = self.cb_tipo.findText(record.tipo or "", Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                self.cb_tipo.setCurrentIndex(index)
        if self.de_inicio and record.data_inicio:
            self.de_inicio.setDate(self._from_date(record.data_inicio))
        if self.de_fim:
            if record.data_fim:
                self.de_fim.setDate(self._from_date(record.data_fim))
            else:
                self.de_fim.setSpecialValueText("")
                self.de_fim.setDate(QDate())
        if self.dsb_custo and record.custo is not None:
            self.dsb_custo.setValue(float(record.custo))
        if self.le_empresa:
            self.le_empresa.setText(record.empresa or "")
        if self.pte_descricao:
            self.pte_descricao.setPlainText(record.descricao or "")

    def _collect_form_data(self) -> Optional[Dict[str, object]]:
        if not self.cb_patrimonio or self.cb_patrimonio.currentIndex() <= 0:
            QMessageBox.warning(self.widget, "Manutenções", "Selecione um patrimônio.")
            return None
        id_patrimonio = self.cb_patrimonio.currentData()
        if id_patrimonio is None:
            QMessageBox.warning(self.widget, "Manutenções", "Selecione um patrimônio válido.")
            return None

        qt_inicio = self.de_inicio.date() if self.de_inicio else self._from_date(datetime.date.today())
        data_inicio = (
            qt_inicio.toPython() if qt_inicio and qt_inicio.isValid() else datetime.date.today()
        )

        data_fim = None
        if self.de_fim:
            qt_fim = self.de_fim.date()
            if qt_fim and qt_fim.isValid():
                data_fim = qt_fim.toPython()

        if data_fim and data_fim < data_inicio:
            QMessageBox.warning(
                self.widget,
                "Manutenções",
                "A data de término não pode ser anterior ao início.",
            )
            return None

        # Validar tipo de manutencao apenas se a coluna existir
        tipo_manutencao = None
        if self.cb_tipo and self.cb_tipo.currentIndex() > 0:
            tipo_manutencao = self.cb_tipo.currentText().strip().lower()
        
        if self._schema_ready and not tipo_manutencao:
            QMessageBox.warning(
                self.widget,
                "Manutencoes",
                "Selecione o tipo de manutencao."
            )
            return None
        
        custo = self.dsb_custo.value() if self.dsb_custo else 0.0
        empresa = self.le_empresa.text().strip() if self.le_empresa else ""
        descricao = self.pte_descricao.toPlainText().strip() if self.pte_descricao else ""
        
        # Determinar status baseado na data de fim
        if data_fim:
            status = "concluida"
        else:
            status = "em_andamento"

        dados: Dict[str, object] = {
            "id_patrimonio": int(id_patrimonio),
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "custo": custo,
            "empresa": empresa or None,
            "descricao": descricao or None,
            "status": status,
            "tipo_manutencao": tipo_manutencao,
            "responsavel": empresa or None,
        }
        return dados

                                                                          
                       
    def _selected_record(self) -> Optional[_ManutencaoRecord]:
        if not self.table:
            return None
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        if 0 <= row < len(self._manutencoes):
            return self._manutencoes[row]
        return None

    def _on_selection_changed(self) -> None:
        if not self._edit_mode:
            record = self._selected_record()
            if record:
                self._populate_form(record)


                                                                          
             
    @staticmethod
    def _to_date(value: object) -> Optional[datetime.date]:
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return None

    @staticmethod
    def _from_date(value: Optional[datetime.date]) -> QDate:
        if isinstance(value, datetime.datetime):
            value = value.date()
        if isinstance(value, datetime.date):
            return QDate(value.year, value.month, value.day)
        return QDate()

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_date(value: Optional[datetime.date]) -> str:
        if not value:
            return "-"
        return value.strftime("%d/%m/%Y")
