CREATE DATABASE IF NOT EXISTS `patrimonio_ideau_v2`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `patrimonio_ideau_v2`;

CREATE TABLE roles (
  id_role SMALLINT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(50) NOT NULL,
  descricao VARCHAR(255) NOT NULL,
  PRIMARY KEY (id_role),
  UNIQUE (codigo)
);

CREATE TABLE usuarios (
  id_usuario BIGINT NOT NULL AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  nome VARCHAR(255) NOT NULL,
  hash_senha VARCHAR(255) NOT NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_usuario),
  UNIQUE (email)
);

CREATE TABLE usuarios_roles (
  id_usuario BIGINT NOT NULL,
  id_role SMALLINT NOT NULL,
  PRIMARY KEY (id_usuario, id_role),
  FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
  FOREIGN KEY (id_role) REFERENCES roles (id_role)
);

CREATE TABLE password_resets (
  id_reset BIGINT NOT NULL AUTO_INCREMENT,
  id_usuario BIGINT NOT NULL,
  token_hash VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME DEFAULT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id_reset),
  UNIQUE (token_hash),
  KEY idx_password_resets_usuario (id_usuario),
  KEY idx_password_resets_expiracao (expires_at),
  FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario)
);

CREATE TABLE fornecedores (
  id_fornecedor BIGINT NOT NULL AUTO_INCREMENT,
  cnpj VARCHAR(18) NOT NULL,
  nome VARCHAR(255) NOT NULL,
  email VARCHAR(255),
  telefone VARCHAR(20),
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_fornecedor),
  UNIQUE (cnpj)
);

CREATE TABLE categorias (
  id_categoria INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(255) NOT NULL,
  descricao TEXT,
  PRIMARY KEY (id_categoria),
  UNIQUE (nome)
);

CREATE TABLE locais (
  id_local INT NOT NULL AUTO_INCREMENT,
  nome VARCHAR(255) NOT NULL,
  localizacao VARCHAR(255),
  descricao TEXT,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id_local),
  UNIQUE (nome)
);

CREATE TABLE centros_custo (
  id_centro_custo INT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(50) NOT NULL,
  nome VARCHAR(255) NOT NULL,
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  notas TEXT,
  PRIMARY KEY (id_centro_custo),
  UNIQUE (codigo),
  UNIQUE (nome)
);

CREATE TABLE status_patrimonio (
  id_status_patrimonio TINYINT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(50) NOT NULL,
  descricao VARCHAR(255) NOT NULL,
  PRIMARY KEY (id_status_patrimonio),
  UNIQUE (codigo)
);

CREATE TABLE tipos_movimentacao (
  id_tipo_movimentacao TINYINT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(50) NOT NULL,
  descricao VARCHAR(255) NOT NULL,
  PRIMARY KEY (id_tipo_movimentacao),
  UNIQUE (codigo)
);

CREATE TABLE status_manutencao (
  id_status_manutencao TINYINT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(50) NOT NULL,
  descricao VARCHAR(255) NOT NULL,
  PRIMARY KEY (id_status_manutencao),
  UNIQUE (codigo)
);

CREATE TABLE tipos_manutencao (
  id_tipo_manutencao TINYINT NOT NULL AUTO_INCREMENT,
  codigo VARCHAR(50) NOT NULL,
  descricao VARCHAR(255) NOT NULL,
  PRIMARY KEY (id_tipo_manutencao),
  UNIQUE (codigo)
);

CREATE TABLE notas_fiscais (
  id_nota_fiscal BIGINT NOT NULL AUTO_INCREMENT,
  numero_nota VARCHAR(255) NOT NULL,
  data_emissao DATE NOT NULL,
  valor_total DECIMAL(12,2) NOT NULL,
  id_fornecedor BIGINT NOT NULL,
  id_centro_custo INT,
  caminho_arquivo VARCHAR(255),
  PRIMARY KEY (id_nota_fiscal),
  UNIQUE (numero_nota),
  KEY idx_notas_fiscais_data_emissao (data_emissao),
  FOREIGN KEY (id_fornecedor) REFERENCES fornecedores (id_fornecedor),
  FOREIGN KEY (id_centro_custo) REFERENCES centros_custo (id_centro_custo)
);

CREATE TABLE nota_fiscal_itens (
  id_item_nf BIGINT NOT NULL AUTO_INCREMENT,
  id_nota_fiscal BIGINT NOT NULL,
  descricao VARCHAR(255) NOT NULL,
  quantidade INT NOT NULL,
  valor_unitario DECIMAL(12,2) NOT NULL,
  ncm VARCHAR(20),
  cfop VARCHAR(20),
  PRIMARY KEY (id_item_nf),
  KEY idx_nfi_nota (id_nota_fiscal),
  FOREIGN KEY (id_nota_fiscal) REFERENCES notas_fiscais (id_nota_fiscal),
  CHECK (quantidade > 0),
  CHECK (valor_unitario >= 0)
);

