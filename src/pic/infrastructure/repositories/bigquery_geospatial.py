from src.api.v1.queries import GEOSPATIAL_LAYERS_QUERY
from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.filters import FilterOption
from src.pic.domain.models.geospatial import GeospatialFilterOptions, GeospatialLayer
from src.pic.infrastructure.geospatial.config import (
    GEOSPATIAL_FILTER_OPTIONS_CONFIG,
)
from src.utils.data_manager import DataManager
from src.utils.log import logger


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
