import json
from typing import Dict, List, Optional, TypeVar, Generic, Any
from pydantic import BaseModel, Field, field_validator, model_validator, model_serializer
from datetime import date, datetime
from src.utils.data_manager_config import DataManagerConfig as config

T = TypeVar("T")

# --- Request Models ---


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(
        config.DEFAULT_PAGE_SIZE,
        ge=-1,  # -1 significa "todos os dados" (bypass paginação)
        le=config.MAX_PAGE_SIZE,
        description="Items per page (-1 para todos os dados)",
    )


class SortParams(BaseModel):
    """Parâmetros de ordenação para endpoints paginados"""

    sort_by: Optional[str] = Field(
        None,
        description="Coluna para ordenar (ex: nome, idade, situacao)",
    )
    sort_order: Optional[str] = Field(
        "asc",
        description="Direção da ordenação: 'asc' ou 'desc'",
        pattern="^(asc|desc)$",
    )


class CommonFilters(BaseModel):
    # Todos os filtros suportam multi-select via comma-separated string
    subprefeitura: Optional[str] = None  # Multi-select
    regiao_administrativa: Optional[str] = None  # Multi-select
    bairro: Optional[str] = None  # Multi-select
    cre: Optional[str] = None  # Multi-select
    ap: Optional[str] = None  # Multi-select
    cas: Optional[str] = None  # Multi-select
    cras: Optional[str] = None  # Multi-select
    escola: Optional[str] = None  # Multi-select
    clinica: Optional[str] = None  # Multi-select
    equipe_familia: Optional[str] = None  # Multi-select
    safra: Optional[str] = None  # Multi-select
    grupo: Optional[str] = None  # Multi-select
    status: Optional[str] = None  # Multi-select
    situacao: Optional[str] = None  # Multi-select
    has_bolsa_familia: Optional[bool] = None  # Filtro booleano
    search: Optional[str] = None  # CPF or name search (NOT multi-select)
    protocolo_descricao: Optional[str] = None  # Multi-select
    protocolo_status: Optional[str] = None  # Multi-select
    protocolo_secretaria: Optional[str] = (
        None  # Filtro por secretaria do protocolo (SME, SMAS, SMS)
    )


class GeospatialFilters(BaseModel):
    """Filtros para camadas geoespaciais"""
    tipo_camada: Optional[str] = None  # Multi-select
    categoria: Optional[str] = None  # Multi-select
    regional: Optional[str] = None  # Multi-select
    bairro: Optional[str] = None  # Multi-select
    regiao_administrativa: Optional[str] = None  # Multi-select
    subprefeitura: Optional[str] = None  # Multi-select
    nome: Optional[str] = None  # Multi-select


# --- Response Models ---


class PaginationMeta(BaseModel):
    page: int
    page_size: Optional[int] = None
    total_rows: int
    total_pages: int
    cache_hit: bool
    profiling: Optional[Any] = None
    can_view_dashboard: Optional[bool] = (
        None  # Indica se o usuário pode visualizar a aba Dashboard
    )


class PaginatedResponse(BaseModel, Generic[T]):
    meta: PaginationMeta
    data: List[T]
    filters: Optional["SmartFilterOptions"] = (
        None  # Opções de filtros dinâmicas baseadas nos dados atuais
    )


# --- Smart Filter Options ---


class FilterOptionItem(BaseModel):
    """Item de filtro simples"""

    id: str
    label: str


class SmartFilterOptions(BaseModel):
    """Opções de filtros disponíveis baseadas nos dados filtrados"""

    # Filtros geoespaciais (geospatial endpoint)
    tipos_camada: List[FilterOptionItem] = []
    categorias: List[FilterOptionItem] = []
    regionais: List[FilterOptionItem] = []
    nomes: List[FilterOptionItem] = []

    # Filtros de participantes
    bairros: List[FilterOptionItem] = []
    subprefeituras: List[FilterOptionItem] = []
    regioes_administrativas: List[FilterOptionItem] = []
    grupos: List[FilterOptionItem] = []
    cohorts: List[FilterOptionItem] = []
    status_list: List[FilterOptionItem] = []
    situacoes: List[FilterOptionItem] = []
    cres: List[FilterOptionItem] = []
    aps: List[FilterOptionItem] = []
    cas_list: List[FilterOptionItem] = []
    cras: List[FilterOptionItem] = []
    escolas: List[FilterOptionItem] = []
    clinicas: List[FilterOptionItem] = []
    equipes_familia: List[FilterOptionItem] = []
    protocolo_descricoes: List[FilterOptionItem] = []  # Descrições de protocolos
    protocolo_status_list: List[FilterOptionItem] = []  # Status de protocolos

    # Filtros de usuários (admin)
    ocupacoes: List[FilterOptionItem] = []
    secretarias: List[FilterOptionItem] = []
    status_ativo: List[FilterOptionItem] = []
    permissions: List[FilterOptionItem] = []
    secretaria_acesso_list: List[FilterOptionItem] = []


