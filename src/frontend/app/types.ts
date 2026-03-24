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

/**
 * Item individual da lista de protocolos do participante
 */
export interface ProtocoloListagemItem {
  id?: string;
  secretaria?: string;
  descricao?: string;
  status?: string;
  irregular_indicador?: boolean;
  protocolo_status_label?: string;
}

export interface Participante {
  // Identificação
  cpf?: string;
  id_membro_familia?: string;
  id_familia?: string;
  nome?: string;
  sexo?: string;

  // Dados demográficos
  nascimento_data?: string; // ISO date string
  idade?: number;
  subprefeitura?: string;
  regiao_administrativa?: string;
  bairro?: string;

  // Programa
  grupo?: string;
  cohort?: string; // ISO date string
  status?: string;
  status_inativo_motivo?: string;

  // Protocolos - Lista detalhada (NOVO)
  protocolo_listagem?: ProtocoloListagemItem[];

  // Protocolos - Contadores gerais
  total_protocolos?: number;
  total_protocolos_irregular?: number; // RENOMEADO de total_protocolos_violados
  total_protocolos_atencao?: number; // NOVO
  total_protocolos_regular?: number; // NOVO
  total_fracao?: string;

  // Protocolos - Assistência Social
  assistencia_protocolos_total?: number;
  assistencia_protocolos_irregular?: number; // RENOMEADO de assistencia_protocolos_violados
  assistencia_protocolos_atencao?: number; // NOVO
  assistencia_protocolos_regular?: number; // NOVO
  assistencia_fracao?: string;

  // Protocolos - Educação
  educacao_protocolos_total?: number;
  educacao_protocolos_irregular?: number; // RENOMEADO de educacao_protocolos_violados
  educacao_protocolos_atencao?: number; // NOVO
  educacao_protocolos_regular?: number; // NOVO
  educacao_fracao?: string;

  // Protocolos - Saúde
  saude_protocolos_total?: number;
  saude_protocolos_irregular?: number; // RENOMEADO de saude_protocolos_violados
  saude_protocolos_atencao?: number; // NOVO
  saude_protocolos_regular?: number; // NOVO
  saude_fracao?: string;

  // Situação
  situacao?: string;

  // Equipamentos - SMAS
  id_cras?: string;
  nome_cras?: string;
  id_cas?: string;
  nome_cas?: string;

  // Equipamentos - SME
  id_escola?: string;
  nome_escola?: string;
  id_cre?: string;
  nome_cre?: string;

  // Equipamentos - SMS
  id_ap?: string; 
  nome_ap?: string; 
  id_clinica_familia?: string;
  nome_clinica_familia?: string;

  // Infraestrutura
  cpf_particao?: number;
}

export interface ProtocoloDetalhes {
  cpf?: string;
  id_membro_familia?: string;
  id_familia?: string;
  nome?: string;
  grupo?: string;
  protocolo_id?: string;
  protocolo_secretaria?: string;
  protocolo_descricao?: string;
  protocolo_level?: string;
  protocolo_status?: string;
  protocolo_irregular?: boolean; // RENOMEADO de protocolo_violado
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
  subprefeituras: FilterOptionItem[];
  regioes_administrativas: FilterOptionItem[];
  grupos: FilterOptionItem[];
  cohorts: FilterOptionItem[];
  status_list: FilterOptionItem[];
  situacoes: FilterOptionItem[];
  cres: FilterOptionItem[];
  aps: FilterOptionItem[];
  cas_list: FilterOptionItem[];
  cras: FilterOptionItem[];
  escolas: FilterOptionItem[];
  clinicas: FilterOptionItem[];
  protocolo_descricoes: FilterOptionItem[]; // Descrições de protocolos
  protocolo_status_list: FilterOptionItem[]; // Status de protocolos

  // Filtros de usuários (admin)
  ocupacoes: FilterOptionItem[];
  secretarias: FilterOptionItem[];
  status_ativo: FilterOptionItem[];
  permissions: FilterOptionItem[];
}

// ============================================================================
// DASHBOARD TYPES
// ============================================================================

/**
 * Indicador individual de um protocolo (card)
 */
export interface ProtocoloIndicador {
  protocolo_id: string;         // "sms_vacinacao_pentavalente"
  protocolo_descricao: string;  // "Vacinação Pentavalente"
  protocolo_secretaria: string; // "SMS", "SME", "SMAS"
  numerador: number;            // Quantos estão regulares
  denominador: number;          // Total aplicável
  percentual_regular: number;   // (numerador/denominador) * 100
  percentual_irregular: number; // 100 - percentual_regular
}

