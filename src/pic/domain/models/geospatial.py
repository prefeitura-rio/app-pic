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