class GeospatialFilterOptions(BaseModel):
    """Opções de filtros disponíveis para camadas geoespaciais"""

    tipos_camada: List[FilterOptionItem] = []
    categorias: List[FilterOptionItem] = []
    regionais: List[FilterOptionItem] = []
    bairros: List[FilterOptionItem] = []
    regioes_administrativas: List[FilterOptionItem] = []
    subprefeituras: List[FilterOptionItem] = []
    nomes: List[FilterOptionItem] = []


class GeospatialPaginatedResponse(BaseModel, Generic[T]):
    """Resposta paginada específica para geospatial com seus próprios filtros"""
    meta: PaginationMeta
    data: List[T]
    filters: Optional[GeospatialFilterOptions] = None


# Shared / Nested Models


class DistribuicaoMotivoSaida(BaseModel):
    motivo: Optional[str] = None
    total: Optional[int] = None


class DistribuicaoGrupo(BaseModel):
    grupo: Optional[str] = None
    total_participantes: Optional[int] = None


class DistribuicaoBairro(BaseModel):
    bairro: Optional[str] = None
    total_participantes: Optional[int] = None


class DistribuicaoSafra(BaseModel):
    safra: Optional[str] = None  # Changed to str to match DataFrame output usually
    total_participantes: Optional[int] = None
    total_ativos: Optional[int] = None
    total_inativos: Optional[int] = None


class ResultadoProgramaPoint(BaseModel):
    """
    Ponto de evolução temporal do programa por dimensão.
    Usado no gráfico de linha "Resultado do Programa".
    """

    mes: str  # "2025-12", "2025-11", etc.
    mes_label: str = ""  # "Dez/25", "Nov/25", etc. (para exibição)
    todos: float = 0.0  # % completude geral (todos protocolos)
    saude: float = 0.0  # % completude SMS
    educacao: float = 0.0  # % completude SME
    assistencia: float = 0.0  # % completude SMAS


class DistribuicaoTempoIrregularidade(BaseModel):
    """
    Distribuição de participantes por faixa de tempo de irregularidade.
    Usado no histograma "Distribuição por Tempo de Irregularidade".
    """

    faixa: str  # "0-30", "31-60", "61-90", "90+"
    faixa_label: str = ""  # "0-30 dias", "31-60 dias", etc.
    count: int = 0  # Quantidade de participantes na faixa
    percentual: float = 0.0  # Percentual do total


class TempoMedioIrregularidade(BaseModel):
    """
    Tempo médio de irregularidade por secretaria.
    Usado nos cards de tempo médio.
    """

    secretaria: str  # "geral", "smas", "sme", "sms"
    secretaria_label: str = ""  # "Geral", "Assistência Social", "Educação", "Saúde"
    tempo_medio_dias: float = 0.0  # Tempo médio em dias
    total_irregulares: int = 0  # Quantidade de participantes irregulares


class TaxaResolucaoMensalPoint(BaseModel):
    """
    Ponto de taxa de resolução mensal por secretaria.
    Usado no gráfico de linha "Taxa de Resolução Mensal".
    """

    mes: str  # "2025-12", "2025-11", etc.
    mes_label: str = ""  # "Dez/25", "Nov/25", etc. (para exibição)
    todos: float = 0.0  # % resolução geral
    saude: float = 0.0  # % resolução SMS
    educacao: float = 0.0  # % resolução SME
    assistencia: float = 0.0  # % resolução SMAS


# ========================================================================
# DASHBOARD - Cards de Indicadores por Protocolo
# ========================================================================


