"""
Diálogos de cadastro rápido para fornecedores e notas fiscais.

Permite criar fornecedores e notas fiscais rapidamente durante o cadastro
de patrimônio, sem precisar sair da tela atual.
"""

from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QDialogButtonBox, QMessageBox, QLabel, QDateEdit, QComboBox,
    QHBoxLayout
)
from PySide6.QtCore import Qt, QDate
from datetime import datetime


class QuickCreateFornecedorDialog(QDialog):
    """
    Diálogo simplificado para cadastro rápido de fornecedor.
    
    Permite cadastrar um fornecedor com os dados essenciais sem sair
    da tela de cadastro de patrimônio.
    """
    
    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.fornecedor_id = None
        
        self.setWindowTitle("Cadastro Rápido de Fornecedor")
        self.setMinimumWidth(400)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura a interface do diálogo"""
        layout = QVBoxLayout(self)
        
        # Título
        title_label = QLabel("📦 Novo Fornecedor")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Formulário
        form_layout = QFormLayout()
        
        self.txt_nome = QLineEdit()
        self.txt_nome.setPlaceholderText("Nome completo do fornecedor")
        form_layout.addRow("Nome*:", self.txt_nome)
        
        self.txt_cnpj = QLineEdit()
        self.txt_cnpj.setPlaceholderText("00.000.000/0000-00")
        self.txt_cnpj.setMaxLength(18)
        form_layout.addRow("CNPJ*:", self.txt_cnpj)
        
        self.txt_contato = QLineEdit()
        self.txt_contato.setPlaceholderText("Nome do contato (opcional)")
        form_layout.addRow("Contato:", self.txt_contato)
        
        self.txt_telefone = QLineEdit()
        self.txt_telefone.setPlaceholderText("(00) 0000-0000")
        self.txt_telefone.setMaxLength(15)
        form_layout.addRow("Telefone:", self.txt_telefone)
        
        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("email@fornecedor.com")
        form_layout.addRow("Email:", self.txt_email)
        
        layout.addLayout(form_layout)
        
        # Nota
        note_label = QLabel("* Campos obrigatórios")
        note_label.setStyleSheet("color: gray; font-size: 9pt; margin-top: 5px;")
        layout.addWidget(note_label)
        
        # Botões
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _on_save(self):
        """Valida e salva o fornecedor"""
        # Validar campos obrigatórios
        nome = self.txt_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Cadastro de Fornecedor", "Informe o nome do fornecedor.")
            self.txt_nome.setFocus()
            return
        
        cnpj = self.txt_cnpj.text().strip()
        if not cnpj:
            QMessageBox.warning(self, "Cadastro de Fornecedor", "Informe o CNPJ do fornecedor.")
            self.txt_cnpj.setFocus()
            return
        
        # Validar CNPJ (básico)
        cnpj_numeros = ''.join(filter(str.isdigit, cnpj))
        if len(cnpj_numeros) != 14:
            QMessageBox.warning(
                self,
                "Cadastro de Fornecedor",
                "CNPJ inválido. Deve conter 14 dígitos."
            )
            self.txt_cnpj.setFocus()
            return
        
        # Preparar dados
        dados = {
            'nome_fornecedor': nome,
            'cnpj': cnpj_numeros,
            'contato': self.txt_contato.text().strip() or None,
            'telefone': ''.join(filter(str.isdigit, self.txt_telefone.text())) or None,
            'email': self.txt_email.text().strip() or None
        }
        
        # Salvar no banco
        cursor = None
        try:
            from backend.utils.duplicate_validator import DuplicateValidator
            validator = DuplicateValidator(self.db_manager)
            
            # Validar CNPJ duplicado
            if not validator.validar_cnpj_fornecedor(cnpj_numeros, None, self):
                return
            
            # Salvar (assumindo que existe uma função no db_manager)
            cursor = self.db_manager.connection.cursor()
            query = """
                INSERT INTO fornecedores (nome_fornecedor, cnpj, contato, telefone, email)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                dados['nome_fornecedor'],
                dados['cnpj'],
                dados['contato'],
                dados['telefone'],
                dados['email']
            ))
            self.db_manager.connection.commit()
            self.fornecedor_id = cursor.lastrowid
            
            # Invalidar cache
            self.db_manager.cache.invalidate('fornecedores:list_all')
            
            QMessageBox.information(
                self,
                "Cadastro de Fornecedor",
                f"Fornecedor '{nome}' cadastrado com sucesso!"
            )
            self.accept()
            
        except Exception as exc:
            try:
                self.db_manager.connection.rollback()
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "Erro ao Cadastrar Fornecedor",
                f"Não foi possível cadastrar o fornecedor.\n\n{exc}"
            )
        finally:
            if cursor:
                cursor.close()
    
    def get_fornecedor_id(self) -> Optional[int]:
        """Retorna o ID do fornecedor criado"""
        return self.fornecedor_id


