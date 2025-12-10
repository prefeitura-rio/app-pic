-- Tabela de governança para controle de acesso por CPF
--
-- IMPORTANTE: Os valores de projeto, dataset e tabela abaixo são exemplos.
-- Ajuste conforme as variáveis de ambiente configuradas em src/config/.env:
--   - BQ_PROJECT_ID (ex: rj-pic-dev)
--   - BQ_DATASET_ID (ex: app_pequenos_cariocas)
--   - BQ_TABLE_ID_DATA_ACCESS (ex: data_access)
--
-- Para criar:
--   Execute este SQL no console do BigQuery
--   Ou use: bq query --use_legacy_sql=false < scripts/create_data_access_table.sql
--
-- Para dropar e recriar:
--   DROP TABLE IF EXISTS `rj-pic-dev.app_pequenos_cariocas.data_access`;
--   Depois execute este arquivo
--
-- NOTA: O script bootstrap_super_admin.py cria esta tabela automaticamente
--       usando as variáveis de ambiente. Use este arquivo SQL apenas se
--       precisar criar a tabela manualmente.

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
  id_ap_list ARRAY<STRUCT<id STRING, nome STRING>>,
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
