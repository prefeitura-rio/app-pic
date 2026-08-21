import json
from datetime import date, datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

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

    sort_by: str | None = Field(
        None,
        description="Coluna para ordenar (ex: nome, idade, situacao)",
    )
    sort_order: str | None = Field(
        "asc",
        description="Direção da ordenação: 'asc' ou 'desc'",
        pattern="^(asc|desc)$",
    )


class CommonFilters(BaseModel):
    # Todos os filtros suportam multi-select via comma-separated string
    subprefeitura: str | None = None  # Multi-select
    regiao_administrativa: str | None = None  # Multi-select
    bairro: str | None = None  # Multi-select
    cre: str | None = None  # Multi-select
    ap: str | None = None  # Multi-select
    cas: str | None = None  # Multi-select
    cras: str | None = None  # Multi-select
    escola: str | None = None  # Multi-select
    clinica: str | None = None  # Multi-select
    equipe_familia: str | None = None  # Multi-select
    safra: str | None = None  # Multi-select
    grupo: str | None = None  # Multi-select
    status: str | None = None  # Multi-select
    situacao: str | None = None  # Multi-select
    has_bolsa_familia: bool | None = None  # Filtro booleano
    raca: str | None = None  # Multi-select
    search: str | None = None  # CPF or name search (NOT multi-select)
    protocolo_descricao: str | None = None  # Multi-select
    protocolo_status: str | None = None  # Multi-select
    protocolo_secretaria: str | None = (
        None  # Filtro por secretaria do protocolo (SME, SMAS, SMS)
    )


class GeospatialFilters(BaseModel):
    """Filtros para camadas geoespaciais"""
    tipo_camada: str | None = None  # Multi-select
    categoria: str | None = None  # Multi-select
    regional: str | None = None  # Multi-select
    bairro: str | None = None  # Multi-select
    regiao_administrativa: str | None = None  # Multi-select
    subprefeitura: str | None = None  # Multi-select
    nome: str | None = None  # Multi-select


# --- Response Models ---


class PaginationMeta(BaseModel):
    page: int
    page_size: int | None = None
    total_rows: int
    total_pages: int
    cache_hit: bool
    profiling: Any | None = None
    can_view_dashboard: bool | None = (
        None  # Indica se o usuário pode visualizar a aba Dashboard
    )


class PaginatedResponse(BaseModel, Generic[T]):
    meta: PaginationMeta
    data: list[T]
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
    tipos_camada: list[FilterOptionItem] = []
    categorias: list[FilterOptionItem] = []
    regionais: list[FilterOptionItem] = []
    nomes: list[FilterOptionItem] = []

    # Filtros de participantes
    bairros: list[FilterOptionItem] = []
    subprefeituras: list[FilterOptionItem] = []
    regioes_administrativas: list[FilterOptionItem] = []
    grupos: list[FilterOptionItem] = []
    cohorts: list[FilterOptionItem] = []
    status_list: list[FilterOptionItem] = []
    situacoes: list[FilterOptionItem] = []
    racas: list[FilterOptionItem] = []
    cres: list[FilterOptionItem] = []
    aps: list[FilterOptionItem] = []
    cas_list: list[FilterOptionItem] = []
    cras: list[FilterOptionItem] = []
    escolas: list[FilterOptionItem] = []
    clinicas: list[FilterOptionItem] = []
    equipes_familia: list[FilterOptionItem] = []
    protocolo_descricoes: list[FilterOptionItem] = []  # Descrições de protocolos
    protocolo_status_list: list[FilterOptionItem] = []  # Status de protocolos

    # Filtros de usuários (admin)
    ocupacoes: list[FilterOptionItem] = []
    secretarias: list[FilterOptionItem] = []
    status_ativo: list[FilterOptionItem] = []
    permissions: list[FilterOptionItem] = []
    secretarias_acesso_list: list[FilterOptionItem] = []


class GeospatialFilterOptions(BaseModel):
    """Opções de filtros disponíveis para camadas geoespaciais"""

    tipos_camada: list[FilterOptionItem] = []
    categorias: list[FilterOptionItem] = []
    regionais: list[FilterOptionItem] = []
    bairros: list[FilterOptionItem] = []
    regioes_administrativas: list[FilterOptionItem] = []
    subprefeituras: list[FilterOptionItem] = []
    nomes: list[FilterOptionItem] = []


