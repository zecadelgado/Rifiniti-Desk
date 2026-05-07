#!/usr/bin/env python3
"""
Script para atualizar assinaturas dos controllers restantes
para aceitar current_user como parâmetro.
"""

import re
from pathlib import Path

# Controllers que precisam ser atualizados
controllers = [
    'centro_custo.py',
    'manutencao_controller.py',
    'patrimonio_controller.py',
    'depreciassao.py',
    'anexos_controller.py',
    'relatorios_controller.py',
    'setores_locais_controller.py'
]

backend_dir = Path(__file__).parent

for controller_file in controllers:
    file_path = backend_dir / controller_file
    
    if not file_path.exists():
        print(f"[Aviso] Arquivo não encontrado: {controller_file}")
        continue
    
    content = file_path.read_text(encoding='utf-8')
    
    # Padrão para encontrar __init__ sem current_user
    pattern1 = r'def __init__\(self, widget[^)]*db_manager\):'
    replacement1 = lambda m: m.group(0).replace(')', ', current_user=None):')
    
    # Verificar se já tem current_user
    if 'current_user' in content:
        print(f"[Info] {controller_file} já possui current_user")
        continue
    
    # Aplicar substituição
    new_content = re.sub(pattern1, replacement1, content)
    
    # Adicionar self.current_user logo após self.db_manager
    pattern2 = r'(self\.db_manager = db_manager)'
    replacement2 = r'\1\n        self.current_user = current_user'
    new_content = re.sub(pattern2, replacement2, new_content)
    
    if new_content != content:
        file_path.write_text(new_content, encoding='utf-8')
        print(f"[OK] Atualizado: {controller_file}")
    else:
        print(f"[Aviso] Nenhuma alteração necessária em: {controller_file}")

print("\n[Concluído] Script de atualização finalizado.")
