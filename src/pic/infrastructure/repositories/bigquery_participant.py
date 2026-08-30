from typing import Any

import polars as pl

from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY
from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    FILTER_COLUMN_MAP,
    PROTOCOLO_FILTER_FIELDS,
    SEARCH_COLUMNS,
    SORTABLE_COLUMNS,
)
from src.utils.data_manager import DataManager
from src.utils.log import logger

# Request filter key -> BigQuery column. Protocolo filters target a field
# inside the `protocolo_listagem` array of structs.
BQ_FILTER_COLUMN_MAP = {
    **FILTER_COLUMN_MAP,
    **{
        key: f"protocolo_listagem.{field}"
        for key, field in PROTOCOLO_FILTER_FIELDS.items()
    },
}


class BigQueryParticipantRepository(IParticipantRepository):
    """CSV export reads (list/detail/vocabulary moved to PostgREST)."""

    async def export_dataframe(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> pl.DataFrame:
        filters_dict = filters.model_dump(exclude_none=True)

        search_term = filters_dict.pop("search", None)

        column_filters: dict[str, Any] = {}
        for key, value in filters_dict.items():
            if key in BQ_FILTER_COLUMN_MAP:
                column_name = BQ_FILTER_COLUMN_MAP[key]
                if isinstance(value, str) and "|" in value:
                    value = [v.strip() for v in value.split("|") if v.strip()]
                column_filters[column_name] = value

        sort_column = None
        sort_descending = False
        if sort.sort_by and sort.sort_by in SORTABLE_COLUMNS:
            sort_column = SORTABLE_COLUMNS[sort.sort_by]
            sort_descending = sort.sort_order == "desc"

        df, meta, _ = await DataManager.fetch_filter_paginate(
            query=PARTICIPANTS_TABLE_QUERY,
            filters_dict=column_filters,
            page=1,
            page_size=-1,
            filter_columns_config={},
            search_term=search_term,
            search_columns=SEARCH_COLUMNS if search_term else None,
            user_permissions=permissions,
            bypass_cache=bypass_cache,
            sort_by=sort_column,
            sort_descending=sort_descending,
        )

        logger.info(f"Export dataset: {len(df)} rows (meta: {meta})")
        return df
