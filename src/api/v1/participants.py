import traceback
import time
from datetime import datetime
import asyncio
import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional, Union

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Participante,
    PaginatedResponse,
    CommonFilters,
    PaginationParams,
    SortParams,
)
from src.utils.data_manager import DataManager
from src.utils.data_manager_config import DataManagerConfig as config
from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY, MOTIVO_IRREGULARIDADE_QUERY

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Participantes"])

# Configuração de filtros para participantes (definido no endpoint, não no DataManager)
PARTICIPANT_FILTER_COLUMN_MAP = {
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
    # Filtros de array (protocolo_listagem) - usa dot notation para indicar campo do array
    "protocolo_descricao": "protocolo_listagem.id",
    "protocolo_status": "protocolo_listagem.protocolo_status_label",
    "protocolo_secretaria": "protocolo_listagem.secretaria",
}

PARTICIPANT_FILTER_OPTIONS_CONFIG = {
    "subprefeituras": {"column": "subprefeitura"},
    "regioes_administrativas": {"column": "regiao_administrativa"},
    "bairros": {"column": "bairro"},
    "grupos": {"column": "grupo"},
    "cohorts": {"column": "cohort"},
    "status_list": {"column": "status"},
    "situacoes": {"column": "situacao"},
    "cres": {"column": "id_cre", "label_column": "nome_cre"},
    "aps": {
        "column": "id_ap",
        "label_column": "nome_ap",
    },
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
    # Filtros de array (protocolo_listagem) - extrai valores únicos do array
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

# Colunas permitidas para ordenação (EXATAMENTE as mesmas da tabela no frontend)
# Segurança: whitelist evita SQL injection
PARTICIPANT_SORTABLE_COLUMNS = {
    "nome": "nome",
    "cpf": "cpf",
    "grupo": "grupo",
    "bairro": "bairro",
    "idade": "idade",
    "status": "status",
    "total_fracao": "total_protocolos_regular",  # Ordena pelo numerador da fração
    "assistencia_fracao": "assistencia_protocolos_regular",
    "educacao_fracao": "educacao_protocolos_regular",
    "saude_fracao": "saude_protocolos_regular",
    "total_irregular": "total_protocolos_irregular",
    "situacao": "situacao",
}

SENSITIVE_COLUMNS = ["latitude", "longitude"]  # Colunas a ocultar para não-super-admins


@router.get(
    "/participants",
    summary="Listar participantes com filtros, paginação e ordenação",
    response_model=PaginatedResponse[Participante],
)
async def get_participants(
    permissions: CurrentUserPermissions,  # NOVO: Inject user permissions
    filters: CommonFilters = Depends(),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
) -> Any:
    """
    Retorna participantes com suporte a filtros e paginação.

    A resposta inclui:
    - data: Lista paginada de participantes
    - meta: Informações de paginação (página atual, total de páginas, etc.)
    - filters: Opções de filtros dinâmicas baseadas nos dados filtrados atuais

    As opções de filtro são calculadas APÓS aplicar os filtros, mostrando apenas
    as opções disponíveis considerando os filtros já ativos. Isso evita discrepâncias
    entre contadores e resultados reais.
    """
    import time

    endpoint_start = time.perf_counter()
    logger.info("⏱️ [TIMING] Endpoint handler started (after auth/permissions)")

    query = PARTICIPANTS_TABLE_QUERY

    # Log download mode if page_size=-1
    if pagination.page_size == -1:
        logger.warning(
            f"⬇️ DOWNLOAD MODE: Fetching ALL participants (no pagination limit). "
            f"Filters: {len([k for k, v in filters.model_dump(exclude_none=True).items() if v])} active"
        )
    else:
        logger.info(
            f"Fetching participants - Page: {pagination.page}, Size: {pagination.page_size}"
        )

    logger.info(f"Filters: {filters.model_dump(exclude_none=True)}")
    logger.info(f"Sort: {sort.sort_by} {sort.sort_order}")
    logger.info(f"🔄 Bypass Cache: {bypass_cache}")

    try:
        # Converter filtros de API para colunas do DataFrame
        filters_dict = filters.model_dump(exclude_none=True)

        # Extrair search_term se existir
        search_term = filters_dict.pop("search", None)

        column_filters = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in PARTICIPANT_FILTER_COLUMN_MAP:
                column_name = PARTICIPANT_FILTER_COLUMN_MAP[filter_key]
                # Handle pipe-separated values (multi-select from frontend)
                # NOTE: pipe is used instead of comma because some values (e.g. protocolo_descricao) contain commas
                if isinstance(filter_value, str) and "|" in filter_value:
                    filter_value = [
                        v.strip() for v in filter_value.split("|") if v.strip()
                    ]
                column_filters[column_name] = filter_value

        # Validar e mapear coluna de ordenação
        sort_column = None
        sort_descending = False
        if sort.sort_by:
            if sort.sort_by in PARTICIPANT_SORTABLE_COLUMNS:
                sort_column = PARTICIPANT_SORTABLE_COLUMNS[sort.sort_by]
                sort_descending = sort.sort_order == "desc"
            else:
                logger.warning(
                    f"⚠️ Coluna de ordenação não permitida: {sort.sort_by}. "
                    f"Colunas válidas: {list(PARTICIPANT_SORTABLE_COLUMNS.keys())}"
                )

        # Pipeline completo: fetch -> governance -> filter -> search -> sort -> filter_options -> paginate
        # Se bypass_cache=True, força query no BigQuery para garantir dados frescos
        # Dispara as duas queries em paralelo (participantes + protocolo_detalhes)
        results = await asyncio.gather(
            DataManager.fetch_filter_paginate(
                query=query,
                filters_dict=column_filters,
                page=pagination.page,
                page_size=pagination.page_size,
                filter_columns_config=PARTICIPANT_FILTER_OPTIONS_CONFIG,
                search_term=search_term,
                search_columns=(
                    ["nome", "cpf", "id_membro_familia", "id_familia"]
                    if search_term
                    else None
                ),
                user_permissions=permissions,
                bypass_cache=bypass_cache,
                sort_by=sort_column,
                sort_descending=sort_descending,
            ),
            DataManager.get_dataset(
                MOTIVO_IRREGULARIDADE_QUERY,
                bypass_cache=bypass_cache,
            ),
            return_exceptions=True,
        )

        participants_result, motivos_result = results

        if isinstance(participants_result, Exception):
            raise participants_result

        df_data, meta, filter_options = participants_result

        # Dropar colunas sensíveis (latitude/longitude) se não for super admin
        if not permissions.is_super_admin:
            columns_to_drop = [
                col for col in SENSITIVE_COLUMNS if col in df_data.columns
            ]
            if columns_to_drop:
                df_data = df_data.drop(columns_to_drop)
                logger.info(
                    f"🔒 Dropped sensitive columns for non-super-admin: {columns_to_drop}"
                )

        # Converter DataFrame para JSON e retornar resposta
        json_start = time.perf_counter()
        data_json = DataManager.df_to_json(df_data)
        json_time = time.perf_counter() - json_start

        if isinstance(motivos_result, Exception):
            logger.warning(
                f"⚠️ Failed to fetch protocolo_detalhes, proceeding without irregularity reasons: {motivos_result}"
            )
        else:
            df_motivos, _, _ = motivos_result

            cpfs_pagina = [p["cpf"] for p in data_json if p.get("cpf")]
            if cpfs_pagina:
                df_lookup = (
                    df_motivos
                    .select(["cpf", "protocolo_id", "protocolo_motivo"])
                    .filter(pl.col("cpf").is_in(cpfs_pagina))
                )

                lookup = {}
                for row in df_lookup.iter_rows(named=True):
                    lookup[(row["cpf"], row["protocolo_id"])] = row["protocolo_motivo"]

                for participant in data_json:
                    cpf = participant.get("cpf")
                    for protocolo in (participant.get("protocolo_listagem") or []):
                        if protocolo.get("irregular_indicador"):
                            protocolo["protocolo_motivo"] = lookup.get(
                                (cpf, protocolo.get("id")), None
                            )

        response_start = time.perf_counter()
        response = PaginatedResponse(
            data=data_json,
            meta=meta,
            filters=filter_options,
        )
        response_time = time.perf_counter() - response_start

        total_endpoint_time = time.perf_counter() - endpoint_start
        logger.info(
            f"⏱️ [TIMING] Endpoint complete: "
            f"df_to_json={json_time:.3f}s, "
            f"response_build={response_time:.3f}s, "
            f"total_handler={total_endpoint_time:.3f}s"
        )

        return response

    except Exception as e:
        import traceback

        logger.error(f"❌ Error fetching participants: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
