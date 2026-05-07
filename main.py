
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QLabel,
    QListWidget,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QFileInfo, QTimer, QDate, QDateTime
from PySide6.QtGui import QBrush, QColor, QFont, QTextCharFormat
from frontend.resources import resources_rc

from backend.database.database_manager import DatabaseManager
from backend.utils.validators import validar_email, validar_senha
from backend.controllers.anexos_controller import AnexosController
from backend.controllers.auditoria_controller import AuditoriaController
from backend.controllers.centro_custo import CentroCustoController
from backend.controllers.depreciassao import DepreciacaoController
from backend.controllers.fornecedores import FornecedoresController
from backend.controllers.manutencao_controller import ManutencaoController
from backend.controllers.movimentacoes_controller import MovimentacoesController
from backend.controllers.Notas import NotasFiscaisController
from backend.controllers.patrimonio_controller import PatrimonioController
from backend.controllers.relatorios_controller import RelatoriosController
from backend.controllers.setores_locais_controller import SetoresLocaisController
from backend.controllers.usuarios_controller import UsuariosController


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
UI_DIR = FRONTEND_DIR / "ui"
STYLE_DIR = FRONTEND_DIR / "styles"


def create_controller(key, widget, db_manager, current_user=None):
    # Passar current_user para todos os controllers que precisam de controle de acesso
    if key == "usuarios":
        return UsuariosController(widget, db_manager, current_user)
    if key == "notas_fiscais":
        return NotasFiscaisController(widget, db_manager, current_user)
    if key == "fornecedores":
        return FornecedoresController(widget, db_manager, current_user)
    if key == "centro_custo":
        return CentroCustoController(widget, db_manager, current_user)
    if key == "movimentacoes":
        return MovimentacoesController(widget, db_manager, current_user)
    if key == "manutencao":
        return ManutencaoController(widget, db_manager, current_user)
    if key == "patrimonio":
        return PatrimonioController(widget, db_manager, current_user)
    if key == "depreciacao":
        return DepreciacaoController(widget, db_manager, current_user)
    if key == "auditoria":
        return AuditoriaController(widget, db_manager, current_user)
    if key == "anexos":
        return AnexosController(widget, db_manager, current_user)
    if key == "relatorios":
        return RelatoriosController(widget, db_manager, current_user)
    if key == "setores_locais":
        return SetoresLocaisController(widget, db_manager, current_user)
    return None

def load_ui(file_name: str):
                                                            
    ui_file_path = UI_DIR / file_name
    loader = QUiLoader()
    loader.setWorkingDirectory(QFileInfo(str(ui_file_path)).dir())
    ui_file = QFile(str(ui_file_path))
    if not ui_file.open(QFile.ReadOnly):
        raise RuntimeError(f"Não foi possível abrir {ui_file_path}")
    widget = loader.load(ui_file)
    ui_file.close()
    if not widget:
        raise RuntimeError(f"Falha ao carregar {ui_file_path}")
    return widget


def load_global_theme():
    """Return the shared NeoBeneSys stylesheet content if available."""
    theme_path = STYLE_DIR / "theme.qss"
    if not theme_path.exists():
        return ""
    try:
        return theme_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[Aviso] Não foi possível aplicar o tema global: {exc}")
        return ""


