from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from backend.database.database_manager import DatabaseManager


class AuditoriaController:
    """Sincroniza a UI de auditoria com o banco de dados."""

    TABLE_HEADERS: List[str] = ["Data", "Tabela", "Registro", "Ação", "Usuário"]

    def __init__(
        self,
        widget: QWidget,
        db_manager: DatabaseManager,
        current_user: Optional[Dict[str, object]] = None,
        dashboard_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user or {}
        self._dashboard_callback = dashboard_callback

        self.tab_widget: Optional[QTabWidget] = self.widget.findChild(QTabWidget, "tabWidget")
        self.table: Optional[QTableWidget] = self.widget.findChild(QTableWidget, "tbl_auditoria")

        self.dt_agendamento: Optional[QDateTimeEdit] = self.widget.findChild(QDateTimeEdit, "dt_agendamento")
        self.cb_tabela: Optional[QComboBox] = self.widget.findChild(QComboBox, "cb_tabela_auditoria")
        self.sb_registro: Optional[QSpinBox] = self.widget.findChild(QSpinBox, "sb_registro_auditoria")
        self.le_acao: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_acao_auditoria")
        self.pte_observacoes: Optional[QPlainTextEdit] = self.widget.findChild(
            QPlainTextEdit, "pte_observacoes_auditoria"
        )
        self.btn_agendar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_agendar_auditoria")
        self.btn_salvar_edicao: Optional[QPushButton] = self.widget.findChild(
            QPushButton, "btn_salvar_edicao_auditoria"
        )
        self.btn_limpar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_limpar_form_auditoria")
        self.btn_atualizar_lista: Optional[QPushButton] = self.widget.findChild(
            QPushButton, "btn_atualizar_lista_auditoria"
        )
        self.btn_editar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_editar_auditoria")

        # Itens de verificação
        self.le_item_id: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_item_id_auditoria")
        self.le_item_descricao: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_item_descricao_auditoria")
        self.cb_item_conformidade: Optional[QComboBox] = self.widget.findChild(QComboBox, "cb_item_conformidade")
        self.lbl_item_observacao: Optional[QLabel] = self.widget.findChild(QLabel, "lbl_item_observacao")
        self.pte_item_observacao: Optional[QPlainTextEdit] = self.widget.findChild(QPlainTextEdit, "pte_item_observacao")
        self.tbl_itens: Optional[QTableWidget] = self.widget.findChild(QTableWidget, "tbl_itens_auditoria")
        self.btn_add_item: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_add_item_auditoria")
        self.btn_remover_item: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_remover_item_auditoria")

        self._auditorias: List[Dict[str, object]] = []
        self._auditoria_em_edicao_id: Optional[int] = None
        self._itens_verificacao: List[Dict[str, object]] = []

        self._setup_table()
        self._setup_itens_table()
        self._connect_signals()
        if self.btn_editar:
            self.btn_editar.setEnabled(False)
        self._reset_form_agendamento()
        self.refresh()

    def set_dashboard_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._dashboard_callback = callback

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
        if self.table:
            self.table.itemSelectionChanged.connect(self._on_selection_changed)
        if self.btn_agendar:
            self.btn_agendar.clicked.connect(self._agendar_auditoria)
        if self.btn_salvar_edicao:
            self.btn_salvar_edicao.clicked.connect(self._salvar_edicao)
        if self.btn_limpar:
            self.btn_limpar.clicked.connect(self._reset_form_agendamento)
        if self.btn_atualizar_lista:
            self.btn_atualizar_lista.clicked.connect(self.refresh)
        if self.btn_editar:
            self.btn_editar.clicked.connect(self._editar_selecionada)
        if self.cb_item_conformidade:
            self.cb_item_conformidade.currentTextChanged.connect(self._on_item_conformidade_changed)
        if self.btn_add_item:
            self.btn_add_item.clicked.connect(self._handle_add_item)
        if self.btn_remover_item:
            self.btn_remover_item.clicked.connect(self._remover_item)
        self._toggle_item_observacao(False)

    def refresh(self) -> None:
        self._carregar_auditorias()

    def _carregar_auditorias(self) -> None:
        try:
            rows = self.db_manager.list_auditorias()
        except Exception as exc:
            QMessageBox.critical(
                self.widget,
                "Auditoria",
                f"Não foi possível carregar os registros de auditoria.\n{exc}",
            )
            rows = []
        self._auditorias = rows
        self._popular_tabela()

    def _popular_tabela(self) -> None:
        if not self.table:
            return
        self.table.setRowCount(len(self._auditorias))
        for index, row in enumerate(self._auditorias):
            data = row.get("data_auditoria")
            data_str = str(data)
            self._set_item(index, 0, data_str)
            self._set_item(index, 1, str(row.get("tabela_afetada") or "-"))
            self._set_item(index, 2, str(row.get("id_registro_afetado") or "-"))
            self._set_item(index, 3, str(row.get("acao") or "-"))
            self._set_item(index, 4, str(row.get("nome_usuario") or "-"))
        self.table.resizeColumnsToContents()
        if self.table.rowCount():
            self.table.selectRow(0)

    def _set_item(self, row: int, column: int, text: str) -> None:
        if not self.table:
            return
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, column, item)

    def _setup_itens_table(self) -> None:
        if not self.tbl_itens:
            return
        headers = ["Patrimônio/Item", "Descrição", "Status", "Observação"]
        self.tbl_itens.setColumnCount(len(headers))
        self.tbl_itens.setHorizontalHeaderLabels(headers)
        header = self.tbl_itens.horizontalHeader()
        if header:
            header.setStretchLastSection(True)
        self.tbl_itens.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_itens.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

    def _toggle_item_observacao(self, visible: bool) -> None:
        if self.lbl_item_observacao:
            self.lbl_item_observacao.setVisible(visible)
        if self.pte_item_observacao:
            self.pte_item_observacao.setVisible(visible)
            if not visible:
                self.pte_item_observacao.clear()

    def _on_item_conformidade_changed(self) -> None:
        status = (
            self.cb_item_conformidade.currentText().strip().lower()
            if self.cb_item_conformidade
            else "conforme"
        )
        self._toggle_item_observacao(status == "não conforme")

    def _handle_add_item(self) -> None:
        identificador = self.le_item_id.text().strip() if self.le_item_id else ""
        descricao = self.le_item_descricao.text().strip() if self.le_item_descricao else ""
        status = (
            self.cb_item_conformidade.currentText().strip().lower()
            if self.cb_item_conformidade
            else "conforme"
        )
        conforme = status != "não conforme"
        observacao = self.pte_item_observacao.toPlainText().strip() if self.pte_item_observacao else ""

        if not identificador and not descricao:
            QMessageBox.warning(self.widget, "Auditoria", "Informe o ID ou a descrição do item verificado.")
            return
        if not conforme and not observacao:
            QMessageBox.warning(
                self.widget,
                "Auditoria",
                "Descreva o que não está conforme antes de adicionar o item.",
            )
            return

        id_patrimonio: Optional[int] = None
        if identificador:
            try:
                id_patrimonio = int(identificador)
            except ValueError:
                id_patrimonio = None

        if id_patrimonio and not descricao:
            descricao = self._buscar_nome_patrimonio(id_patrimonio) or ""

        if not descricao:
            QMessageBox.warning(self.widget, "Auditoria", "Informe uma descrição para o item verificado.")
            return

        item_payload = {
            "id_patrimonio": id_patrimonio,
            "identificador": identificador or None,
            "descricao": descricao,
            "conforme": conforme,
            "observacao": observacao if not conforme else "",
        }
        self._itens_verificacao.append(item_payload)
        self._refresh_itens_table()
        self._clear_item_inputs()

    def _remover_item(self) -> None:
        if not self.tbl_itens:
            return
        selected = self.tbl_itens.selectedItems()
        if not selected:
            QMessageBox.information(self.widget, "Auditoria", "Selecione um item para remover.")
            return
        row = selected[0].row()
        if not (0 <= row < len(self._itens_verificacao)):
            return
        self._itens_verificacao.pop(row)
        self._refresh_itens_table()

    def _refresh_itens_table(self) -> None:
        if not self.tbl_itens:
            return
        self.tbl_itens.setRowCount(len(self._itens_verificacao))
        for row, item in enumerate(self._itens_verificacao):
            identificador = item.get("id_patrimonio") or item.get("identificador") or "-"
            descricao = item.get("descricao") or "-"
            status = "Conforme" if item.get("conforme", True) else "Não conforme"
            observacao = item.get("observacao") or "-"
            self.tbl_itens.setItem(row, 0, QTableWidgetItem(str(identificador)))
            self.tbl_itens.setItem(row, 1, QTableWidgetItem(str(descricao)))
            self.tbl_itens.setItem(row, 2, QTableWidgetItem(status))
            self.tbl_itens.setItem(row, 3, QTableWidgetItem(str(observacao)))
        self.tbl_itens.resizeColumnsToContents()

    def _clear_item_inputs(self) -> None:
        if self.le_item_id:
            self.le_item_id.clear()
        if self.le_item_descricao:
            self.le_item_descricao.clear()
        if self.cb_item_conformidade:
            self.cb_item_conformidade.setCurrentIndex(0)
        self._toggle_item_observacao(False)

    def _carregar_itens_de_detalhes(self, detalhes: Optional[Dict[str, object]]) -> None:
        itens_norm: List[Dict[str, object]] = []
        if detalhes and isinstance(detalhes.get("itens_verificados"), list):
            for bruto in detalhes["itens_verificados"]:
                if not isinstance(bruto, dict):
                    continue
                conforme = bruto.get("conforme")
                if conforme is None:
                    conforme = True
                item_normalizado = {
                    "id_patrimonio": bruto.get("id_patrimonio"),
                    "identificador": bruto.get("identificador"),
                    "descricao": bruto.get("descricao") or "",
                    "conforme": bool(conforme),
                    "observacao": bruto.get("observacao") or "",
                }
                if not item_normalizado["identificador"] and bruto.get("id"):
                    item_normalizado["identificador"] = bruto.get("id")
                itens_norm.append(item_normalizado)
        self._itens_verificacao = itens_norm
        self._refresh_itens_table()

    def _buscar_nome_patrimonio(self, patrimonio_id: int) -> Optional[str]:
        try:
            registro = self.db_manager.get_patrimonio(patrimonio_id)
        except Exception as exc:
            print(f"[Aviso] Não consegui carregar o patrimônio {patrimonio_id}: {exc}")
            return None
        if not registro:
            return None
        return registro.get("nome") or registro.get("descricao")

    def _on_selection_changed(self) -> None:
        if not self.table or not self.btn_editar:
            return
        selected = self.table.selectedItems()
        if not selected:
            self.btn_editar.setEnabled(False)
            return
        row_index = selected[0].row()
        if not (0 <= row_index < len(self._auditorias)):
            self.btn_editar.setEnabled(False)
            return
        registro = self._auditorias[row_index]
        self.btn_editar.setEnabled(self._is_agendada(registro))

    def _editar_selecionada(self) -> None:
        if not self.table:
            return
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self.widget, "Auditoria", "Selecione uma linha para editar.")
            return
        row_index = selected[0].row()
        if not (0 <= row_index < len(self._auditorias)):
            return
        registro = self._auditorias[row_index]
        if not self._is_agendada(registro):
            QMessageBox.information(
                self.widget,
                "Auditoria",
                "Somente auditorias agendadas podem ser editadas.",
            )
            return
        self._preencher_formulario_para_registro(registro)
        if self.tab_widget:
            tab_agendar = self.widget.findChild(QWidget, "tab_agendar")
            if tab_agendar:
                idx = self.tab_widget.indexOf(tab_agendar)
                if idx >= 0:
                    self.tab_widget.setCurrentIndex(idx)

    def _preencher_formulario_para_registro(self, registro: Dict[str, object]) -> None:
        self._auditoria_em_edicao_id = int(registro.get("id_auditoria") or 0) or None
        if self.dt_agendamento:
            qdt = self._to_qdatetime(registro.get("data_auditoria"))
            if qdt:
                self.dt_agendamento.setDateTime(qdt)
        if self.cb_tabela:
            tabela = (registro.get("tabela_afetada") or "").strip()
            index = self.cb_tabela.findText(tabela, Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                self.cb_tabela.setCurrentIndex(index)
        if self.sb_registro:
            valor = registro.get("id_registro_afetado") or 0
            try:
                self.sb_registro.setValue(int(valor))
            except (ValueError, TypeError):
                self.sb_registro.setValue(0)
        if self.le_acao:
            self.le_acao.setText(str(registro.get("acao") or ""))
        if self.pte_observacoes:
            self.pte_observacoes.setPlainText(self._extrair_observacoes(registro))
        detalhes = self._parse_detalhes(registro.get("detalhes_novos"))
        self._carregar_itens_de_detalhes(detalhes)
        if self.btn_salvar_edicao:
            self.btn_salvar_edicao.setEnabled(self._auditoria_em_edicao_id is not None)

    def _reset_form_agendamento(self) -> None:
        if self.dt_agendamento:
            self.dt_agendamento.setDateTime(QDateTime.currentDateTime())
        if self.cb_tabela:
            self.cb_tabela.setCurrentIndex(0)
        if self.sb_registro:
            self.sb_registro.setValue(0)
        if self.le_acao:
            self.le_acao.clear()
        if self.pte_observacoes:
            self.pte_observacoes.clear()
        self._auditoria_em_edicao_id = None
        if self.btn_salvar_edicao:
            self.btn_salvar_edicao.setEnabled(False)
        self._itens_verificacao = []
        self._refresh_itens_table()
        self._clear_item_inputs()

    def _montar_payload_agendado(self) -> Optional[Tuple[Dict[str, object], str]]:
        acao = self.le_acao.text().strip() if self.le_acao else ""
        if not acao:
            QMessageBox.warning(self.widget, "Auditoria", "Informe a ação da auditoria.")
            return None

        tabela = self.cb_tabela.currentText().strip() if self.cb_tabela else ""
        registro_id = self.sb_registro.value() if self.sb_registro else 0
        observacoes = self.pte_observacoes.toPlainText().strip() if self.pte_observacoes else ""
        usuario_id = int(self.current_user.get("id_usuario", 1))

        programada = self._get_programmed_datetime().strftime("%Y-%m-%d %H:%M:%S")
        detalhes = {
            "status": "agendado",
            "observacoes": observacoes,
            "tabela": tabela or None,
            "registro": registro_id or None,
        }
        if not observacoes:
            detalhes.pop("observacoes")
        if detalhes.get("registro") is None:
            detalhes.pop("registro")
        if detalhes.get("tabela") is None:
            detalhes.pop("tabela")
        if self._itens_verificacao:
            detalhes["itens_verificados"] = self._itens_verificacao

        payload = {
            "id_usuario": usuario_id,
            "acao": acao,
            "tabela_afetada": tabela or None,
            "id_registro_afetado": registro_id or None,
            "data_auditoria": programada,
            "detalhes_novos": detalhes if detalhes else None,
        }

        if not tabela:
            payload["tabela_afetada"] = None
        if not registro_id:
            payload["id_registro_afetado"] = None
        return payload, programada

    def _agendar_auditoria(self) -> None:
        resultado = self._montar_payload_agendado()
        if not resultado:
            return
        payload, _ = resultado

        try:
            self.db_manager.create_auditoria(payload)
        except Exception as exc:
            QMessageBox.critical(self.widget, "Auditoria", f"Não foi possível agendar a auditoria.\n{exc}")
            return

        QMessageBox.information(self.widget, "Auditoria", "Auditoria agendada com sucesso.")
        self._reset_form_agendamento()
        if self.tab_widget:
            self.tab_widget.setCurrentIndex(0)
        self.refresh()
        self._emit_dashboard_update()

    def _salvar_edicao(self) -> None:
        if not self._auditoria_em_edicao_id:
            QMessageBox.information(self.widget, "Auditoria", "Nenhuma auditoria selecionada para edição.")
            return
        resultado = self._montar_payload_agendado()
        if not resultado:
            return
        payload, _ = resultado
        try:
            atualizada = self.db_manager.update_auditoria(self._auditoria_em_edicao_id, payload)
        except Exception as exc:
            QMessageBox.critical(self.widget, "Auditoria", f"Não foi possível atualizar a auditoria.\n{exc}")
            return
        if not atualizada:
            QMessageBox.warning(self.widget, "Auditoria", "Nenhuma alteração foi aplicada.")
            return
        QMessageBox.information(self.widget, "Auditoria", "Auditoria atualizada com sucesso.")
        self._reset_form_agendamento()
        self.refresh()
        self._emit_dashboard_update()

    def _emit_dashboard_update(self) -> None:
        if callable(self._dashboard_callback):
            try:
                self._dashboard_callback()
            except Exception as exc:
                print(f"[Aviso] Não consegui atualizar o calendário do dashboard: {exc}")

    def _extrair_observacoes(self, registro: Dict[str, object]) -> str:
        detalhes = self._parse_detalhes(registro.get("detalhes_novos"))
        if isinstance(detalhes, dict):
            return str(detalhes.get("observacoes") or "")
        return ""

    def _parse_detalhes(self, valor: object) -> Optional[Dict[str, object]]:
        if isinstance(valor, dict):
            return valor
        if not valor:
            return None
        if isinstance(valor, str):
            valor = valor.strip()
            if not valor:
                return None
            try:
                return json.loads(valor)
            except json.JSONDecodeError:
                return None
        return None

    def _is_agendada(self, registro: Dict[str, object]) -> bool:
        detalhes = self._parse_detalhes(registro.get("detalhes_novos"))
        if not detalhes:
            return False
        status = str(detalhes.get("status") or "").lower()
        return status == "agendado"

    def _get_programmed_datetime(self) -> datetime:
        if self.dt_agendamento:
            qdt = self.dt_agendamento.dateTime()
            if hasattr(qdt, "toPython"):
                return qdt.toPython()
            qdate = qdt.date()
            qtime = qdt.time()
            return datetime(
                qdate.year(),
                qdate.month(),
                qdate.day(),
                qtime.hour(),
                qtime.minute(),
                qtime.second(),
            )
        return datetime.now()

    @staticmethod
    def _to_qdatetime(valor: object) -> Optional[QDateTime]:
        if isinstance(valor, QDateTime):
            return valor
        dt_value: Optional[datetime] = None
        if isinstance(valor, datetime):
            dt_value = valor
        elif isinstance(valor, str):
            texto = valor.strip()
            if not texto:
                return None
            try:
                dt_value = datetime.fromisoformat(texto.replace("Z", ""))
            except ValueError:
                return None
        if not dt_value:
            return None
        qdate = QDate(dt_value.year, dt_value.month, dt_value.day)
        qtime = QTime(dt_value.hour, dt_value.minute, dt_value.second)
        return QDateTime(qdate, qtime)
