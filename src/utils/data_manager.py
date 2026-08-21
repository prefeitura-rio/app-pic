import asyncio
import polars as pl
from typing import Dict, Any, Optional, Tuple
from math import ceil
import time

# Limit concurrent BQ fetches to 1 to prevent OOM on cold start / pod restart.
# When multiple endpoints hit BQ simultaneously (cache miss), they serialise here.
# Double-checked locking ensures the second waiter re-uses the cache populated by
# the first waiter instead of launching a redundant fetch.
_bq_semaphore: Optional[asyncio.Semaphore] = None

from src.utils.bigquery import execute_query
from src.utils.log import logger
from src.utils.cache_manager import query_cache
from src.utils.text_utils import TextNormalizer
from src.utils.secretaria_access import filter_and_recalculate_by_secretaria
from src.utils.data_manager_config import (
    DataManagerConfig as config,
    DataManagerError,
    ValidationError,
    FilterColumnNotFoundError,
    ProfilingData,
)
from src.api.v1.schemas import (
    PaginatedResponse,
    PaginationMeta,
    SmartFilterOptions,
    FilterOptionItem,
)


# =============================================================================
# HELPER: Natural Sort (para ordenar opções de filtro com números)
# =============================================================================
def natural_sort_key(text: str) -> tuple:
    """
    Ordena naturalmente considerando números no início da string.
    Ex: "3ª Rio" < "10ª Centro" (ao invés de ordem alfabética onde "10" < "3")

    Args:
        text: String para extrair chave de ordenação

    Returns:
        Tupla (número ou infinito, texto completo) para ordenação
    """
    import re
    match = re.match(r'^(\d+)', text)
    if match:
        # Se começa com número, ordenar por (número, resto da string)
        return (int(match.group(1)), text)
    else:
        # Se não começa com número, ordenar alfabeticamente (com prioridade baixa)
        return (float('inf'), text)


# =============================================================================
# CACHE OTIMIZADO: Estrutura para dados pré-computados (POLARS)
# =============================================================================
class CachedDataset:
    """
    Dataset otimizado com dados pré-computados para performance.

    OTIMIZAÇÃO V2: Usa Polars DataFrame (muito mais rápido que Pandas).

    Armazena:
    - Polars DataFrame principal
    - Filter options pré-computadas
    """

    __slots__ = ["df", "filter_options_cache"]

    def __init__(
        self,
        df: pl.DataFrame,
        filter_options_cache: Optional[Dict[str, list]] = None,
    ):
        self.df = df
        self.filter_options_cache = filter_options_cache or {}


