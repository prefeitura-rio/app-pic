// ============================================================================
// BACKEND RESPONSE TYPES (matching src/api/v1/schemas.py)
// ============================================================================

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
  cache_hit: boolean;
  profiling?: any;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: PaginationMeta;
  filters?: SmartFilterOptions; // Opções de filtros dinâmicas baseadas nos dados filtrados
}

// ============================================================================
// PARTICIPANT TYPES
// ============================================================================

export interface Participante {
  cpf?: string;
  id_membro_familia?: string;
  nome?: string;
  sexo?: string;
  nascimento_data?: string; // ISO date string
  idade?: number;
  grupo?: string;
  cohort?: string; // ISO date string
  status?: string;
  status_inativo_motivo?: string;
  bairro?: string;
  logradouro?: string;
  numero?: string;
  cep?: string;
  telefone_principal?: string;
  email_principal?: string;
  total_protocolos_violados?: number;
  total_protocolos?: number;
  total_fracao?: string;
  assistencia_protocolos_violados?: number;
  assistencia_protocolos_total?: number;
  assistencia_fracao?: string;
  educacao_protocolos_violados?: number;
  educacao_protocolos_total?: number;
  educacao_fracao?: string;
  saude_protocolos_violados?: number;
  saude_protocolos_total?: number;
  saude_fracao?: string;
  situacao?: string;
  cadunico_indicador?: boolean;
  bolsa_familia_indicador?: boolean;
  bolsa_familia_valor?: number;
  id_cras?: string;
  nome_cras?: string;
  id_escola?: string;
  nome_escola?: string;
  id_cre?: string;
  nome_cre?: string;
  id_cap?: string;
  nome_cap?: string;
  id_cas?: string;
  nome_cas?: string;
  frequencia_escolar_percentual?: number;
  id_clinica_familia?: string;
  nome_clinica_familia?: string;
  cpf_particao?: number;
}

export interface ProtocoloDetalhes {
  cpf?: string;
  id_membro_familia?: string;
  nome?: string;
  grupo?: string;
  protocolo_id?: string;
  protocolo_secretaria?: string;
  protocolo_descricao?: string;
  protocolo_level?: string;
  protocolo_status?: string;
  protocolo_violado?: boolean;
  protocolo_data_referencia_particicao?: string; // ISO date string
  protocolo_status_label?: string;
  cpf_particao?: number;
}

// ============================================================================
// FILTER OPTION TYPES (matching SmartFilterOptions schema)
// ============================================================================

export interface FilterOptionItem {
  id: string;
  label: string;
}

export interface SmartFilterOptions {
  // Filtros de participantes
  bairros: FilterOptionItem[];
  grupos: FilterOptionItem[];
  cohorts: FilterOptionItem[];
  status_list: FilterOptionItem[];
  situacoes: FilterOptionItem[];
  cres: FilterOptionItem[];
  caps: FilterOptionItem[];
  cas_list: FilterOptionItem[];
  cras: FilterOptionItem[];
  escolas: FilterOptionItem[];
  clinicas: FilterOptionItem[];

  // Filtros de usuários (admin)
  ocupacoes: FilterOptionItem[];
  secretarias: FilterOptionItem[];
  status_ativo: FilterOptionItem[];
  permissions: FilterOptionItem[];
}

// ============================================================================
// DASHBOARD TYPES
// ============================================================================

export interface DistribuicaoMotivoSaida {
  motivo?: string;
  total?: number;
}

export interface DistribuicaoGrupo {
  grupo?: string;
  total_participantes?: number;
}

export interface DistribuicaoBairro {
  bairro?: string;
  total_participantes?: number;
}

export interface DistribuicaoSafra {
  safra?: string;
  total_participantes?: number;
  total_ativos?: number;
  total_inativos?: number;
}

export interface ResultadoProgramaPoint {
  mes: string;
  todos: number; // % completude geral
  saude: number; // % completude saúde
  educacao: number; // % completude educação
  assistencia: number; // % completude assistência
}

export interface Dashboard {
  // Totais básicos
  total_participantes_ativos?: number;
  total_participantes_inativos?: number;
  total_participantes_geral?: number;

  // Métricas principais (Regular/Irregular)
  total_participantes_regulares?: number;
  total_participantes_irregulares?: number;
  percentual_regular?: number;
  percentual_irregular?: number;

  // Métricas antigas (manter compatibilidade)
  total_participantes_em_atencao?: number;
  percentual_em_atencao?: number;

  // Protocolos gerais
  total_protocolos?: number;
  total_protocolos_violados?: number;
  percentual_protocolos_violados?: number;