class ProtocoloIndicador(BaseModel):
    """
    Card de indicador individual de um protocolo.
    Calculado a partir de `valor_mais_recente` do BigQuery.
    """

    protocolo_id: str  # "sms_vacinacao_pentavalente"
    protocolo_descricao: str  # "Vacinação Pentavalente"
    protocolo_secretaria: str  # "SMS", "SME", "SMAS"
    numerador: int = 0  # Quantos estão regulares
    denominador: int = 0  # Total aplicável
    percentual_regular: float = 0.0  # (numerador/denominador) * 100
    percentual_irregular: float = 0.0  # 100 - percentual_regular


# Endpoint Models


class Dashboard(BaseModel):
    """
    Modelo principal do Dashboard.
    Todos os valores são calculados no backend e prontos para exibição no frontend.
    """

    # =========================================================================
    # SEÇÃO 1: INDICADORES PRINCIPAIS (3 cards)
    # Fonte: indicador_participantes_percentual_regular/irregular
    # =========================================================================
    total_participantes: int = 0  # Total de participantes (denominador)
    total_regulares: int = 0  # Participantes com TODOS protocolos regulares
    total_irregulares: int = 0  # Participantes com ALGUM protocolo irregular
    percentual_regular: float = 0.0  # (total_regulares / total_participantes) * 100
    percentual_irregular: float = 0.0  # (total_irregulares / total_participantes) * 100

    # =========================================================================
    # SEÇÃO 2: INDICADORES POR PROTOCOLO (cards individuais)
    # Fonte: indicador_protocolos_percentual_regular[].valor_mais_recente
    # =========================================================================
    protocolos: List[ProtocoloIndicador] = []

    # =========================================================================
    # SEÇÃO 3: RESULTADO DO PROGRAMA (gráfico de linha evolução temporal)
    # Fonte: indicador_protocolos_percentual_regular[].valores_mensais
    # Agrupa por mês e por secretaria (SMAS, SME, SMS)
    # =========================================================================
    resultado_programa: List[ResultadoProgramaPoint] = []

    # =========================================================================
    # SEÇÃO 4: DISTRIBUIÇÃO POR SAFRA (gráfico de barras)
    # =========================================================================
    distribuicao_por_safra: List[DistribuicaoSafra] = []

    # =========================================================================
    # SEÇÃO 5: MOTIVOS DE SAÍDA (gráfico pizza)
    # =========================================================================
    distribuicao_motivo_saida: List[DistribuicaoMotivoSaida] = []

    # =========================================================================
    # SEÇÃO 6: TEMPO DE IRREGULARIDADE (cards + histograma)
    # Fonte: indicador_tempo_irregular
    # =========================================================================
    tempo_medio_irregularidade: List["TempoMedioIrregularidade"] = []
    distribuicao_tempo_irregularidade: List["DistribuicaoTempoIrregularidade"] = []

    # =========================================================================
    # SEÇÃO 7: TAXA DE RESOLUÇÃO MENSAL (gráfico de linha)
    # Fonte: serie_resolucao_alertas_percentual
    # =========================================================================
    taxa_resolucao_mensal: List["TaxaResolucaoMensalPoint"] = []

    # =========================================================================
    # METADADOS
    # =========================================================================
    data_atualizacao: Optional[datetime] = None


class FiltroRegional(BaseModel):
    id: Optional[str] = None
    nome: Optional[str] = None
    tipo: Optional[str] = None
    secretaria: Optional[str] = None
    bairros: List[str] = []
    data_atualizacao: Optional[datetime] = None


class FiltroEquipamento(BaseModel):
    id: Optional[str] = None
    nome: Optional[str] = None
    tipo: Optional[str] = None
    secretaria: Optional[str] = None
    id_regional: Optional[str] = None
    cep: Optional[str] = None
    bairro: Optional[str] = None
    data_atualizacao: Optional[datetime] = None


class EnderecoSMS(BaseModel):
    """Endereço estruturado vindo da tabela SMS (campo JSON serializado)"""
    endereco: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    regiao_administrativa: Optional[str] = None
    subprefeitura: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None

