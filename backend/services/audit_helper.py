"""
Módulo auxiliar para registro de auditoria no sistema NeoBenesys.
Facilita o registro de ações críticas (CREATE, UPDATE, DELETE) na tabela de auditorias.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any


def registrar_auditoria(
    db_manager,
    usuario: Dict[str, Any],
    tabela: str,
    id_registro: Optional[int],
    acao: str,
    detalhes: Optional[str] = None
) -> bool:
    """
    Registra uma ação de auditoria no banco de dados.
    
    Args:
        db_manager: Instância do DatabaseManager
        usuario: Dicionário com dados do usuário atual (deve conter 'id_usuario')
        tabela: Nome da tabela afetada
        id_registro: ID do registro afetado
        acao: Tipo de ação ('CREATE', 'UPDATE', 'DELETE')
        detalhes: Detalhes adicionais da operação (opcional, pode ser JSON ou texto)
        
    Returns:
        True se o registro foi criado com sucesso, False caso contrário
    """
    if not usuario or 'id_usuario' not in usuario:
        print("[Aviso] Não foi possível registrar auditoria: usuário inválido")
        return False
    
    cursor = None
    try:
        cursor = db_manager.connection.cursor()
        
        query = """
            INSERT INTO auditorias 
            (data_auditoria, tabela_afetada, id_registro_afetado, acao, id_usuario, detalhes)
            VALUES (NOW(), %s, %s, %s, %s, %s)
        """
        
        valores = (
            tabela,
            id_registro,
            acao,
            usuario['id_usuario'],
            detalhes
        )
        
        cursor.execute(query, valores)
        db_manager.connection.commit()
        
        return True
        
    except Exception as e:
        try:
            db_manager.connection.rollback()
        except Exception:
            pass
        print(f"[Erro] Falha ao registrar auditoria: {e}")
        return False
    finally:
        if cursor:
            cursor.close()


def criar_detalhes_json(dados: Dict[str, Any]) -> str:
    """
    Converte um dicionário de dados em uma string JSON para armazenar nos detalhes da auditoria.
    
    Args:
        dados: Dicionário com os dados a serem convertidos
        
    Returns:
        String JSON formatada
    """
    try:
        return json.dumps(dados, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[Aviso] Erro ao criar JSON de detalhes: {e}")
        return str(dados)


def criar_detalhes_alteracao(campo: str, valor_anterior: Any, valor_novo: Any) -> str:
    """
    Cria uma string de detalhes para uma alteração de campo.
    
    Args:
        campo: Nome do campo alterado
        valor_anterior: Valor anterior do campo
        valor_novo: Valor novo do campo
        
    Returns:
        String descrevendo a alteração
    """
    return f"Alterado campo '{campo}' de '{valor_anterior}' para '{valor_novo}'"


def criar_detalhes_multiplos_campos(alteracoes: Dict[str, tuple]) -> str:
    """
    Cria uma string de detalhes para múltiplas alterações de campos.
    
    Args:
        alteracoes: Dicionário onde a chave é o nome do campo e o valor é uma tupla (valor_anterior, valor_novo)
        
    Returns:
        String JSON com todas as alterações
    """
    detalhes = {
        "alteracoes": [
            {
                "campo": campo,
                "anterior": str(valores[0]),
                "novo": str(valores[1])
            }
            for campo, valores in alteracoes.items()
        ]
    }
    return criar_detalhes_json(detalhes)


def registrar_criacao(db_manager, usuario: Dict[str, Any], tabela: str, id_registro: int, dados: Optional[Dict[str, Any]] = None) -> bool:
    """
    Registra a criação de um novo registro.
    
    Args:
        db_manager: Instância do DatabaseManager
        usuario: Dicionário com dados do usuário atual
        tabela: Nome da tabela
        id_registro: ID do registro criado
        dados: Dados do registro criado (opcional)
        
    Returns:
        True se o registro foi criado com sucesso, False caso contrário
    """
    detalhes = None
    if dados:
        detalhes = criar_detalhes_json({"dados_criados": dados})
    
    return registrar_auditoria(db_manager, usuario, tabela, id_registro, "CREATE", detalhes)


def registrar_atualizacao(db_manager, usuario: Dict[str, Any], tabela: str, id_registro: int, alteracoes: Optional[Dict[str, tuple]] = None) -> bool:
    """
    Registra a atualização de um registro.
    
    Args:
        db_manager: Instância do DatabaseManager
        usuario: Dicionário com dados do usuário atual
        tabela: Nome da tabela
        id_registro: ID do registro atualizado
        alteracoes: Dicionário com as alterações (campo -> (valor_anterior, valor_novo))
        
    Returns:
        True se o registro foi criado com sucesso, False caso contrário
    """
    detalhes = None
    if alteracoes:
        detalhes = criar_detalhes_multiplos_campos(alteracoes)
    
    return registrar_auditoria(db_manager, usuario, tabela, id_registro, "UPDATE", detalhes)


def registrar_exclusao(db_manager, usuario: Dict[str, Any], tabela: str, id_registro: int, dados: Optional[Dict[str, Any]] = None) -> bool:
    """
    Registra a exclusão de um registro.
    
    Args:
        db_manager: Instância do DatabaseManager
        usuario: Dicionário com dados do usuário atual
        tabela: Nome da tabela
        id_registro: ID do registro excluído
        dados: Dados do registro excluído antes da exclusão (opcional)
        
    Returns:
        True se o registro foi criado com sucesso, False caso contrário
    """
    detalhes = None
    if dados:
        detalhes = criar_detalhes_json({"dados_excluidos": dados})
    
    return registrar_auditoria(db_manager, usuario, tabela, id_registro, "DELETE", detalhes)
