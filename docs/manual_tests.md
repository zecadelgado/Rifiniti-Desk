# Testes Manuais

## Alerta de schema incompleto em Manutenções
1. **Preparar ambiente de teste:** em um banco de homologação, remova temporariamente as colunas `tipo_manutencao` e `empresa` da tabela `manutencoes` (ex.: `ALTER TABLE manutencoes DROP COLUMN tipo_manutencao;` e `ALTER TABLE manutencoes DROP COLUMN empresa;`). Faça backup antes de aplicar as alterações.
2. **Abrir a tela de Manutenções:** iniciar o aplicativo e navegar até a tela de manutenções.
3. **Confirmar o alerta:** ao carregar a tela, verificar se surge um `QMessageBox` de aviso solicitando a execução de `database/migrations_manutencao.sql`.
4. **Checar bloqueio de campos:** confirmar que os campos/ações dependentes (`Tipo`, `Empresa`, Novo, Editar e Salvar) permanecem desabilitados enquanto o schema estiver incompleto.
5. **Restaurar o schema:** aplicar `database/migrations_manutencao.sql` para repor as colunas removidas e reabrir a tela para confirmar que os campos voltam a habilitar.
