"""
Validador de duplicatas para evitar cadastros repetidos.

Verifica duplicatas antes de salvar no banco, fornecendo feedback
imediato ao usuário e evitando retrabalho.
"""

from typing import Optional, Tuple
from PySide6.QtWidgets import QMessageBox, QWidget


class DuplicateValidator:
    """Validador de duplicatas para diversos tipos de registros"""
    
    def __init__(self, db_manager):
        """
        Inicializa o validador.
        
        Args:
            db_manager: Instância do DatabaseManager
        """
        self.db_manager = db_manager
    
    def validar_email_usuario(self, email: str, id_atual: Optional[int] = None, widget: Optional[QWidget] = None) -> bool:
        """
        Verifica se email de usuário já existe.
        
        Args:
            email: Email a verificar
            id_atual: ID do usuário em edição (None para novo)
            widget: Widget pai para exibir mensagem
        
        Returns:
            True se email está disponível, False se duplicado
        """
        try:
            cursor = self.db_manager.connection.cursor()
            
            if id_atual:
                cursor.execute(
                    "SELECT id_usuario, nome FROM usuarios WHERE email = %s AND id_usuario != %s",
                    (email, id_atual)
                )
            else:
                cursor.execute(
                    "SELECT id_usuario, nome FROM usuarios WHERE email = %s",
                    (email,)
                )
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                if widget:
                    QMessageBox.warning(
                        widget,
                        "Email Duplicado",
                        f"O email '{email}' já está cadastrado para o usuário '{result[1]}'.\n\n"
                        f"Por favor, utilize outro email."
                    )
                return False
            
            return True
            
        except Exception as e:
            print(f"Erro ao validar email: {e}")
            return True  # Em caso de erro, permitir continuar
    
    def validar_cnpj_fornecedor(self, cnpj: str, id_atual: Optional[int] = None, widget: Optional[QWidget] = None) -> bool:
        """
        Verifica se CNPJ de fornecedor já existe.
        
        Args:
            cnpj: CNPJ a verificar (apenas números)
            id_atual: ID do fornecedor em edição (None para novo)
            widget: Widget pai para exibir mensagem
        
        Returns:
            True se CNPJ está disponível, False se duplicado
        """
        try:
            cursor = self.db_manager.connection.cursor()
            cursor.execute("SHOW COLUMNS FROM fornecedores")
            columns = {row[0] for row in cursor.fetchall()}
            name_column = next(
                (candidate for candidate in ("nome_fornecedor", "nome", "razao_social") if candidate in columns),
                None,
            )
            if not name_column:
                cursor.close()
                return True
            
            if id_atual:
                cursor.execute(
                    f"SELECT id_fornecedor, `{name_column}` FROM fornecedores WHERE cnpj = %s AND id_fornecedor != %s",
                    (cnpj, id_atual)
                )
            else:
                cursor.execute(
                    f"SELECT id_fornecedor, `{name_column}` FROM fornecedores WHERE cnpj = %s",
                    (cnpj,)
                )
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                if widget:
                    # Formatar CNPJ para exibição
                    cnpj_formatado = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
                    QMessageBox.warning(
                        widget,
                        "CNPJ Duplicado",
                        f"O CNPJ {cnpj_formatado} já está cadastrado para o fornecedor '{result[1]}'.\n\n"
                        f"Por favor, verifique se o fornecedor já existe no sistema."
                    )
                return False
            
            return True
            
        except Exception as e:
            print(f"Erro ao validar CNPJ: {e}")
            return True  # Em caso de erro, permitir continuar
    
    def validar_numero_nota_fiscal(self, numero: str, id_fornecedor: int, id_atual: Optional[int] = None, widget: Optional[QWidget] = None) -> bool:
        """
        Verifica se número de nota fiscal já existe.
        
        Args:
            numero: Número da nota fiscal
            id_fornecedor: ID do fornecedor (mantido por compatibilidade da chamada)
            id_atual: ID da nota em edição (None para nova)
            widget: Widget pai para exibir mensagem
        
        Returns:
            True se número está disponível, False se duplicado
        """
        try:
            cursor = self.db_manager.connection.cursor()
            
            if id_atual:
                cursor.execute(
                    "SELECT id_nota_fiscal FROM notas_fiscais WHERE numero_nota = %s AND id_nota_fiscal != %s",
                    (numero, id_atual)
                )
            else:
                cursor.execute(
                    "SELECT id_nota_fiscal FROM notas_fiscais WHERE numero_nota = %s",
                    (numero,)
                )
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                if widget:
                    QMessageBox.warning(
                        widget,
                        "Nota Fiscal Duplicada",
                        f"Já existe uma nota fiscal com o número '{numero}'.\n\n"
                        f"Por favor, verifique se a nota já foi cadastrada."
                    )
                return False
            
            return True
            
        except Exception as e:
            print(f"Erro ao validar número de nota fiscal: {e}")
            return True  # Em caso de erro, permitir continuar
    
    def validar_patrimonio_plaqueta(self, plaqueta: str, id_atual: Optional[int] = None, widget: Optional[QWidget] = None) -> bool:
        """
        Verifica se número de plaqueta de patrimônio já existe.
        
        Args:
            plaqueta: Número da plaqueta
            id_atual: ID do patrimônio em edição (None para novo)
            widget: Widget pai para exibir mensagem
        
        Returns:
            True se plaqueta está disponível, False se duplicada
        """
        try:
            cursor = self.db_manager.connection.cursor()
            cursor.execute("SHOW COLUMNS FROM patrimonios")
            columns = {row[0] for row in cursor.fetchall()}
            column = next(
                (candidate for candidate in ("plaqueta", "numero_patrimonio", "numero_serie") if candidate in columns),
                None,
            )
            if not column:
                cursor.close()
                return True
            
            if id_atual:
                cursor.execute(
                    f"SELECT id_patrimonio, nome FROM patrimonios WHERE `{column}` = %s AND id_patrimonio != %s",
                    (plaqueta, id_atual),
                )
            else:
                cursor.execute(
                    f"SELECT id_patrimonio, nome FROM patrimonios WHERE `{column}` = %s",
                    (plaqueta,),
                )
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                if widget:
                    QMessageBox.warning(
                        widget,
                        "Plaqueta Duplicada",
                        f"A plaqueta '{plaqueta}' já está cadastrada para o patrimônio '{result[1]}'.\n\n"
                        f"Por favor, utilize outro número de plaqueta."
                    )
                return False
            
            return True
            
        except Exception as e:
            print(f"Erro ao validar plaqueta: {e}")
            return True  # Em caso de erro, permitir continuar


if __name__ == '__main__':
    print("Módulo de validação de duplicatas carregado com sucesso!")
