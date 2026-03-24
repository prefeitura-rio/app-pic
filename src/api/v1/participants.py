from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Union
import polars as pl

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Participante,
    ProtocoloDetalhes,
    PaginatedResponse,
    CommonFilters,
    PaginationParams,
    SortParams,
    SmartFilterOptions,
)
from src.utils.data_manager import DataManager
from src.utils.data_manager_config import DataManagerConfig as config
from src.api.v1.queries import PARTICIPANTS_TABLE_QUERY

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
    "safra": "cohort",
    "grupo": "grupo",
    "status": "status",
    "situacao": "situacao",
    # Filtros de array (protocolo_listagem) - usa dot notation para indicar campo do array
    "protocolo_descricao": "protocolo_listagem.descricao",
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
    # Filtros de array (protocolo_listagem) - extrai valores únicos do array
    "protocolo_descricoes": {
        "column": "protocolo_listagem",
        "array_field": "descricao",
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
    "situacao": "situacao",
}


def _filter_filter_options_by_secretaria(
    filter_options: SmartFilterOptions,
    secretaria_acesso: Optional[str],
    is_super_admin: bool
) -> SmartFilterOptions:
    """
    Filter equipment and protocol options based on secretaria_acesso.

    SME: keep only CRE, Escolas, and SME protocols
    SMS: keep only AP, Clínicas, and SMS protocols
    SMAS: keep only CAS, CRAS, and SMAS protocols
    TODOS/super_admin: keep all
    NULL: remove all equipment and protocols

    Always keep: bairros, subprefeituras, regioes_administrativas, grupos, cohorts, status_list, situacoes

    NOTE: User's equipment access is already filtered by governance filters before filter_options are calculated.
    """
    # Super admin or TODOS: no filtering
    if is_super_admin or secretaria_acesso == "TODOS":
        return filter_options

    # NULL: remove all equipment and protocols
    if not secretaria_acesso:
        filter_options.cres = []
        filter_options.aps = []
        filter_options.cas_list = []
        filter_options.cras = []
        filter_options.escolas = []
        filter_options.clinicas = []
        filter_options.protocolo_descricoes = []
        filter_options.protocolo_status_list = []
        logger.info("🔒 Filter options: secretaria_acesso=NULL, removed all equipment and protocols")
        return filter_options

    # Map secretaria to allowed equipment and protocol prefix
    equipment_map = {
        "SME": {"keep": ["cres", "escolas"], "remove": ["aps", "cas_list", "cras", "clinicas"]},
        "SMS": {"keep": ["aps", "clinicas"], "remove": ["cres", "escolas", "cas_list", "cras"]},
        "SMAS": {"keep": ["cas_list", "cras"], "remove": ["cres", "escolas", "aps", "clinicas"]},
    }

    equipment_config = equipment_map.get(secretaria_acesso)
    if not equipment_config:
        # Unknown secretaria: remove everything
        filter_options.cres = []
        filter_options.aps = []
        filter_options.cas_list = []
        filter_options.cras = []
        filter_options.escolas = []
        filter_options.clinicas = []
        filter_options.protocolo_descricoes = []
        filter_options.protocolo_status_list = []
        logger.info(f"🔒 Filter options: unknown secretaria={secretaria_acesso}, removed all equipment")
        return filter_options

    # Remove equipment types not allowed for this secretaria
    for field in equipment_config["remove"]:
        setattr(filter_options, field, [])

    # Filter protocols by secretaria prefix (sme_, sms_, smas_)
    protocol_prefix = secretaria_acesso.lower() + "_"
    filter_options.protocolo_descricoes = [
        p for p in filter_options.protocolo_descricoes
        if p.id.startswith(protocol_prefix)
    ]

    # Keep protocol_status_list as is (it's generic: regular, irregular, attention)

    logger.info(
        f"🔒 Filter options filtered for secretaria={secretaria_acesso}: "
        f"kept {equipment_config['keep']}, removed {equipment_config['remove']}, "
        f"kept {len(filter_options.protocolo_descricoes)} protocols with prefix '{protocol_prefix}'"
    )

    return filter_options


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
                # Handle comma-separated values (multi-select from frontend)
                if isinstance(filter_value, str) and "," in filter_value:
                    filter_value = [
                        v.strip() for v in filter_value.split(",") if v.strip()
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
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=pagination.page,
            page_size=pagination.page_size,
            filter_columns_config=PARTICIPANT_FILTER_OPTIONS_CONFIG,
            search_term=search_term,
            search_columns=["nome", "cpf", "id_membro_familia", "id_familia"] if search_term else None,
            user_permissions=permissions,  # NOVO: Pass user permissions
            bypass_cache=bypass_cache,  # IMPORTANTE: Passa bypass_cache para forçar refresh
            sort_by=sort_column,  # NOVO: Coluna para ordenação
            sort_descending=sort_descending,  # NOVO: Direção da ordenação
        )

        # Filter filter_options by secretaria_acesso (equipment access already filtered by governance)
        filter_options = _filter_filter_options_by_secretaria(
            filter_options,
            secretaria_acesso=permissions.secretaria_acesso,
            is_super_admin=permissions.is_super_admin
        )

        # Converter DataFrame para JSON e retornar resposta
        # NOTE: Secretaria filtering now done in apply_governance_filters (data_manager.py)
        json_start = time.perf_counter()
        data_json = DataManager.df_to_json(df_data)
        json_time = time.perf_counter() - json_start

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
        logger.error(f"❌ Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))
