-- ============================================================================
-- Script para criar a tabela data_access (STANDALONE)
-- ============================================================================
-- Execute este script no BigQuery Console se preferir criar manualmente
-- NOTA: O script bootstrap_super_admin.py já cria a tabela automaticamente
-- ============================================================================

CREATE TABLE `rj-pic-dev.app_pequenos_cariocas.data_access` (
  cpf STRING NOT NULL,
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
  description="Tabela de governança - controle de acesso por CPF"
);

-- ============================================================================
-- NOTA SOBRE DEFAULT VALUES
-- ============================================================================
-- BigQuery não suporta DEFAULT na definição de colunas via DDL
-- Os valores padrão são aplicados no código da aplicação:
-- - is_admin: FALSE (aplicado no backend)
-- - is_super_admin: FALSE (aplicado no backend)
-- - active: TRUE (aplicado no backend)
-- - created_at: CURRENT_TIMESTAMP() (aplicado no INSERT)
-- ============================================================================
