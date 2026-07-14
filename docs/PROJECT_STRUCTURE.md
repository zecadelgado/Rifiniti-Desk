# Estrutura do Projeto

Este projeto foi organizado por responsabilidade:

- `frontend/ui/`: telas `.ui`.
- `frontend/images/`: imagens usadas pela interface.
- `frontend/resources/`: recursos Qt compilados e arquivo `.qrc`.
- `frontend/styles/`: tema visual `.qss`.
- `backend/controllers/`: controllers das telas e fluxos de interface.
- `backend/database/`: conexao PostgreSQL, gerenciador de dados e compatibilidade do schema.
- `backend/services/`: servicos auxiliares como auditoria, cache, importacao e logs.
- `backend/utils/`: validadores, dialogs e utilitarios compartilhados.
- `database/`: scripts SQL, schema, migracoes e modelo do banco.
- `scripts/`: setup, preparo do banco e diagnostico.
- `tests/`: suites de teste.
- `templates/`: arquivos-modelo usados pelo sistema.
- `docs/`: documentacao de instalacao, testes manuais e estrutura.

Os arquivos Python antigos dentro de `backend/` foram mantidos como pontes de compatibilidade. Eles importam os modulos das novas subpastas para evitar quebra nos imports existentes enquanto o codigo evolui.
