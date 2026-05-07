-- ========================================================================
-- Migração: Garantir restrição de exclusão para vínculos de patrimônios
-- Data: 2025-02-04
-- Objetivo: Reforçar integridade referencial antes de operações de DELETE,
--           evitando remoção de patrimônios com vínculos dependentes.
-- ========================================================================

-- Defina o schema alvo a partir do database ativo ou, como fallback seguro,
-- pelo nome configurado na aplicacao (backend/database/config_db.py).
SET @schema := IFNULL(NULLIF(DATABASE(), ''), 'patrimonio_ideau');
SELECT CONCAT('Usando schema: ', @schema) AS info;

-- Helper para adicionar constraints com ON DELETE RESTRICT apenas quando
-- a tabela existe e a constraint ainda não foi criada.
SET @table_name := '';
SET @constraint_name := '';
SET @column_name := '';
SET @qualified_table := '';
SET @sql := '';

-- Patrimônios x Centro de Custo
SET @table_name = 'patrimonios_centro_custo';
SET @constraint_name = 'fk_patrimonios_has_centro_custo_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de centro de custo já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Demais relações diretas com patrimônios
-- Movimentações
SET @table_name = 'movimentacoes';
SET @constraint_name = 'fk_movimentacoes_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de movimentações já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Manutenções
SET @table_name = 'manutencoes';
SET @constraint_name = 'fk_manutencoes_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de manutenções já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Depreciações
SET @table_name = 'depreciacoes';
SET @constraint_name = 'fk_depreciacoes_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de depreciações já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Anexos
SET @table_name = 'anexos';
SET @constraint_name = 'fk_anexos_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de anexos já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Itens de Nota Fiscal
SET @table_name = 'itens_nota_fiscal';
SET @constraint_name = 'fk_itens_nota_fiscal_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de itens de nota fiscal já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Garantias
SET @table_name = 'garantias';
SET @constraint_name = 'fk_garantias_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de garantias já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Baixas
SET @table_name = 'baixas';
SET @constraint_name = 'fk_baixas_patrimonios1';
SET @column_name = 'id_patrimonio';
SET @qualified_table = CONCAT('`', @schema, '`.`', @table_name, '`');
SET @sql = (
    SELECT IF(
        EXISTS(SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = @schema AND TABLE_NAME = @table_name)
        AND NOT EXISTS(
            SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = @schema AND CONSTRAINT_NAME = @constraint_name
        ),
        CONCAT(
            'ALTER TABLE ', @qualified_table,
            ' ADD CONSTRAINT ', @constraint_name,
            ' FOREIGN KEY (', @column_name, ') REFERENCES patrimonios(id_patrimonio)',
            ' ON DELETE RESTRICT ON UPDATE CASCADE'
        ),
        'SELECT "Constraint de baixas já existe ou tabela ausente." AS info'
    )
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Validação: listar constraints que apontam para patrimonios e o comportamento
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    DELETE_RULE,
    UPDATE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = @schema
  AND REFERENCED_TABLE_NAME = 'patrimonios';

-- Espera-se que DELETE_RULE esteja em ('RESTRICT', 'NO ACTION') para proteger exclusões.
