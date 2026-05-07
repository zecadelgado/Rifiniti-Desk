"""
Sistema de cache para reduzir consultas ao banco de dados.

Implementa cache com timeout automático para dados que mudam raramente,
como fornecedores, categorias, setores, etc.
"""

from datetime import datetime, timedelta
from typing import Any, Optional, Dict, Callable
from functools import wraps


class CacheManager:
    """
    Gerenciador de cache com timeout automático.
    
    Armazena resultados de consultas ao banco com validade configurável,
    reduzindo a carga no servidor e melhorando a performance.
    """
    
    def __init__(self):
        """Inicializa o gerenciador de cache"""
        self._cache: Dict[str, Any] = {}
        self._cache_timeout: Dict[str, datetime] = {}
        self._default_timeout = 300  # 5 minutos
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtém valor do cache se ainda válido.
        
        Args:
            key: Chave do cache
        
        Returns:
            Valor do cache ou None se expirado/inexistente
        """
        if key not in self._cache:
            return None
        
        if key in self._cache_timeout:
            if datetime.now() >= self._cache_timeout[key]:
                # Cache expirado, remover
                self.invalidate(key)
                return None
        
        return self._cache[key]
    
    def set(self, key: str, value: Any, timeout_seconds: Optional[int] = None) -> None:
        """
        Define valor no cache com timeout.
        
        Args:
            key: Chave do cache
            value: Valor a armazenar
            timeout_seconds: Tempo de validade em segundos (None = padrão)
        """
        self._cache[key] = value
        
        if timeout_seconds is None:
            timeout_seconds = self._default_timeout
        
        self._cache_timeout[key] = datetime.now() + timedelta(seconds=timeout_seconds)
    
    def invalidate(self, key: str) -> None:
        """
        Invalida uma entrada específica do cache.
        
        Args:
            key: Chave do cache a invalidar
        """
        if key in self._cache:
            del self._cache[key]
        if key in self._cache_timeout:
            del self._cache_timeout[key]
    
    def invalidate_pattern(self, pattern: str) -> None:
        """
        Invalida todas as entradas que contêm o padrão.
        
        Args:
            pattern: Padrão a buscar nas chaves
        """
        keys_to_remove = [key for key in self._cache.keys() if pattern in key]
        for key in keys_to_remove:
            self.invalidate(key)
    
    def clear(self) -> None:
        """Limpa todo o cache"""
        self._cache.clear()
        self._cache_timeout.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do cache.
        
        Returns:
            Dicionário com estatísticas
        """
        total_entries = len(self._cache)
        expired_entries = 0
        
        now = datetime.now()
        for key, timeout in self._cache_timeout.items():
            if now >= timeout:
                expired_entries += 1
        
        return {
            'total_entries': total_entries,
            'active_entries': total_entries - expired_entries,
            'expired_entries': expired_entries
        }


def cached(timeout_seconds: int = 300, key_prefix: str = ''):
    """
    Decorator para cachear resultado de métodos.
    
    Args:
        timeout_seconds: Tempo de validade do cache em segundos
        key_prefix: Prefixo para a chave do cache
    
    Usage:
        @cached(timeout_seconds=600, key_prefix='fornecedores')
        def list_fornecedores(self):
            return self.db_manager.list_fornecedores()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Criar chave única baseada na função e argumentos
            cache_key = f"{key_prefix}:{func.__name__}"
            
            # Adicionar argumentos à chave se houver
            if args:
                cache_key += f":{str(args)}"
            if kwargs:
                cache_key += f":{str(sorted(kwargs.items()))}"
            
            # Verificar se tem cache_manager no objeto
            if not hasattr(self, '_cache_manager'):
                self._cache_manager = CacheManager()
            
            # Tentar obter do cache
            cached_value = self._cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Executar função e cachear resultado
            result = func(self, *args, **kwargs)
            self._cache_manager.set(cache_key, result, timeout_seconds)
            
            return result
        
        return wrapper
    return decorator


# Instância global do cache (opcional)
global_cache = CacheManager()


if __name__ == '__main__':
    # Teste do cache
    cache = CacheManager()
    
    # Adicionar valores
    cache.set('fornecedores', ['Fornecedor 1', 'Fornecedor 2'], timeout_seconds=5)
    cache.set('categorias', ['Categoria 1', 'Categoria 2'], timeout_seconds=10)
    
    # Obter valores
    print("Fornecedores:", cache.get('fornecedores'))
    print("Categorias:", cache.get('categorias'))
    
    # Estatísticas
    print("Stats:", cache.get_stats())
    
    # Aguardar expiração
    import time
    print("\nAguardando 6 segundos...")
    time.sleep(6)
    
    # Tentar obter novamente
    print("Fornecedores (após 6s):", cache.get('fornecedores'))  # None (expirado)
    print("Categorias (após 6s):", cache.get('categorias'))  # Ainda válido
    
    print("Stats:", cache.get_stats())
