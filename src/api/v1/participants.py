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
    "raca": "raca",
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
    "racas": {"column": "raca"},
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
        logger.error(f"❌ Error fetching participants: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Mapeamento de colunas do DataFrame para os cabeçalhos CSV esperados pelo
# frontend (espelha exatamente a lógica de jsonToCSVChunk em DashboardClient)
# ---------------------------------------------------------------------------
_PARTICIPANT_CSV_COLUMNS = [
    "nome",
    "cpf",
    "nis",
    "data_nascimento",
    "idade",
    "endereco",           # → endereco_smas_endereco
    "complemento",        # → endereco_smas_complemento
    "bairro",             # → endereco_smas_bairro
    "endereco_sms",       # struct: .endereco / .complemento / .bairro (tratado abaixo)
    "telefone_1_ddd",
    "telefone_1_numero",
    "telefone_2_ddd",
    "telefone_2_numero",
    "subprefeitura",
    "regiao_administrativa",
    "grupo",
    "cohort",
    "has_bolsa_familia",
    "has_cartao_pic",
    "status",
    "status_inativo_motivo",
    "situacao",
    "total_protocolos",
    "total_protocolos_regular",
    "total_protocolos_irregular",
    "total_protocolos_atencao",
    "total_fracao",
    "assistencia_protocolos_total",
    "assistencia_protocolos_regular",
    "assistencia_protocolos_irregular",
    "assistencia_protocolos_atencao",
    "assistencia_fracao",
    "educacao_protocolos_total",
    "educacao_protocolos_regular",
    "educacao_protocolos_irregular",
    "educacao_protocolos_atencao",
    "educacao_fracao",
    "saude_protocolos_total",
    "saude_protocolos_regular",
    "saude_protocolos_irregular",
    "saude_protocolos_atencao",
    "saude_fracao",
    "id_cras",
    "nome_cras",
    "source_cras",
    "id_cas",
    "nome_cas",
    "id_escola",
    "nome_escola",
    "source_escola",
    "id_cre",
    "nome_cre",
    "id_ap",
    "nome_ap",
    "id_clinica_familia",
    "nome_clinica_familia",
    "source_clinica_familia",
    "has_cobertura_clinica_familia",
    "id_equipe_familia",
    "nome_equipe_familia",
    "source_equipe_familia",
    "has_cobertura_equipe_familia",
    "equipe_familia",
]

_CSV_HEADERS = [
    "nome",
    "cpf",
    "nis",
    "data_nascimento",
    "idade",
    "endereco_smas_endereco",
    "endereco_smas_complemento",
    "endereco_smas_bairro",
    "endereco_sms_endereco",
    "endereco_sms_complemento",
    "endereco_sms_bairro",
    "telefone_1_ddd",
    "telefone_1_numero",
    "telefone_2_ddd",
    "telefone_2_numero",
    "subprefeitura",
    "regiao_administrativa",
    "grupo",
    "cohort",
    "has_bolsa_familia",
    "has_cartao_pic",
    "status",
    "status_inativo_motivo",
    "situacao",
    "total_protocolos",
    "total_protocolos_regular",
    "total_protocolos_irregular",
    "total_protocolos_atencao",
    "total_fracao",
    "assistencia_protocolos_total",
    "assistencia_protocolos_regular",
    "assistencia_protocolos_irregular",
    "assistencia_protocolos_atencao",
    "assistencia_fracao",
    "educacao_protocolos_total",
    "educacao_protocolos_regular",
    "educacao_protocolos_irregular",
    "educacao_protocolos_atencao",
    "educacao_fracao",
    "saude_protocolos_total",
    "saude_protocolos_regular",
    "saude_protocolos_irregular",
    "saude_protocolos_atencao",
    "saude_fracao",
    "id_cras",
    "nome_cras",
    "source_cras",
    "id_cas",
    "nome_cas",
    "id_escola",
    "nome_escola",
    "source_escola",
    "id_cre",
    "nome_cre",
    "id_ap",
    "nome_ap",
    "id_clinica_familia",
    "nome_clinica_familia",
    "source_clinica_familia",
    "has_cobertura_clinica_familia",
    "id_equipe_familia",
    "nome_equipe_familia",
    "source_equipe_familia",
    "has_cobertura_equipe_familia",
    "equipe_familia",
    "protocolo_id",
    "protocolo_secretaria",
    "protocolo_descricao",
    "protocolo_status",
    "protocolo_irregular_indicador",
    "protocolo_status_label",
]

_DELIMITER = ";"
_CHUNK_ROWS = 5000  # linhas por chunk gerado


def _escape_csv(value: object) -> str:
    """Escapa um valor para CSV com ponto-e-vírgula como delimitador."""
    if value is None:
        return '""'
    s = str(value).replace("\r", "").replace("\n", " ").replace('"', '""')
    return f'"{s}"'


def _df_to_csv_stream(df: pl.DataFrame):
    """
    Gera o CSV como um iterador de bytes, linha por linha, usando
    polars para iterar com iter_rows() sem acumular tudo em memória.

    Explode a coluna `protocolo_listagem` (lista de structs) da mesma
    forma que o frontend fazia em JavaScript.
    """
    DELIM = _DELIMITER

    # BOM UTF-8 + cabeçalho
    header_line = DELIM.join(_CSV_HEADERS)
    yield ("\uFEFF" + header_line + "\n").encode("utf-8")

    # Verificar quais colunas existem no DataFrame
    existing_cols = set(df.columns)

    rows_buffer: list[str] = []

    for row in df.iter_rows(named=True):
        # Resolver campos especiais de endereço SMS (struct aninhado)
        endereco_sms = row.get("endereco_sms") or {}
        if isinstance(endereco_sms, dict):
            sms_end = endereco_sms.get("endereco")
            sms_comp = endereco_sms.get("complemento")
            sms_bairro = endereco_sms.get("bairro")
        else:
            sms_end = sms_comp = sms_bairro = None

        # Protocolos: lista de dicts
        protocolos = row.get("protocolo_listagem") or []

        def _build_participant_cells() -> list[str]:
            return [
                _escape_csv(row.get("nome")),
                _escape_csv(row.get("cpf")),
                _escape_csv(row.get("nis")),
                _escape_csv(row.get("data_nascimento")),
                _escape_csv(row.get("idade")),
                _escape_csv(row.get("endereco")),
                _escape_csv(row.get("complemento")),
                _escape_csv(row.get("bairro")),
                _escape_csv(sms_end),
                _escape_csv(sms_comp),
                _escape_csv(sms_bairro),
                _escape_csv(row.get("telefone_1_ddd")),
                _escape_csv(row.get("telefone_1_numero")),
                _escape_csv(row.get("telefone_2_ddd")),
                _escape_csv(row.get("telefone_2_numero")),
                _escape_csv(row.get("subprefeitura")),
                _escape_csv(row.get("regiao_administrativa")),
                _escape_csv(row.get("grupo")),
                _escape_csv(row.get("cohort")),
                _escape_csv(row.get("has_bolsa_familia")),
                _escape_csv(row.get("has_cartao_pic")),
                _escape_csv(row.get("status")),
                _escape_csv(row.get("status_inativo_motivo")),
                _escape_csv(row.get("situacao")),
                _escape_csv(row.get("total_protocolos")),
                _escape_csv(row.get("total_protocolos_regular")),
                _escape_csv(row.get("total_protocolos_irregular")),
                _escape_csv(row.get("total_protocolos_atencao")),
                _escape_csv(row.get("total_fracao")),
                _escape_csv(row.get("assistencia_protocolos_total")),
                _escape_csv(row.get("assistencia_protocolos_regular")),
                _escape_csv(row.get("assistencia_protocolos_irregular")),
                _escape_csv(row.get("assistencia_protocolos_atencao")),
                _escape_csv(row.get("assistencia_fracao")),
                _escape_csv(row.get("educacao_protocolos_total")),
                _escape_csv(row.get("educacao_protocolos_regular")),
                _escape_csv(row.get("educacao_protocolos_irregular")),
                _escape_csv(row.get("educacao_protocolos_atencao")),
                _escape_csv(row.get("educacao_fracao")),
                _escape_csv(row.get("saude_protocolos_total")),
                _escape_csv(row.get("saude_protocolos_regular")),
                _escape_csv(row.get("saude_protocolos_irregular")),
                _escape_csv(row.get("saude_protocolos_atencao")),
                _escape_csv(row.get("saude_fracao")),
                _escape_csv(row.get("id_cras")),
                _escape_csv(row.get("nome_cras")),
                _escape_csv(row.get("source_cras")),
                _escape_csv(row.get("id_cas")),
                _escape_csv(row.get("nome_cas")),
                _escape_csv(row.get("id_escola")),
                _escape_csv(row.get("nome_escola")),
                _escape_csv(row.get("source_escola")),
                _escape_csv(row.get("id_cre")),
                _escape_csv(row.get("nome_cre")),
                _escape_csv(row.get("id_ap")),
                _escape_csv(row.get("nome_ap")),
                _escape_csv(row.get("id_clinica_familia")),
                _escape_csv(row.get("nome_clinica_familia")),
                _escape_csv(row.get("source_clinica_familia")),
                _escape_csv(row.get("has_cobertura_clinica_familia")),
                _escape_csv(row.get("id_equipe_familia")),
                _escape_csv(row.get("nome_equipe_familia")),
                _escape_csv(row.get("source_equipe_familia")),
                _escape_csv(row.get("has_cobertura_equipe_familia")),
                _escape_csv(row.get("equipe_familia")),
            ]

        participant_cells = _build_participant_cells()

        if protocolos:
            for prot in protocolos:
                if not isinstance(prot, dict):
                    continue
                protocol_cells = [
                    _escape_csv(prot.get("id")),
                    _escape_csv(prot.get("secretaria")),
                    _escape_csv(prot.get("descricao")),
                    _escape_csv(prot.get("status")),
                    _escape_csv(prot.get("irregular_indicador")),
                    _escape_csv(prot.get("protocolo_status_label")),
                ]
                rows_buffer.append(DELIM.join(participant_cells + protocol_cells))
        else:
            empty_protocol = ['""'] * 6
            rows_buffer.append(DELIM.join(participant_cells + empty_protocol))

        if len(rows_buffer) >= _CHUNK_ROWS:
            yield ("\n".join(rows_buffer) + "\n").encode("utf-8")
            rows_buffer = []

    if rows_buffer:
        yield ("\n".join(rows_buffer) + "\n").encode("utf-8")


@router.get(
    "/participants/export",
    summary="Exportar participantes filtrados como CSV via streaming",
    response_class=StreamingResponse,
)
async def export_participants_csv(
    permissions: CurrentUserPermissions,
    filters: CommonFilters = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
) -> StreamingResponse:
    """
    Exporta todos os participantes filtrados diretamente como CSV via streaming.

    - Não usa paginação: retorna todos os dados de uma vez.
    - Gera o CSV server-side com Polars (muito mais rápido que JS).
    - Responde com Transfer-Encoding: chunked — o browser inicia o download
      imediatamente, sem aguardar todo o dataset ser carregado em memória.
    - O proxy Next.js deve fazer pipe deste stream sem bufferizar.
    """
    export_start = time.perf_counter()
    logger.info("⬇️ [EXPORT] CSV export iniciado")

    try:
        filters_dict = filters.model_dump(exclude_none=True)
        search_term = filters_dict.pop("search", None)

        column_filters: dict = {}
        for filter_key, filter_value in filters_dict.items():
            if filter_key in PARTICIPANT_FILTER_COLUMN_MAP:
                column_name = PARTICIPANT_FILTER_COLUMN_MAP[filter_key]
                if isinstance(filter_value, str) and "|" in filter_value:
                    filter_value = [v.strip() for v in filter_value.split("|") if v.strip()]
                column_filters[column_name] = filter_value

        sort_column = None
        sort_descending = False
        if sort.sort_by:
            if sort.sort_by in PARTICIPANT_SORTABLE_COLUMNS:
                sort_column = PARTICIPANT_SORTABLE_COLUMNS[sort.sort_by]
                sort_descending = sort.sort_order == "desc"

        # Busca todos os dados sem paginação (page_size=-1)
        df_data, meta, _ = await DataManager.fetch_filter_paginate(
            query=PARTICIPANTS_TABLE_QUERY,
            filters_dict=column_filters,
            page=1,
            page_size=-1,
            filter_columns_config={},   # Não precisamos de filter_options no export
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
        )

        # Remover colunas sensíveis para não-super-admins
        if not permissions.is_super_admin:
            cols_to_drop = [c for c in SENSITIVE_COLUMNS if c in df_data.columns]
            if cols_to_drop:
                df_data = df_data.drop(cols_to_drop)

        total_rows = len(df_data)
        fetch_time = time.perf_counter() - export_start
        logger.info(
            f"⬇️ [EXPORT] Dataset pronto: {total_rows} participantes em {fetch_time:.2f}s — iniciando stream CSV"
        )

        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"participantes_{timestamp}.csv"

        return StreamingResponse(
            _df_to_csv_stream(df_data),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    except Exception as e:
        logger.error(f"❌ [EXPORT] Erro ao exportar CSV: {e}")
        logger.error(f"❌ [EXPORT] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
