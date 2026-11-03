from pydantic import BaseModel

from src.pic.domain.models.filters import FilterOption


class GeospatialLayer(BaseModel):
    tipo_camada: str | None = None
    tipo_geometria: str | None = None
    categoria: str | None = None
    id: str | None = None
    id_unico: str | None = None
    nome: str | None = None
    geometry_geojson: str | None = None
    regional: str | None = None
    bairro: str | None = None
    regiao_administrativa: str | None = None
    subprefeitura: str | None = None
    metadata: str | None = None


class GeospatialFilterOptions(BaseModel):
    tipos_camada: list[FilterOption] = []
    categorias: list[FilterOption] = []
    regionais: list[FilterOption] = []
    bairros: list[FilterOption] = []
    regioes_administrativas: list[FilterOption] = []
    subprefeituras: list[FilterOption] = []
    nomes: list[FilterOption] = []


class CamadaRegularidadeAggregate(BaseModel):
    """Agregado de regularidade por região de uma camada territorial.

    Fonte: ``endpoint_participante_visao_geral_consolidado`` (mesma métrica
    do dashboard: participantes regulares — situação Regular + Atenção —
    sobre o total de participantes). Vem de uma query agregada do PostgREST
    (RLS aplicada antes do GROUP BY). O campo ``regiao`` é o identificador
    da região na coluna de agregação da camada (ex.: nome do bairro,
    ``"3ª Rio Comprido"`` para RA, código da CAS/CRE/AP).
    """

    regiao: str
    total_participantes: int = 0
    total_regulares: int = 0
    total_irregulares: int = 0


# Coluna do consolidado usada no GROUP BY do PostgREST por camada territorial.
# "bairro" e "ra" são as camadas implementadas; "cas"/"cre"/"ap" usam os ids
# das regionalizações (fase 3d do plano de mapas).
CAMADA_GROUP_COLUMN: dict[str, str] = {
    "bairro": "bairro",
    "ra": "regiao_administrativa",
    "cas": "id_cas",
    "cre": "id_cre",
    "ap": "id_ap",
}


class ProtocoloOption(BaseModel):
    """Opção de filtro de protocolo (fonte: endpoint_participante_visao_geral_protocolos)."""

    protocolo_id: str
    protocolo_secretaria: str | None = None
    protocolo_descricao: str | None = None


class RegiaoRegularidadeResumo(BaseModel):
    """Métrica de regularidade (geral ou de um protocolo) numa região (3j)."""

    total_participantes: int = 0
    total_regulares: int = 0
    total_irregulares: int = 0
    taxa_regularidade: float | None = None


class RegiaoProtocoloAggregate(RegiaoRegularidadeResumo):
    """Métrica de um protocolo numa região (fase 3j — cards por protocolo)."""

    protocolo_id: str
    protocolo_secretaria: str | None = None
    protocolo_descricao: str | None = None


class RegiaoDetalhes(BaseModel):
    """Detalhes da região clicada: métrica geral + protocolos da região (3j/3k).

    ``protocolo_geral`` (3k) é a métrica do protocolo selecionado em TODAS
    as regiões (média geral), usada no comparativo "acima/abaixo da média".
    """

    camada: str
    regiao: str
    geral: RegiaoRegularidadeResumo | None = None
    protocolo_geral: RegiaoRegularidadeResumo | None = None
    protocolos: list[RegiaoProtocoloAggregate] = []


class GeospatialFilters(BaseModel):
    tipo_camada: str | None = None
    categoria: str | None = None
    regional: str | None = None
    bairro: str | None = None
    regiao_administrativa: str | None = None
    subprefeitura: str | None = None
    nome: str | None = None


GEOSPATIAL_FILTER_COLUMN_MAP: dict[str, str] = {
    "tipo_camada": "tipo_camada",
    "categoria": "categoria",
    "regional": "regional",
    "bairro": "bairro",
    "regiao_administrativa": "regiao_administrativa",
    "subprefeitura": "subprefeitura",
    "nome": "nome",
}


def geospatial_filters_to_columns(
    filters: GeospatialFilters,
) -> dict[str, object]:
    """Single translation rule: API filter names -> DB columns.

    Comma-separated values become lists (multi-select parity).
    """
    column_filters: dict[str, object] = {}
    for filter_key, filter_value in filters.model_dump(exclude_none=True).items():
        if filter_key not in GEOSPATIAL_FILTER_COLUMN_MAP:
            continue
        column_name = GEOSPATIAL_FILTER_COLUMN_MAP[filter_key]
        if isinstance(filter_value, str) and "," in filter_value:
            filter_value = [
                v.strip() for v in filter_value.split(",") if v.strip()
            ]
        column_filters[column_name] = filter_value
    return column_filters
