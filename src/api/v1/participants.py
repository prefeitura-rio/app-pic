import asyncio
import io
import traceback
import time
from datetime import datetime
from typing import AsyncIterator, Dict, Any, List, Optional, Union

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.core.security.jwt import verify_jwt, CurrentUserPermissions
from src.utils.log import logger
from src.api.v1.schemas import (
    Participante,
    ProtocoloDetalhes,
    PaginatedResponse,
    CommonFilters,
    PaginationParams,
    SortParams,
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
    "situacao": "situacao",
}

SENSITIVE_COLUMNS = ["latitude", "longitude"]  # Colunas a ocultar para não-super-admins

# Colunas para exportação CSV na mesma ordem do frontend
CSV_COLUMN_ORDER = [
    'cpf', 'id_membro_familia', 'id_familia', 'nome', 'sexo', 'nascimento_data', 'idade',
    'endereco_smas_endereco', 'endereco_smas_complemento', 'endereco_smas_bairro',
    'endereco_sms_endereco', 'endereco_sms_complemento', 'endereco_sms_bairro',
    'telefone_1_ddd', 'telefone_1_numero', 'telefone_2_ddd', 'telefone_2_numero',
    'subprefeitura', 'regiao_administrativa',
    'grupo', 'cohort', 'has_bolsa_familia', 'has_cartao_pic', 'status', 'status_inativo_motivo', 'situacao',
    'total_protocolos', 'total_protocolos_regular', 'total_protocolos_irregular', 'total_protocolos_atencao', 'total_fracao',
    'assistencia_protocolos_total', 'assistencia_protocolos_regular', 'assistencia_protocolos_irregular', 'assistencia_protocolos_atencao', 'assistencia_fracao',
    'educacao_protocolos_total', 'educacao_protocolos_regular', 'educacao_protocolos_irregular', 'educacao_protocolos_atencao', 'educacao_fracao',
    'saude_protocolos_total', 'saude_protocolos_regular', 'saude_protocolos_irregular', 'saude_protocolos_atencao', 'saude_fracao',
    'id_cras', 'nome_cras', 'source_cras', 'id_cas', 'nome_cas',
    'id_escola', 'nome_escola', 'source_escola', 'id_cre', 'nome_cre',
    'id_ap', 'nome_ap', 'id_clinica_familia', 'nome_clinica_familia', 'source_clinica_familia',
    'has_cobertura_clinica_familia', 'id_equipe_familia', 'nome_equipe_familia', 'source_equipe_familia',
    'has_cobertura_equipe_familia', 'equipe_familia',
    'protocolo_id', 'protocolo_secretaria', 'protocolo_descricao', 'protocolo_status',
    'protocolo_irregular_indicador', 'protocolo_status_label',
]


PROTOCOL_STRUCT_FIELDS = {
    'protocolo_id': 'id',
    'protocolo_secretaria': 'secretaria',
    'protocolo_descricao': 'descricao',
    'protocolo_status': 'status',
    'protocolo_irregular_indicador': 'irregular_indicador',
    'protocolo_status_label': 'protocolo_status_label',
}


SMS_STRUCT_SCHEMA = pl.Struct([
    pl.Field('endereco', pl.Utf8),
    pl.Field('complemento', pl.Utf8),
    pl.Field('bairro', pl.Utf8),
    pl.Field('regiao_administrativa', pl.Utf8),
    pl.Field('subprefeitura', pl.Utf8),
    pl.Field('longitude', pl.Float64),
    pl.Field('latitude', pl.Float64),
])

SMS_TARGET_FIELDS = {'endereco', 'complemento', 'bairro'}


def _flatten_for_csv(df: pl.DataFrame) -> pl.DataFrame:
    cols = set(df.columns)

    # 1. endereco_smas_* = alias dos campos planos existentes
    if {'endereco', 'complemento', 'bairro'}.issubset(cols):
        df = df.with_columns(
            pl.col('endereco').alias('endereco_smas_endereco'),
            pl.col('complemento').alias('endereco_smas_complemento'),
            pl.col('bairro').alias('endereco_smas_bairro'),
        )

    # 2. endereco_sms_* = extrair do struct — seguro contra campos ausentes
    if 'endereco_sms' in cols:
        dtype = df.schema['endereco_sms']
        sms = pl.col('endereco_sms')

        if isinstance(dtype, pl.Struct):
            extract = sms
            available = {f.name for f in dtype.fields}
        elif dtype == pl.Utf8:
            extract = sms.str.json_decode(dtype=SMS_STRUCT_SCHEMA)
            available = {f.name for f in SMS_STRUCT_SCHEMA.fields}
        else:
            extract = None
            available = set()

        if extract is not None:
            present = sorted(SMS_TARGET_FIELDS & available)
            if present:
                df = df.with_columns([
                    extract.struct.field(f).alias(f'endereco_sms_{f}')
                    for f in present
                ])

    # 3. protocolo_listagem — split, explode, extrair fields
    if 'protocolo_listagem' in cols:
        has_protocolo = (
            pl.col('protocolo_listagem').is_not_null()
            & (pl.col('protocolo_listagem').list.len() > 0)
        )
        df_com = df.filter(has_protocolo)
        df_sem = df.filter(~has_protocolo)

        if df_com.height > 0:
            df_com = df_com.explode('protocolo_listagem')
            field_exprs = [
                pl.col('protocolo_listagem').struct.field(col).alias(name)
                for name, col in PROTOCOL_STRUCT_FIELDS.items()
            ]
            df_com = df_com.with_columns(field_exprs)

        if df_sem.height > 0:
            if df_com.height > 0:
                null_exprs = [
                    pl.lit(None).cast(
                        df_com.select(pl.col('protocolo_listagem').struct.field(col)).dtypes[0]
                    ).alias(name)
                    for name, col in PROTOCOL_STRUCT_FIELDS.items()
                ]
            else:
                null_exprs = [
                    pl.lit(None).cast(pl.Utf8).alias(name)
                    for name in PROTOCOL_STRUCT_FIELDS
                ]
            df_sem = df_sem.with_columns(null_exprs)

        parts = [p for p in [df_com, df_sem] if p.height > 0]
        df = pl.concat(parts, how='diagonal_relaxed') if len(parts) > 1 else parts[0]

    # 4. Remover colunas aninhadas originais
    drop_cols = [c for c in ['protocolo_listagem', 'endereco_sms'] if c in df.columns]
    if drop_cols:
        df = df.drop(drop_cols)

    # 5. Selecionar e ordenar colunas (apenas as que existem no DF)
    existing = [c for c in CSV_COLUMN_ORDER if c in df.columns]
    return df.select(existing)


