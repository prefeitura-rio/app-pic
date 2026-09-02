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