CREATE TABLE patrimonios (
  id_patrimonio BIGINT NOT NULL AUTO_INCREMENT,
  numero_patrimonio BIGINT NOT NULL,
  nome VARCHAR(255) NOT NULL,
  descricao TEXT,
  numero_serie VARCHAR(255),
  valor_compra DECIMAL(12,2),
  valor_atual DECIMAL(12,2),
  id_categoria INT NOT NULL,
  id_fornecedor BIGINT,
  id_local_atual INT,
  id_item_nf BIGINT,
  id_status_patrimonio TINYINT NOT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_patrimonio),
  UNIQUE (numero_patrimonio),
  UNIQUE (numero_serie),
  KEY idx_patrimonios_categoria (id_categoria),
  FOREIGN KEY (id_categoria) REFERENCES categorias (id_categoria),
  FOREIGN KEY (id_fornecedor) REFERENCES fornecedores (id_fornecedor),
  FOREIGN KEY (id_local_atual) REFERENCES locais (id_local),
  FOREIGN KEY (id_item_nf) REFERENCES nota_fiscal_itens (id_item_nf),
  FOREIGN KEY (id_status_patrimonio) REFERENCES status_patrimonio (id_status_patrimonio),
  CHECK (valor_compra IS NULL OR valor_compra >= 0),
  CHECK (valor_atual IS NULL OR valor_atual >= 0)
);

CREATE TABLE patrimonio_centro_custo_hist (
  id_patrimonio BIGINT NOT NULL,
  id_centro_custo INT NOT NULL,
  inicio_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fim_em DATETIME DEFAULT NULL,
  PRIMARY KEY (id_patrimonio, id_centro_custo, inicio_em),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio),
  FOREIGN KEY (id_centro_custo) REFERENCES centros_custo (id_centro_custo),
  CHECK (fim_em IS NULL OR fim_em >= inicio_em)
);

CREATE TABLE movimentacoes (
  id_movimentacao BIGINT NOT NULL AUTO_INCREMENT,
  id_patrimonio BIGINT NOT NULL,
  id_usuario BIGINT NOT NULL,
  id_tipo_movimentacao TINYINT NOT NULL,
  data_mov DATETIME NOT NULL,
  id_origem INT,
  id_destino INT,
  event_uuid CHAR(36) NOT NULL,
  observacoes TEXT,
  PRIMARY KEY (id_movimentacao),
  UNIQUE (event_uuid),
  KEY idx_movimentacoes_patrimonio_data (id_patrimonio, data_mov),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio),
  FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
  FOREIGN KEY (id_tipo_movimentacao) REFERENCES tipos_movimentacao (id_tipo_movimentacao),
  FOREIGN KEY (id_origem) REFERENCES locais (id_local),
  FOREIGN KEY (id_destino) REFERENCES locais (id_local)
);

CREATE TABLE manutencoes (
  id_manutencao BIGINT NOT NULL AUTO_INCREMENT,
  id_patrimonio BIGINT NOT NULL,
  data_inicio DATE NOT NULL,
  data_fim DATE DEFAULT NULL,
  id_tipo_manutencao TINYINT NOT NULL,
  id_status_manutencao TINYINT NOT NULL,
  custo DECIMAL(12,2) DEFAULT NULL,
  descricao TEXT,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_manutencao),
  KEY idx_manutencoes_status_inicio (id_status_manutencao, data_inicio),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio),
  FOREIGN KEY (id_tipo_manutencao) REFERENCES tipos_manutencao (id_tipo_manutencao),
  FOREIGN KEY (id_status_manutencao) REFERENCES status_manutencao (id_status_manutencao),
  CHECK (custo IS NULL OR custo >= 0),
  CHECK (data_fim IS NULL OR data_fim >= data_inicio)
);

CREATE TABLE depreciacoes (
  id_depreciacao BIGINT NOT NULL AUTO_INCREMENT,
  id_patrimonio BIGINT NOT NULL,
  data_ref DATE NOT NULL,
  valor_depreciado DECIMAL(12,2) NOT NULL,
  valor_resultante DECIMAL(12,2) DEFAULT NULL,
  metodo VARCHAR(50) DEFAULT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_depreciacao),
  KEY idx_depreciacoes_patrimonio_data (id_patrimonio, data_ref),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio),
  CHECK (valor_depreciado >= 0),
  CHECK (valor_resultante IS NULL OR valor_resultante >= 0)
);

CREATE TABLE baixas (
  id_baixa BIGINT NOT NULL AUTO_INCREMENT,
  id_patrimonio BIGINT NOT NULL,
  data_baixa DATE NOT NULL,
  motivo VARCHAR(255) NOT NULL,
  valor_residual DECIMAL(12,2) DEFAULT NULL,
  documento VARCHAR(255) DEFAULT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_baixa),
  KEY idx_baixas_patrimonio_data (id_patrimonio, data_baixa),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio),
  CHECK (valor_residual IS NULL OR valor_residual >= 0)
);

CREATE TABLE anexos (
  id_anexo BIGINT NOT NULL AUTO_INCREMENT,
  id_patrimonio BIGINT NOT NULL,
  nome VARCHAR(255) NOT NULL,
  caminho VARCHAR(255) NOT NULL,
  mime VARCHAR(100) DEFAULT NULL,
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_anexo),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio)
);

CREATE TABLE garantias (
  id_garantia BIGINT NOT NULL AUTO_INCREMENT,
  id_patrimonio BIGINT NOT NULL,
  data_inicio DATE NOT NULL,
  data_fim DATE DEFAULT NULL,
  termos TEXT,
  documento VARCHAR(255),
  criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_garantia),
  FOREIGN KEY (id_patrimonio) REFERENCES patrimonios (id_patrimonio),
  CHECK (data_fim IS NULL OR data_fim >= data_inicio)
);

CREATE TABLE auditorias (
  id_auditoria BIGINT NOT NULL AUTO_INCREMENT,
  id_usuario BIGINT NOT NULL,
  data_evento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  acao VARCHAR(255) NOT NULL,
  tabela_afetada VARCHAR(255),
  id_registro_afetado BIGINT,
  detalhes_antigos JSON,
  detalhes_novos JSON,
  PRIMARY KEY (id_auditoria),
  FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario)
);