@router.get(
    "/participants/export",
    summary="Exportar participantes filtrados como CSV",
)
async def export_participants_csv(
    permissions: CurrentUserPermissions,
    filters: CommonFilters = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
):
    start = time.perf_counter()
    logger.info("⬇️ Export CSV started")

    query = PARTICIPANTS_TABLE_QUERY

    filters_dict = filters.model_dump(exclude_none=True)
    search_term = filters_dict.pop("search", None)

    column_filters = {}
    for filter_key, filter_value in filters_dict.items():
        if filter_key in PARTICIPANT_FILTER_COLUMN_MAP:
            col = PARTICIPANT_FILTER_COLUMN_MAP[filter_key]
            if isinstance(filter_value, str) and "|" in filter_value:
                filter_value = [v.strip() for v in filter_value.split("|") if v.strip()]
            column_filters[col] = filter_value

    sort_column = None
    sort_descending = False
    if sort.sort_by and sort.sort_by in PARTICIPANT_SORTABLE_COLUMNS:
        sort_column = PARTICIPANT_SORTABLE_COLUMNS[sort.sort_by]
        sort_descending = sort.sort_order == "desc"

    try:
        df_data, meta, _ = await DataManager.fetch_filter_paginate(
            query=query,
            filters_dict=column_filters,
            page=1,
            page_size=-1,
            filter_columns_config=PARTICIPANT_FILTER_OPTIONS_CONFIG,
            search_term=search_term,
            search_columns=(
                ["nome", "cpf", "id_membro_familia", "id_familia"]
                if search_term else None
            ),
            user_permissions=permissions,
            bypass_cache=bypass_cache,
            sort_by=sort_column,
            sort_descending=sort_descending,
        )

        if not permissions.is_super_admin:
            drop = [c for c in SENSITIVE_COLUMNS if c in df_data.columns]
            if drop:
                df_data = df_data.drop(drop)

        flattened = _flatten_for_csv(df_data)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        total_rows = meta.total_rows if meta else df_data.height
        filename = f'participantes_{timestamp}_{total_rows}rows.csv'

        CHUNK_ROWS = 50000
        import zlib

        async def _iter_csv_gz() -> AsyncIterator[bytes]:
            compressor = zlib.compressobj(level=6, wbits=zlib.MAX_WBITS + 16)
            yield compressor.compress('\uFEFF'.encode('utf-8'))
            loop = asyncio.get_event_loop()
            for i in range(0, len(flattened), CHUNK_ROWS):
                chunk = flattened.slice(i, CHUNK_ROWS)
                buf = io.BytesIO()
                await loop.run_in_executor(
                    None,
                    lambda b=buf, c=chunk, h=(i == 0): c.write_csv(
                        b,
                        separator=';',
                        include_header=h,
                        include_bom=False,
                        quote_style='always',
                    ),
                )
                yield compressor.compress(buf.getvalue())
            yield compressor.flush()

        elapsed = time.perf_counter() - start
        logger.info(
            f"✅ Export CSV started — {total_rows} participants, "
            f"{flattened.height} rows (chunked gzip)"
        )

        return StreamingResponse(
            _iter_csv_gz(),
            media_type='text/csv; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Encoding': 'gzip',
            },
        )

    except Exception as e:
        logger.error(f"❌ Error exporting participants CSV: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


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
        df_data, meta, filter_options = await DataManager.fetch_filter_paginate(
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
            user_permissions=permissions,  # NOVO: Pass user permissions
            bypass_cache=bypass_cache,  # IMPORTANTE: Passa bypass_cache para forçar refresh
            sort_by=sort_column,  # NOVO: Coluna para ordenação
            sort_descending=sort_descending,  # NOVO: Direção da ordenação
        )

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
