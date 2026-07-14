DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN unnest(c.conkey) colnum ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = colnum
    WHERE c.contype = 'f'
      AND t.relname = 'movimentacoes'
      AND a.attname = 'id_patrimonio'
  ) THEN
    ALTER TABLE movimentacoes
      ADD CONSTRAINT fk_movimentacoes_patrimonio
      FOREIGN KEY (id_patrimonio) REFERENCES patrimonios(id_patrimonio);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN unnest(c.conkey) colnum ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = colnum
    WHERE c.contype = 'f'
      AND t.relname = 'manutencoes'
      AND a.attname = 'id_patrimonio'
  ) THEN
    ALTER TABLE manutencoes
      ADD CONSTRAINT fk_manutencoes_patrimonio
      FOREIGN KEY (id_patrimonio) REFERENCES patrimonios(id_patrimonio);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN unnest(c.conkey) colnum ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = colnum
    WHERE c.contype = 'f'
      AND t.relname = 'depreciacoes'
      AND a.attname = 'id_patrimonio'
  ) THEN
    ALTER TABLE depreciacoes
      ADD CONSTRAINT fk_depreciacoes_patrimonio
      FOREIGN KEY (id_patrimonio) REFERENCES patrimonios(id_patrimonio);
  END IF;
END $$;
