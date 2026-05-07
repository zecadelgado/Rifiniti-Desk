"""
Diálogos de confirmação para operações críticas.

Implementa confirmações duplas e detalhadas para prevenir erros acidentais
em operações importantes como exclusões e alterações de valores.
"""

from typing import List, Optional, Dict, Any
from PySide6.QtWidgets import QMessageBox, QWidget
from PySide6.QtCore import Qt


def confirmar_exclusao_simples(parent: QWidget, titulo: str, item_nome: str) -> bool:
    """
    Confirmação simples para exclusão.
    
    Args:
        parent: Widget pai
        titulo: Título da janela
        item_nome: Nome do item a ser excluído
    
    Returns:
        True se confirmado, False caso contrário
    """
    resposta = QMessageBox.question(
        parent,
        titulo,
        f"Tem certeza que deseja excluir '{item_nome}'?\n\n"
        f"Esta ação não poderá ser desfeita.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def confirmar_exclusao_com_impacto(
    parent: QWidget,
    titulo: str,
    item_nome: str,
    impactos: List[str]
) -> bool:
    """
    Confirmação de exclusão mostrando impactos.
    
    Args:
        parent: Widget pai
        titulo: Título da janela
        item_nome: Nome do item a ser excluído
        impactos: Lista de impactos da exclusão
    
    Returns:
        True se confirmado, False caso contrário
    """
    mensagem = f"Tem certeza que deseja excluir '{item_nome}'?\n\n"
    mensagem += "⚠️ ATENÇÃO - Esta ação terá os seguintes impactos:\n\n"
    
    for impacto in impactos:
        mensagem += f"• {impacto}\n"
    
    mensagem += "\nEsta ação não poderá ser desfeita!"
    
    resposta = QMessageBox.warning(
        parent,
        titulo,
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def confirmar_alteracao_critica(
    parent: QWidget,
    titulo: str,
    item_nome: str,
    alteracoes: Dict[str, tuple]
) -> bool:
    """
    Confirmação de alterações críticas mostrando valores antigos e novos.
    
    Args:
        parent: Widget pai
        titulo: Título da janela
        item_nome: Nome do item sendo alterado
        alteracoes: Dict com campo: (valor_antigo, valor_novo)
    
    Returns:
        True se confirmado, False caso contrário
    """
    if not alteracoes:
        return True  # Sem alterações críticas
    
    mensagem = f"Você está alterando dados importantes de '{item_nome}':\n\n"
    
    for campo, (antigo, novo) in alteracoes.items():
        mensagem += f"📝 {campo}:\n"
        mensagem += f"   De: {antigo}\n"
        mensagem += f"   Para: {novo}\n\n"
    
    mensagem += "Deseja realmente continuar com estas alterações?"
    
    resposta = QMessageBox.question(
        parent,
        titulo,
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def confirmar_alteracao_valor_patrimonio(
    parent: QWidget,
    patrimonio_nome: str,
    valor_antigo: float,
    valor_novo: float
) -> bool:
    """
    Confirmação específica para alteração de valor de patrimônio.
    
    Args:
        parent: Widget pai
        patrimonio_nome: Nome do patrimônio
        valor_antigo: Valor atual
        valor_novo: Novo valor
    
    Returns:
        True se confirmado, False caso contrário
    """
    diferenca = valor_novo - valor_antigo
    percentual = (diferenca / valor_antigo * 100) if valor_antigo > 0 else 0
    
    mensagem = f"⚠️ ALTERAÇÃO DE VALOR - '{patrimonio_nome}'\n\n"
    mensagem += f"Valor Atual: R$ {valor_antigo:,.2f}\n"
    mensagem += f"Novo Valor: R$ {valor_novo:,.2f}\n\n"
    
    if diferenca > 0:
        mensagem += f"Aumento: R$ {diferenca:,.2f} (+{percentual:.1f}%)\n\n"
    else:
        mensagem += f"Redução: R$ {abs(diferenca):,.2f} ({percentual:.1f}%)\n\n"
    
    mensagem += "Esta alteração afetará:\n"
    mensagem += "• Valor total do patrimônio\n"
    mensagem += "• Cálculo de depreciação\n"
    mensagem += "• Relatórios financeiros\n\n"
    mensagem += "Deseja realmente alterar o valor?"
    
    resposta = QMessageBox.warning(
        parent,
        "Confirmação de Alteração de Valor",
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def confirmar_exclusao_multipla(
    parent: QWidget,
    titulo: str,
    quantidade: int,
    tipo_item: str
) -> bool:
    """
    Confirmação para exclusão de múltiplos itens.
    
    Args:
        parent: Widget pai
        titulo: Título da janela
        quantidade: Quantidade de itens a excluir
        tipo_item: Tipo do item (ex: "patrimônios", "fornecedores")
    
    Returns:
        True se confirmado, False caso contrário
    """
    mensagem = f"⚠️ EXCLUSÃO EM LOTE\n\n"
    mensagem += f"Você está prestes a excluir {quantidade} {tipo_item}.\n\n"
    mensagem += "Esta ação não poderá ser desfeita!\n\n"
    mensagem += "Tem certeza que deseja continuar?"
    
    resposta = QMessageBox.warning(
        parent,
        titulo,
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def confirmar_alteracao_categoria(
    parent: QWidget,
    patrimonio_nome: str,
    categoria_antiga: str,
    categoria_nova: str
) -> bool:
    """
    Confirmação específica para alteração de categoria de patrimônio.
    
    Args:
        parent: Widget pai
        patrimonio_nome: Nome do patrimônio
        categoria_antiga: Categoria atual
        categoria_nova: Nova categoria
    
    Returns:
        True se confirmado, False caso contrário
    """
    mensagem = f"⚠️ ALTERAÇÃO DE CATEGORIA - '{patrimonio_nome}'\n\n"
    mensagem += f"Categoria Atual: {categoria_antiga}\n"
    mensagem += f"Nova Categoria: {categoria_nova}\n\n"
    mensagem += "Esta alteração pode afetar:\n"
    mensagem += "• Taxa de depreciação\n"
    mensagem += "• Relatórios por categoria\n"
    mensagem += "• Agrupamentos e filtros\n\n"
    mensagem += "Deseja realmente alterar a categoria?"
    
    resposta = QMessageBox.question(
        parent,
        "Confirmação de Alteração de Categoria",
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def confirmar_baixa_patrimonio(
    parent: QWidget,
    patrimonio_nome: str,
    valor_atual: float,
    motivo: Optional[str] = None
) -> bool:
    """
    Confirmação específica para baixa de patrimônio.
    
    Args:
        parent: Widget pai
        patrimonio_nome: Nome do patrimônio
        valor_atual: Valor atual do patrimônio
        motivo: Motivo da baixa (opcional)
    
    Returns:
        True se confirmado, False caso contrário
    """
    mensagem = f"⚠️ BAIXA DE PATRIMÔNIO - '{patrimonio_nome}'\n\n"
    mensagem += f"Valor Atual: R$ {valor_atual:,.2f}\n\n"
    
    if motivo:
        mensagem += f"Motivo: {motivo}\n\n"
    
    mensagem += "Esta ação irá:\n"
    mensagem += "• Remover o patrimônio do sistema\n"
    mensagem += "• Afetar o valor total do patrimônio\n"
    mensagem += "• Gerar registro de auditoria\n\n"
    mensagem += "⚠️ ATENÇÃO: Esta ação não poderá ser desfeita!\n\n"
    mensagem += "Deseja realmente dar baixa neste patrimônio?"
    
    resposta = QMessageBox.warning(
        parent,
        "Confirmação de Baixa de Patrimônio",
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


def alerta_operacao_irreversivel(
    parent: QWidget,
    titulo: str,
    operacao: str,
    detalhes: Optional[List[str]] = None
) -> bool:
    """
    Alerta genérico para operações irreversíveis.
    
    Args:
        parent: Widget pai
        titulo: Título da janela
        operacao: Descrição da operação
        detalhes: Lista de detalhes adicionais (opcional)
    
    Returns:
        True se confirmado, False caso contrário
    """
    mensagem = f"⚠️ OPERAÇÃO IRREVERSÍVEL\n\n"
    mensagem += f"{operacao}\n\n"
    
    if detalhes:
        mensagem += "Detalhes:\n"
        for detalhe in detalhes:
            mensagem += f"• {detalhe}\n"
        mensagem += "\n"
    
    mensagem += "Esta ação não poderá ser desfeita!\n\n"
    mensagem += "Tem certeza que deseja continuar?"
    
    resposta = QMessageBox.warning(
        parent,
        titulo,
        mensagem,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    return resposta == QMessageBox.StandardButton.Yes


if __name__ == '__main__':
    # Teste dos diálogos
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Teste 1: Exclusão simples
    if confirmar_exclusao_simples(None, "Teste", "Item de Teste"):
        print("✅ Exclusão confirmada")
    else:
        print("❌ Exclusão cancelada")
    
    # Teste 2: Alteração de valor
    if confirmar_alteracao_valor_patrimonio(None, "Notebook Dell", 3000.00, 2500.00):
        print("✅ Alteração confirmada")
    else:
        print("❌ Alteração cancelada")
    
    sys.exit(0)
