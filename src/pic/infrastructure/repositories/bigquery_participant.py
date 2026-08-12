import json
from typing import Any

import polars as pl

from src.api.v1.queries import (
    MOTIVO_IRREGULARIDADE_QUERY,
    PARTICIPANTS_TABLE_QUERY,
)
from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.domain.models.filters import FilterCriteria, FilterVocabulary
from src.pic.domain.models.pagination import (
    PaginationMeta,
    PaginationParams,
    SortParams,
)
from src.pic.domain.models.participante import Participante, ParticipanteListItem
from src.pic.domain.models.protocolo import ProtocoloMotivo
from src.utils.data_manager import DataManager
from src.utils.log import logger

# --- Constants (imported from V1 for wrapping; extracted when V1 deprecated) ---

FILTER_COLUMN_MAP = {
    "subprefeitura": "subprefeitura",
    "regiao_administrativa": "regiao_administrativa",
    "bairro": "bairro",
    "cre": "id_cre",
    "ap": "id_ap",
    "cas": "id_cas",
    "cras": "id_cras",
    "escola": "id_escola",
    "clinica": "id_clinica_familia",
    "equipe_familia": "id_equipe_familia",
    "safra": "cohort",
    "grupo": "grupo",
    "status": "status",
    "situacao": "situacao",
    "has_bolsa_familia": "has_bolsa_familia",
    "raca": "raca",
    "protocolo_descricao": "protocolo_listagem.id",
    "protocolo_status": "protocolo_listagem.protocolo_status_label",
    "protocolo_secretaria": "protocolo_listagem.secretaria",
}

SORTABLE_COLUMNS = {
    "nome": "nome",
    "cpf": "cpf",
    "grupo": "grupo",
    "bairro": "bairro",
    "idade": "idade",
    "status": "status",
    "total_fracao": "total_protocolos_regular",
    "total_irregular": "total_protocolos_irregular",
    "assistencia_fracao": "assistencia_protocolos_regular",
    "educacao_fracao": "educacao_protocolos_regular",
    "saude_fracao": "saude_protocolos_regular",
    "situacao": "situacao",
}

SEARCH_COLUMNS = ["nome", "cpf", "id_membro_familia", "id_familia"]

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
    "clinicas": {"column": "id_clinica_familia", "label_column": "nome_clinica_familia"},
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
    async def find_paginated(
        self,
        filters: FilterCriteria,
        pagination: PaginationParams,
        sort: SortParams,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> tuple[list[ParticipanteListItem], PaginationMeta]:
        filters_dict = filters.model_dump(exclude_none=True)

        search_term = filters_dict.pop("search", None)

        column_filters: dict[str, Any] = {}
        for key, value in filters_dict.items():
            if key in FILTER_COLUMN_MAP:
                column_name = FILTER_COLUMN_MAP[key]
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
            page=pagination.page,
            page_size=pagination.page_size,
            search_term=search_term,
            search_columns=SEARCH_COLUMNS if search_term else None,
            user_permissions=permissions,
            bypass_cache=bypass_cache,
            sort_by=sort_column,
            sort_descending=sort_descending,
        )

        LIST_ITEM_COLUMNS = [
            "id_familia",
            "id_membro_familia",
            "nome",
            "cpf",
            "grupo",
            "bairro",
            "idade",
            "status",
            "situacao",
            "total_fracao",
            "assistencia_fracao",
            "educacao_fracao",
            "saude_fracao",
            "total_protocolos_irregular",
            "raca",
        ]

        data: list[ParticipanteListItem] = []
        if not df.is_empty():
            for row in df.to_dicts():
                item = ParticipanteListItem(
                    **{col: row.get(col) for col in LIST_ITEM_COLUMNS}
                )
                data.append(item)

        v2_meta = PaginationMeta(
            page=meta.page,
            page_size=meta.page_size,
            total_rows=meta.total_rows,
            total_pages=meta.total_pages,
            cache_hit=meta.cache_hit,
            profiling=meta.profiling,
            can_view_dashboard=meta.can_view_dashboard,
        )

        return data, v2_meta

    async def find_by_membro_familia(
        self,
        id_membro_familia: str,
        permissions: Any = None,
        bypass_cache: bool = False,
    ) -> Participante | None:
        import asyncio

        participants_result, motivos_result = await asyncio.gather(
            DataManager.fetch_filter_paginate(
                query=PARTICIPANTS_TABLE_QUERY,
                filters_dict={"id_membro_familia": id_membro_familia},
                page=1,
                page_size=1,
                user_permissions=permissions,
                bypass_cache=bypass_cache,
            ),
            DataManager.get_dataset(
                MOTIVO_IRREGULARIDADE_QUERY,
                bypass_cache=bypass_cache,
            ),
            return_exceptions=True,
        )

        if isinstance(participants_result, Exception):
            raise participants_result

        df, _, _ = participants_result

        if df.is_empty():
            return None

        row = df.to_dicts()[0]
        participante = Participante(**row)

        if not isinstance(motivos_result, Exception):
            motivos_df, _, _ = motivos_result
            cpf = participante.cpf
            if cpf and not motivos_df.is_empty():
                df_lookup = motivos_df.filter(pl.col("cpf") == cpf)
                lookup: dict[str, str] = {}
                for r in df_lookup.iter_rows(named=True):
                    lookup[r["protocolo_id"]] = r["protocolo_motivo"]

                for protocolo in participante.protocolo_listagem or []:
                    if protocolo.irregular_indicador and protocolo.id:
                        motivo_raw = lookup.get(protocolo.id)
                        if motivo_raw:
                            data = (
                                json.loads(motivo_raw)
                                if isinstance(motivo_raw, str)
                                else motivo_raw
                            )
                            protocolo.protocolo_motivo = ProtocoloMotivo.model_validate(data)
        else:
            logger.warning(
                f"Failed to fetch protocolo_detalhes, proceeding without irregularity reasons: {motivos_result}"
            )

        return participante

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
            if key in FILTER_COLUMN_MAP:
                column_name = FILTER_COLUMN_MAP[key]
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
            if key in FILTER_COLUMN_MAP:
                column_name = FILTER_COLUMN_MAP[key]
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

        logger.info(f"Export dataset: {len(df)} rows")
        return df
