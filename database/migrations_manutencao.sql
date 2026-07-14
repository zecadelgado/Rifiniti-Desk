ALTER TABLE manutencoes
  ADD COLUMN IF NOT EXISTS tipo_manutencao VARCHAR(20),
  ADD COLUMN IF NOT EXISTS empresa VARCHAR(255),
  ADD COLUMN IF NOT EXISTS responsavel VARCHAR(255),
  ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pendente';

CREATE INDEX IF NOT EXISTS idx_manutencoes_tipo_manutencao ON manutencoes(tipo_manutencao);
CREATE INDEX IF NOT EXISTS idx_manutencoes_empresa ON manutencoes(empresa);