class NeoBenesysApp:
    def __init__(self, global_theme: str = ""):
        self._global_theme = global_theme
        self._theme_applied = False
        self.db_manager = DatabaseManager()
        if not self.db_manager.connect():
            QMessageBox.critical(None, "Erro de Conexão", "Não foi possível conectar ao banco de dados.")
            sys.exit(1)

        try:
            self.db_manager.ensure_categorias(PatrimonioController.FIXED_CATEGORIES)
        except Exception as exc:
            print(f"[Aviso] Não foi possível garantir as categorias padrão: {exc}")

        try:
            self.db_manager.ensure_patrimonio_optional_columns()
        except Exception as exc:
            print(f"[Aviso] Nao foi possivel ajustar as colunas opcionais de patrimonio: {exc}")

        self.login = load_ui("login.ui")
        self.login.setWindowTitle("NeoBenesys - Login")

        btn_entrar = self.login.findChild(QPushButton, "btn_entrar")
        btn_cadastrar = self.login.findChild(QPushButton, "btn_cadastrar")
        btn_esqueci_senha = self.login.findChild(QPushButton, "btn_esqueci_senha")

        if btn_entrar is not None:
            btn_entrar.clicked.connect(self.handle_login)
        else:
            print("[Aviso] Botão 'btn_entrar' não encontrado no login.ui")

        if btn_cadastrar is not None:
            btn_cadastrar.clicked.connect(self.abrir_cadastro)
        else:
            print("[Aviso] Botão 'btn_cadastrar' não encontrado no login.ui")

        if btn_esqueci_senha is not None:
            btn_esqueci_senha.clicked.connect(self.abrir_recuperar_senha_dialog)
        else:
            print("[Aviso] Botão 'btn_esqueci_senha' não encontrado no login.ui")

        self.dashboard = None
        self.cadastro = None
        self.widgets = {}
        self.screens = {}
        self.controllers = {}
        self.current_user = None
        self._calendar_widget = None
        self._calendar_list = None
        self._calendar_summary_label = None
        self._calendar_highlighted_dates = []
        self._auditorias_por_data = {}
        self._calendar_setup_done = False
        self.recuperar_dialog = None
        self.redefinir_dialog = None

    def _apply_theme_if_needed(self, widget=None):
        if self._theme_applied or not self._global_theme or widget is None:
            return
        widget.setStyleSheet(self._global_theme)
        self._theme_applied = True

    def handle_login(self):
        email_input = self.login.findChild(QLineEdit, "txt_email")
        senha_input = self.login.findChild(QLineEdit, "txt_senha")

        email = email_input.text().strip() if email_input else ""
        senha = senha_input.text() if senha_input else ""

        # Validar campos vazios
        if not email:
            QMessageBox.warning(None, "Login", "Preencha o e-mail.")
            return
        
        if not senha:
            QMessageBox.warning(None, "Login", "Preencha a senha.")
            return
        
        # Validar formato de e-mail
        valido, mensagem = validar_email(email)
        if not valido:
            QMessageBox.warning(None, "Login", mensagem)
            return

        user = self.db_manager.verify_password(email, senha)

        if user:
            self.current_user = user
            QMessageBox.information(None, "Login", f"Bem-vindo, {user.get('nome', 'usuário')}!")
            self.abrir_dashboard()
        else:
            QMessageBox.warning(None, "Login", "Email ou senha incorretos, ou usuário inativo.")

    def abrir_recuperar_senha_dialog(self):
        self.recuperar_dialog = load_ui("recuperar_senha.ui")
        self.recuperar_dialog.setWindowTitle("Recuperar senha")

        btn_enviar = self.recuperar_dialog.findChild(QPushButton, "btn_enviar_token")
        btn_cancelar = self.recuperar_dialog.findChild(QPushButton, "btn_cancelar_recuperar")
        btn_ir_redefinir = self.recuperar_dialog.findChild(QPushButton, "btn_ir_redefinir")

        if btn_enviar is not None:
            btn_enviar.clicked.connect(self.handle_recuperar_senha)
        if btn_cancelar is not None:
            btn_cancelar.clicked.connect(self.recuperar_dialog.close)
        if btn_ir_redefinir is not None:
            btn_ir_redefinir.clicked.connect(lambda: self.abrir_redefinir_senha_dialog())

        self.recuperar_dialog.show()

    def handle_recuperar_senha(self):
        if not self.recuperar_dialog:
            return

        email_input = self.recuperar_dialog.findChild(QLineEdit, "txt_email_recuperar")
        email = email_input.text().strip() if email_input else ""

        valido, mensagem = validar_email(email)
        if not valido:
            QMessageBox.warning(self.recuperar_dialog, "Recuperação de senha", mensagem)
            return

        sucesso, msg = self.db_manager.create_password_reset_token(email)
        if sucesso:
            QMessageBox.information(self.recuperar_dialog, "Recuperacao de senha", msg)
            self.recuperar_dialog.close()
            self.recuperar_dialog = None
            self.abrir_redefinir_senha_dialog()
        else:
            QMessageBox.warning(self.recuperar_dialog, "Recuperacao de senha", msg)

    def abrir_redefinir_senha_dialog(self, token: str = ""):
        if self.recuperar_dialog:
            self.recuperar_dialog.close()
            self.recuperar_dialog = None

        self.redefinir_dialog = load_ui("redefinir_senha.ui")
        self.redefinir_dialog.setWindowTitle("Redefinir senha")

        token_input = self.redefinir_dialog.findChild(QLineEdit, "txt_token")
        nova_senha_input = self.redefinir_dialog.findChild(QLineEdit, "txt_nova_senha")
        confirmar_senha_input = self.redefinir_dialog.findChild(QLineEdit, "txt_confirmar_senha")

        if token and token_input:
            token_input.setText(token)

        btn_redefinir = self.redefinir_dialog.findChild(QPushButton, "btn_confirmar_redefinir")
        btn_cancelar = self.redefinir_dialog.findChild(QPushButton, "btn_cancelar_redefinir")

        if btn_redefinir is not None:
            btn_redefinir.clicked.connect(self.handle_redefinir_senha)
        if btn_cancelar is not None:
            btn_cancelar.clicked.connect(self.redefinir_dialog.close)

        self.redefinir_dialog.show()

    def handle_redefinir_senha(self):
        if not self.redefinir_dialog:
            return

        token_input = self.redefinir_dialog.findChild(QLineEdit, "txt_token")
        nova_senha_input = self.redefinir_dialog.findChild(QLineEdit, "txt_nova_senha")
        confirmar_senha_input = self.redefinir_dialog.findChild(QLineEdit, "txt_confirmar_senha")

        token = token_input.text().strip() if token_input else ""
        nova_senha = nova_senha_input.text() if nova_senha_input else ""
        confirmar_senha = confirmar_senha_input.text() if confirmar_senha_input else ""

        if not token:
            QMessageBox.warning(self.redefinir_dialog, "Redefinir senha", "Informe o token recebido.")
            return

        if not nova_senha or not confirmar_senha:
            QMessageBox.warning(self.redefinir_dialog, "Redefinir senha", "Preencha a nova senha e a confirmação.")
            return

        if nova_senha != confirmar_senha:
            QMessageBox.warning(self.redefinir_dialog, "Redefinir senha", "As senhas não conferem.")
            return

        valido, mensagem = validar_senha(nova_senha)
        if not valido:
            QMessageBox.warning(self.redefinir_dialog, "Redefinir senha", mensagem)
            return

        sucesso, msg = self.db_manager.reset_password_with_token(token, nova_senha)
        if sucesso:
            QMessageBox.information(self.redefinir_dialog, "Redefinir senha", msg)
            self.redefinir_dialog.close()
            self.redefinir_dialog = None
        else:
            QMessageBox.warning(self.redefinir_dialog, "Redefinir senha", msg)

    def abrir_cadastro(self):
        self.cadastro = load_ui("cadastro.ui")
        self.cadastro.setWindowTitle("NeoBenesys - Cadastro")

        btn_cadastrar_form = self.cadastro.findChild(QPushButton, "btn_cadastrar")
        if btn_cadastrar_form is not None:
            btn_cadastrar_form.clicked.connect(self.handle_cadastro)
        else:
            print("[Aviso] Botão 'btn_cadastrar' não encontrado no cadastro.ui")

        self.cadastro.show()

    def handle_cadastro(self):
        nome_input = self.cadastro.findChild(QLineEdit, "txt_nome")
        email_input = self.cadastro.findChild(QLineEdit, "txt_email")
        senha_input1 = self.cadastro.findChild(QLineEdit, "txt_senha1")
        senha_input2 = self.cadastro.findChild(QLineEdit, "txt_senha2")

        nome = nome_input.text().strip() if nome_input else ""
        email = email_input.text().strip() if email_input else ""
        senha1 = senha_input1.text() if senha_input1 else ""
        senha2 = senha_input2.text() if senha_input2 else ""

        if not nome or not email or not senha1 or not senha2:
            QMessageBox.warning(self.cadastro, "Cadastro", "Preencha todos os campos.")
            return
        
        # Validar formato de e-mail
        valido_email, msg_email = validar_email(email)
        if not valido_email:
            QMessageBox.warning(self.cadastro, "Cadastro", msg_email)
            return
        
        # Validar tamanho mínimo da senha
        valido_senha, msg_senha = validar_senha(senha1)
        if not valido_senha:
            QMessageBox.warning(self.cadastro, "Cadastro", msg_senha)
            return

        if senha1 != senha2:
            QMessageBox.warning(self.cadastro, "Cadastro", "As senhas não conferem.")
            return

        user = self.db_manager.create_user(nome, email, senha1)

        if user:
            QMessageBox.information(self.cadastro, "Cadastro", "Usuário criado com sucesso!")
            self.cadastro.close()
            self.login.show()
        else:
            QMessageBox.warning(self.cadastro, "Cadastro", "E-mail já cadastrado.")

    def abrir_dashboard(self):
        self.dashboard = load_ui("home.ui")
        self.dashboard.setWindowTitle("NeoBenesys - Dashboard")
        self._apply_theme_if_needed(self.dashboard)
        self.widgets = {}
        self.controllers = {}

        lbl_saudacao = self.dashboard.findChild(QLabel, "lbl_saudacao")
        if lbl_saudacao and self.current_user:
            lbl_saudacao.setText(f"Olá, {self.current_user.get('nome', 'Usuário')}")

        self.screens = {
            "usuarios": "usuarios.ui",
            "patrimonio": "patrimonio.ui",
            "manutencao": "manutencao.ui",
            "depreciacao": "depreciacao.ui",
            "auditoria": "auditoria.ui",
            "anexos": "anexos.ui",
            "relatorios": "relatorios.ui",
            "fornecedores": "fornecedores.ui",
            "centro_custo": "centro_custo.ui",
            "notas_fiscais": "notas_fiscais.ui",
            "movimentacoes": "movimentacoes.ui",
            "setores_locais": "setores_locais.ui",
        }

        stacked = self.dashboard.findChild(QStackedWidget, "stackedWidget")
        if stacked is None:
            print("[Erro] 'stackedWidget' não encontrado no home.ui. Verifique o objectName.")
        else:
            if stacked.count() > 0:
                dashboard_page = stacked.widget(0)
                if dashboard_page:
                    self.widgets["dashboard"] = dashboard_page
            for key, ui_file in self.screens.items():
                try:
                    widget = load_ui(ui_file)
                    if not widget.objectName():
                        widget.setObjectName(key)
                    stacked.addWidget(widget)
                    self.widgets[key] = widget

                    controller = create_controller(key, widget, self.db_manager, self.current_user)
                    if controller:
                        self.controllers[key] = controller
                        if key == "patrimonio" and hasattr(controller, "set_dashboard_updater"):
                            controller.set_dashboard_updater(self.atualizar_cards_dashboard)
                        if key == "auditoria" and hasattr(controller, "set_dashboard_callback"):
                            controller.set_dashboard_callback(self._atualizar_calendario_auditorias_widget)
                except Exception as e:
                    print(f"[Aviso] Não consegui carregar {ui_file}: {e}")

        button_map = {
            "btn_dashboard": "dashboard",
            "btn_patrimonio": "patrimonio",
            "btn_movimentacoes": "movimentacoes",
            "btn_manutencoes": "manutencao",
            "btn_notas_fiscais": "notas_fiscais",
            "btn_fornecedores": "fornecedores",
            "btn_centro_custo": "centro_custo",
            "btn_setores_locais": "setores_locais",
            "btn_depreciacao": "depreciacao",
            "btn_usuarios": "usuarios",
            "btn_relatorios": "relatorios",
            "btn_auditoria": "auditoria",
            "btn_anexos": "anexos",
        }

        # Controle de acesso por nível de usuário
        role = (self.current_user or {}).get('nivel_acesso')
        has_admin_access = role in {'admin', 'master'}

        # Telas restritas apenas para admin/master
        admin_only_screens = ['auditoria', 'usuarios']
        
        for btn_name, screen_key in button_map.items():
            btn = self.dashboard.findChild(QPushButton, btn_name)
            if btn is None:
                print(f"[Aviso] Botão '{btn_name}' não encontrado no home.ui")
                continue
            if screen_key not in self.widgets:
                print(f"[Aviso] Tela '{screen_key}' não carregada; verifique {self.screens.get(screen_key)}")
                continue
            
            # Ocultar botões de telas restritas para usuários não-admin
            if screen_key in admin_only_screens and not has_admin_access:
                btn.setVisible(False)
                continue

            def navigate(_, key=screen_key):
                if key in admin_only_screens and not has_admin_access:
                    QMessageBox.warning(self.dashboard, "Acesso restrito", "Apenas administradores ou usuarios master podem acessar esta tela.")
                    return
                target_widget = self.widgets.get(key)
                if target_widget:
                    stacked.setCurrentWidget(target_widget)
                if key == "dashboard":
                    self.atualizar_cards_dashboard()
                    return
                controller = self.controllers.get(key)
                if controller and hasattr(controller, "refresh"):
                    try:
                        controller.refresh()
                    except Exception as e:
                        print(f"[Aviso] refresh() falhou para '{key}': {e}")

            btn.clicked.connect(navigate)

        btn_sair = self.dashboard.findChild(QPushButton, "btn_sair")
        if btn_sair:
            btn_sair.clicked.connect(QApplication.instance().quit)

        self._setup_dashboard_calendar()
        self.atualizar_cards_dashboard()
        self.iniciar_relogio_dashboard()
        self.dashboard.show()
        self.login.close()

    def run(self):
        self.login.show()

    def atualizar_cards_dashboard(self):
        if not self.dashboard:
            return

        try:
            metrics = self.db_manager.get_patrimonio_dashboard_metrics()
        except Exception as exc:
            print(f"[Aviso] Não consegui obter métricas do dashboard: {exc}")
            metrics = {"ativos": 0, "baixados": 0, "manutencao": 0, "total_valor": 0.0}

        lbl_ativos = self.dashboard.findChild(QLabel, "lbl_card_1_value")
        lbl_manutencao = self.dashboard.findChild(QLabel, "lbl_card_2_value")
        lbl_baixados = self.dashboard.findChild(QLabel, "lbl_card_3_value")
        lbl_total = self.dashboard.findChild(QLabel, "lbl_card_4_value")

        if lbl_ativos:
            lbl_ativos.setText(str(metrics.get("ativos", 0)))
        if lbl_manutencao:
            lbl_manutencao.setText(str(metrics.get("manutencao", 0)))
        if lbl_baixados:
            lbl_baixados.setText(str(metrics.get("baixados", 0)))
        if lbl_total:
            total = metrics.get("total_valor", 0.0) or 0.0
            total_text = f"R$ {float(total):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lbl_total.setText(total_text)
        self._atualizar_calendario_auditorias_widget()

    def _setup_dashboard_calendar(self):
        if not self.dashboard or self._calendar_setup_done:
            return
        self._calendar_widget = self.dashboard.findChild(QCalendarWidget, "calendar_auditorias")
        self._calendar_list = self.dashboard.findChild(QListWidget, "lst_auditorias_dia")
        self._calendar_summary_label = self.dashboard.findChild(QLabel, "lbl_auditorias_resumo")
        if self._calendar_widget:
            self._calendar_widget.selectionChanged.connect(self._on_dashboard_calendar_selection)
            self._calendar_setup_done = True
            self._calendar_highlighted_dates = []

    def _on_dashboard_calendar_selection(self):
        if not self._calendar_widget:
            return
        selected = self._calendar_widget.selectedDate()
        if selected:
            self._atualizar_lista_auditorias_por_data(selected)

    def _atualizar_calendario_auditorias_widget(self):
        if not self.dashboard or not self._calendar_widget:
            return
        try:
            rows = self.db_manager.list_auditorias_agendadas()
        except Exception as exc:
            print(f"[Aviso] Não consegui obter auditorias agendadas: {exc}")
            rows = []

        self._auditorias_por_data = {}
        novos_formatos: List[QDate] = []
        for row in rows:
            qdate = self._to_qdate(row.get("data_auditoria"))
            if not qdate:
                continue
            chave = (qdate.year(), qdate.month(), qdate.day())
            self._auditorias_por_data.setdefault(chave, []).append(row)
            novos_formatos.append(qdate)

        # limpar formatação antiga
        for qdate in self._calendar_highlighted_dates:
            self._calendar_widget.setDateTextFormat(qdate, QTextCharFormat())

        destaque = QTextCharFormat()
        destaque.setBackground(QBrush(QColor("#c6f6d5")))
        destaque.setFontWeight(QFont.Weight.Bold)

        vistos = set()
        atual = []
        for qdate in novos_formatos:
            chave = (qdate.year(), qdate.month(), qdate.day())
            if chave in vistos:
                continue
            vistos.add(chave)
            atual.append(qdate)
            self._calendar_widget.setDateTextFormat(qdate, destaque)
        self._calendar_highlighted_dates = atual

        selecionado = self._calendar_widget.selectedDate()
        if not selecionado or (selecionado.year(), selecionado.month(), selecionado.day()) not in self._auditorias_por_data:
            if atual:
                self._calendar_widget.setSelectedDate(atual[0])
                selecionado = atual[0]
        self._atualizar_lista_auditorias_por_data(selecionado or QDate.currentDate())

    def _atualizar_lista_auditorias_por_data(self, qdate: QDate) -> None:
        if not self._calendar_list:
            return
        chave = (qdate.year(), qdate.month(), qdate.day())
        registros = self._auditorias_por_data.get(chave, [])
        registros = sorted(
            registros,
            key=lambda row: self._to_datetime(row.get("data_auditoria")) or datetime.max,
        )

        self._calendar_list.clear()
        if not registros:
            self._calendar_list.addItem("Nenhuma auditoria agendada nesta data.")
        else:
            for registro in registros:
                dt = self._to_datetime(registro.get("data_auditoria"))
                hora = dt.strftime("%H:%M") if dt else "--:--"
                descricao = registro.get("acao") or "Auditoria"
                tabela = registro.get("tabela_afetada")
                extra = f" ({tabela})" if tabela else ""
                self._calendar_list.addItem(f"{hora} - {descricao}{extra}")

        if self._calendar_summary_label:
            data_texto = qdate.toString("dd/MM/yyyy")
            self._calendar_summary_label.setText(f"{len(registros)} auditoria(s) em {data_texto}")

    @staticmethod
    def _to_qdate(valor: object) -> Optional[QDate]:
        if isinstance(valor, QDate):
            return valor
        dt = NeoBenesysApp._to_datetime_static(valor)
        if not dt:
            return None
        return QDate(dt.year, dt.month, dt.day)

    @staticmethod
    def _to_datetime(valor: object) -> Optional[datetime]:
        return NeoBenesysApp._to_datetime_static(valor)

    @staticmethod
    def _to_datetime_static(valor: object) -> Optional[datetime]:
        if isinstance(valor, datetime):
            return valor
        if isinstance(valor, QDateTime):
            if hasattr(valor, "toPython"):
                return valor.toPython()
            return datetime(
                valor.date().year(),
                valor.date().month(),
                valor.date().day(),
                valor.time().hour(),
                valor.time().minute(),
                valor.time().second(),
            )
        if isinstance(valor, str):
            texto = valor.strip()
            if not texto:
                return None
            try:
                return datetime.fromisoformat(texto.replace("Z", ""))
            except ValueError:
                return None
        return None

    def iniciar_relogio_dashboard(self):
        lbl_data = self.dashboard.findChild(QLabel, "lbl_data")
        lbl_relogio = self.dashboard.findChild(QLabel, "lbl_relogio")

        def tick():
            agora = QDateTime.currentDateTime()
            if lbl_data:
                lbl_data.setText(agora.toString("dd/MM/yyyy"))
            if lbl_relogio:
                lbl_relogio.setText(agora.toString("HH:mm:ss"))

        self._timer = QTimer(self.dashboard)
        self._timer.timeout.connect(tick)
        self._timer.start(1000)
        tick()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    global_theme = load_global_theme()
    sistema = NeoBenesysApp(global_theme)
    sistema.run()
    sys.exit(app.exec())