class QuickCreateNotaFiscalDialog(QDialog):
    """
    Diálogo simplificado para cadastro rápido de nota fiscal.
    
    Permite cadastrar uma nota fiscal com os dados essenciais sem sair
    da tela de cadastro de patrimônio.
    """
    
    def __init__(self, parent=None, db_manager=None, fornecedor_id=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.fornecedor_id = fornecedor_id
        self.nota_fiscal_id = None
        self._centro_custo_required = False

        self.setWindowTitle("Cadastro Rápido de Nota Fiscal")
        self.setMinimumWidth(450)

        self._setup_ui()
        self._load_fornecedores()
        self._descobrir_obrigatoriedade_centro_custo()
        self._load_centros_custo()

        if fornecedor_id:
            self._select_fornecedor(fornecedor_id)
    
    def _setup_ui(self):
        """Configura a interface do diálogo"""
        layout = QVBoxLayout(self)
        
        # Título
        title_label = QLabel("📄 Nova Nota Fiscal")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Formulário
        form_layout = QFormLayout()
        
        # Fornecedor com botão de novo
        fornecedor_layout = QHBoxLayout()
        self.cmb_fornecedor = QComboBox()
        self.cmb_fornecedor.setMinimumWidth(250)
        fornecedor_layout.addWidget(self.cmb_fornecedor)
        
        btn_novo_fornecedor = QPushButton("+ Novo")
        btn_novo_fornecedor.setMaximumWidth(80)
        btn_novo_fornecedor.clicked.connect(self._on_novo_fornecedor)
        fornecedor_layout.addWidget(btn_novo_fornecedor)
        
        form_layout.addRow("Fornecedor*:", fornecedor_layout)
        
        self.txt_numero_nota = QLineEdit()
        self.txt_numero_nota.setPlaceholderText("Número da nota fiscal")
        form_layout.addRow("Número NF*:", self.txt_numero_nota)
        
        self.date_emissao = QDateEdit()
        self.date_emissao.setDate(QDate.currentDate())
        self.date_emissao.setCalendarPopup(True)
        self.date_emissao.setDisplayFormat("dd/MM/yyyy")
        form_layout.addRow("Data Emissão*:", self.date_emissao)
        
        self.txt_valor_total = QLineEdit()
        self.txt_valor_total.setPlaceholderText("0.00")
        form_layout.addRow("Valor Total:", self.txt_valor_total)
        
        # Centro de custo (opcional)
        self.cmb_centro_custo = QComboBox()
        self.cmb_centro_custo.addItem("(Nenhum)", None)
        form_layout.addRow("Centro de Custo:", self.cmb_centro_custo)
        
        layout.addLayout(form_layout)
        
        # Nota
        note_label = QLabel("* Campos obrigatórios\nOs itens da nota poderão ser adicionados depois.")
        note_label.setStyleSheet("color: gray; font-size: 9pt; margin-top: 5px;")
        layout.addWidget(note_label)
        
        # Botões
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _load_fornecedores(self):
        """Carrega lista de fornecedores"""
        try:
            fornecedores = self.db_manager.list_fornecedores()
            self.cmb_fornecedor.clear()
            self.cmb_fornecedor.addItem("Selecione um fornecedor...", None)
            
            for fornecedor in fornecedores:
                nome = fornecedor.get('nome_fornecedor', '')
                id_fornecedor = fornecedor.get('id_fornecedor')
                self.cmb_fornecedor.addItem(nome, id_fornecedor)
                
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Cadastro de Nota Fiscal",
                f"Erro ao carregar fornecedores: {exc}"
            )

    def _descobrir_obrigatoriedade_centro_custo(self):
        """Define se centro de custo é obrigatório conforme esquema."""
        cursor = None
        try:
            cursor = self.db_manager.connection.cursor()
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'notas_fiscais' AND column_name = 'id_centro_custo'
                """
            )
            row = cursor.fetchone()
            if row and len(row) >= 3:
                nullable = row[2]
                self._centro_custo_required = (nullable == "NO")
        except Exception:
            self._centro_custo_required = False
        finally:
            if cursor:
                cursor.close()
        if self._centro_custo_required and self.cmb_centro_custo.count() > 0:
            self.cmb_centro_custo.setItemText(0, "(Selecione)")
    
    def _load_centros_custo(self):
        """Carrega lista de centros de custo"""
        try:
            centros = self.db_manager.list_centros_custo()
            self.cmb_centro_custo.clear()
            placeholder = "(Selecione)" if self._centro_custo_required else "(Nenhum)"
            self.cmb_centro_custo.addItem(placeholder, None)
            
            for centro in centros:
                nome = centro.get('nome_centro', '')
                id_centro = centro.get('id_centro_custo')
                self.cmb_centro_custo.addItem(nome, id_centro)
                
        except Exception as exc:
            print(f"Erro ao carregar centros de custo: {exc}")
    
    def _select_fornecedor(self, fornecedor_id: int):
        """Seleciona um fornecedor no combo"""
        for i in range(self.cmb_fornecedor.count()):
            if self.cmb_fornecedor.itemData(i) == fornecedor_id:
                self.cmb_fornecedor.setCurrentIndex(i)
                break
    
    def _on_novo_fornecedor(self):
        """Abre diálogo de cadastro rápido de fornecedor"""
        dialog = QuickCreateFornecedorDialog(self, self.db_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fornecedor_id = dialog.get_fornecedor_id()
            if fornecedor_id:
                # Recarregar lista e selecionar o novo
                self._load_fornecedores()
                self._select_fornecedor(fornecedor_id)
    
    def _on_save(self):
        """Valida e salva a nota fiscal"""
        # Validar fornecedor
        fornecedor_id = self.cmb_fornecedor.currentData()
        if not fornecedor_id:
            QMessageBox.warning(
                self,
                "Cadastro de Nota Fiscal",
                "Selecione um fornecedor."
            )
            self.cmb_fornecedor.setFocus()
            return
        
        # Validar número da nota
        numero_nota = self.txt_numero_nota.text().strip()
        if not numero_nota:
            QMessageBox.warning(
                self,
                "Cadastro de Nota Fiscal",
                "Informe o número da nota fiscal."
            )
            self.txt_numero_nota.setFocus()
            return
        
        # Validar duplicata
        try:
            from backend.utils.duplicate_validator import DuplicateValidator
            validator = DuplicateValidator(self.db_manager)
            
            if not validator.validar_numero_nota_fiscal(numero_nota, fornecedor_id, None, self):
                return
        except Exception:
            pass  # Se não tiver validador, continua
        
        # Preparar dados
        data_emissao = self.date_emissao.date().toPython()
        valor_total_str = self.txt_valor_total.text().strip().replace(',', '.')
        valor_total = float(valor_total_str) if valor_total_str else 0.0
        centro_custo_id = self.cmb_centro_custo.currentData()
        if self._centro_custo_required and centro_custo_id is None:
            QMessageBox.warning(
                self,
                "Cadastro de Nota Fiscal",
                "Selecione um centro de custo."
            )
            self.cmb_centro_custo.setFocus()
            return

        # Salvar no banco
        cursor = None
        try:
            cursor = self.db_manager.connection.cursor()
            query = """
                INSERT INTO notas_fiscais (id_fornecedor, numero_nota, data_emissao, valor_total, id_centro_custo)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                fornecedor_id,
                numero_nota,
                data_emissao,
                valor_total,
                centro_custo_id
            ))
            self.db_manager.connection.commit()
            self.nota_fiscal_id = cursor.lastrowid
            
            QMessageBox.information(
                self,
                "Cadastro de Nota Fiscal",
                f"Nota fiscal '{numero_nota}' cadastrada com sucesso!\n\n"
                f"Os itens da nota poderão ser adicionados na tela de Notas Fiscais."
            )
            self.accept()
            
        except Exception as exc:
            try:
                self.db_manager.connection.rollback()
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "Erro ao Cadastrar Nota Fiscal",
                f"Não foi possível cadastrar a nota fiscal.\n\n{exc}"
            )
        finally:
            if cursor:
                cursor.close()
    
    def get_nota_fiscal_id(self) -> Optional[int]:
        """Retorna o ID da nota fiscal criada"""
        return self.nota_fiscal_id


if __name__ == '__main__':
    # Teste dos diálogos
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Teste diálogo de fornecedor
    dialog = QuickCreateFornecedorDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        print(f"✅ Fornecedor criado: ID {dialog.get_fornecedor_id()}")
    else:
        print("❌ Cadastro cancelado")
    
    sys.exit(0)
