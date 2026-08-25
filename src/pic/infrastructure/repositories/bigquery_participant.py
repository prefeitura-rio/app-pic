from typing import Any

import polars as pl

from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY
from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.domain.models.filters import FilterCriteria, FilterVocabulary
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

FILTER_OPTIONS_CONFIG = {
    "subprefeituras": {"column": "subprefeitura"},
    "regioes_administrativas": {"column": "regiao_administrativa"},
    "bairros": {"column": "bairro"},
    "grupos": {"column": "grupo"},
    "cohorts": {"column": "cohort"},
    "status_list": {"column": "status"},
    "situacoes": {"column": "situacao"},
    "racas": {"column": "raca"},
    "cres": {"column": "id_cre", "label_column": "nome_cre"},
    "aps": {"column": "id_ap", "label_column": "nome_ap"},
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {
        "column": "id_clinica_familia",
        "label_column": "nome_clinica_familia",
    },
    "equipes_familia": {
        "column": "id_equipe_familia",
        "label_column": "nome_equipe_familia",
    },
    "protocolo_descricoes": {
        "column": "protocolo_listagem",
        "array_field": "id",
        "label_field": "descricao",
        "type": "array_extract",
    },
    "protocolo_status_list": {
        "column": "protocolo_listagem",
        "array_field": "protocolo_status_label",
        "type": "array_extract",
    },
}


class BigQueryParticipantRepository(IParticipantRepository):
    """Vocabulary + CSV export reads (list/detail moved to PostgREST)."""

    async def get_filter_vocabulary(
        self,
        filters: FilterCriteria,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> FilterVocabulary:
        filters_dict = filters.model_dump(exclude_none=True)

        search_term = filters_dict.pop("search", None)

        column_filters: dict[str, Any] = {}
        for key, value in filters_dict.items():
            if key in BQ_FILTER_COLUMN_MAP:
                column_name = BQ_FILTER_COLUMN_MAP[key]
                if isinstance(value, str) and "|" in value:
                    value = [v.strip() for v in value.split("|") if v.strip()]
                column_filters[column_name] = value

        df, _, precomputed = await DataManager.get_dataset(
            query=PARTICIPANTS_TABLE_QUERY,
            bypass_cache=bypass_cache,
            filter_columns_config=FILTER_OPTIONS_CONFIG,
        )

        use_precomputed = (
            precomputed
            and not column_filters
            and not search_term
            and permissions
            and permissions.is_super_admin
        )
        if use_precomputed:
            return FilterVocabulary.model_validate(precomputed)

        if permissions:
            df = DataManager.apply_governance_filters(df, permissions)

        if df.is_empty():
            return FilterVocabulary()

        df_after_governance = df

        if column_filters:
            df = DataManager.apply_filters(df, column_filters)

        if search_term:
            df = DataManager.apply_search(df, search_term, SEARCH_COLUMNS)

        if df.is_empty():
            return FilterVocabulary()

        smart_filters = DataManager.calculate_filter_options_fast(
            df_original=df_after_governance,
            filter_columns_config=FILTER_OPTIONS_CONFIG,
            active_filters=column_filters,
            df_already_filtered=df,
        )

        return FilterVocabulary.model_validate(smart_filters.model_dump())

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
