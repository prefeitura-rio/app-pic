-- Tabela de governança para controle de acesso por CPF
--
-- Para criar:
--   Execute este SQL no console do BigQuery
--   Ou use: bq query --use_legacy_sql=false < scripts/create_data_access_table.sql
--
-- Para dropar e recriar:
--   DROP TABLE IF EXISTS `rj-pic-dev.app_pequenos_cariocas.data_access`;
--   Depois execute este arquivo

CREATE TABLE IF NOT EXISTS `rj-pic-dev.app_pequenos_cariocas.data_access` (
  -- Identificação do usuário
  cpf STRING NOT NULL,
  nome STRING,
  ocupacao STRING,  -- Ex: Coordenador, Assistente Social, Diretor
  secretaria STRING,  -- Ex: SMAS, SME, SMS

  -- Permissões administrativas
  is_admin BOOLEAN NOT NULL,
  is_super_admin BOOLEAN NOT NULL,

  -- IDs autorizados com nomes (arrays de STRUCT)
  id_cras_list ARRAY<STRUCT<id STRING, nome STRING>>,
  id_escola_list ARRAY<STRUCT<id STRING, nome STRING>>,
  id_cre_list ARRAY<STRUCT<id STRING, nome STRING>>,
  id_cap_list ARRAY<STRUCT<id STRING, nome STRING>>,
  id_cas_list ARRAY<STRUCT<id STRING, nome STRING>>,
  id_clinica_familia_list ARRAY<STRUCT<id STRING, nome STRING>>,

  -- Auditoria
  created_by STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_by STRING,
  updated_at TIMESTAMP,

  -- Metadata
  active BOOLEAN NOT NULL,
  notes STRING
)
PARTITION BY DATE(created_at)
CLUSTER BY cpf, active
OPTIONS(
  description="Tabela de governança - controle de acesso por CPF com informações do usuário"
);
