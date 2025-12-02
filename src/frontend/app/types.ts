export interface Individual {
  cpf: string;
  nome: string;
  grupo: string;
  cohort: string;
  status: string;
  status_inativo_motivo?: string;
  data_referencia?: string;

  // Protocolos
  protocolo_smas_cadunico_atualizado: string; // "regular" | "irregular" | "nao_aplica" | "atencao"
  protocolo_sme_frequencia_escolar: string;
  protocolo_sme_matriculado_creche: string;
  protocolo_sme_matriculado_pre_escola: string;
  protocolo_sms_consulta_puerperal: string;
  protocolo_sms_consultas_minimas_infantil: string;
  protocolo_sms_consultas_pre_natal: string;
  protocolo_sms_gestantes_testes_rapidos: string;
  protocolo_sms_possui_equipe_familia: string;
  protocolo_sms_vacinacao_pentavalente: string;
  protocolo_sms_visitas_domiciliares_infantil: string;
  protocolo_sms_visitas_domiciliares_puerperio: string;

  datahora_atualizacao: string;

  // Fields that were "Generated" in CSV Loader but should come from API now
  bairro: string;
  unidade: string;
  bolsa_familia: boolean;
  idade_anos?: number;
  faixa_etaria?: string; // "0-1", "1-2", "2-3", "3-4", "4-5", "5-6"
  
  // Tracking fields for irregularity duration
  dias_irregularidade?: number;
  data_inicio_irregularidade?: string;
  
  // Optional ID if present in DB
  id?: string | number;
}

export interface DashboardSummary {
  total_participantes_ativos: number;
  total_participantes_inativos: number;
  total_participantes_geral: number;
  total_participantes_em_atencao: number;
  percentual_em_atencao: number;
  total_protocolos: number;
  total_protocolos_violados: number;
  percentual_protocolos_violados: number;
  total_protocolos_smas: number;
  total_protocolos_smas_violados: number;
  percentual_smas_violados: number;
  total_protocolos_sme: number;
  total_protocolos_sme_violados: number;
  percentual_sme_violados: number;
  total_protocolos_sms: number;
  total_protocolos_sms_violados: number;
  percentual_sms_violados: number;
  distribuicao_por_grupo: Array<{ grupo: string; total_participantes: number }>;
  top_bairros: Array<{ bairro: string; total_participantes: number }>;
  distribuicao_motivo_saida: Array<{ motivo: string; total: number }>;
  distribuicao_por_safra: Array<{ safra: number; total_participantes: number }>;
  data_atualizacao: number;
}

export interface BackendResponse<T> {
  data: T[];
  meta: {
    page: number;
    page_size: number;
    total_rows: number;
    total_pages: number;
    cache_hit: boolean;
    profiling: any;
  };
}

export type PaginatedResponse<T> = BackendResponse<T>;