class DetalhesProtocoloParticipante(BaseModel):
    """
    Apresenta os detalhes de um protocolo específico para um participante, em específico o motivo para as irregularidades, caso existam.
    """
    id_membro_familia: Optional[str] = None
    cpf: Optional[str] = None
    nome: Optional[str] = None
    protocolo_id: Optional[str] = None
    protocolo_secretaria: Optional[str] = None
    protocolo_descricao: Optional[str] = None
    protocolo_level: Optional[str] = None
    protocolo_status: Optional[str] = None
    protocolo_motivo: Optional[str] = None
    protocolo_debug: Optional[str] = None

class ProtocoloMotivoDetalhe(BaseModel):
    """
        Apresenta os detalhes de um motivo de irregularidade de um protocolo específico, incluindo a fonte e a data da partição.
    """
    fonte: str
    data_particao: Optional[str] = None

class ProtocoloMotivo(BaseModel):
    """
        Apresenta os detalhes de um motivo de irregularidade de um protocolo específico, incluindo a fonte e a data da partição.
    """
    motivos: List[str]
    detalhes: Dict[str, ProtocoloMotivoDetalhe] = {}

    @model_validator(mode='before')
    @classmethod
    def parse_json_string(cls, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                return {}
        if isinstance(data, dict):
            detalhes = data.get("detalhes", {})
            data["detalhes"] = {k: v for k, v in detalhes.items() if v is not None}
        return data

class ProtocoloListagemItem(BaseModel):
    """Item individual da lista de protocolos do participante"""

    id: Optional[str] = None
    secretaria: Optional[str] = None
    descricao: Optional[str] = None
    status: Optional[str] = None
    irregular_indicador: Optional[bool] = None
    protocolo_status_label: Optional[str] = None
    protocolo_motivo: Optional[ProtocoloMotivo] = None  # array de strings com os motivos de irregularidade

    @model_serializer(mode="wrap")
    def _drop_none_motivo(self, handler, info):
        result = handler(self, info)
        if result.get("protocolo_motivo") is None:
            result.pop("protocolo_motivo", None)
        return result


class Participante(BaseModel):
    @field_validator("endereco_sms", mode="before")
    @classmethod
    def parse_endereco_sms(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    # Identificação
    cpf: Optional[str] = None
    id_membro_familia: Optional[str] = None
    id_familia: Optional[str] = None
    nome: Optional[str] = None
    sexo: Optional[str] = None

    # Dados demográficos
    nascimento_data: Optional[date] = None
    idade: Optional[int] = None
    endereco: Optional[str] = None
    complemento: Optional[str] = None
    endereco_sms: Optional[EnderecoSMS] = None
    telefone_1_ddd: Optional[str] = None
    telefone_1_numero: Optional[str] = None
    telefone_2_ddd: Optional[str] = None
    telefone_2_numero: Optional[str] = None
    subprefeitura: Optional[str] = None
    regiao_administrativa: Optional[str] = None
    bairro: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Programa
    grupo: Optional[str] = None
    cohort: Optional[date] = None
    has_bolsa_familia: Optional[bool] = None
    has_cartao_pic: Optional[bool] = None
    status: Optional[str] = None
    status_inativo_motivo: Optional[str] = None

    # Protocolos - Lista detalhada (NOVO)
    protocolo_listagem: Optional[List["ProtocoloListagemItem"]] = None

    # Protocolos - Contadores gerais
    total_protocolos: Optional[int] = None
    total_protocolos_irregular: Optional[int] = (
        None  # RENOMEADO de total_protocolos_violados
    )
    total_protocolos_atencao: Optional[int] = None  # NOVO
    total_protocolos_regular: Optional[int] = None  # NOVO
    total_fracao: Optional[str] = None

    # Protocolos - Assistência Social
    assistencia_protocolos_total: Optional[int] = None
    assistencia_protocolos_irregular: Optional[int] = (
        None  # RENOMEADO de assistencia_protocolos_violados
    )
    assistencia_protocolos_atencao: Optional[int] = None  # NOVO
    assistencia_protocolos_regular: Optional[int] = None  # NOVO
    assistencia_fracao: Optional[str] = None

    # Protocolos - Educação
    educacao_protocolos_total: Optional[int] = None
    educacao_protocolos_irregular: Optional[int] = (
        None  # RENOMEADO de educacao_protocolos_violados
    )
    educacao_protocolos_atencao: Optional[int] = None  # NOVO
    educacao_protocolos_regular: Optional[int] = None  # NOVO
    educacao_fracao: Optional[str] = None

    # Protocolos - Saúde
    saude_protocolos_total: Optional[int] = None
    saude_protocolos_irregular: Optional[int] = (
        None  # RENOMEADO de saude_protocolos_violados
    )
    saude_protocolos_atencao: Optional[int] = None  # NOVO
    saude_protocolos_regular: Optional[int] = None  # NOVO
    saude_fracao: Optional[str] = None

    # Situação
    situacao: Optional[str] = None

    # Equipamentos - SMAS
    id_cras: Optional[str] = None
    nome_cras: Optional[str] = None
    id_cas: Optional[str] = None
    nome_cas: Optional[str] = None
    source_cras: Optional[str] = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )

    # Equipamentos - SME
    id_escola: Optional[str] = None
    nome_escola: Optional[str] = None
    id_cre: Optional[str] = None
    nome_cre: Optional[str] = None
    source_escola: Optional[str] = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )

    # Equipamentos - SMS
    id_ap: Optional[str] = None
    nome_ap: Optional[str] = None
    id_clinica_familia: Optional[str] = None
    nome_clinica_familia: Optional[str] = None
    source_clinica_familia: Optional[str] = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )
    has_cobertura_clinica_familia: Optional[bool] = None
    id_equipe_familia: Optional[str] = None
    nome_equipe_familia: Optional[str] = None
    source_equipe_familia: Optional[str] = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )
    equipe_familia: Optional[str] = None
    has_cobertura_equipe_familia: Optional[bool] = None

    # Infraestrutura
    cpf_particao: Optional[int] = None