/**
 * Ponto de evolução temporal do programa (gráfico de linha)
 */
export interface ResultadoProgramaPoint {
  mes: string;           // "2025-12"
  mes_label: string;     // "Dez/25"
  todos: number;         // % completude geral
  saude: number;         // % completude SMS
  educacao: number;      // % completude SME
  assistencia: number;   // % completude SMAS
}

/**
 * Distribuição por safra (gráfico de barras)
 */
export interface DistribuicaoSafra {
  safra?: string;
  total_participantes?: number;
  total_ativos?: number;
  total_inativos?: number;
}

/**
 * Motivo de saída do programa (gráfico pizza)
 */
export interface DistribuicaoMotivoSaida {
  motivo?: string;
  total?: number;
}

/**
 * Distribuição por tempo de irregularidade (histograma)
 */
export interface DistribuicaoTempoIrregularidade {
  faixa: string;           // "0-30", "31-60", "61-90", "90+"
  faixa_label: string;     // "0-30 dias", "31-60 dias", etc.
  count: number;           // Quantidade de participantes na faixa
  percentual: number;      // Percentual do total
}

/**
 * Tempo médio de irregularidade por secretaria (cards)
 */
export interface TempoMedioIrregularidade {
  secretaria: string;           // "geral", "smas", "sme", "sms"
  secretaria_label: string;     // "Geral", "Assistência Social", "Educação", "Saúde"
  tempo_medio_dias: number;     // Tempo médio em dias
  total_irregulares: number;    // Quantidade de participantes irregulares
}

/**
 * Ponto de taxa de resolução mensal (gráfico de linha)
 */
export interface TaxaResolucaoMensalPoint {
  mes: string;           // "2025-12"
  mes_label: string;     // "Dez/25"
  todos: number;         // % resolução geral
  saude: number;         // % resolução SMS
  educacao: number;      // % resolução SME
  assistencia: number;   // % resolução SMAS
}

/**
 * Modelo principal do Dashboard
 * Todos os valores são calculados no backend e prontos para exibição
 */
export interface Dashboard {
  // =========================================================================
  // SEÇÃO 1: INDICADORES PRINCIPAIS (3 cards)
  // =========================================================================
  total_participantes: number;     // Total de participantes (denominador)
  total_regulares: number;         // Participantes com TODOS protocolos regulares
  total_irregulares: number;       // Participantes com ALGUM protocolo irregular
  percentual_regular: number;      // (total_regulares / total_participantes) * 100
  percentual_irregular: number;    // (total_irregulares / total_participantes) * 100

  // =========================================================================
  // SEÇÃO 2: INDICADORES POR PROTOCOLO (cards individuais)
  // =========================================================================
  protocolos: ProtocoloIndicador[];

  // =========================================================================
  // SEÇÃO 3: RESULTADO DO PROGRAMA (gráfico de linha)
  // =========================================================================
  resultado_programa: ResultadoProgramaPoint[];

  // =========================================================================
  // SEÇÃO 4: DISTRIBUIÇÃO POR SAFRA (gráfico de barras)
  // =========================================================================
  distribuicao_por_safra: DistribuicaoSafra[];

  // =========================================================================
  // SEÇÃO 5: MOTIVOS DE SAÍDA (gráfico pizza)
  // =========================================================================
  distribuicao_motivo_saida: DistribuicaoMotivoSaida[];

  // =========================================================================
  // SEÇÃO 6: TEMPO DE IRREGULARIDADE (cards + histograma)
  // =========================================================================
  tempo_medio_irregularidade: TempoMedioIrregularidade[];
  distribuicao_tempo_irregularidade: DistribuicaoTempoIrregularidade[];

  // =========================================================================
  // SEÇÃO 7: TAXA DE RESOLUÇÃO MENSAL (gráfico de linha)
  // =========================================================================
  taxa_resolucao_mensal: TaxaResolucaoMensalPoint[];