  // Protocolos por dimensão
  total_protocolos_smas?: number;
  total_protocolos_smas_violados?: number;
  percentual_smas_violados?: number;
  total_protocolos_sme?: number;
  total_protocolos_sme_violados?: number;
  percentual_sme_violados?: number;
  total_protocolos_sms?: number;
  total_protocolos_sms_violados?: number;
  percentual_sms_violados?: number;

  // Dimensão Assistência Social
  assistencia_bolsa_familia_total?: number;
  assistencia_bolsa_familia_percentual?: number;
  assistencia_cadunico_atualizado_total?: number;
  assistencia_cadunico_atualizado_percentual?: number;
  assistencia_completude_total?: number;
  assistencia_completude_percentual?: number;

  // Dimensão Educação
  educacao_frequencia_adequada_total?: number;
  educacao_frequencia_adequada_percentual?: number;
  educacao_completude_total?: number;
  educacao_completude_percentual?: number;

  // Dimensão Saúde
  saude_completude_total?: number;
  saude_completude_percentual?: number;

  // Distribuições
  distribuicao_por_grupo?: DistribuicaoGrupo[];
  top_bairros?: DistribuicaoBairro[];
  distribuicao_motivo_saida?: DistribuicaoMotivoSaida[];
  distribuicao_por_safra?: DistribuicaoSafra[];

  // Resultado do Programa (evolução temporal)
  resultado_programa?: ResultadoProgramaPoint[];

  data_atualizacao?: string; // ISO datetime string
}

// ============================================================================
// FILTER EQUIPMENT & REGIONAL TYPES
// ============================================================================

export interface FiltroEquipamento {
  id?: string;
  nome?: string;
  tipo?: string;
  secretaria?: string;
  id_regional?: string;
  cep?: string;
  bairro?: string;
  data_atualizacao?: string; // ISO datetime string
}

export interface FiltroRegional {
  id?: string;
  nome?: string;
  tipo?: string;
  secretaria?: string;
  bairros?: string[];
  data_atualizacao?: string; // ISO datetime string
}

// ============================================================================
// FRONTEND-SPECIFIC TYPES
// ============================================================================

/**
 * Active filters for the dashboard/overview tab
 */
export interface DashboardFilters {
  bairro?: string;
  cre?: string;
  cap?: string;
  cas?: string;
  cras?: string;
  escola?: string;
  clinica?: string;
  safra?: string;
  grupo?: string;
  status?: string;
}

/**
 * Active filters for the professional/participant search tab
 */
export interface ParticipantFilters {
  bairro?: string;
  cre?: string;
  cap?: string;
  cas?: string;
  cras?: string;
  escola?: string;
  clinica?: string;
  safra?: string;
  grupo?: string;
  status?: string;
  situacao?: string;
  search?: string; // CPF or name search
}

/**
 * Pagination state for frontend tables
 */
export interface PaginationState {
  currentPage: number;
  pageSize: number;
  totalRows: number;
  totalPages: number;
}

// ============================================================================
// UTILITY TYPES
// ============================================================================

/**
 * Generic API error response
 */
export interface ApiError {
  detail: string;
  status?: number;
}

/**
 * Loading state for async operations
 */
export type LoadingState = "idle" | "loading" | "success" | "error";

// ============================================================================
// ADMIN / GOVERNANCE TYPES
// ============================================================================

/**
 * ID with name for UI display
 */
export interface IdWithName {
  id: string;
  nome: string;
}

/**
 * Available IDs for assignment (from /admin/available-ids endpoint)
 */
export interface AvailableIds {
  cras: IdWithName[];
  escolas: IdWithName[];
  cres: IdWithName[];
  caps: IdWithName[];
  cas: IdWithName[];
  clinicas: IdWithName[];
}

/**
 * User access record (from /admin/users endpoint)
 */
export interface UserAccessRecord {
  cpf: string;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  is_admin: boolean;
  is_super_admin: boolean;

  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_cap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;

  active: boolean;
  notes?: string | null;
  created_by: string;
  created_at: string; // ISO datetime string
  updated_by?: string | null;
  updated_at?: string | null;
}

/**
 * Create user request payload
 */
export interface CreateUserRequest {
  cpf: string;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  is_admin?: boolean;
  is_super_admin?: boolean;

  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_cap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;

  notes?: string | null;
  is_update?: boolean; // Indica se é uma atualização intencional (vs criação)
}

/**
 * Update user request payload
 */
export interface UpdateUserRequest {
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  is_admin?: boolean | null;
  is_super_admin?: boolean | null;

  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_cap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;

  notes?: string | null;
  active?: boolean | null;
  is_update?: boolean; // Indica se é uma atualização intencional (vs criação)
}
