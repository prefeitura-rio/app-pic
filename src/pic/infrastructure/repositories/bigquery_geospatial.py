from src.api.v1.queries import GEOSPATIAL_LAYERS_QUERY
from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import GeospatialFilterOptions, GeospatialLayer
from src.pic.infrastructure.geospatial.config import (
    GEOSPATIAL_FILTER_OPTIONS_CONFIG,
)
from src.utils.data_manager import DataManager
from src.utils.log import logger

# Column that each external field name maps to in the BigQuery table
_FIELD_COLUMN: dict[str, str] = {
    "tipos_camada": "tipo_camada",
    "categorias": "categoria",
    "regionais": "regional",
    "bairros": "bairro",
    "regioes_administrativas": "regiao_administrativa",
    "subprefeituras": "subprefeitura",
    "nomes": "nome",
}


def _to_filter_options(items: list) -> list[FilterOption]:
    return [
        FilterOption(id=item.id, label=item.label)
        if hasattr(item, "id") and hasattr(item, "label")
        else FilterOption(**item)
        for item in (items or [])
    ]


def _convert_smart_filters_to_geospatial(filter_options) -> GeospatialFilterOptions:
    if not filter_options:
        return GeospatialFilterOptions()
    return GeospatialFilterOptions(
        tipos_camada=_to_filter_options(getattr(filter_options, "tipos_camada", [])),
        categorias=_to_filter_options(getattr(filter_options, "categorias", [])),
        regionais=_to_filter_options(getattr(filter_options, "regionais", [])),
        bairros=_to_filter_options(getattr(filter_options, "bairros", [])),
        regioes_administrativas=_to_filter_options(getattr(filter_options, "regioes_administrativas", [])),
        subprefeituras=_to_filter_options(getattr(filter_options, "subprefeituras", [])),
        nomes=_to_filter_options(getattr(filter_options, "nomes", [])),
    )


class BigQueryGeospatialRepository(IGeospatialRepository):
    async def fetch_layers(
        self,
        column_filters: dict[str, object],
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[GeospatialLayer]:
        df_data, meta, filter_options = await DataManager.fetch_filter_paginate(
            query=GEOSPATIAL_LAYERS_QUERY,
            filters_dict=column_filters,
            page=1,
            page_size=-1,
            filter_columns_config=GEOSPATIAL_FILTER_OPTIONS_CONFIG,
            user_permissions=None,
            bypass_cache=bypass_cache,
        )

        data_json = DataManager.df_to_json(df_data)
        layers = [GeospatialLayer(**item) for item in data_json]

        logger.info(
            f"Geospatial layers fetched: {len(layers)} layers, "
            f"filters_active={len(column_filters)}"
        )

        return layers

    async def get_filter_vocabulary(
        self,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> GeospatialFilterOptions:
        df, _, _ = await DataManager.get_dataset(
            query=GEOSPATIAL_LAYERS_QUERY,
            bypass_cache=bypass_cache,
        )

        if df.is_empty():
            return GeospatialFilterOptions()

        smart_filters = DataManager.calculate_filter_options_fast(
            df_original=df,
            filter_columns_config=GEOSPATIAL_FILTER_OPTIONS_CONFIG,
            active_filters={},
            df_already_filtered=df,
        )

        return _convert_smart_filters_to_geospatial(smart_filters)

    async def get_filter_options(
        self,
        field: str,
        column_filters: dict[str, object] | None = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> list[FilterOption]:
        """Lazy per-field vocabulary (BigQuery fallback — fetches full dataset).

        NOTE: This implementation fetches the entire BigQuery dataset to derive
        distinct values for one field.  It is kept only for backward compatibility;
        the PostgREST implementation is far more efficient.
        """
        if field not in _FIELD_COLUMN:
            logger.warning(f"[geospatial/bq] unknown filter field: {field!r}")
            return []

        col = _FIELD_COLUMN[field]
        df, _, _ = await DataManager.get_dataset(
            query=GEOSPATIAL_LAYERS_QUERY,
            bypass_cache=bypass_cache,
        )
        if df.is_empty() or col not in df.columns:
            return []

        distinct = (
            df.filter(df[col].is_not_null())
            .select(col)
            .unique()
            .sort(col)[col]
            .to_list()
        )
        return [FilterOption(id=str(v), label=str(v)) for v in distinct]