  // =========================================================================
  // METADADOS
  // =========================================================================
  data_atualizacao?: string;
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
 * Todos os filtros suportam multi-select
 */
export interface DashboardFilters {
  subprefeitura?: string | string[]; // Multi-select
  regiao_administrativa?: string | string[]; // Multi-select
  bairro?: string | string[]; // Multi-select
  cre?: string | string[]; // Multi-select
  ap?: string | string[]; // Multi-select
  cas?: string | string[]; // Multi-select
  cras?: string | string[]; // Multi-select
  escola?: string | string[]; // Multi-select
  clinica?: string | string[]; // Multi-select
  safra?: string | string[]; // Multi-select
  grupo?: string | string[]; // Multi-select
  status?: string | string[]; // Multi-select
  situacao?: string | string[]; // Multi-select
  bypass_cache?: boolean;
  protocolo_descricao?: string | string[]; // Filtro por descrição do protocolo (multi-select)
  protocolo_status?: string | string[]; // Filtro por status do protocolo (multi-select)
}

/**
 * Active filters for the professional/participant search tab
 * Todos os filtros suportam multi-select
 */
export interface ParticipantFilters {
  subprefeitura?: string | string[]; // Multi-select
  regiao_administrativa?: string | string[]; // Multi-select
  bairro?: string | string[]; // Multi-select
  cre?: string | string[]; // Multi-select
  ap?: string | string[]; // Multi-select
  cas?: string | string[]; // Multi-select
  cras?: string | string[]; // Multi-select
  escola?: string | string[]; // Multi-select
  clinica?: string | string[]; // Multi-select
  safra?: string | string[]; // Multi-select
  grupo?: string | string[]; // Multi-select
  status?: string | string[]; // Multi-select
  situacao?: string | string[]; // Multi-select
  search?: string; // CPF or name search
  bypass_cache?: boolean;
  protocolo_descricao?: string | string[]; // Filtro por descrição do protocolo (multi-select)
  protocolo_status?: string | string[]; // Filtro por status do protocolo (multi-select)
  protocolo_secretaria?: string; // Filtro por secretaria do protocolo (SME, SMAS, SMS)
  sort_by?: string; // Coluna para ordenação
  sort_order?: SortOrder; // Direção da ordenação (asc/desc)
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

/**
 * Sort state for tables
 */
export type SortOrder = "asc" | "desc";

export interface SortState {
  sortBy: string | null;
  sortOrder: SortOrder;
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
  aps: IdWithName[]; 
  cas: IdWithName[];
  clinicas: IdWithName[];
}

/**
 * User access record (from /admin/users endpoint)
 */
export interface UserAccessRecord {
  cpf: string;
  email?: string | null;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  is_admin: boolean;
  is_super_admin: boolean;
  permission?: string | null;

  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;

  secretaria_acesso?: string | null;

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
  email?: string | null;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  is_admin?: boolean;
  is_super_admin?: boolean;

  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;

  secretaria_acesso?: string | null;

  notes?: string | null;
  is_update?: boolean; // Indica se é uma atualização intencional (vs criação)
}

/**
 * Update user request payload
 */
export interface UpdateUserRequest {
  email?: string | null;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  is_admin?: boolean | null;
  is_super_admin?: boolean | null;

  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null; 
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;

  notes?: string | null;
  active?: boolean | null;
  is_update?: boolean; // Indica se é uma atualização intencional (vs criação)
}

// ============================================================================
// BATCH IMPORT TYPES
// ============================================================================

/**
 * Error for a specific row during batch import
 */
export interface BatchImportError {
  row: number;
  cpf?: string | null;
  error: string;
}

/**
 * Imported user with status
 */
export interface ImportedUser {
  cpf: string;
  nome?: string | null;
  email?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  status: 'new' | 'exists' | 'error';
  error_message?: string | null;

  // Permissões existentes (preenchido apenas para status="exists")
  is_admin?: boolean | null;
  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;
}

/**
 * Result of batch import operation
 */
export interface BatchImportResult {
  total: number;
  imported: number;
  skipped: number;
  errors: BatchImportError[];
  imported_users: ImportedUser[];
}

/**
 * User data for batch permissions update
 */
export interface BatchUserData {
  cpf: string;
  nome?: string | null;
  email?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
}

/**
 * Request for batch permissions update
 */
export interface BatchPermissionsRequest {
  users: BatchUserData[];
  is_admin?: boolean;
  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;
}

/**
 * Error for a specific CPF during batch permissions update
 */
export interface BatchPermissionsError {
  cpf: string;
  error: string;
}

/**
 * Result of batch permissions operation
 */
export interface BatchPermissionsResult {
  total: number;
  updated: number;
  errors: BatchPermissionsError[];
}

/**
 * Imported user with local edits (for frontend state)
 * Extends ImportedUser but adds 'done' status for post-permission assignment
 */
export interface ImportedUserWithEdits {
  cpf: string;
  nome?: string | null;
  email?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  status: 'new' | 'exists' | 'error' | 'done';
  error_message?: string | null;
  edited?: {
    nome?: string;
    ocupacao?: string;
    secretaria?: string;
  };

  // Permissões existentes (preenchido apenas para status="exists")
  is_admin?: boolean | null;
  is_super_admin?: boolean | null;
  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;
}