class DataManager:
    """
    Centralized manager for fetching, caching, filtering, and paginating data.
    Genérico - não conhece as colunas específicas, recebe tudo via parâmetros.
    """

    @staticmethod
    def df_to_json(df: pl.DataFrame) -> list[dict]:
        """
        Converte Polars DataFrame para lista de dicts.

        OTIMIZAÇÃO V2: Polars to_dicts() é muito mais rápido que Pandas.
        Polars converte null automaticamente para None.

        Args:
            df: Polars DataFrame para converter

        Returns:
            Lista de dicts pronta para JSON serialization

        Example:
            >>> df = pl.DataFrame({'a': [1, None], 'b': ['x', 'y']})
            >>> DataManager.df_to_json(df)
            [{'a': 1, 'b': 'x'}, {'a': None, 'b': 'y'}]
        """
        if df.is_empty():
            return []

        # Polars to_dicts() é extremamente rápido
        return df.to_dicts()

    @staticmethod
    def df_to_json_string(df: pl.DataFrame) -> str:
        """
        Converte Polars DataFrame diretamente para string JSON.

        OTIMIZAÇÃO V2: Polars write_json() é muito mais rápido que Pandas.

        Args:
            df: Polars DataFrame para converter

        Returns:
            String JSON pronta para enviar ao cliente

        Example:
            >>> df = pl.DataFrame({'a': [1, None], 'b': ['x', 'y']})
            >>> DataManager.df_to_json_string(df)
            '[{"a":1,"b":"x"},{"a":null,"b":"y"}]'
        """
        if df.is_empty():
            return "[]"

        # Polars: converter para JSON string via to_dicts() + json.dumps()
        import json

        return json.dumps(df.to_dicts())

    @staticmethod
    async def fetch_filter_paginate(
        query: str,
        filters_dict: Dict[str, Any],
        page: int,
        page_size: Optional[int],
        filter_columns_config: Optional[Dict[str, Dict[str, str]]] = None,
        search_term: Optional[str] = None,
        search_columns: Optional[list[str]] = None,
        user_permissions=None,  # NOVO: Optional[UserPermissions]
        bypass_cache: bool = False,  # NOVO: Força query no BigQuery
        sort_by: Optional[str] = None,  # NOVO: Coluna para ordenação
        sort_descending: bool = False,  # NOVO: True para DESC, False para ASC
    ) -> tuple[pl.DataFrame, PaginationMeta, Optional[SmartFilterOptions]]:
        """
        Executa pipeline completo de fetch → filter → filter_options → paginate.

        OTIMIZAÇÃO: Retorna DataFrame direto, não converte para dict.
        A API deve fazer a conversão para JSON apenas no último momento.

        Pipeline:
            1. GET DATASET: Busca do cache/BigQuery (~0.2s em cache hit)
            2. APPLY FILTERS: Aplica filtras CASe-insensitive (~0.05s)
            3. APPLY SEARCH: Busca parcial em múltiplas colunas (~0.02s)
            4. CALCULATE FILTER OPTIONS: Valores únicos para cascata (~0.5s)
            5. PAGINATE: Slice + clean (~0.01s)

        Performance:
            - Cache hit: ~0.5-1s (antes era 8-17s!)
            - Cache miss: ~3-5s (primeira request)

        Args:
            query: SQL completa com SELECT, FROM, WHERE, ORDER BY
            filters_dict: {col_name: value} - Normalização automática
            page: Página desejada (1-indexed, min=1)
            page_size: Itens por página (min=1, max=10000). Se None, retorna TODOS os dados sem paginação.
            filter_columns_config: Config para calcular filter options
            search_term: Termo de busca parcial (opcional)
            search_columns: Colunas para buscar o termo (ex: ['nome', 'cpf'])

        Returns:
            Tuple de (DataFrame, PaginationMeta, SmartFilterOptions):
                - DataFrame: Dados paginados e limpos (ready para to_dict)
                - PaginationMeta: Paginação + profiling detalhado
                - SmartFilterOptions: Opções de filtro baseadas nos dados filtrados

        Raises:
            ValidationError: Se parâmetros inválidos
            FilterColumnNotFoundError: Se coluna de filtro não existe
            DataManagerError: Outros erros do DataManager

        Example:
            >>> # Exemplo 1: Com filtros
            >>> response = DataManager.fetch_filter_paginate(
            ...     query="SELECT * FROM participants",
            ...     filters_dict={"grupo": "gestante"},
            ...     page=1,
            ...     page_size=20,
            ... )
            >>> print(response.meta.total_rows)
            50000

            >>> # Exemplo 2: Com busca de nome/CPF
            >>> response = DataManager.fetch_filter_paginate(
            ...     query="SELECT * FROM participants",
            ...     filters_dict={},
            ...     page=1,
            ...     page_size=20,
            ...     search_term="maria",
            ...     search_columns=["nome", "cpf"],
            ... )
            >>> print(response.meta.total_rows)
            1234
        """
        # VALIDAÇÕES
        if not query or not query.strip():
            raise ValidationError("query cannot be empty")

        if page < 1:
            raise ValidationError(f"page must be >= 1, got {page}")

        # Se page_size é None ou -1, não validar (retorna todos os dados)
        # -1 é usado para download/export de todos os dados (bypass paginação)
        if page_size is not None and page_size != -1:
            if page_size < config.MIN_PAGE_SIZE:
                raise ValidationError(
                    f"page_size must be >= {config.MIN_PAGE_SIZE}, got {page_size}"
                )

            if page_size > config.MAX_PAGE_SIZE:
                raise ValidationError(
                    f"page_size must be <= {config.MAX_PAGE_SIZE}, got {page_size}"
                )

        pipeline_start = time.perf_counter()
        profiling = ProfilingData()

        # 1. GET DATASET (cache + DataFrame conversion + precomputed filter options)
        get_start = time.perf_counter()
        df, cache_hit, precomputed_filter_options = await DataManager.get_dataset(
            query,
            bypass_cache=bypass_cache,
            filter_columns_config=filter_columns_config,  # Pass config for precomputation
        )
        get_time = time.perf_counter() - get_start
        profiling.get_dataset_s = round(get_time, config.PROFILING_DECIMAL_PLACES)
        profiling.cache_hit = cache_hit
        profiling.rows_before_filter = len(df)

        # 1.5. APPLY GOVERNANCE FILTERS (FIRST, before everything else)
        # CRITICAL: Applied AFTER cache to not affect shared cache
        if user_permissions:
            governance_start = time.perf_counter()
            df = DataManager.apply_governance_filters(df, user_permissions)
            governance_time = time.perf_counter() - governance_start
            logger.info(f"⚖️ Governance filters applied in {governance_time:.3f}s")
            profiling.rows_before_filter = len(df)  # Update count after governance

        # 2. APPLY FILTERS
        filter_start = time.perf_counter()
        df_filtered = DataManager.apply_filters(df, filters_dict)
        filter_time = time.perf_counter() - filter_start
        profiling.apply_filters_s = round(filter_time, config.PROFILING_DECIMAL_PLACES)
        profiling.filters_applied = len(
            [
                v
                for v in filters_dict.values()
                if v and str(v) not in config.FILTER_IGNORE_VALUES
            ]
        )
        profiling.rows_after_filter = len(df_filtered)

        # 3. APPLY SEARCH (busca parcial em múltiplas colunas)
        if search_term and search_columns:
            search_start = time.perf_counter()
            df_filtered = DataManager.apply_search(
                df_filtered, search_term, search_columns
            )
            search_time = time.perf_counter() - search_start
            profiling.search_s = round(search_time, config.PROFILING_DECIMAL_PLACES)
            profiling.rows_after_search = len(df_filtered)

        # 3.5. APPLY SORTING (ANTES da paginação!)
        if sort_by and sort_by in df_filtered.columns:
            sort_start = time.perf_counter()
            df_filtered = df_filtered.sort(
                sort_by, descending=sort_descending, nulls_last=True
            )
            sort_time = time.perf_counter() - sort_start
            logger.info(
                f"📊 Sort applied: {sort_by} {'DESC' if sort_descending else 'ASC'} in {sort_time:.3f}s"
            )
        elif sort_by:
            logger.warning(f"⚠️ Sort column '{sort_by}' not found in DataFrame")

        # 4. FILTER OPTIONS - usar pré-computadas se disponíveis (OTIMIZAÇÃO V2)
        filter_options_dict = None
        if filter_columns_config:
            filter_opts_start = time.perf_counter()

            # OTIMIZAÇÃO: Se temos filter options pré-computadas E não há filtros ativos,
            # retornar diretamente (instant!)
            # IMPORTANTE: Não usar precomputed se há governança ativa (usuário não-super-admin)
            # porque as options pré-computadas contêm TODOS os dados (cache compartilhado)
            active_filter_count = len(
                [
                    v
                    for v in filters_dict.values()
                    if v and str(v) not in config.FILTER_IGNORE_VALUES
                ]
            )

            # Verificar se pode usar cache: sem filtros E sem governança (ou super admin)
            has_governance = user_permissions and not user_permissions.has_full_access()
            can_use_precomputed = precomputed_filter_options and active_filter_count == 0 and not has_governance

            if can_use_precomputed:
                # Converter dict para SmartFilterOptions (instant)
                filter_options_dict = SmartFilterOptions(
                    **{
                        k: [FilterOptionItem(**opt) for opt in v]
                        for k, v in precomputed_filter_options.items()
                    }
                )
                logger.info("⚡ Using precomputed filter options (instant, with equipment filtering)")
            else:
                # Fallback: calcular dinamicamente (quando há filtros ativos)
                # OTIMIZAÇÃO: Passar AMBOS DataFrames para evitar recálculos
                # - df_filtered: usado para colunas SEM filtro ativo (maioria)
                # - df: usado para recalcular quando precisamos excluir um filtro
                filter_options_dict = DataManager.calculate_filter_options_fast(
                    df_original=df,  # DataFrame ANTES dos filtros (para exclusão)
                    df_already_filtered=df_filtered,  # DataFrame JÁ filtrado (otimização)
                    filter_columns_config=filter_columns_config,
                    active_filters=filters_dict,  # Filtros atualmente ativos
                )

            filter_opts_time = time.perf_counter() - filter_opts_start
            profiling.filter_options_s = round(
                filter_opts_time, config.PROFILING_DECIMAL_PLACES
            )

        # 4. PAGINATE (última etapa) - ou pular se page_size=None ou page_size=-1
        paginate_start = time.perf_counter()
        total_rows = len(df_filtered)
        # Se page_size é None ou -1, retornar TODOS os dados (sem paginação)
        # -1 é usado por download/export para bypass do limite de paginação
        if page_size is None or page_size == -1:
            total_pages = 1
            df_result = df_filtered
            logger.info(f"⬇️ Returning ALL {total_rows} rows (no pagination, download mode)")
        else:
            total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0
            start_idx = (page - 1) * page_size
            # Polars slice: offset, length
            df_result = df_filtered.slice(start_idx, page_size)

        # NOTA: Polars não precisa de limpeza de NaN/Inf como Pandas
        # Polars usa null nativamente e to_dicts() converte para None

        profiling.clean_s = 0.0  # Não precisa limpar em Polars
        # Paginação completa
        paginate_time = time.perf_counter() - paginate_start
        profiling.paginate_s = round(paginate_time, config.PROFILING_DECIMAL_PLACES)

        # OTIMIZAÇÃO: NÃO converter para dict aqui!
        # Deixar a API fazer isso apenas no momento de serializar JSON
        profiling.convert_to_dict_s = 0.0  # Não convertemos mais aqui

        # 5. TOTAL TIME
        pipeline_time = time.perf_counter() - pipeline_start
        profiling.total_pipeline_s = round(
            pipeline_time, config.PROFILING_DECIMAL_PLACES
        )

        # Log estruturado
        logger.info(
            "fetch_filter_paginate_completed",
            extra={
                "duration_s": profiling.total_pipeline_s,
                "cache_hit": profiling.cache_hit,
                "filters_applied": profiling.filters_applied,
                "search_applied": bool(search_term),
                "rows_before_filter": profiling.rows_before_filter,
                "rows_after_filter": profiling.rows_after_filter,
                "rows_after_search": profiling.rows_after_search,
                "page": page,
                "page_size": page_size,
                "returned_rows": len(df_result),
            },
        )
        logger.info(f"Profiling: {profiling}")

        # RETORNA POLARS DATAFRAME, não lista de dicts!
        return (
            df_result,
            PaginationMeta(
                page=page,
                page_size=page_size if page_size != -1 else None,  # -1 -> None na metadata
                total_rows=total_rows,
                total_pages=total_pages,
                cache_hit=cache_hit,
                profiling=profiling.to_dict(),
            ),
            filter_options_dict,
        )

    @staticmethod
    async def get_dataset(
        query: str,
        bypass_cache: bool = False,
        filter_columns_config: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> Tuple[pl.DataFrame, bool, Optional[Dict[str, list]]]:
        """
        Busca dataset completo do cache ou BigQuery.

        OTIMIZAÇÃO V2: Retorna também filter options pré-computadas.

        Fluxo:
            1. Tenta buscar do cache persistente (~0.01s se hit)
            2. Se miss (ou bypass_cache=True), busca do BigQuery (~2-3s)
            3. Pré-computa filter options e índices de array
            4. Armazena CachedDataset no cache

        Args:
            query: SQL completa para buscar dados
            bypass_cache: Se True, ignora cache e força query no BigQuery
            filter_columns_config: Config para pré-computar filter options

        Returns:
            Tuple de (DataFrame, cache_hit: bool, filter_options_dict)

        Example:
            >>> df, cache_hit, filter_opts = DataManager.get_dataset(
            ...     "SELECT * FROM participants",
            ...     filter_columns_config={...}
            ... )
            >>> print(f"Rows: {len(df)}, Cache: {cache_hit}")
            Rows: 179234, Cache: True
        """
        start_time = time.perf_counter()

        # 1. Try to get data from persistent cache (unless bypassing)
        cache_start = time.perf_counter()
        raw_data = None if bypass_cache else query_cache.get(query)
        cache_time = time.perf_counter() - cache_start

        cache_hit = raw_data is not None

        if cache_hit:
            # Cache retorna CachedDataset (Polars) ou Polars DataFrame
            if isinstance(raw_data, CachedDataset):
                logger.info(
                    f"✅ Cache HIT - CachedDataset with precomputed options - {cache_time:.3f}s"
                )
                return raw_data.df, True, raw_data.filter_options_cache
            elif isinstance(raw_data, pl.DataFrame):
                logger.info(f"✅ Cache HIT (Polars DataFrame) - {cache_time:.3f}s")
                return raw_data, True, None
            else:
                # Fallback: cache antigo (dict/list) - converter para Polars DataFrame
                logger.info(
                    f"Cache HIT (old format) - Converting to Polars - {cache_time:.3f}s"
                )
                df = pl.DataFrame(raw_data)
                return df, True, None
        else:
            # 2. Cache MISS — serialise BQ fetches via semaphore to avoid concurrent
            # Arrow→Polars allocations that can spike memory and cause OOMKill.
            global _bq_semaphore
            if _bq_semaphore is None:
                _bq_semaphore = asyncio.Semaphore(1)

            logger.info("❌ Cache MISS - Waiting for BQ semaphore...")
            async with _bq_semaphore:
                # Double-check: another coroutine may have populated the cache
                # while we were waiting for the semaphore.
                if not bypass_cache:
                    raw_data = query_cache.get(query)
                    if raw_data is not None:
                        if isinstance(raw_data, CachedDataset):
                            logger.info("✅ Cache HIT (populated while waiting for semaphore)")
                            return raw_data.df, True, raw_data.filter_options_cache
                        elif isinstance(raw_data, pl.DataFrame):
                            return raw_data, True, None
                        else:
                            return pl.DataFrame(raw_data), True, None

                logger.info("❌ Cache MISS confirmed - Fetching from BigQuery (thread pool)")

                def _fetch_and_cache() -> Tuple[pl.DataFrame, bool, Optional[Dict[str, list]]]:
                    bq_start = time.perf_counter()
                    df = execute_query(query, return_polars=True)  # Polars via Arrow!
                    bq_time = time.perf_counter() - bq_start
                    logger.info(f"BigQuery fetch time: {bq_time:.3f}s")

                    if df.is_empty():
                        return pl.DataFrame(), False, None

                    # PRÉ-COMPUTAR FILTER OPTIONS (durante cache write)
                    filter_options_cache: Dict[str, list] = {}
                    if filter_columns_config:
                        precompute_start = time.perf_counter()
                        filter_options_cache = DataManager._precompute_filter_options(
                            df, filter_columns_config
                        )
                        precompute_time = time.perf_counter() - precompute_start
                        logger.info(f"📊 Precomputed filter options: {precompute_time:.3f}s")

                    # Criar e salvar CachedDataset
                    cached_dataset = CachedDataset(
                        df=df,
                        filter_options_cache=filter_options_cache,
                    )
                    cache_write_start = time.perf_counter()
                    query_cache.set(query, cached_dataset)
                    cache_write_time = time.perf_counter() - cache_write_start
                    logger.info(f"💾 Cache write (CachedDataset): {cache_write_time:.3f}s")

                    total_time = time.perf_counter() - start_time
                    logger.info(
                        f"get_dataset completed (CACHE MISS) - total: {total_time:.3f}s, rows: {len(df)}"
                    )
                    return df, False, filter_options_cache

                return await asyncio.to_thread(_fetch_and_cache)

    @staticmethod
    def _precompute_filter_options(
        df: pl.DataFrame,
        filter_columns_config: Dict[str, Dict[str, str]],
    ) -> Dict[str, list]:
        """
        Pré-computa filter options durante cache write (POLARS).

        OTIMIZAÇÃO: Calcula UMA VEZ durante cache miss.
        Próximas requests usam valores pré-computados (instant).
        """
        if df.is_empty():
            return {}

        result = {}

        for result_key, cfg in filter_columns_config.items():
            column = cfg.get("column")
            label_column = cfg.get("label_column")
            config_type = cfg.get("type")
            array_field = cfg.get("array_field")

            if not column or column not in df.columns:
                result[result_key] = []
                continue

            # Array extraction (protocolo_listagem)
            if config_type == "array_extract" and array_field:
                label_field = cfg.get("label_field")
                if label_field:
                    # Extract id+label pairs (análogo a label_column nos escalares)
                    pairs = DataManager._extract_id_label_pairs_from_array_polars(
                        df, column, array_field, label_field
                    )
                    options = [
                        {"id": id_val, "label": label_val}
                        for id_val, label_val in sorted(pairs, key=lambda x: natural_sort_key(x[1]))
                        if id_val and id_val.strip()
                    ]
                else:
                    unique_values = DataManager._extract_unique_from_array_polars(
                        df, column, array_field
                    )
                    options = [
                        {"id": str(v), "label": str(v)}
                        for v in sorted(unique_values, key=natural_sort_key)
                        if v and str(v).strip()
                    ]
                result[result_key] = options
                continue

            # Scalar columns - Polars unique()
            unique_values = df[column].drop_nulls().unique().to_list()

            # Create label map if needed
            label_map = {}
            if label_column and label_column in df.columns:
                # Polars: select unique pairs and convert to dict
                pairs = (
                    df.select([column, label_column])
                    .drop_nulls()
                    .unique(subset=[column])
                )
                for row in pairs.to_dicts():
                    label_map[row[column]] = row[label_column]

            # Agrupar IDs por label (resolver duplicação de nomes)
            label_to_ids = {}
            for value in unique_values:
                value_str = str(value).strip()
                if value_str:
                    label = str(label_map.get(value, value))
                    if label not in label_to_ids:
                        label_to_ids[label] = []
                    label_to_ids[label].append(value_str)

            # Criar opções consolidadas (um nome pode representar múltiplos IDs)
            options = []
            for label, ids in label_to_ids.items():
                options.append(
                    {"id": "|".join(ids), "label": label}
                )

            options.sort(key=lambda x: natural_sort_key(x["label"]))
            result[result_key] = options

        return result

    @staticmethod
    def _filter_array_column_polars(
        df: pl.DataFrame, array_col: str, field_name: str, filter_values: list
    ) -> pl.DataFrame:
        """
        Filtra linhas onde QUALQUER item em uma coluna de array corresponde ao filtro (POLARS).

        OTIMIZAÇÃO: Usa explode + filter + unique ao invés de map_elements.
        Muito mais rápido para grandes datasets.

        Args:
            df: DataFrame completo
            array_col: Nome da coluna contendo arrays de structs (ex: "protocolo_listagem")
            field_name: Campo a buscar dentro de cada struct (ex: "descricao")
            filter_values: Lista de valores para match

        Returns:
            DataFrame filtrado
        """
        # Normalizar valores de filtro (apenas lowercase)
        normalized_values = [
            str(v).lower().strip() for v in filter_values if v and str(v).strip()
        ]

        if not normalized_values:
            return df

        logger.info(
            f"🔍 Filtering array column '{array_col}.{field_name}' with values: {normalized_values}"
        )

        # Verificar se a coluna existe
        if array_col not in df.columns:
            logger.error(f"❌ Array column '{array_col}' not found in DataFrame")
            return df

        # Estratégia: explode, filtrar, pegar índices únicos
        # 1. Adicionar índice temporário
        df_with_idx = df.with_row_index("_temp_idx")

        # 2. Explodir a coluna de array (cada item do array vira uma linha)
        df_exploded = df_with_idx.explode(array_col)

        if df_exploded.is_empty():
            logger.warning(f"⚠️ Exploded DataFrame is empty for column '{array_col}'")
            return df.head(0)  # Retornar DataFrame vazio

        # 3. Extrair o campo do struct e filtrar
        field_expr = pl.col(array_col).struct.field(field_name)
        matching_idx = (
            df_exploded.filter(
                field_expr.cast(pl.Utf8).str.to_lowercase().is_in(normalized_values)
            )
            .select("_temp_idx")
            .unique()
        )

        logger.info(f"📊 Array filter matched {matching_idx.height} unique rows")

        # 4. Filtrar df original pelos índices que deram match
        result = df_with_idx.filter(
            pl.col("_temp_idx").is_in(matching_idx["_temp_idx"])
        ).drop("_temp_idx")

        return result

    @staticmethod
    def _filter_array_column_combined_polars(
        df: pl.DataFrame,
        array_col: str,
        field_filters: Dict[str, list],
    ) -> pl.DataFrame:
        """
        Filtra linhas onde TODOS os campos especificados correspondem no MESMO item do array.

        LÓGICA AND PARA MULTI-SELECT:
        Quando um campo tem múltiplos valores (ex: descricao=["cadunico", "creche"]),
        o participante deve ter um match para CADA valor (AND), não apenas para algum (OR).

        Exemplo: descricao=["cadunico", "creche"] + status="irregular"
        → Mostra participantes que têm AMBOS:
          - cadunico com status irregular
          - creche com status irregular

        Args:
            df: DataFrame completo
            array_col: Nome da coluna contendo arrays de structs (ex: "protocolo_listagem")
            field_filters: Dict de {campo: [valores]} a serem filtrados conjuntamente

        Returns:
            DataFrame filtrado
        """
        if not field_filters:
            return df

        # Normalizar todos os valores de filtro
        normalized_filters = {}
        for field, values in field_filters.items():
            normalized_values = [
                str(v).lower().strip() for v in values if v and str(v).strip()
            ]
            if normalized_values:
                normalized_filters[field] = normalized_values

        if not normalized_filters:
            return df

        logger.info(f"🔗 Combined array filter on '{array_col}': {normalized_filters}")

        # Verificar se a coluna existe
        if array_col not in df.columns:
            logger.error(f"❌ Array column '{array_col}' not found in DataFrame")
            return df

        # Identificar o campo principal (com múltiplos valores) - geralmente 'descricao'
        # Os outros campos são aplicados como filtro adicional
        multi_value_field = None
        multi_values = []
        single_value_filters = {}

        for field, values in normalized_filters.items():
            if len(values) > 1 and multi_value_field is None:
                # Primeiro campo com múltiplos valores é o principal
                multi_value_field = field
                multi_values = values
            else:
                single_value_filters[field] = values

        # 1. Adicionar índice temporário
        df_with_idx = df.with_row_index("_temp_idx")

        # 2. Explodir a coluna de array
        df_exploded = df_with_idx.explode(array_col)

        if df_exploded.is_empty():
            logger.warning(f"⚠️ Exploded DataFrame is empty for column '{array_col}'")
            return df.head(0)

        # Se não há campo multi-valor, usar lógica simples (OR)
        if multi_value_field is None:
            # Construir expressão combinada simples
            combined_expr = pl.lit(True)
            for field, values in normalized_filters.items():
                field_expr = pl.col(array_col).struct.field(field)
                combined_expr = combined_expr & field_expr.cast(
                    pl.Utf8
                ).str.to_lowercase().is_in(values)

            df_filtered_items = df_exploded.filter(combined_expr)

            if df_filtered_items.is_empty():
                logger.info(f"📊 Combined array filter matched 0 rows")
                return df.head(0)

            matching_idx = df_filtered_items.select("_temp_idx").unique()
        else:
            # LÓGICA AND: Para cada valor do campo multi-valor, verificar se existe match
            # O participante só é incluído se TODOS os valores tiverem match
            matching_idx_sets = []

            for value in multi_values:
                # Construir expressão: campo_principal = value E outros_campos
                expr = (
                    pl.col(array_col)
                    .struct.field(multi_value_field)
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                    == value
                )

                for field, values in single_value_filters.items():
                    field_expr = pl.col(array_col).struct.field(field)
                    expr = expr & field_expr.cast(pl.Utf8).str.to_lowercase().is_in(
                        values
                    )

                # Pegar índices que têm match para este valor específico
                matched = df_exploded.filter(expr).select("_temp_idx").unique()
                matching_idx_sets.append(set(matched["_temp_idx"].to_list()))

            # Interseção de todos os conjuntos (AND)
            if matching_idx_sets:
                final_idx_set = matching_idx_sets[0]
                for idx_set in matching_idx_sets[1:]:
                    final_idx_set = final_idx_set.intersection(idx_set)

                if not final_idx_set:
                    logger.info(f"📊 Combined array filter (AND) matched 0 rows")
                    return df.head(0)

                matching_idx = pl.DataFrame({"_temp_idx": list(final_idx_set)})
            else:
                logger.info(f"📊 Combined array filter matched 0 rows (no values)")
                return df.head(0)

        logger.info(
            f"📊 Combined array filter matched {matching_idx.height} unique rows"
        )

        # Filtrar df original pelos índices que deram match
        result = df_with_idx.filter(
            pl.col("_temp_idx").is_in(matching_idx["_temp_idx"])
        ).drop("_temp_idx")

        return result

    @staticmethod
    def apply_filters(df: pl.DataFrame, filters_dict: Dict[str, Any]) -> pl.DataFrame:
        """
        Aplica filtras CASe-insensitive ao Polars DataFrame.

        OTIMIZAÇÃO V2: Usa Polars que é muito mais rápido que Pandas.

        Args:
            df: Polars DataFrame a ser filtrado
            filters_dict: {nome_coluna: valor_ou_lista_de_valores}

        Returns:
            Polars DataFrame filtrado
        """
        start_time = time.perf_counter()

        if df.is_empty():
            return df

        initial_rows = len(df)
        filter_times = {}

        # Polars: construir expressão de filtro
        filter_expr = pl.lit(True)

        # PASSO 1: Agrupar filtros de array por coluna base para aplicar combinados
        # Isso garante que filtros como protocolo_descricao + protocolo_status
        # sejam aplicados no MESMO item do array (filtros dependentes)
        array_filters_by_column: Dict[str, Dict[str, list]] = {}
        scalar_filters: Dict[str, Any] = {}

        for col, filter_value in filters_dict.items():
            # Converter para lista se não for
            if not isinstance(filter_value, list):
                filter_value = [filter_value]

            # Log para debug de filtros booleanos
            if col == "active":
                logger.info(f"🔍 [apply_filters] Processing 'active' filter: value={filter_value}, types={[type(v).__name__ for v in filter_value]}")

            # Pular valores vazios ou valores especiais (todos, todas)
            # IMPORTANTE: Manter False (boolean) pois é valor válido para filtros boolean
            cleaned_values = []
            for v in filter_value:
                # Sempre manter valores booleanos (True e False são válidos)
                if isinstance(v, bool):
                    cleaned_values.append(v)
                # Para outros tipos, aplicar validação normal
                elif v and str(v).strip() and str(v) not in config.FILTER_IGNORE_VALUES:
                    cleaned_values.append(v)

            filter_value = cleaned_values
            if not filter_value:
                continue

            # Separar filtros de array e escalares
            if "." in col:
                array_col, field_name = col.split(".", 1)
                if array_col not in array_filters_by_column:
                    array_filters_by_column[array_col] = {}
                array_filters_by_column[array_col][field_name] = filter_value
            else:
                scalar_filters[col] = filter_value

        # PASSO 2: Aplicar filtros de array combinados (por coluna base)
        for array_col, field_filters in array_filters_by_column.items():
            filter_start = time.perf_counter()

            if array_col not in df.columns:
                logger.warning(
                    f"Array filter column '{array_col}' not found in DataFrame"
                )
                continue

            before_filter = len(df)

            # Usar filtro combinado para garantir que todos os campos
            # correspondam ao MESMO item do array
            df = DataManager._filter_array_column_combined_polars(
                df, array_col, field_filters
            )

            filter_time = time.perf_counter() - filter_start
            filter_times[f"{array_col}.*"] = filter_time
            logger.info(
                f"Filter (array combined) '{array_col}' with {list(field_filters.keys())}: {before_filter} -> {len(df)} rows in {filter_time:.3f}s"
            )

        # PASSO 3: Aplicar filtros escalares (colunas normais)
        for col, filter_value in scalar_filters.items():
            filter_start = time.perf_counter()

            # Pular se coluna não existe
            if col not in df.columns:
                logger.warning(f"Filter column '{col}' not found in DataFrame")
                continue

            before_filter = df.filter(filter_expr).height

            # Detectar tipo da coluna para aplicar filtro adequado
            col_dtype = df[col].dtype

            # Tratamento especial para colunas booleanas
            if col_dtype == pl.Boolean:
                # Converter valores do filtro para boolean
                bool_values = []
                for v in filter_value:
                    if isinstance(v, bool):
                        bool_values.append(v)
                    elif isinstance(v, str):
                        # Aceitar "true"/"false" (case insensitive) ou "1"/"0"
                        v_lower = v.lower().strip()
                        if v_lower in ["true", "1", "yes", "sim"]:
                            bool_values.append(True)
                        elif v_lower in ["false", "0", "no", "não", "nao"]:
                            bool_values.append(False)
                    elif isinstance(v, (int, float)):
                        bool_values.append(bool(v))

                if bool_values:
                    rows_before = df.filter(filter_expr).height
                    filter_expr = filter_expr & pl.col(col).is_in(bool_values)
                    rows_after = df.filter(filter_expr).height
                    logger.info(f"🔍 Boolean filter on '{col}': {bool_values} -> {rows_before} to {rows_after} rows")
            else:
                # Filtro padrão para strings (case-insensitive)
                normalized_filter_values = [str(v).lower().strip() for v in filter_value]
                col_expr = pl.col(col).cast(pl.Utf8).str.to_lowercase()
                filter_expr = filter_expr & col_expr.is_in(normalized_filter_values)

            filter_time = time.perf_counter() - filter_start
            filter_times[col] = filter_time

        # Aplicar filtro final de colunas escalares
        df_filtered = df.filter(filter_expr)

        total_time = time.perf_counter() - start_time
        logger.info(
            f"apply_filters completed - filters: {sum(filter_times.values()):.3f}s, total: {total_time:.3f}s, result: {initial_rows} -> {len(df_filtered)} rows"
        )

        return df_filtered

    @staticmethod
    def apply_search(
        df: pl.DataFrame, search_term: str, search_columns: list[str]
    ) -> pl.DataFrame:
        """
        Aplica busca parcial (contains) em múltiplas colunas (POLARS).

        Args:
            df: Polars DataFrame a ser pesquisado
            search_term: Termo de busca (ex: "maria", "123.456")
            search_columns: Lista de colunas para buscar (ex: ['nome', 'cpf'])

        Returns:
            Polars DataFrame filtrado com linhas que contêm o termo
        """
        start_time = time.perf_counter()

        if df.is_empty() or not search_term or not search_columns:
            return df

        # Normalizar termo de busca
        search_normalized = TextNormalizer.normalize(search_term.strip())

        if not search_normalized:
            return df

        logger.info(
            f"Searching for '{search_term}' (normalized: '{search_normalized}') in columns: {search_columns}"
        )

        # Polars: construir expressão OR
        search_expr = pl.lit(False)

        for col in search_columns:
            if col not in df.columns:
                logger.warning(f"Search column '{col}' not found in DataFrame")
                continue

            # Polars: busca case-insensitive usando str.to_lowercase().str.contains()
            col_expr = (
                pl.col(col)
                .cast(pl.Utf8)
                .str.to_lowercase()
                .str.contains(search_normalized, literal=True)
            )
            search_expr = search_expr | col_expr

        df_searched = df.filter(search_expr)

        total_time = time.perf_counter() - start_time
        logger.info(
            f"apply_search completed in {total_time:.3f}s - result: {len(df)} -> {len(df_searched)} rows"
        )

        return df_searched

    @staticmethod
    def _extract_unique_from_array_polars(
        df: pl.DataFrame, array_col: str, field_name: str
    ) -> set:
        """
        Extrai valores únicos de um campo específico dentro de uma coluna de arrays (POLARS).

        OTIMIZAÇÃO: Usa explode + struct.field nativo do Polars (operações vetorizadas).

        Args:
            df: DataFrame com a coluna de arrays
            array_col: Nome da coluna contendo arrays de structs
            field_name: Campo a extrair (ex: "descricao", "status")

        Returns:
            Set de valores únicos encontrados
        """
        if df.is_empty() or array_col not in df.columns:
            return set()

        # Explodir array para linhas individuais (operação vetorizada)
        df_exploded = df.select(array_col).drop_nulls().explode(array_col)

        if df_exploded.is_empty():
            return set()

        # Extrair campo do struct e pegar valores únicos (operação vetorizada)
        unique_values = (
            df_exploded.select(
                pl.col(array_col).struct.field(field_name).cast(pl.Utf8).alias("value")
            )
            .drop_nulls()
            .unique()
            .get_column("value")
            .to_list()
        )

        # Filtrar valores vazios e converter para set
        result = {v.strip() for v in unique_values if v and v.strip()}

        logger.info(
            f"Extracted {len(result)} unique values from {array_col}.{field_name}"
        )
        return result

    @staticmethod
    def _extract_id_label_pairs_from_array_polars(
        df: pl.DataFrame, array_col: str, id_field: str, label_field: str
    ) -> list[tuple[str, str]]:
        """
        Extrai pares únicos (id, label) de dois campos dentro de uma coluna de arrays.
        Análogo a label_column nos filtros escalares.
        """
        if df.is_empty() or array_col not in df.columns:
            return []

        df_exploded = df.select(array_col).drop_nulls().explode(array_col)

        if df_exploded.is_empty():
            return []

        pairs = (
            df_exploded.select([
                pl.col(array_col).struct.field(id_field).cast(pl.Utf8).alias("id"),
                pl.col(array_col).struct.field(label_field).cast(pl.Utf8).alias("label"),
            ])
            .drop_nulls()
            .unique(subset=["id"])
            .to_dicts()
        )

        return [(r["id"].strip(), r["label"].strip()) for r in pairs if r["id"] and r["id"].strip()]

    @staticmethod
    def _extract_unique_from_array_with_filter_polars(
        df: pl.DataFrame,
        array_col: str,
        field_name: str,
        filter_fields: Dict[str, list],
        exclude_field: Optional[str] = None,
    ) -> set:
        """
        Extrai valores únicos de um campo do array, aplicando filtros nos itens do array.

        Usado para calcular filter options com cascata entre campos do mesmo array.
        Por exemplo: ao filtrar por protocolo_status=atenção, mostrar apenas os
        protocolo_descricao que têm status atenção.

        Args:
            df: DataFrame com a coluna de arrays
            array_col: Nome da coluna contendo arrays de structs
            field_name: Campo a extrair valores únicos
            filter_fields: Dict de {campo: [valores]} para filtrar itens do array
            exclude_field: Campo a excluir do filtro (para manter opções do próprio filtro)

        Returns:
            Set de valores únicos encontrados
        """
        if df.is_empty() or array_col not in df.columns:
            return set()

        # Explodir array para linhas individuais
        df_exploded = df.select(array_col).drop_nulls().explode(array_col)

        if df_exploded.is_empty():
            return set()

        # Aplicar filtros nos itens do array (exceto o campo que estamos extraindo)
        filter_expr = pl.lit(True)
        for field, values in filter_fields.items():
            if field == exclude_field:
                continue
            if values:
                normalized_values = [str(v).lower().strip() for v in values]
                field_expr = (
                    pl.col(array_col)
                    .struct.field(field)
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                )
                filter_expr = filter_expr & field_expr.is_in(normalized_values)

        df_filtered = df_exploded.filter(filter_expr)

        if df_filtered.is_empty():
            return set()

        # Extrair valores únicos do campo desejado
        unique_values = (
            df_filtered.select(
                pl.col(array_col).struct.field(field_name).cast(pl.Utf8).alias("value")
            )
            .drop_nulls()
            .unique()
            .get_column("value")
            .to_list()
        )

        result = {v.strip() for v in unique_values if v and v.strip()}
        return result

    @staticmethod
    def calculate_filter_options_fast(
        df_original: pl.DataFrame,
        filter_columns_config: Dict[str, Dict[str, str]],
        active_filters: Dict[str, Any],
        df_already_filtered: Optional[pl.DataFrame] = None,
    ) -> SmartFilterOptions:
        """
        VERSÃO V7 POLARS de calculate_filter_options - SUPER OTIMIZADA.

        LÓGICA DE CASCATA INTELIGENTE:
        Para cada filter option, aplicamos TODOS os filtros EXCETO o do próprio campo.

        OTIMIZAÇÃO PRINCIPAL: Usa df_already_filtered para colunas sem filtro ativo,
        evitando recálculos desnecessários. Só recalcula quando precisa excluir um filtro.
        """
        start_time = time.perf_counter()

        if df_original.is_empty():
            return SmartFilterOptions()

        # Usar df já filtrado se disponível, senão usar original
        df_base_filtered = (
            df_already_filtered if df_already_filtered is not None else df_original
        )

        # Identificar quais filtros estão ativos
        active_scalar_filters: Dict[str, list] = {}
        active_array_filters: Dict[str, Dict[str, list]] = {}

        for k, v in active_filters.items():
            if v in [None, "", "todos", "todas"]:
                continue

            values = v if isinstance(v, list) else [v]
            values = [
                val
                for val in values
                if val
                and str(val).strip()
                and str(val) not in config.FILTER_IGNORE_VALUES
            ]
            if not values:
                continue

            if "." in k:
                array_col, field_name = k.split(".", 1)
                if array_col not in active_array_filters:
                    active_array_filters[array_col] = {}
                active_array_filters[array_col][field_name] = values
            else:
                if k in df_original.columns:
                    active_scalar_filters[k] = values
                else:
                    logger.warning(f"⚠️ Filter key '{k}' not found in DataFrame columns")

        filter_options_dict = {}

        for result_key, cfg in filter_columns_config.items():
            column = cfg.get("column")
            label_column = cfg.get("label_column")
            config_type = cfg.get("type")
            array_field = cfg.get("array_field")

            if not column or column not in df_original.columns:
                filter_options_dict[result_key] = []
                continue

            is_array_filter = config_type == "array_extract" and array_field

            # Determinar qual DataFrame usar
            if column in active_scalar_filters:
                # Filtro escalar ativo - precisa recalcular excluindo este filtro
                # Aplicar todos os filtros escalares EXCETO este
                filter_expr = pl.lit(True)
                for filter_col, filter_vals in active_scalar_filters.items():
                    if filter_col != column:
                        normalized = [str(v).lower().strip() for v in filter_vals]
                        filter_expr = filter_expr & pl.col(filter_col).cast(
                            pl.Utf8
                        ).str.to_lowercase().is_in(normalized)

                df_filtered = df_original.filter(filter_expr)

                # Aplicar filtros de array (todos)
                for array_col, field_filters in active_array_filters.items():
                    if array_col in df_filtered.columns:
                        df_filtered = DataManager._filter_array_column_combined_polars(
                            df_filtered, array_col, field_filters
                        )

            elif is_array_filter and array_field:
                # Verificar se este campo de array tem filtro ativo
                array_col_for_filter = column  # ex: "protocolo_listagem"
                if (
                    array_col_for_filter in active_array_filters
                    and array_field in active_array_filters[array_col_for_filter]
                ):
                    # Precisa recalcular excluindo este campo do filtro de array
                    # Primeiro aplicar todos os filtros escalares
                    filter_expr = pl.lit(True)
                    for filter_col, filter_vals in active_scalar_filters.items():
                        normalized = [str(v).lower().strip() for v in filter_vals]
                        filter_expr = filter_expr & pl.col(filter_col).cast(
                            pl.Utf8
                        ).str.to_lowercase().is_in(normalized)

                    df_filtered = df_original.filter(filter_expr)

                    # Aplicar filtros de array excluindo este campo
                    for arr_col, field_filters in active_array_filters.items():
                        if arr_col not in df_filtered.columns:
                            continue

                        if arr_col == array_col_for_filter:
                            # Excluir o campo atual
                            other_filters = {
                                f: v
                                for f, v in field_filters.items()
                                if f != array_field
                            }
                            if other_filters:
                                df_filtered = (
                                    DataManager._filter_array_column_combined_polars(
                                        df_filtered, arr_col, other_filters
                                    )
                                )
                        else:
                            df_filtered = (
                                DataManager._filter_array_column_combined_polars(
                                    df_filtered, arr_col, field_filters
                                )
                            )
                else:
                    # Nenhum filtro ativo neste campo - usar DataFrame já filtrado
                    df_filtered = df_base_filtered
            else:
                # Coluna sem filtro ativo - usar DataFrame já filtrado (OTIMIZAÇÃO!)
                df_filtered = df_base_filtered

            # Tratar extração de array
            if config_type == "array_extract" and array_field:
                label_field = cfg.get("label_field")
                # Verificar se há filtros de array ativos para este array
                array_col_name = column  # ex: "protocolo_listagem"
                if label_field:
                    # id_field + label_field: extrair pares (análogo a label_column nos escalares)
                    pairs = DataManager._extract_id_label_pairs_from_array_polars(
                        df_filtered, array_col_name, array_field, label_field
                    )
                    options = [
                        FilterOptionItem(id=id_val, label=label_val)
                        for id_val, label_val in sorted(pairs, key=lambda x: natural_sort_key(x[1]))
                        if id_val and id_val.strip()
                    ]
                elif array_col_name in active_array_filters:
                    # Usar função que aplica filtros nos itens do array (cascata)
                    # Exclui o próprio campo para manter suas opções
                    unique_values = (
                        DataManager._extract_unique_from_array_with_filter_polars(
                            df_filtered,
                            array_col_name,
                            array_field,
                            filter_fields=active_array_filters[array_col_name],
                            exclude_field=array_field,  # Excluir próprio campo
                        )
                    )
                    options = [
                        FilterOptionItem(id=str(v), label=str(v))
                        for v in sorted(unique_values, key=natural_sort_key)
                        if v and str(v).strip()
                    ]
                else:
                    # Sem filtros de array ativos - extrair normalmente
                    unique_values = DataManager._extract_unique_from_array_polars(
                        df_filtered, column, array_field
                    )
                    options = [
                        FilterOptionItem(id=str(v), label=str(v))
                        for v in sorted(unique_values, key=natural_sort_key)
                        if v and str(v).strip()
                    ]
                filter_options_dict[result_key] = options
                continue

            # Pegar valores únicos - Polars
            # Para secretaria_acesso, incluir NULL como opção válida
            if column == "secretaria_acesso":
                # Incluir NULL/None como valor
                unique_values = df_filtered[column].unique().to_list()
            else:
                unique_values = df_filtered[column].drop_nulls().unique().to_list()

            # Criar label map se necessário
            label_map = {}
            if label_column and label_column in df_filtered.columns:
                pairs = (
                    df_filtered.select([column, label_column])
                    .drop_nulls()
                    .unique(subset=[column])
                )
                for row in pairs.to_dicts():
                    label_map[row[column]] = row[label_column]

            # Agrupar IDs por label (resolver duplicação de nomes)
            label_to_ids = {}
            for value in unique_values:
                # Converter None para "NULL" string para secretaria_acesso
                if value is None and column == "secretaria_acesso":
                    value_str = "NULL"
                else:
                    value_str = str(value).strip() if value is not None else ""

                if value_str:
                    label = str(label_map.get(value, value_str))
                    if label not in label_to_ids:
                        label_to_ids[label] = []
                    label_to_ids[label].append(value_str)

            # Criar opções consolidadas (um nome pode representar múltiplos IDs)
            options = []
            for label, ids in label_to_ids.items():
                options.append(
                    FilterOptionItem(
                        id="|".join(ids), label=label
                    )
                )

            # Ordenação natural: considera números no início da string
            # Ex: "3ª Rio" vem antes de "10ª Centro" (ao invés de ordem alfabética)
            options.sort(key=lambda opt: natural_sort_key(opt.label))
            filter_options_dict[result_key] = options

        total_time = time.perf_counter() - start_time
        logger.info(
            f"calculate_filter_options_fast completed in {total_time:.3f}s (POLARS)"
        )

        return SmartFilterOptions(**filter_options_dict)

    # ========================================================================
    # GOVERNANCE METHODS
    # ========================================================================

    @staticmethod
    async def get_user_permissions(cpf: str):
        """
        Fetch permissions for a specific CPF from cached governance table (POLARS).

        NOTE: v1-only. BigQuery-backed (endpoint_data_access). v2 uses
        PostgresAdminRepository.fetch_user_permissions instead. Keep this on
        BigQuery as long as v1's admin CRUD writes to BigQuery.

        OPTIMIZATION: Uses get_dataset() with shared cache.

        Args:
            cpf: User's CPF from JWT token

        Returns:
            UserPermissions object

        Raises:
            PermissionDeniedError: If CPF not found or inactive
        """
        from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
        from src.core.security.permissions_models import (
            PermissionDeniedError,
            UserPermissions,
        )
        from src.utils.constants import (
            SECRETARIA_SMAS,
            SECRETARIA_SME,
            SECRETARIA_SMS,
            SECRETARIA_TODOS,
        )

        # Buscar tabela completa (do cache) - agora retorna Polars
        governance_df, _, _ = await DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)

        # DEBUG LOGGING START
        logger.info(f"Auth Check for CPF: '{cpf}'")
        if not governance_df.is_empty():
            logger.info(
                f"Governance Table Stats: {len(governance_df)} rows. CPF Col Type: {governance_df['cpf'].dtype}"
            )
            # Check for exact match count
            match_count = governance_df.filter(pl.col("cpf") == cpf).height
            logger.info(f"Exact matches found: {match_count}")
        else:
            logger.warning("Governance DataFrame is EMPTY!")
        # DEBUG LOGGING END

        # Polars: Adicionar coluna _active_bool
        if "active" in governance_df.columns:
            # Converter para string, lowercase, comparar com 'true' ou '1'
            governance_df = governance_df.with_columns(
                pl.col("active")
                .cast(pl.Utf8)
                .str.to_lowercase()
                .is_in(["true", "1", "1.0", "yes"])
                .alias("_active_bool")
            )
        else:
            logger.warning(
                "Column 'active' not found in governance table. Defaulting to False."
            )
            governance_df = governance_df.with_columns(
                pl.lit(False).alias("_active_bool")
            )

        # Filter by CPF
        user_rows = governance_df.filter(pl.col("cpf") == cpf)

        if user_rows.is_empty():
            raise PermissionDeniedError(f"CPF {cpf} não cadastrado na base de acessos")

        # Check active status - pegar primeira linha
        user_row = user_rows.row(0, named=True)
        if not user_row["_active_bool"]:
            raise PermissionDeniedError(f"Usuário {cpf} está inativo")

        # row já é um dict
        row_dict = dict(user_row)

        # Garantir que active no objeto final seja bool limpo
        row_dict["active"] = bool(row_dict["_active_bool"])

        # Convert legacy scalar secretaria_acesso (BigQuery column) into the
        # new secretarias_acesso list field. `secretaria_acesso` itself is now
        # a read-only compat @property on UserPermissions, so passing it as a
        # constructor kwarg would be silently dropped (Pydantic ignores
        # unknown/property kwargs) leaving secretarias_acesso as [].
        raw_secretaria = row_dict.pop("secretaria_acesso", None)
        if raw_secretaria == SECRETARIA_TODOS:
            row_dict["secretarias_acesso"] = [SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS]
        elif raw_secretaria:
            row_dict["secretarias_acesso"] = [raw_secretaria]
        else:
            row_dict["secretarias_acesso"] = []

        # Convert struct arrays to list of IdWithName
        for id_type in [
            "id_cras",
            "id_escola",
            "id_cre",
            "id_ap",
            "id_cas",
            "id_clinica_familia",
        ]:
            list_key = f"{id_type}_list"
            if row_dict.get(list_key) is not None:
                # If it's a list of dicts (from BigQuery STRUCT)
                if isinstance(row_dict[list_key], list) and len(row_dict[list_key]) > 0:
                    row_dict[list_key] = [
                        {
                            "id": item.get("id", item.get(id_type, "")),
                            "nome": item.get(
                                "nome",
                                item.get(f'nome_{id_type.replace("id_", "")}', ""),
                            ),
                        }
                        for item in row_dict[list_key]
                    ]

        permissions = UserPermissions(**row_dict)
        return permissions

    @staticmethod
    def apply_governance_filters(df: pl.DataFrame, user_permissions) -> pl.DataFrame:
        """
        Apply governance filters IN MEMORY over cached data (POLARS).

        CRITICAL: Applied AFTER get_dataset() to not affect shared cache.

        Args:
            df: Polars DataFrame from cache (all participants)
            user_permissions: Current user's permissions

        Returns:
            Polars DataFrame filtered to only data the user can see
        """
        if user_permissions.has_full_access():
            logger.info("Super admin - no governance filters")
            return df

        # Polars: Construir expressão OR entre todos os IDs autorizados
        filter_expr = pl.lit(False)

        for id_type in [
            "id_cras",
            "id_escola",
            "id_cre",
            "id_ap",
            "id_cas",
            "id_clinica_familia",
            "id_equipe_familia",
        ]:
            ids = user_permissions.get_filter_ids(id_type)
            if ids:
                filter_expr = filter_expr | pl.col(id_type).is_in(ids)

        df_filtered = df.filter(filter_expr)

        # Apply protocol filtering by secretarias_acesso
        df_filtered = filter_and_recalculate_by_secretaria(
            df_filtered,
            user_permissions.secretarias_acesso
        )

        logger.info(
            f"Governance filters applied: {len(df)} -> {len(df_filtered)} rows "
            f"(CPF: {user_permissions.cpf})"
        )

        return df_filtered
