"""
Módulo de validações de campos para o sistema NeoBenesys.
Contém funções para validar email, CNPJ, telefone, NCM, CFOP e outros campos.
"""

import re


def validar_email(email: str) -> tuple[bool, str]:
    """
    Valida o formato de um endereço de e-mail.
    
    Args:
        email: String contendo o e-mail a ser validado
        
    Returns:
        Tupla (válido, mensagem_erro)
        - válido: True se o e-mail é válido, False caso contrário
        - mensagem_erro: String vazia se válido, mensagem de erro caso contrário
    """
    if not email or not email.strip():
        return False, "O e-mail não pode estar vazio."
    
    email = email.strip()
    
    # Padrão básico de e-mail: algo@dominio.extensao
    padrao = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(padrao, email):
        return False, "Informe um e-mail válido."
    
    # Verificar se tem exatamente um @
    if email.count('@') != 1:
        return False, "Informe um e-mail válido."
    
    return True, ""


def validar_cnpj(cnpj: str) -> tuple[bool, str]:
    """
    Valida o formato e dígitos verificadores de um CNPJ.
    
    Args:
        cnpj: String contendo o CNPJ (pode conter máscara)
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not cnpj or not cnpj.strip():
        return False, "O CNPJ não pode estar vazio."
    
    # Remover caracteres não numéricos
    cnpj_limpo = re.sub(r'[^0-9]', '', cnpj)
    
    # Verificar se tem 14 dígitos
    if len(cnpj_limpo) != 14:
        return False, "CNPJ inválido. Verifique se digitou os 14 dígitos corretamente."
    
    # Verificar se não é uma sequência de números iguais
    if cnpj_limpo == cnpj_limpo[0] * 14:
        return False, "CNPJ inválido."
    
    # Validar dígitos verificadores
    def calcular_digito(cnpj_parcial, pesos):
        soma = sum(int(cnpj_parcial[i]) * pesos[i] for i in range(len(pesos)))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto
    
    # Primeiro dígito verificador
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digito1 = calcular_digito(cnpj_limpo[:12], pesos1)
    
    if int(cnpj_limpo[12]) != digito1:
        return False, "CNPJ inválido. Dígito verificador incorreto."
    
    # Segundo dígito verificador
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    digito2 = calcular_digito(cnpj_limpo[:13], pesos2)
    
    if int(cnpj_limpo[13]) != digito2:
        return False, "CNPJ inválido. Dígito verificador incorreto."
    
    return True, ""


def remover_mascara_cnpj(cnpj: str) -> str:
    """
    Remove a máscara de um CNPJ, deixando apenas os dígitos.
    
    Args:
        cnpj: String contendo o CNPJ (pode conter máscara)
        
    Returns:
        String contendo apenas os dígitos do CNPJ
    """
    return re.sub(r'[^0-9]', '', cnpj) if cnpj else ""


def validar_telefone(telefone: str) -> tuple[bool, str]:
    """
    Valida o formato de um telefone brasileiro.
    
    Args:
        telefone: String contendo o telefone (pode conter máscara)
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not telefone or not telefone.strip():
        return False, "O telefone não pode estar vazio."
    
    # Remover caracteres não numéricos
    telefone_limpo = re.sub(r'[^0-9]', '', telefone)
    
    # Verificar se tem entre 10 e 11 dígitos (DDD + número)
    if len(telefone_limpo) < 10 or len(telefone_limpo) > 11:
        return False, "Telefone inválido. Informe apenas números com DDD (10 ou 11 dígitos)."
    
    return True, ""


def remover_mascara_telefone(telefone: str) -> str:
    """
    Remove a máscara de um telefone, deixando apenas os dígitos.
    
    Args:
        telefone: String contendo o telefone (pode conter máscara)
        
    Returns:
        String contendo apenas os dígitos do telefone
    """
    return re.sub(r'[^0-9]', '', telefone) if telefone else ""


def validar_ncm(ncm: str) -> tuple[bool, str]:
    """
    Valida o formato de um código NCM (Nomenclatura Comum do Mercosul).
    
    Args:
        ncm: String contendo o NCM
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not ncm or not ncm.strip():
        return False, "O NCM não pode estar vazio."
    
    # Remover caracteres não numéricos
    ncm_limpo = re.sub(r'[^0-9]', '', ncm)
    
    # Verificar se tem 8 dígitos
    if len(ncm_limpo) != 8:
        return False, "NCM deve conter 8 dígitos numéricos."
    
    return True, ""


def validar_cfop(cfop: str) -> tuple[bool, str]:
    """
    Valida o formato de um código CFOP (Código Fiscal de Operações e Prestações).
    
    Args:
        cfop: String contendo o CFOP
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not cfop or not cfop.strip():
        return False, "O CFOP não pode estar vazio."
    
    # Remover caracteres não numéricos
    cfop_limpo = re.sub(r'[^0-9]', '', cfop)
    
    # Verificar se tem 4 dígitos
    if len(cfop_limpo) != 4:
        return False, "CFOP deve conter 4 dígitos numéricos."
    
    return True, ""


def validar_numero_nota_fiscal(numero: str) -> tuple[bool, str]:
    """
    Valida o formato de um número de nota fiscal.
    
    Args:
        numero: String contendo o número da nota fiscal
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not numero or not numero.strip():
        return False, "O número da nota fiscal não pode estar vazio."
    
    # Remover espaços
    numero_limpo = numero.strip()
    
    # Verificar se tem pelo menos 3 caracteres
    if len(numero_limpo) < 3:
        return False, "Número da nota fiscal inválido."
    
    # Verificar se contém apenas dígitos (ou dígitos + alguns caracteres permitidos)
    if not re.match(r'^[0-9\-/]+$', numero_limpo):
        return False, "Número da nota fiscal inválido."
    
    return True, ""


def validar_senha(senha: str, tamanho_minimo: int = 6) -> tuple[bool, str]:
    """
    Valida se a senha atende aos requisitos mínimos.
    
    Args:
        senha: String contendo a senha
        tamanho_minimo: Tamanho mínimo da senha (padrão: 6)
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not senha:
        return False, "A senha não pode estar vazia."
    
    if len(senha) < tamanho_minimo:
        return False, f"A senha deve conter pelo menos {tamanho_minimo} caracteres."
    
    return True, ""


def validar_campo_obrigatorio(valor: str, nome_campo: str) -> tuple[bool, str]:
    """
    Valida se um campo obrigatório foi preenchido.
    
    Args:
        valor: Valor do campo
        nome_campo: Nome do campo para mensagem de erro
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    if not valor or not str(valor).strip():
        return False, f"O campo '{nome_campo}' é obrigatório."
    
    return True, ""


def validar_valor_positivo(valor: float, nome_campo: str = "Valor") -> tuple[bool, str]:
    """
    Valida se um valor numérico é positivo (maior ou igual a zero).
    
    Args:
        valor: Valor numérico a ser validado
        nome_campo: Nome do campo para mensagem de erro
        
    Returns:
        Tupla (válido, mensagem_erro)
    """
    try:
        valor_float = float(valor)
        
        if valor_float < 0:
            return False, f"{nome_campo} não pode ser negativo."
        
        return True, ""
    except (ValueError, TypeError):
        return False, f"{nome_campo} deve ser um número válido."
