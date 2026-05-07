"""
Indicador de carregamento para operações longas.

Fornece feedback visual ao usuário durante operações que podem demorar,
melhorando a experiência do usuário.
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


class LoadingCursor:
    """
    Context manager para exibir cursor de carregamento.
    
    Uso:
        with LoadingCursor():
            # operação demorada
            resultado = processar_dados()
    """
    
    def __enter__(self):
        """Ativa cursor de espera"""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()  # Atualizar UI imediatamente
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restaura cursor normal"""
        QApplication.restoreOverrideCursor()
        return False  # Não suprimir exceções


class BusyCursor(LoadingCursor):
    """Alias para LoadingCursor (mais semântico em alguns contextos)"""
    pass


def with_loading_cursor(func):
    """
    Decorator para adicionar cursor de carregamento a uma função.
    
    Uso:
        @with_loading_cursor
        def processar_dados(self):
            # operação demorada
            pass
    """
    def wrapper(*args, **kwargs):
        with LoadingCursor():
            return func(*args, **kwargs)
    return wrapper


if __name__ == '__main__':
    # Teste do indicador
    import time
    from PySide6.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget
    import sys
    
    app = QApplication(sys.argv)
    
    window = QMainWindow()
    window.setWindowTitle("Teste Loading Cursor")
    
    central = QWidget()
    layout = QVBoxLayout()
    
    def teste_loading():
        with LoadingCursor():
            time.sleep(2)  # Simular operação demorada
    
    btn = QPushButton("Testar Loading (2s)")
    btn.clicked.connect(teste_loading)
    layout.addWidget(btn)
    
    central.setLayout(layout)
    window.setCentralWidget(central)
    window.show()
    
    sys.exit(app.exec())
