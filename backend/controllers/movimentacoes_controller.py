from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QDateEdit,
    QComboBox,
    QTextEdit,
    QTableView,
    QWidget,
)

from backend.database.database_manager import DatabaseManager


class MovimentacoesController:
    """Gerencia a tela de movimentações de patrimônio."""

    HISTORY_HEADERS: List[str] = [
        "Data",
        "Patrimônio",
        "Tipo",
        "Origem",
        "Destino",
        "Responsável",
        "Usuário",
    ]

    def __init__(
        self,
        widget: QWidget,
        db_manager: DatabaseManager,
        current_user: Optional[Dict[str, object]] = None,
    ) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user or {}

                      
        self.txt_patrimonio: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_patrimonio")
        self.btn_buscar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_buscar_patrimonio")
        self.date_movimentacao: Optional[QDateEdit] = self.widget.findChild(QDateEdit, "date_movimentacao")
        self.cmb_tipo: Optional[QComboBox] = self.widget.findChild(QComboBox, "cmb_tipo_movimentacao")
        self.cmb_setor_destino: Optional[QComboBox] = self.widget.findChild(QComboBox, "cmb_setor_destino")
        self.cmb_local_destino: Optional[QComboBox] = self.widget.findChild(QComboBox, "cmb_local_destino")
        self.txt_responsavel: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_responsavel")
        self.txt_motivo: Optional[QTextEdit] = self.widget.findChild(QTextEdit, "txt_motivo")
        self.btn_registrar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_registrar")

                     
        self.lbl_info_descricao: Optional[QLabel] = self.widget.findChild(QLabel, "lbl_info_descricao_valor")
        self.lbl_info_categoria: Optional[QLabel] = self.widget.findChild(QLabel, "lbl_info_categoria_valor")
        self.lbl_info_setor: Optional[QLabel] = self.widget.findChild(QLabel, "lbl_info_setor_atual_valor")
        self.lbl_info_local: Optional[QLabel] = self.widget.findChild(QLabel, "lbl_info_local_atual_valor")

                         
        self.txt_filtro_patrimonio: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "txt_filtro_patrimonio")
        self.date_filtro_inicio: Optional[QDateEdit] = self.widget.findChild(QDateEdit, "date_filtro_inicio")
        self.date_filtro_fim: Optional[QDateEdit] = self.widget.findChild(QDateEdit, "date_filtro_fim")
        self.btn_filtrar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_filtrar")
        self.btn_exportar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_exportar")
        self.tbl_historico: Optional[QTableView] = self.widget.findChild(QTableView, "tbl_historico")

        self._history_model: Optional[QStandardItemModel] = None
        self._patrimonio_atual: Optional[Dict[str, object]] = None

        self._setup_history_table()
        self._connect_signals()
        self._populate_destinos()
        self._reset_form()
        self.refresh()

                                                                          
                   
    def _setup_history_table(self) -> None:
        if not self.tbl_historico:
            return
        self._history_model = QStandardItemModel(self.tbl_historico)
        self._history_model.setHorizontalHeaderLabels(self.HISTORY_HEADERS)
        self.tbl_historico.setModel(self._history_model)
        header = self.tbl_historico.horizontalHeader()
        if header:
            header.setStretchLastSection(True)

    def _connect_signals(self) -> None:
        if self.btn_buscar:
            self.btn_buscar.clicked.connect(self._buscar_patrimonio)
        if self.txt_patrimonio:
            self.txt_patrimonio.returnPressed.connect(self._buscar_patrimonio)
        if self.btn_registrar:
            self.btn_registrar.clicked.connect(self._registrar_movimentacao)
        if self.btn_filtrar:
            self.btn_filtrar.clicked.connect(self._aplicar_filtros)
        if self.btn_exportar:
            self.btn_exportar.clicked.connect(self._exportar_historico)

    def _populate_destinos(self) -> None:
        try:
            setores = self.db_manager.list_setores_locais()
        except Exception as exc:                                       
            QMessageBox.warning(
                self.widget,
                "Movimentações",
                f"Não foi possível carregar os destinos.\n{exc}",
            )
            setores = []
        combos = [self.cmb_setor_destino, self.cmb_local_destino]
        for combo in combos:
            if not combo:
                continue
            combo.clear()
            combo.addItem("Selecione", None)
            for setor in setores:
                nome = setor.get("nome_setor_local")
                setor_id = setor.get("id_setor_local")
                if nome and setor_id is not None:
                    combo.addItem(str(nome), int(setor_id))

    def _reset_form(self) -> None:
        if self.txt_patrimonio:
            self.txt_patrimonio.clear()
        if self.date_movimentacao:
            self.date_movimentacao.setDate(QDate.currentDate())
        if self.cmb_tipo:
            self.cmb_tipo.setCurrentIndex(0)
        if self.cmb_setor_destino:
            self.cmb_setor_destino.setCurrentIndex(0)
        if self.cmb_local_destino:
            self.cmb_local_destino.setCurrentIndex(0)
        if self.txt_responsavel:
            self.txt_responsavel.clear()
        if self.txt_motivo:
            self.txt_motivo.clear()
        self._patrimonio_atual = None
        self._atualizar_labels()

                                                                          
                
    def refresh(self) -> None:
        self._carregar_historico()

                                                                          
                        
    def _buscar_patrimonio(self) -> None:
        if not self.txt_patrimonio:
            return
        codigo = self.txt_patrimonio.text().strip()
        if not codigo:
            QMessageBox.information(self.widget, "Movimentações", "Informe o ID ou código do patrimônio.")
            return
        try:
            patrimonio_id = int(codigo)
        except ValueError:
            QMessageBox.warning(self.widget, "Movimentações", "Informe um número (ID ou código).")
            return
        try:
            patrimonio = self.db_manager.get_patrimonio(patrimonio_id)
            if not patrimonio:
                alt = self.db_manager.fetch_one(
                    "SELECT id_patrimonio FROM patrimonios WHERE numero_patrimonio = %s",
                    (patrimonio_id,),
                )
                if alt:
                    patrimonio = self.db_manager.get_patrimonio(int(alt.get("id_patrimonio")))
        except Exception as exc:                                       
            QMessageBox.critical(
                self.widget,
                "Movimentações",
                f"Não foi possível buscar o patrimônio.\n{exc}",
            )
            return
        if not patrimonio:
            QMessageBox.information(
                self.widget,
                "Movimentações",
                "Patrimônio não encontrado.",
            )
            return
        self._patrimonio_atual = patrimonio
        self._atualizar_labels()

    def _atualizar_labels(self) -> None:
        patrimonio = self._patrimonio_atual or {}
        if self.lbl_info_descricao:
            self.lbl_info_descricao.setText(str(patrimonio.get("descricao") or "-"))
        if self.lbl_info_categoria:
            self.lbl_info_categoria.setText(str(patrimonio.get("nome_categoria") or "-"))
        if self.lbl_info_setor:
            self.lbl_info_setor.setText(str(patrimonio.get("nome_setor_local") or "-"))
        if self.lbl_info_local:
            self.lbl_info_local.setText(str(patrimonio.get("localizacao") or "-"))

                                                                          
                            
    def _registrar_movimentacao(self) -> None:
        if not self._patrimonio_atual:
            QMessageBox.warning(self.widget, "Movimentações", "Busque um patrimônio antes de registrar.")
            return
        if not self.cmb_tipo:
            return
        destino_id = None
        destino_nome = None
        if self.cmb_local_destino and self.cmb_local_destino.currentIndex() > 0:
            destino_id = self.cmb_local_destino.currentData()
            destino_nome = self.cmb_local_destino.currentText()
        elif self.cmb_setor_destino and self.cmb_setor_destino.currentIndex() > 0:
            destino_id = self.cmb_setor_destino.currentData()
            destino_nome = self.cmb_setor_destino.currentText()

        if destino_id is None:
            QMessageBox.warning(self.widget, "Movimentações", "Selecione o destino da movimentação.")
            return

        data_mov = self.date_movimentacao.date().toPython() if self.date_movimentacao else datetime.date.today()
        responsavel = self.txt_responsavel.text().strip() if self.txt_responsavel else ""
        observacoes = self.txt_motivo.toPlainText().strip() if self.txt_motivo else ""

        origem = self._descricao_origem()
        destino = destino_nome or "-"

        payload: Dict[str, object] = {
            "id_patrimonio": int(self._patrimonio_atual.get("id_patrimonio")),
            "id_usuario": int(self.current_user.get("id_usuario", 1)),
            "data_movimentacao": data_mov,
            "tipo_movimentacao": self.cmb_tipo.currentText(),
            "origem": origem,
            "destino": destino,
            "observacoes": observacoes or None,
            "responsavel": responsavel or None,
        }

        try:
            self.db_manager.create_movimentacao(payload)
            self.db_manager.update_patrimonio_setor_local(payload["id_patrimonio"], destino_id)
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Movimentações", f"Não foi possível registrar.\n{exc}")
            return

        QMessageBox.information(
            self.widget,
            "Movimentações",
            "Movimentação registrada com sucesso.",
        )
        self._reset_form()
        self.refresh()

    def _descricao_origem(self) -> str:
        if not self._patrimonio_atual:
            return "-"
        setor = self._patrimonio_atual.get("nome_setor_local")
        local = self._patrimonio_atual.get("localizacao")
        descricao = self._patrimonio_atual.get("descricao")
        partes = [p for p in [setor, local, descricao] if p]
        return " - ".join(str(p) for p in partes) if partes else "-"

                                                                          
               
    def _carregar_historico(self, filtros: Optional[Dict[str, object]] = None) -> None:
        try:
            rows = self.db_manager.list_movimentacoes(filters=filtros or {}, limit=200)
        except Exception as exc:                                       
            QMessageBox.critical(
                self.widget,
                "Movimentações",
                f"Não foi possível carregar o histórico.\n{exc}",
            )
            rows = []
        if not self._history_model:
            return
        self._history_model.removeRows(0, self._history_model.rowCount())
        for row in rows:
            data = row.get("data_movimentacao")
            if isinstance(data, datetime.datetime):
                data_str = data.strftime("%d/%m/%Y %H:%M")
            elif isinstance(data, datetime.date):
                data_str = data.strftime("%d/%m/%Y")
            else:
                data_str = str(data or "-")
            registro = [
                data_str,
                str(row.get("nome_patrimonio") or "-"),
                str(row.get("tipo_movimentacao") or "-"),
                str(row.get("origem") or "-"),
                str(row.get("destino") or "-"),
                str(row.get("responsavel") or "-"),
                str(row.get("nome_usuario") or "-"),
            ]
            items = [QStandardItem(valor) for valor in registro]
            for item in items:
                item.setEditable(False)
            self._history_model.appendRow(items)

    def _aplicar_filtros(self) -> None:
        filtros: Dict[str, object] = {}
        if self.txt_filtro_patrimonio:
            codigo = self.txt_filtro_patrimonio.text().strip()
            if codigo:
                try:
                    filtros["id_patrimonio"] = int(codigo)
                except ValueError:
                    QMessageBox.warning(self.widget, "Movimentações", "ID do filtro deve ser numérico.")
                    return
        if self.date_filtro_inicio and self.date_filtro_inicio.date().isValid():
            filtros["data_inicio"] = self.date_filtro_inicio.date().toPython()
        if self.date_filtro_fim and self.date_filtro_fim.date().isValid():
            filtros["data_fim"] = self.date_filtro_fim.date().toPython()
        self._carregar_historico(filtros)

                                                                          
            
    def _exportar_historico(self) -> None:
        if not self._history_model:
            return
        path, _ = QFileDialog.getSaveFileName(
            self.widget,
            "Exportar histórico",
            str(Path.home() / "movimentacoes.csv"),
            "CSV (*.csv)",
        )
        if not path:
            return
        rows = []
        for row in range(self._history_model.rowCount()):
            rows.append([
                self._history_model.item(row, col).text() if self._history_model.item(row, col) else ""
                for col in range(self._history_model.columnCount())
            ])
        try:
            with open(path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(self.HISTORY_HEADERS)
                writer.writerows(rows)
        except OSError as exc:                                          
            QMessageBox.critical(self.widget, "Movimentações", f"Não foi possível exportar.\n{exc}")
            return
        QMessageBox.information(self.widget, "Movimentações", "Histórico exportado com sucesso.")