class GeospatialPaginatedResponse(BaseModel, Generic[T]):
    """Resposta paginada específica para geospatial com seus próprios filtros"""
    meta: PaginationMeta
    data: list[T]
    filters: GeospatialFilterOptions | None = None


# Shared / Nested Models


class DistribuicaoGrupo(BaseModel):
    grupo: str | None = None
    total_participantes: int | None = None


class DistribuicaoBairro(BaseModel):
    bairro: str | None = None
    total_participantes: int | None = None


from src.pic.domain.models.dashboard import (  # noqa: E402, F401
    Dashboard,
    DistribuicaoMotivoSaida,
    DistribuicaoSafra,
    DistribuicaoTempoIrregularidade,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
    TaxaResolucaoMensalPoint,
    TempoMedioIrregularidade,
)


class FiltroRegional(BaseModel):
    id: str | None = None
    nome: str | None = None
    tipo: str | None = None
    secretaria: str | None = None
    bairros: list[str] = []
    data_atualizacao: datetime | None = None


class FiltroEquipamento(BaseModel):
    id: str | None = None
    nome: str | None = None
    tipo: str | None = None
    secretaria: str | None = None
    id_regional: str | None = None
    cep: str | None = None
    bairro: str | None = None
    data_atualizacao: datetime | None = None


class EnderecoSMS(BaseModel):
    """Endereço estruturado vindo da tabela SMS (campo JSON serializado)"""
    endereco: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    regiao_administrativa: str | None = None
    subprefeitura: str | None = None
    longitude: float | None = None
    latitude: float | None = None

class DetalhesProtocoloParticipante(BaseModel):
    """
    Apresenta os detalhes de um protocolo específico para um participante, em específico o motivo para as irregularidades, caso existam.
    """
    id_membro_familia: str | None = None
    cpf: str | None = None
    nome: str | None = None
    protocolo_id: str | None = None
    protocolo_secretaria: str | None = None
    protocolo_descricao: str | None = None
    protocolo_level: str | None = None
    protocolo_status: str | None = None
    protocolo_motivo: str | None = None
    protocolo_debug: str | None = None

class ProtocoloMotivoDetalhe(BaseModel):
    """
        Apresenta os detalhes de um motivo de irregularidade de um protocolo específico, incluindo a fonte e a data da partição.
    """
    fonte: str
    data_particao: str | None = None

class ProtocoloMotivo(BaseModel):
    """
        Apresenta os detalhes de um motivo de irregularidade de um protocolo específico, incluindo a fonte e a data da partição.
    """
    motivos: list[str]
    detalhes: dict[str, ProtocoloMotivoDetalhe] = {}

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

    id: str | None = None
    secretaria: str | None = None
    descricao: str | None = None
    status: str | None = None
    irregular_indicador: bool | None = None
    protocolo_status_label: str | None = None
    protocolo_motivo: ProtocoloMotivo | None = None  # array de strings com os motivos de irregularidade

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
    cpf: str | None = None
    id_membro_familia: str | None = None
    id_familia: str | None = None
    nome: str | None = None
    sexo: str | None = None

    # Dados demográficos
    nascimento_data: date | None = None
    idade: int | None = None
    raca: str | None = None
    endereco: str | None = None
    complemento: str | None = None
    endereco_sms: EnderecoSMS | None = None
    telefone_1_ddd: str | None = None
    telefone_1_numero: str | None = None
    telefone_2_ddd: str | None = None
    telefone_2_numero: str | None = None
    subprefeitura: str | None = None
    regiao_administrativa: str | None = None
    bairro: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    # Programa
    grupo: str | None = None
    cohort: date | None = None
    has_bolsa_familia: bool | None = None
    has_cartao_pic: bool | None = None
    status: str | None = None
    status_inativo_motivo: str | None = None

    # Protocolos - Lista detalhada (NOVO)
    protocolo_listagem: list["ProtocoloListagemItem"] | None = None

    # Protocolos - Contadores gerais
    total_protocolos: int | None = None
    total_protocolos_irregular: int | None = (
        None  # RENOMEADO de total_protocolos_violados
    )
    total_protocolos_atencao: int | None = None  # NOVO
    total_protocolos_regular: int | None = None  # NOVO
    total_fracao: str | None = None

    # Protocolos - Assistência Social
    assistencia_protocolos_total: int | None = None
    assistencia_protocolos_irregular: int | None = (
        None  # RENOMEADO de assistencia_protocolos_violados
    )
    assistencia_protocolos_atencao: int | None = None  # NOVO
    assistencia_protocolos_regular: int | None = None  # NOVO
    assistencia_fracao: str | None = None

    # Protocolos - Educação
    educacao_protocolos_total: int | None = None
    educacao_protocolos_irregular: int | None = (
        None  # RENOMEADO de educacao_protocolos_violados
    )
    educacao_protocolos_atencao: int | None = None  # NOVO
    educacao_protocolos_regular: int | None = None  # NOVO
    educacao_fracao: str | None = None

    # Protocolos - Saúde
    saude_protocolos_total: int | None = None
    saude_protocolos_irregular: int | None = (
        None  # RENOMEADO de saude_protocolos_violados
    )
    saude_protocolos_atencao: int | None = None  # NOVO
    saude_protocolos_regular: int | None = None  # NOVO
    saude_fracao: str | None = None

    # Situação
    situacao: str | None = None

    # Equipamentos - SMAS
    id_cras: str | None = None
    nome_cras: str | None = None
    id_cas: str | None = None
    nome_cas: str | None = None
    source_cras: str | None = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )

    # Equipamentos - SME
    id_escola: str | None = None
    nome_escola: str | None = None
    id_cre: str | None = None
    nome_cre: str | None = None
    source_escola: str | None = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )

    # Equipamentos - SMS
    id_ap: str | None = None
    nome_ap: str | None = None
    id_clinica_familia: str | None = None
    nome_clinica_familia: str | None = None
    source_clinica_familia: str | None = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )
    has_cobertura_clinica_familia: bool | None = None
    id_equipe_familia: str | None = None
    nome_equipe_familia: str | None = None
    source_equipe_familia: str | None = (
        None  # "rmi" (fonte original) | "geo" (fallback geolocalização) | null
    )
    equipe_familia: str | None = None
    has_cobertura_equipe_familia: bool | None = None

    # Infraestrutura
    cpf_particao: int | None = None


