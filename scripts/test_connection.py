#!/usr/bin/env python3
"""
Script de teste de conexão com MySQL - NeoBenesys
Versão: 2.2
"""

import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from backend.database.config_db import get_db_config
from backend.database.db_compat import ensure_runtime_schema

def test_connection():
    """Testa conexão com o banco de dados"""
    
    print("=" * 70)
    print("TESTE DE CONEXÃO - NeoBenesys v2.2")
    print("=" * 70)
    
    # Configurações (mesmas do config_db.py)
    config = get_db_config(include_database=True)
    
    print(f"\n📋 Configurações:")
    print(f"   Host: {config['host']}")
    print(f"   Usuário: {config['user']}")
    print(f"   Banco: {config['database']}")
    print(f"   Senha: {'*' * len(config['password'])}")
    
    # Teste 1: Conexão sem banco
    print(f"\n{'─' * 70}")
    print(f"🔍 Teste 1: Conectar ao MySQL (sem banco específico)...")
    print(f"{'─' * 70}")
    try:
        conn = mysql.connector.connect(
            host=config['host'],
            user=config['user'],
            password=config['password']
        )
        print("✅ Conexão com MySQL bem-sucedida!")
        
        # Verificar versão
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        print(f"   Versão do MySQL: {version}")
        
        # Listar bancos
        cursor.execute("SHOW DATABASES")
        databases = [db[0] for db in cursor.fetchall()]
        print(f"\n   📊 Bancos disponíveis ({len(databases)}):")
        
        target_found = False
        for db in databases:
            if db == config['database']:
                print(f"      ✅ {db} (BANCO DO SISTEMA)")
                target_found = True
            else:
                print(f"         {db}")
        
        if not target_found:
            print(f"\n   ⚠️  ATENÇÃO: Banco '{config['database']}' NÃO ENCONTRADO!")
            print(f"   💡 Solução:")
            print(f"      mysql -u {config['user']} -p")
            print(f"      CREATE DATABASE {config['database']};")
        
        cursor.close()
        conn.close()
        
        if not target_found:
            return False
        
    except Error as e:
        print(f"❌ ERRO: {e}")
        print(f"\n💡 Possíveis soluções:")
        
        if "Access denied" in str(e):
            print(f"   1. Verificar se a senha está correta")
            print(f"   2. Resetar senha do MySQL:")
            print(f"      ALTER USER '{config['user']}'@'{config['host']}' IDENTIFIED BY '{config['password']}';")
        elif "Can't connect" in str(e):
            print(f"   1. Verificar se o MySQL está rodando:")
            print(f"      Windows: net start MySQL80")
            print(f"      Linux: sudo systemctl start mysql")
            print(f"   2. Verificar se o host está correto")
        else:
            print(f"   Consulte o GUIA_TROUBLESHOOTING_BANCO.md")
        
        return False
    
    # Teste 2: Conexão com banco específico
    print(f"\n{'─' * 70}")
    print(f"🔍 Teste 2: Conectar ao banco '{config['database']}'...")
    print(f"{'─' * 70}")
    try:
        conn = mysql.connector.connect(**config)
        print("✅ Conexão com banco bem-sucedida!")
        ensure_runtime_schema(conn)
        
        # Listar tabelas
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        
        if tables:
            print(f"\n   📊 Tabelas encontradas ({len(tables)}):")
            
            # Tabelas esperadas
            expected_tables = [
                'usuarios', 'fornecedores', 'categorias', 'patrimonios',
                'notas_fiscais', 'itens_nota_fiscal', 'movimentacoes',
                'manutencoes', 'centro_custo', 'setores_locais',
                'auditorias', 'anexos'
            ]
            
            for table in sorted(tables):
                if table in expected_tables:
                    print(f"      ✅ {table}")
                else:
                    print(f"      ℹ️  {table}")
            
            # Verificar tabelas faltando
            missing = set(expected_tables) - set(tables)
            if missing:
                print(f"\n   ⚠️  Tabelas faltando ({len(missing)}):")
                for table in sorted(missing):
                    print(f"      ❌ {table}")
                print(f"\n   💡 Execute o setup_database.py para importar database/data.sql:")
                print(f"      .\\.venv\\Scripts\\python.exe .\\scripts\\setup_database.py")
        else:
            print(f"\n   ⚠️  Banco existe mas não tem tabelas!")
            print(f"\n   💡 Execute o setup_database.py para importar database/data.sql:")
            print(f"      .\\.venv\\Scripts\\python.exe .\\scripts\\setup_database.py")
            cursor.close()
            conn.close()
            return False
        
        # Teste 3: Verificar usuários
        print(f"\n{'─' * 70}")
        print(f"🔍 Teste 3: Verificar dados de teste...")
        print(f"{'─' * 70}")
        
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        user_count = cursor.fetchone()[0]
        print(f"   Usuários cadastrados: {user_count}")
        
        if user_count == 0:
            print(f"   ⚠️  Nenhum usuário cadastrado!")
            print(f"   💡 Crie um usuário admin para fazer login")
        else:
            cursor.execute("SELECT nome, email, nivel_acesso FROM usuarios LIMIT 5")
            users = cursor.fetchall()
            print(f"\n   👥 Primeiros usuários:")
            for nome, email, nivel in users:
                print(f"      • {nome} ({email}) - Nível: {nivel}")
        
        cursor.execute("SELECT COUNT(*) FROM fornecedores")
        fornecedor_count = cursor.fetchone()[0]
        print(f"\n   Fornecedores cadastrados: {fornecedor_count}")
        
        cursor.execute("SELECT COUNT(*) FROM patrimonios")
        patrimonio_count = cursor.fetchone()[0]
        print(f"   Patrimônios cadastrados: {patrimonio_count}")
        
        cursor.close()
        conn.close()
        
        # Resultado final
        print(f"\n{'=' * 70}")
        print(f"✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
        print(f"{'=' * 70}")
        print(f"\n🎉 O sistema está pronto para uso!")
        print(f"\n📝 Próximos passos:")
        print(f"   1. Execute: python main.py")
        print(f"   2. Faça login com um usuário cadastrado")
        print(f"   3. Comece a usar o sistema!")
        
        if user_count == 0:
            print(f"\n⚠️  IMPORTANTE: Crie um usuário admin antes de usar o sistema")
        
        return True
        
    except Error as e:
        print(f"❌ ERRO: {e}")
        
        if "Unknown database" in str(e):
            print(f"\n💡 Solução: Criar o banco de dados")
            print(f"   mysql -u {config['user']} -p")
            print(f"   CREATE DATABASE {config['database']};")
        elif "Access denied" in str(e):
            print(f"\n💡 Solução: Verificar permissões do usuário")
            print(f"   GRANT ALL PRIVILEGES ON {config['database']}.* TO '{config['user']}'@'{config['host']}';")
            print(f"   FLUSH PRIVILEGES;")
        elif "doesn't exist" in str(e):
            print(f"\n💡 Solução: Executar o setup_database.py")
            print(f"   .\\.venv\\Scripts\\python.exe .\\scripts\\setup_database.py")
        else:
            print(f"\n💡 Consulte o GUIA_TROUBLESHOOTING_BANCO.md para mais soluções")
        
        return False

if __name__ == '__main__':
    try:
        success = test_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Teste interrompido pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
