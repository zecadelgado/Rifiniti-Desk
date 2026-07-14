from __future__ import annotations

import datetime
from typing import Dict, Optional

from PySide6.QtCore import QDate
from backend.database.postgres_driver import DatabaseError
from backend.utils.validators import validar_numero_nota_fiscal, validar_ncm, validar_cfop
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QSpinBox,
)


class NotasFiscaisController:
    def __init__(self, widget, db_manager, current_user=None):
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user
        self.current_invoice_id: Optional[int] = None
        self.editing_item_id: Optional[int] = None
        self.itens_model: Optional[QStandardItemModel] = None
        self._cmb_centro_custo = self.widget.findChild(QComboBox, "cmb_centro_custo")
        self.invoice_columns: Dict[str, Optional[str]] = {}
        self._invoice_columns_meta: Dict[str, Dict[str, Optional[str]]] = {}
        self._centro_custo_available = False
        self._centro_custo_required = False
        self._discover_invoice_columns()
        self._ensure_items_model()
        self._connect_signals()
        self._load_fornecedores_no_combo()
        self._load_centros_custo_no_combo()
        self._set_buttons_state()

    def _connect_signals(self):
        w = self.widget
        btn = w.findChild(QPushButton, "btn_novo")
        if btn:
            btn.clicked.connect(self._new_invoice)
        btn = w.findChild(QPushButton, "btn_salvar")
        if btn:
            btn.clicked.connect(self._save_invoice)
        btn = w.findChild(QPushButton, "btn_excluir")
        if btn:
            btn.clicked.connect(self._delete_invoice)
        btn = w.findChild(QPushButton, "btn_buscar")
        if btn:
            btn.clicked.connect(self._handle_search)
        btn = w.findChild(QPushButton, "btn_anexar")
        if btn:
            btn.clicked.connect(self._attach_document)
        btn = w.findChild(QPushButton, "btn_visualizar")
        if btn:
            btn.clicked.connect(self._view_document)
        btn = w.findChild(QPushButton, "btn_novo_item")
        if btn:
            btn.clicked.connect(self._new_item)
        btn = w.findChild(QPushButton, "btn_editar_item")
        if btn:
            btn.clicked.connect(self._edit_item)
        btn = w.findChild(QPushButton, "btn_excluir_item")
        if btn:
            btn.clicked.connect(self._delete_item)
        btn = w.findChild(QPushButton, "btn_salvar_item")
        if btn:
            btn.clicked.connect(self._save_item)

    def _set_buttons_state(self):
        w = self.widget
        has_id = self.current_invoice_id is not None
        for obj_name, enabled in [
            ("btn_excluir", has_id),
            ("btn_anexar", has_id),
            ("btn_visualizar", has_id),
            ("btn_novo_item", has_id),
            ("btn_editar_item", has_id),
            ("btn_excluir_item", has_id),
            ("btn_salvar_item", has_id),
        ]:
            btn = w.findChild(QPushButton, obj_name)
            if btn:
                btn.setEnabled(enabled)

    def _load_fornecedores_no_combo(self):
        w = self.widget
        cmb = w.findChild(QComboBox, "cmb_fornecedor")
        if cmb is None:
            return
        current_value = cmb.currentData() if cmb.currentIndex() >= 0 else None
        cmb.clear()
        try:
            conn = self.db_manager.connection
            cur = conn.cursor()
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("fornecedores",),
            )
            cols = [row[0] for row in cur.fetchall()]
            id_candidates = ["id_fornecedor", "id", "fornecedor_id", "cod_fornecedor", "codigo", "idFornecedor"]
            name_candidates = ["nome", "razao_social", "fantasia", "descricao", "nome_fornecedor", "empresa", "razaosocial", "nm_fornecedor"]
            id_col = next((c for c in id_candidates if c in cols), None)
            name_col = next((c for c in name_candidates if c in cols), None)
            if not id_col or not name_col:
                raise DatabaseError(f"Nao encontrei colunas de id/nome em 'fornecedores'. Colunas: {', '.join(cols)}")
            sql = f"SELECT \"{id_col}\", \"{name_col}\" FROM fornecedores ORDER BY \"{name_col}\""
            cur.execute(sql)
            for id_val, name_val in cur.fetchall():
                cmb.addItem(str(name_val), id_val)
        except DatabaseError as err:
            QMessageBox.warning(w, "Fornecedores", f"Não foi possível carregar fornecedores.\n{err}")
            return
        self._select_combo_by_data(cmb, current_value)

    def _discover_invoice_columns(self):
        self.invoice_columns = {"id": None, "centro_custo": None}
        self._invoice_columns_meta = {}
        self._centro_custo_available = False
        self._centro_custo_required = False
        if self._cmb_centro_custo is None:
            return
        cursor = None
        try:
            conn = self.db_manager.connection
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable, NULL, column_default, NULL
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("notas_fiscais",),
            )
            rows = cursor.fetchall()
        except DatabaseError as err:
            self._cmb_centro_custo.setEnabled(False)
            self._cmb_centro_custo.setToolTip(f"Nao foi possivel ler as colunas de notas_fiscais.\n{err}")
            return
        finally:
            if cursor:
                cursor.close()
        columns = []
        for field, col_type, is_null, key, default, extra in rows:
            columns.append(field)
            self._invoice_columns_meta[field] = {"type": col_type, "nullable": is_null == "YES", "default": default}
        def pick(*candidates):
            for candidate in candidates:
                if candidate in columns:
                    return candidate
            return None
        self.invoice_columns["id"] = pick("id_nota_fiscal", "id")
        self.invoice_columns["centro_custo"] = pick("id_centro_custo", "centro_custo_id", "idCentroCusto", "fk_centro_custo")
        centro_col = self.invoice_columns.get("centro_custo")
        if centro_col:
            self._centro_custo_available = True
            meta = self._invoice_columns_meta.get(centro_col) or {}
            self._centro_custo_required = not meta.get("nullable", True)
            self._cmb_centro_custo.setEnabled(True)
            self._cmb_centro_custo.setToolTip("")
        else:
            self._cmb_centro_custo.setEnabled(False)
            self._cmb_centro_custo.setToolTip("Coluna de centro de custo nao encontrada em notas_fiscais.")

    def _load_centros_custo_no_combo(self):
        combo = self._cmb_centro_custo
        if combo is None:
            return
        current_value = combo.currentData() if combo.currentIndex() >= 0 else None
        combo.clear()
        if not self._centro_custo_available:
            combo.setEnabled(False)
            combo.setCurrentIndex(-1)
            return
        combo.setEnabled(True)
        combo.setToolTip("")
        cursor = None
        rows = []
        code_col = None
        try:
            conn = self.db_manager.connection
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                ("centro_custo",),
            )
            cols = [row[0] for row in cursor.fetchall()]
            id_candidates = ["id_centro_custo", "id", "centro_custo_id", "idCentroCusto"]
            name_candidates = ["nome_centro", "nome", "descricao", "titulo"]
            code_candidates = ["codigo", "cod_centro", "cod", "sigla"]
            has_ativo = "ativo" in cols
            id_col = next((c for c in id_candidates if c in cols), None)
            name_col = next((c for c in name_candidates if c in cols), None)
            code_col = next((c for c in code_candidates if c in cols), None)
            if not id_col or not name_col:
                raise DatabaseError(f"Nao encontrei colunas de id/nome em 'centro_custo'. Colunas: {', '.join(cols)}")
            select_cols = [f'"{id_col}"', f'"{name_col}"']
            if code_col:
                select_cols.append(f'"{code_col}"')
            where_clause = ' WHERE "ativo" = 1' if has_ativo else ""
            sql = f"SELECT {', '.join(select_cols)} FROM centro_custo{where_clause} ORDER BY \"{name_col}\""
            cursor.execute(sql)
            rows = cursor.fetchall()
        except DatabaseError as err:
            QMessageBox.warning(self.widget, "Centro de Custo", f"Nao foi possivel carregar centros de custo.\n{err}")
            return
        finally:
            if cursor:
                cursor.close()
        for row in rows:
            id_val = row[0]
            name_val = row[1]
            display = str(name_val)
            if code_col and len(row) > 2:
                code_val = row[2]
                if code_val:
                    display = f"{code_val} - {display}"
            combo.addItem(display, id_val)
        self._select_combo_by_data(combo, current_value)

    @staticmethod
    def _select_combo_by_data(combo: QComboBox, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(-1)

    def _ensure_items_model(self):
        if self.itens_model is not None:
            return
        self.itens_model = QStandardItemModel(0, 6, self.widget)
        self.itens_model.setHorizontalHeaderLabels(["Descrição", "Qtd", "Valor", "NCM", "CFOP", "ID_ITEM"])
        view = self.widget.findChild(QTableView, "tbl_itens")
        if view:
            view.setModel(self.itens_model)
            view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
            view.setColumnHidden(5, True)

    def _clear_items_model(self):
        if self.itens_model:
            self.itens_model.removeRows(0, self.itens_model.rowCount())

    def _item_widget_refs(self):
        w = self.widget
        return (
            w.findChild(QLineEdit, "txt_item_descricao"),
            w.findChild(QSpinBox, "spin_item_quantidade"),
            w.findChild(QDoubleSpinBox, "spin_item_valor"),
            w.findChild(QLineEdit, "txt_item_ncm"),
            w.findChild(QLineEdit, "txt_item_cfop"),
            w.findChild(QTableView, "tbl_itens"),
        )

    def _clear_item_fields(self):
        desc, sp_qtd, sp_valor, txt_ncm, txt_cfop, _ = self._item_widget_refs()
        if desc:
            desc.clear()
        if sp_qtd:
            sp_qtd.setValue(1)
        if sp_valor:
            sp_valor.setValue(0.0)
        if txt_ncm:
            txt_ncm.clear()
        if txt_cfop:
            txt_cfop.clear()
        self.editing_item_id = None

    def _selected_item_row_id(self):
        view = self.widget.findChild(QTableView, "tbl_itens")
        if not view or not self.itens_model:
            return -1, None
        sel = view.selectionModel().selectedRows()
        if not sel:
            return -1, None
        row = sel[0].row()
        idx = self.itens_model.index(row, 5)
        item_id = self.itens_model.data(idx)
        try:
            item_id = int(item_id)
        except Exception:
            item_id = None
        return row, item_id

    def _append_item_to_model(self, desc: str, qtd: int, valor: float, ncm: str | None, cfop: str | None, item_id: int):
        if not self.itens_model:
            return
        row = self.itens_model.rowCount()
        self.itens_model.insertRow(row)
        self.itens_model.setItem(row, 0, QStandardItem(str(desc)))
        self.itens_model.setItem(row, 1, QStandardItem(str(qtd)))
        self.itens_model.setItem(row, 2, QStandardItem(f"{valor:.2f}"))
        self.itens_model.setItem(row, 3, QStandardItem(str(ncm or "")))
        self.itens_model.setItem(row, 4, QStandardItem(str(cfop or "")))
        self.itens_model.setItem(row, 5, QStandardItem(str(item_id)))

    def _recalc_total_from_items(self):
        if not self.itens_model:
            return
        total = 0.0
        for r in range(self.itens_model.rowCount()):
            try:
                qtd = int(self.itens_model.index(r, 1).data())
                val = float(str(self.itens_model.index(r, 2).data()).replace(",", "."))
                total += qtd * val
            except Exception:
                pass
        spin_total = self.widget.findChild(QDoubleSpinBox, "spin_valor_total")
        if spin_total:
            spin_total.setValue(total)

    def _new_invoice(self):
        w = self.widget
        w.findChild(QLineEdit, "txt_numero").clear()
        w.findChild(QDateEdit, "date_emissao").setDate(QDate.currentDate())
        cmb = w.findChild(QComboBox, "cmb_fornecedor")
        if cmb:
            cmb.setCurrentIndex(-1)
        if self._cmb_centro_custo:
            self._cmb_centro_custo.setCurrentIndex(-1)
        w.findChild(QDoubleSpinBox, "spin_valor_total").setValue(0.0)
        w.findChild(QLineEdit, "txt_anexo").clear()
        self._clear_items_model()
        self.current_invoice_id = None
        self.editing_item_id = None
        self._set_buttons_state()

    def _save_invoice(self):
        w = self.widget
        txt_num = w.findChild(QLineEdit, "txt_numero")
        date_edit = w.findChild(QDateEdit, "date_emissao")
        cmb_for = w.findChild(QComboBox, "cmb_fornecedor")
        spin_total = w.findChild(QDoubleSpinBox, "spin_valor_total")
        txt_anexo = w.findChild(QLineEdit, "txt_anexo")
        numero = (txt_num.text() if txt_num else "").strip()
        if not numero:
            QMessageBox.warning(w, "Validação", "Informe o número da nota.")
            return
        
        # Validar formato do número da nota
        valido, mensagem = validar_numero_nota_fiscal(numero)
        if not valido:
            QMessageBox.warning(w, "Validação", mensagem)
            return
        qd = date_edit.date() if date_edit else QDate.currentDate()
        data_emissao = qd.toPython()
        id_fornecedor = cmb_for.currentData() if cmb_for else None
        if id_fornecedor is None:
            QMessageBox.warning(w, "Validação", "Selecione um fornecedor.")
            return
        centro_col = self.invoice_columns.get("centro_custo")
        id_centro_custo = None
        if centro_col and self._cmb_centro_custo and self._centro_custo_available:
            idx = self._cmb_centro_custo.currentIndex()
            if idx >= 0:
                id_centro_custo = self._cmb_centro_custo.itemData(idx)
            if isinstance(id_centro_custo, str):
                trimmed = id_centro_custo.strip()
                if trimmed.isdigit():
                    try:
                        id_centro_custo = int(trimmed)
                    except ValueError:
                        id_centro_custo = trimmed
                else:
                    id_centro_custo = trimmed or None
            if self._centro_custo_required and id_centro_custo is None:
                QMessageBox.warning(w, "Validação", "Selecione um centro de custo.")
                return
        valor_total = float(spin_total.value()) if spin_total else 0.0
        caminho = (txt_anexo.text() if txt_anexo else "").strip() or None
        columns = ["numero_nota", "data_emissao", "valor_total", "id_fornecedor", "caminho_arquivo_nf"]
        values = [numero, data_emissao, valor_total, id_fornecedor, caminho]
        if centro_col:
            columns.append(centro_col)
            values.append(id_centro_custo)
        try:
            conn = self.db_manager.connection
            cur = conn.cursor()
            if self.current_invoice_id is None:
                col_identifiers = ", ".join(f'"{col}"' for col in columns)
                placeholders = ", ".join(["%s"] * len(values))
                sql = f"INSERT INTO notas_fiscais ({col_identifiers}) VALUES ({placeholders})"
                cur.execute(sql, tuple(values))
                conn.commit()
                self.current_invoice_id = cur.lastrowid
                QMessageBox.information(w, "Sucesso", f"Nota {numero} criada (ID {self.current_invoice_id}).")
            else:
                assignments = ", ".join(f'"{col}"=%s' for col in columns)
                params = list(values)
                params.append(self.current_invoice_id)
                sql = f"UPDATE notas_fiscais SET {assignments} WHERE id_nota_fiscal=%s"
                cur.execute(sql, tuple(params))
                conn.commit()
                QMessageBox.information(w, "Sucesso", f"Nota {numero} atualizada.")
        except DatabaseError as err:
            QMessageBox.critical(w, "Erro ao salvar", f"Banco: {err}")
            return
        self._set_buttons_state()

    def _handle_search(self):
        w = self.widget
        termo = w.findChild(QLineEdit, "txt_buscar")
        termo_str = (termo.text() if termo else "").strip()
        if not termo_str:
            return
        centro_col = self.invoice_columns.get("centro_custo")
        try:
            cur = self.db_manager.connection.cursor(dictionary=True)
            select_cols = [
                "id_nota_fiscal",
                "numero_nota",
                "data_emissao",
                "valor_total",
                "id_fornecedor",
                "caminho_arquivo_nf",
            ]
            if centro_col:
                select_cols.append(f'"{centro_col}"')
            sql = f"SELECT {', '.join(select_cols)} FROM notas_fiscais WHERE numero_nota = %s"
            cur.execute(sql, (termo_str,))
            row = cur.fetchone()
        except DatabaseError as err:
            QMessageBox.critical(w, "Erro na busca", f"Banco: {err}")
            return
        if not row:
            QMessageBox.information(w, "Busca", "Nenhuma nota encontrada para o número informado.")
            return
        self.current_invoice_id = row["id_nota_fiscal"]
        w.findChild(QLineEdit, "txt_numero").setText(row["numero_nota"])
        dt = row["data_emissao"]
        if isinstance(dt, (datetime.date, datetime.datetime)):
            qd = QDate(dt.year, dt.month, dt.day)
            w.findChild(QDateEdit, "date_emissao").setDate(qd)
        w.findChild(QDoubleSpinBox, "spin_valor_total").setValue(float(row["valor_total"]))
        self._select_combo_by_data(w.findChild(QComboBox, "cmb_fornecedor"), row["id_fornecedor"])
        if self._cmb_centro_custo:
            if centro_col:
                self._select_combo_by_data(self._cmb_centro_custo, row.get(centro_col))
            else:
                self._cmb_centro_custo.setCurrentIndex(-1)
        w.findChild(QLineEdit, "txt_anexo").setText(row.get("caminho_arquivo_nf") or "")
        self._load_items_for_invoice(self.current_invoice_id)
        self._set_buttons_state()
        QMessageBox.information(w, "Busca", f"Nota {row['numero_nota']} carregada.")

    def _delete_invoice(self):
        w = self.widget
        if not self.current_invoice_id:
            return
        resp = QMessageBox.question(
            w,
            "Confirmar exclusão",
            "Deseja realmente excluir esta nota fiscal e seus itens?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        try:
            conn = self.db_manager.connection
            cur = conn.cursor()
            cur.execute("DELETE FROM itens_nota_fiscal WHERE id_nota_fiscal = %s", (self.current_invoice_id,))
            cur.execute("DELETE FROM notas_fiscais WHERE id_nota_fiscal = %s", (self.current_invoice_id,))
            conn.commit()
        except DatabaseError as err:
            QMessageBox.critical(w, "Erro ao excluir", f"Banco: {err}")
            return
        self._new_invoice()
        QMessageBox.information(w, "Exclusão", "Nota fiscal excluída com sucesso.")

    def _attach_document(self):
        w = self.widget
        if not self.current_invoice_id:
            QMessageBox.warning(w, "Atenção", "Salve a nota antes de anexar um documento.")
            return
        path, _ = QFileDialog.getOpenFileName(
            w,
            "Selecione um arquivo",
            "",
            "PDF (*.pdf);;Imagens (*.png *.jpg);;Todos os arquivos (*.*)",
        )
        if not path:
            return
        try:
            cur = self.db_manager.connection.cursor()
            cur.execute(
                "UPDATE notas_fiscais SET caminho_arquivo_nf=%s WHERE id_nota_fiscal=%s",
                (path, self.current_invoice_id),
            )
            self.db_manager.connection.commit()
            w.findChild(QLineEdit, "txt_anexo").setText(path)
            QMessageBox.information(w, "Documento", "Documento anexado com sucesso.")
        except DatabaseError as err:
            QMessageBox.critical(w, "Erro ao anexar", f"Banco: {err}")

    def _view_document(self):
        w = self.widget
        path = w.findChild(QLineEdit, "txt_anexo").text().strip()
        if not path:
            QMessageBox.warning(w, "Documento", "Nenhum arquivo anexado.")
            return
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        if not ok:
            QMessageBox.warning(w, "Documento", "Não foi possível abrir o arquivo.")

    def _load_items_for_invoice(self, id_nota: int):
        self._clear_items_model()
        if not id_nota:
            return
        try:
            cur = self.db_manager.connection.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id_item_nf, descricao, quantidade, valor_unitario, ncm, cfop
                FROM itens_nota_fiscal
                WHERE id_nota_fiscal = %s
                ORDER BY id_item_nf
                """,
                (id_nota,),
            )
            rows = cur.fetchall()
        except DatabaseError as err:
            QMessageBox.critical(self.widget, "Itens", f"Erro ao carregar itens: {err}")
            return
        for r in rows:
            self._append_item_to_model(
                r["descricao"],
                int(r["quantidade"]),
                float(r["valor_unitario"]),
                r.get("ncm") or "",
                r.get("cfop") or "",
                int(r["id_item_nf"]),
            )
        self.editing_item_id = None
        self._recalc_total_from_items()

    def _new_item(self):
        self._clear_item_fields()
        desc, *_ = self._item_widget_refs()
        if desc:
            desc.setFocus()

    def _edit_item(self):
        view = self.widget.findChild(QTableView, "tbl_itens")
        if not view or not self.itens_model:
            return
        row, item_id = self._selected_item_row_id()
        if row < 0:
            QMessageBox.warning(self.widget, "Itens", "Selecione um item para editar.")
            return
        desc = self.itens_model.index(row, 0).data() or ""
        qtd = int(self.itens_model.index(row, 1).data() or 1)
        valor = float(str(self.itens_model.index(row, 2).data() or 0).replace(",", "."))
        ncm = self.itens_model.index(row, 3).data() or ""
        cfop = self.itens_model.index(row, 4).data() or ""
        w_desc, w_qtd, w_valor, w_ncm, w_cfop, _ = self._item_widget_refs()
        if w_desc:
            w_desc.setText(str(desc))
        if w_qtd:
            w_qtd.setValue(int(qtd))
        if w_valor:
            w_valor.setValue(float(valor))
        if w_ncm:
            w_ncm.setText(str(ncm))
        if w_cfop:
            w_cfop.setText(str(cfop))
        self.editing_item_id = item_id

    def _delete_item(self):
        row, item_id = self._selected_item_row_id()
        if row < 0 or not item_id:
            QMessageBox.warning(self.widget, "Itens", "Selecione um item para excluir.")
            return
        resp = QMessageBox.question(
            self.widget,
            "Excluir item",
            "Deseja remover este item da nota fiscal?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        try:
            cur = self.db_manager.connection.cursor()
            cur.execute("DELETE FROM itens_nota_fiscal WHERE id_item_nf=%s", (item_id,))
            self.db_manager.connection.commit()
            self.itens_model.removeRow(row)
            self.editing_item_id = None
            self._recalc_total_from_items()
        except DatabaseError as err:
            QMessageBox.critical(self.widget, "Itens", f"Erro ao excluir item: {err}")

    def _save_item(self):
        if not self.current_invoice_id:
            QMessageBox.warning(self.widget, "Itens", "Salve a nota antes de adicionar itens.")
            return
        w_desc, w_qtd, w_valor, w_ncm, w_cfop, _ = self._item_widget_refs()
        desc = (w_desc.text() if w_desc else "").strip()
        if not desc:
            QMessageBox.warning(self.widget, "Validação", "Descrição do item é obrigatória.")
            return
        qtd = int(w_qtd.value()) if w_qtd else 1
        valor = float(w_valor.value()) if w_valor else 0.0
        
        # Validar NCM se preenchido
        ncm_texto = (w_ncm.text() if w_ncm else "").strip()
        ncm = None
        if ncm_texto:
            valido, mensagem = validar_ncm(ncm_texto)
            if not valido:
                QMessageBox.warning(self.widget, "Validação", mensagem)
                return
            ncm = ncm_texto
        
        # Validar CFOP se preenchido
        cfop_texto = (w_cfop.text() if w_cfop else "").strip()
        cfop = None
        if cfop_texto:
            valido, mensagem = validar_cfop(cfop_texto)
            if not valido:
                QMessageBox.warning(self.widget, "Validação", mensagem)
                return
            cfop = cfop_texto
        try:
            conn = self.db_manager.connection
            cur = conn.cursor()
            if self.editing_item_id is None:
                cur.execute(
                    """
                    INSERT INTO itens_nota_fiscal (id_nota_fiscal, descricao, quantidade, valor_unitario, ncm, cfop)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (self.current_invoice_id, desc, qtd, valor, ncm, cfop),
                )
                conn.commit()
                item_id = cur.lastrowid
                self._append_item_to_model(desc, qtd, valor, ncm, cfop, item_id)
                QMessageBox.information(self.widget, "Itens", "Item inserido com sucesso.")
            else:
                cur.execute(
                    """
                    UPDATE itens_nota_fiscal
                    SET descricao=%s, quantidade=%s, valor_unitario=%s, ncm=%s, cfop=%s
                    WHERE id_item_nf=%s
                    """,
                    (desc, qtd, valor, ncm, cfop, self.editing_item_id),
                )
                conn.commit()
                target_row = None
                for r in range(self.itens_model.rowCount()):
                    if str(self.itens_model.index(r, 5).data()) == str(self.editing_item_id):
                        target_row = r
                        break
                if target_row is not None:
                    self.itens_model.setItem(target_row, 0, QStandardItem(str(desc)))
                    self.itens_model.setItem(target_row, 1, QStandardItem(str(qtd)))
                    self.itens_model.setItem(target_row, 2, QStandardItem(f"{valor:.2f}"))
                    self.itens_model.setItem(target_row, 3, QStandardItem(str(ncm or "")))
                    self.itens_model.setItem(target_row, 4, QStandardItem(str(cfop or "")))
                QMessageBox.information(self.widget, "Itens", "Item atualizado com sucesso.")
            self._recalc_total_from_items()
            self._clear_item_fields()
        except DatabaseError as err:
            QMessageBox.critical(self.widget, "Itens", f"Erro ao salvar item: {err}")

    def refresh(self):
        self._load_fornecedores_no_combo()
        self._load_centros_custo_no_combo()