class ProtocoloDetalhes(BaseModel):
    cpf: str | None = None
    id_membro_familia: str | None = None
    id_familia: str | None = None
    nome: str | None = None
    grupo: str | None = None
    protocolo_id: str | None = None
    protocolo_secretaria: str | None = None
    protocolo_descricao: str | None = None
    protocolo_level: str | None = None
    protocolo_status: str | None = None
    protocolo_irregular: bool | None = None  # RENOMEADO de protocolo_violado
    protocolo_data_referencia_particicao: date | None = None
    protocolo_status_label: str | None = None
    cpf_particao: int | None = None


class ProtocoloResumo(BaseModel):
    protocolo_secretaria: str | None = None
    protocolo_id: str | None = None
    protocolo_descricao: str | None = None
    protocolo_level: str | None = None
    total_participantes: int | None = None
    total_irregular: int | None = None
    total_regular: int | None = None
    total_nao_aplica: int | None = None
    percentual_irregular: float | None = None
    nivel_prioridade: str | None = None
    data_atualizacao: datetime | None = None


class EvolucaoSafra(BaseModel):
    safra: date | None = None
    total_entrada: int | None = None
    total_ativos: int | None = None
    total_inativos: int | None = None
    distribuicao_motivo_saida: list[DistribuicaoMotivoSaida] = []
    data_atualizacao: datetime | None = None


# ========================================================================
# GEOSPATIAL MODELS
# ========================================================================


class GeospatialLayer(BaseModel):
    """
    Camada geoespacial para visualização em mapas.
    Representa equipamentos públicos ou divisões administrativas com geometrias.
    """

    tipo_camada: str | None = None  # "equipamento", "divisao_administrativa", etc
    tipo_geometria: str | None = None  # "POINT", "POLYGON", "MULTIPOLYGON", etc
    categoria: str | None = None  # "escola", "cras", "clinica", "ap", "cre", "bairro", etc
    id: str | None = None  # Identificador único do item
    id_unico: str | None = None  # Identificador único alternativo
    nome: str | None = None  # Nome do equipamento/área
    geometry_geojson: str | None = None  # GeoJSON da geometria (convertido de GEOGRAPHY)
    regional: str | None = None  # Regional (CRE, AP, CAS)
    bairro: str | None = None
    regiao_administrativa: str | None = None
    subprefeitura: str | None = None
    metadata: str | None = None  # JSON string com metadados adicionais
