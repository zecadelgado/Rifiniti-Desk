"""
Configuração de logging estruturado para o sistema NeoBenesys.

Este módulo fornece logging com rotação automática de arquivos e
formatação padronizada para facilitar debug e rastreamento de problemas.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_logger(name='neobenesys', level=logging.INFO):
    """
    Configura e retorna um logger com rotação de arquivos.
    
    Args:
        name: Nome do logger
        level: Nível de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    
    # Evitar duplicação de handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Criar diretório de logs
    log_dir = Path.home() / '.neobenesys' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Handler para arquivo com rotação
    log_file = log_dir / 'neobenesys.log'
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,  # Manter 5 arquivos de backup
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    
    # Handler para console (apenas WARNING e acima)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    
    # Formato detalhado
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def log_user_action(logger, user, action, details=None):
    """
    Registra ação do usuário de forma padronizada.
    
    Args:
        logger: Logger configurado
        user: Dicionário com dados do usuário
        action: Descrição da ação
        details: Detalhes adicionais (opcional)
    """
    user_id = user.get('id_usuario', 'N/A') if user else 'N/A'
    user_name = user.get('nome', 'N/A') if user else 'N/A'
    
    msg = f"Usuário {user_name} (ID: {user_id}) - {action}"
    if details:
        msg += f" - {details}"
    
    logger.info(msg)


def log_database_error(logger, operation, error, context=None):
    """
    Registra erro de banco de dados de forma padronizada.
    
    Args:
        logger: Logger configurado
        operation: Operação que falhou
        error: Exceção capturada
        context: Contexto adicional (opcional)
    """
    msg = f"Erro de BD na operação '{operation}': {str(error)}"
    if context:
        msg += f" | Contexto: {context}"
    
    logger.error(msg, exc_info=True)


# Logger global do sistema
system_logger = setup_logger()


if __name__ == '__main__':
    # Teste do logger
    logger = setup_logger('teste')
    logger.debug("Mensagem de debug")
    logger.info("Mensagem de info")
    logger.warning("Mensagem de warning")
    logger.error("Mensagem de erro")
    logger.critical("Mensagem crítica")
    
    print(f"Logs salvos em: {Path.home() / '.neobenesys' / 'logs' / 'neobenesys.log'}")