class ProtocoloDetalhes(BaseModel):
    cpf: Optional[str] = None
    id_membro_familia: Optional[str] = None
    id_familia: Optional[str] = None
    nome: Optional[str] = None
    grupo: Optional[str] = None
    protocolo_id: Optional[str] = None
    protocolo_secretaria: Optional[str] = None
    protocolo_descricao: Optional[str] = None
    protocolo_level: Optional[str] = None
    protocolo_status: Optional[str] = None
    protocolo_irregular: Optional[bool] = None  # RENOMEADO de protocolo_violado
    protocolo_data_referencia_particicao: Optional[date] = None
    protocolo_status_label: Optional[str] = None
    cpf_particao: Optional[int] = None


class ProtocoloResumo(BaseModel):
    protocolo_secretaria: Optional[str] = None
    protocolo_id: Optional[str] = None
    protocolo_descricao: Optional[str] = None
    protocolo_level: Optional[str] = None
    total_participantes: Optional[int] = None
    total_irregular: Optional[int] = None
    total_regular: Optional[int] = None
    total_nao_aplica: Optional[int] = None
    percentual_irregular: Optional[float] = None
    nivel_prioridade: Optional[str] = None
    data_atualizacao: Optional[datetime] = None


class EvolucaoSafra(BaseModel):
    safra: Optional[date] = None
    total_entrada: Optional[int] = None
    total_ativos: Optional[int] = None
    total_inativos: Optional[int] = None
    distribuicao_motivo_saida: List[DistribuicaoMotivoSaida] = []
    data_atualizacao: Optional[datetime] = None


# ========================================================================
# GEOSPATIAL MODELS
# ========================================================================


class GeospatialLayer(BaseModel):
    """
    Camada geoespacial para visualização em mapas.
    Representa equipamentos públicos ou divisões administrativas com geometrias.
    """

    tipo_camada: Optional[str] = None  # "equipamento", "divisao_administrativa", etc
    tipo_geometria: Optional[str] = None  # "POINT", "POLYGON", "MULTIPOLYGON", etc
    categoria: Optional[str] = None  # "escola", "cras", "clinica", "ap", "cre", "bairro", etc
    id: Optional[str] = None  # Identificador único do item
    id_unico: Optional[str] = None  # Identificador único alternativo
    nome: Optional[str] = None  # Nome do equipamento/área
    geometry_geojson: Optional[str] = None  # GeoJSON da geometria (convertido de GEOGRAPHY)
    regional: Optional[str] = None  # Regional (CRE, AP, CAS)
    bairro: Optional[str] = None
    regiao_administrativa: Optional[str] = None
    subprefeitura: Optional[str] = None
    metadata: Optional[str] = None  # JSON string com metadados adicionais
