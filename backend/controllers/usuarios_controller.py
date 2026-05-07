from __future__ import annotations

from dataclasses import dataclass
from numbers import Number
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.database.database_manager import DatabaseManager
from backend.utils.validators import validar_email, validar_senha
from backend.services.audit_helper import registrar_criacao, registrar_atualizacao, registrar_exclusao
from backend.utils.loading_indicator import LoadingCursor
import bcrypt


@dataclass
class _UserRecord:
    id_usuario: int
    nome: str
    email: str
    nivel_acesso: str
    ativo: Optional[bool] = None
    ativo_label: str = "-"


class UsuariosController:
    """Controller responsável pela tela de usuários."""

    TABLE_HEADERS: List[str] = ["ID", "Nome", "Email", "Papel", "Ativo"]

    def __init__(self, widget: QWidget, db_manager: DatabaseManager, current_user=None) -> None:
        self.widget = widget
        self.db_manager = db_manager
        self.current_user = current_user or {}

        self.table: Optional[QTableWidget] = self.widget.findChild(QTableWidget, "tbl_users")
        self.search_input: Optional[QLineEdit] = self.widget.findChild(QLineEdit, "le_search")
        self.btn_search: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_search")
        self.btn_reset: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_reset")
        self.btn_novo: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_novo")
        self.btn_editar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_editar")
        self.btn_excluir: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_excluir")
        self.btn_salvar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_salvar")
        self.btn_cancelar: Optional[QPushButton] = self.widget.findChild(QPushButton, "btn_cancelar")

        self._usuarios: List[_UserRecord] = []
        self._setup_table()
        self._connect_signals()
        self._configure_permissions()
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
        if self.btn_search:
            self.btn_search.clicked.connect(self.apply_filters)
        if self.btn_reset:
            self.btn_reset.clicked.connect(self.clear_filters)
        if self.search_input:
            self.search_input.returnPressed.connect(self.apply_filters)
        if self.btn_novo:
            self.btn_novo.clicked.connect(self._handle_novo)
        if self.btn_editar:
            self.btn_editar.clicked.connect(self._handle_editar)
        if self.btn_excluir:
            self.btn_excluir.clicked.connect(self._handle_excluir)
        if self.btn_salvar:
            self.btn_salvar.clicked.connect(self._handle_editar)
        if self.btn_cancelar:
            self.btn_cancelar.clicked.connect(self._handle_cancelar)


    def _configure_permissions(self) -> None:
        """Desabilita ações restritas para perfis sem privilégio de admin/master."""
        is_admin = DatabaseManager.has_admin_privileges(self.current_user)
        restricted_buttons = [
            self.btn_novo,
            self.btn_editar,
            self.btn_excluir,
            self.btn_salvar,
            self.btn_cancelar,
        ]

        for btn in restricted_buttons:
            if not btn:
                continue
            btn.setEnabled(is_admin)
            if not is_admin:
                btn.setToolTip(
                    "Somente administradores ou usuários master podem criar, editar ou excluir contas."
                )
            else:
                btn.setToolTip(None)


                
    def refresh(self) -> None:
        self._carregar_usuarios()

    def apply_filters(self) -> None:
        self._carregar_usuarios()

    def clear_filters(self) -> None:
        if self.search_input:
            self.search_input.clear()
        self._carregar_usuarios()

                                                                          
                  
    @staticmethod
    def _parse_active_value(value: object) -> Tuple[Optional[bool], str]:
        truthy = {"1", "true", "t", "sim", "s", "yes", "y", "ativo", "active"}
        falsy = {"0", "false", "f", "nao", "não", "n", "inativo", "inactive"}

        if isinstance(value, bool):
            return value, "Sim" if value else "Não"
        if value is None:
            return None, "-"
        if isinstance(value, Number):
            flag = value != 0
            return flag, "Sim" if flag else "Não"
        if isinstance(value, (bytes, bytearray)):
            try:
                decoded = value.decode().strip()
            except Exception:
                return None, "-"
            return UsuariosController._parse_active_value(decoded)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None, "-"
            lowered = text.lower()
            if lowered in truthy:
                return True, "Sim"
            if lowered in falsy:
                return False, "Não"
            try:
                numeric = float(text.replace(",", "."))
            except ValueError:
                return None, text
            flag = numeric != 0.0
            return flag, "Sim" if flag else "Não"

        flag = bool(value)
        return flag, "Sim" if flag else "Não"

    def _carregar_usuarios(self) -> None:
        with LoadingCursor():
            termo = self.search_input.text().strip() if self.search_input else None
            rows = self.db_manager.list_users(termo or None)
        self._usuarios = []
        if self.table:
            self.table.setRowCount(0)
        for row in rows:
            ativo_bool, ativo_label = self._parse_active_value(row.get("ativo"))
            record = _UserRecord(
                id_usuario=int(row.get("id_usuario")),
                nome=str(row.get("nome")),
                email=str(row.get("email")),
                nivel_acesso=str(row.get("nivel_acesso", "-")),
                ativo=ativo_bool,
                ativo_label=ativo_label,
            )
            self._usuarios.append(record)
        self._popular_tabela()

    def _popular_tabela(self) -> None:
        if not self.table:
            return
        self.table.setRowCount(len(self._usuarios))
        for row_index, usuario in enumerate(self._usuarios):
            self._set_item(row_index, 0, str(usuario.id_usuario), selectable=False)
            self._set_item(row_index, 1, usuario.nome)
            self._set_item(row_index, 2, usuario.email)
            self._set_item(row_index, 3, usuario.nivel_acesso)
            self._set_item(row_index, 4, usuario.ativo_label)
        self.table.resizeColumnsToContents()

    def _set_item(self, row: int, column: int, text: str, selectable: bool = True) -> None:
        if not self.table:
            return
        item = QTableWidgetItem(text)
        flags = item.flags()
        flags &= ~Qt.ItemFlag.ItemIsEditable
        if not selectable:
            flags &= ~Qt.ItemFlag.ItemIsSelectable
        item.setFlags(flags)
        self.table.setItem(row, column, item)

    def _current_level(self) -> str:
        if isinstance(self.current_user, dict):
            level = self.current_user.get("nivel_acesso")
            if level:
                return str(level).lower()
        return "user"

    def _allowed_roles_to_assign(self, existing_level: Optional[str] = None) -> List[str]:
        level = self._current_level()
        if level == "master":
            return ["master", "admin", "user"]
        if level == "admin":
            return ["user"]
        if existing_level and existing_level.lower() == "user":
            return ["user"]
        return ["user"] if existing_level is None else []

    def _can_manage(self, target_level: Optional[str]) -> bool:
        level = self._current_level()
        target = (target_level or "user").lower()
        if level == "master":
            return True
        if level == "admin":
            return target == "user"
        return level == "user" and target == "user"

    def _can_assign_role(self, desired_level: Optional[str]) -> bool:
        target = (desired_level or "user").lower()
        return target in [role.lower() for role in self._allowed_roles_to_assign(desired_level)]

    def _show_hierarchy_warning(self, target_level: Optional[str]) -> None:
        target = (target_level or "usuário").lower()
        level = self._current_level()
        if target == "master":
            msg = "Apenas usuários com papel master podem gerenciar contas master."
        elif target == "admin":
            msg = "Administradores não podem alterar ou remover outros administradores ou masters."
        elif level == "user":
            msg = "Usuários comuns não têm permissão para esta ação."
        else:
            msg = "Você não tem permissão para realizar esta ação para este papel."
        QMessageBox.warning(self.widget, "Usuários", msg)

                                                                          
                   
    def _handle_novo(self) -> None:
        dialog = _UsuarioDialog(parent=self.widget, title="Novo usuário", current_user=self.current_user)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dados = dialog.collect_data()
        if not dados:
            return
        if (
            dados.get("nivel_acesso") == "master"
            and not DatabaseManager.has_master_privileges(self.current_user)
        ):
            QMessageBox.warning(
                self.widget,
                "Usuários",
                "Apenas um usuário master pode criar outro usuário master.",
            )
            return
        try:
            user = self.db_manager.create_user(
                dados["nome"],
                dados["email"],
                dados["senha"],
                nivel_acesso=dados.get("nivel_acesso", "user"),
                ativo=dados.get("ativo"),
            )
            if not user:
                QMessageBox.warning(self.widget, "Usuários", "E-mail já cadastrado.")
                return
            
            # Registrar auditoria
            if self.current_user:
                registrar_criacao(
                    self.db_manager, 
                    self.current_user, 
                    "usuarios", 
                    user['id_usuario'],
                    {"nome": user['nome'], "email": user['email'], "nivel_acesso": user['nivel_acesso']}
                )
        except Exception as exc:
            import mysql.connector
            if isinstance(exc, mysql.connector.Error) and exc.errno == 1062:
                QMessageBox.warning(self.widget, "Usuários", "E-mail já cadastrado.")
            else:
                QMessageBox.critical(self.widget, "Usuários", f"Não foi possível criar o usuário.\n{exc}")
            return
        self.refresh()

    def _handle_editar(self) -> None:
        usuario = self._usuario_selecionado()
        if not usuario:
            QMessageBox.information(self.widget, "Usuários", "Selecione um usuário para editar.")
            return
        if usuario.nivel_acesso == "master" and not DatabaseManager.has_master_privileges(self.current_user):
            QMessageBox.warning(
                self.widget,
                "Usuários",
                "Somente um usuário master pode editar outro usuário com papel master.",
            )
            return
        dialog = _UsuarioDialog(
            parent=self.widget,
            title=f"Editar usuário #{usuario.id_usuario}",
            usuario=usuario,
            current_user=self.current_user,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dados = dialog.collect_data(include_password=False)
        if dialog.password_changed:
            # Gerar hash da nova senha
            senha_hash = bcrypt.hashpw(dialog.password_value.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            dados["senha"] = senha_hash
        if (
            dados.get("nivel_acesso") == "master"
            and not DatabaseManager.has_master_privileges(self.current_user)
        ):
            QMessageBox.warning(
                self.widget,
                "Usuários",
                "Apenas um usuário master pode atribuir ou manter o papel master.",
            )
            return
        try:
            self.db_manager.update_user(usuario.id_usuario, dados)
            
            # Registrar auditoria
            if self.current_user:
                registrar_atualizacao(
                    self.db_manager, 
                    self.current_user, 
                    "usuarios", 
                    usuario.id_usuario
                )
        except Exception as exc:                                       
            QMessageBox.critical(self.widget, "Usuários", f"Não foi possível atualizar o usuário.\n{exc}")
            return
        self.refresh()

    def _handle_excluir(self) -> None:
        # Verificar permissão de admin/master
        if not DatabaseManager.has_admin_privileges(self.current_user):
            QMessageBox.warning(
                self.widget,
                "Usuários",
                "Ação permitida apenas para administradores ou usuários master.",
            )
            return
        
        usuario = self._usuario_selecionado()
        if not usuario:
            QMessageBox.information(self.widget, "Usuários", "Selecione um usuário para excluir.")
            return
        if (
            usuario.nivel_acesso
            and usuario.nivel_acesso.lower() == "master"
            and not DatabaseManager.has_master_privileges(self.current_user)
        ):
            QMessageBox.warning(
                self.widget,
                "Usuários",
                "Somente um usuário master pode remover outro usuário com papel master.",
            )
            return
        resposta = QMessageBox.question(
            self.widget,
            "Usuários",
            f"Tem certeza que deseja remover '{usuario.nome}'?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        try:
            # Registrar auditoria antes de excluir
            if self.current_user:
                registrar_exclusao(
                    self.db_manager, 
                    self.current_user, 
                    "usuarios", 
                    usuario.id_usuario,
                    {"nome": usuario.nome, "email": usuario.email}
                )
            
            self.db_manager.delete_user(usuario.id_usuario)
        except Exception as exc:
            import mysql.connector
            if isinstance(exc, mysql.connector.Error) and exc.errno == 1451:
                QMessageBox.warning(self.widget, "Usuários", "Não é possível excluir este usuário pois existem dados relacionados.")
            else:
                QMessageBox.critical(self.widget, "Usuários", f"Não foi possível remover o usuário.\n{exc}")
            return
        self.refresh()

    def _handle_cancelar(self) -> None:
        if self.table:
            self.table.clearSelection()
        self.refresh()

    def _usuario_selecionado(self) -> Optional[_UserRecord]:
        if not self.table:
            return None
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        if 0 <= row < len(self._usuarios):
            return self._usuarios[row]
        return None


class _UsuarioDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        usuario: Optional[_UserRecord] = None,
        current_user: Optional[dict] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.usuario = usuario
        self.current_user = current_user or {}
        self.password_changed = False
        self.password_value = ""
        self._is_master_user = DatabaseManager.has_master_privileges(self.current_user)

        self.nome_input = QLineEdit(self)
        self.email_input = QLineEdit(self)
        self.senha_input = QLineEdit(self)
        self.confirmacao_input = QLineEdit(self)
        self.nivel_combo = QComboBox(self)
        self.ativo_check = QCheckBox("Usuário ativo", self)

        self.senha_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirmacao_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.nivel_combo.addItems(["master", "admin", "user"])
        if not self._is_master_user:
            master_index = self.nivel_combo.findText("master", Qt.MatchFlag.MatchFixedString)
            if master_index >= 0:
                model = self.nivel_combo.model()
                item = model.item(master_index) if hasattr(model, "item") else None
                if item:
                    item.setEnabled(False)
                    item.setData(Qt.ItemDataRole.ToolTipRole, "Apenas um usuário master pode atribuir este papel.")
        self.nivel_combo.setCurrentText("user")

        form_layout = QFormLayout()
        form_layout.addRow("Nome:", self.nome_input)
        form_layout.addRow("Email:", self.email_input)
        form_layout.addRow("Senha:", self.senha_input)
        form_layout.addRow("Confirmar senha:", self.confirmacao_input)
        form_layout.addRow("Papel:", self.nivel_combo)
        form_layout.addRow("", self.ativo_check)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(self.buttons)

        if usuario:
            self._populate(usuario)

    def _populate(self, usuario: _UserRecord) -> None:
        self.nome_input.setText(usuario.nome)
        self.email_input.setText(usuario.email)
        index = self.nivel_combo.findText(usuario.nivel_acesso, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.nivel_combo.setCurrentIndex(index)
        is_active = bool(usuario.ativo) if usuario.ativo is not None else False
        self.ativo_check.setChecked(is_active)
        self.senha_input.setPlaceholderText("Manter senha atual")
        self.confirmacao_input.setPlaceholderText("Manter senha atual")

    def _on_accept(self) -> None:
        if not self.nome_input.text().strip():
            QMessageBox.warning(self, "Usuários", "Informe o nome do usuário.")
            return
        
        email = self.email_input.text().strip()
        if not email:
            QMessageBox.warning(self, "Usuários", "Informe o email do usuário.")
            return
        
        # Validar formato de e-mail
        valido_email, msg_email = validar_email(email)
        if not valido_email:
            QMessageBox.warning(self, "Usuários", msg_email)
            return

        role = self.nivel_combo.currentText()
        if role == "master" and not self._is_master_user:
            QMessageBox.warning(
                self,
                "Usuários",
                "Apenas um usuário master pode atribuir o papel master.",
            )
            return
        if self.usuario and self.usuario.nivel_acesso == "master" and not self._is_master_user:
            QMessageBox.warning(
                self,
                "Usuários",
                "Você não pode editar um usuário com papel master.",
            )
            return

        senha = self.senha_input.text()
        confirmacao = self.confirmacao_input.text()
        
        if self.usuario is None:
            # Novo usuário - senha é obrigatória
            if not senha:
                QMessageBox.warning(self, "Usuários", "Informe uma senha para o novo usuário.")
                return
            
            # Validar tamanho mínimo da senha
            valido_senha, msg_senha = validar_senha(senha)
            if not valido_senha:
                QMessageBox.warning(self, "Usuários", msg_senha)
                return
            
            if senha != confirmacao:
                QMessageBox.warning(self, "Usuários", "As senhas não conferem.")
                return
            
            self.password_changed = True
            self.password_value = senha
        else:
            # Edição - senha é opcional
            if senha or confirmacao:
                # Se informou senha, validar
                valido_senha, msg_senha = validar_senha(senha)
                if not valido_senha:
                    QMessageBox.warning(self, "Usuários", msg_senha)
                    return
                
                if senha != confirmacao:
                    QMessageBox.warning(self, "Usuários", "As senhas não conferem.")
                    return
                
                self.password_changed = True
                self.password_value = senha
        
        self.accept()

    def collect_data(self, include_password: bool = True) -> Dict[str, object]:
        data: Dict[str, object] = {
            "nome": self.nome_input.text().strip(),
            "email": self.email_input.text().strip(),
            "nivel_acesso": self.nivel_combo.currentText(),
            "ativo": self.ativo_check.isChecked(),
        }
        if include_password:
            data["senha"] = self.senha_input.text()
        return data
