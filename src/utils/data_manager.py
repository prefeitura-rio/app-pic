import polars as pl
from typing import Dict, Any, Optional, Tuple
from math import ceil
import time

from src.utils.bigquery import execute_query
from src.utils.log import logger
from src.utils.cache_manager import query_cache
from src.utils.text_utils import TextNormalizer
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
    __slots__ = ['df', 'filter_options_cache']

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
    def fetch_filter_paginate(
        query: str,
        filters_dict: Dict[str, Any],
        page: int,
        page_size: Optional[int],
        filter_columns_config: Optional[Dict[str, Dict[str, str]]] = None,
        search_term: Optional[str] = None,
        search_columns: Optional[list[str]] = None,
        user_permissions=None,  # NOVO: Optional[UserPermissions]
        bypass_cache: bool = False,  # NOVO: Força query no BigQuery
    ) -> tuple[pl.DataFrame, PaginationMeta, Optional[SmartFilterOptions]]:
        """
        Executa pipeline completo de fetch → filter → filter_options → paginate.

        OTIMIZAÇÃO: Retorna DataFrame direto, não converte para dict.
        A API deve fazer a conversão para JSON apenas no último momento.

        Pipeline:
            1. GET DATASET: Busca do cache/BigQuery (~0.2s em cache hit)
            2. APPLY FILTERS: Aplica filtros case-insensitive (~0.05s)
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

        # Se page_size é None, não validar (retorna todos os dados)
        if page_size is not None:
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
        df, cache_hit, precomputed_filter_options = DataManager.get_dataset(
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

        # 4. FILTER OPTIONS - usar pré-computadas se disponíveis (OTIMIZAÇÃO V2)
        filter_options_dict = None
        if filter_columns_config:
            filter_opts_start = time.perf_counter()

            # OTIMIZAÇÃO: Se temos filter options pré-computadas E não há filtros ativos,
            # retornar diretamente (instant!)
            active_filter_count = len([
                v for v in filters_dict.values()
                if v and str(v) not in config.FILTER_IGNORE_VALUES
            ])

            if precomputed_filter_options and active_filter_count == 0:
                # Converter dict para SmartFilterOptions (instant)
                filter_options_dict = SmartFilterOptions(**{
                    k: [FilterOptionItem(**opt) for opt in v]
                    for k, v in precomputed_filter_options.items()
                })
                logger.info("⚡ Using precomputed filter options (instant)")
            else:
                # Fallback: calcular dinamicamente (quando há filtros ativos)
                filter_options_dict = DataManager.calculate_filter_options_fast(
                    df_original=df,  # DataFrame completo (sem filtros)
                    filter_columns_config=filter_columns_config,
                    active_filters=filters_dict,  # Filtros atualmente ativos
                )

            filter_opts_time = time.perf_counter() - filter_opts_start
            profiling.filter_options_s = round(
                filter_opts_time, config.PROFILING_DECIMAL_PLACES
            )

        # 4. PAGINATE (última etapa) - ou pular se page_size=None
        paginate_start = time.perf_counter()
        total_rows = len(df_filtered)
        # Se page_size é None, retornar TODOS os dados (sem paginação)
        if page_size is None:
            total_pages = 1
            df_result = df_filtered
            logger.info(f"Returning ALL {total_rows} rows (no pagination)")
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
                page_size=page_size,
                total_rows=total_rows,
                total_pages=total_pages,
                cache_hit=cache_hit,
                profiling=profiling.to_dict(),
            ),
            filter_options_dict,
        )

    @staticmethod
    def get_dataset(
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
                logger.info(
                    f"✅ Cache HIT (Polars DataFrame) - {cache_time:.3f}s"
                )
                return raw_data, True, None
            else:
                # Fallback: cache antigo (dict/list) - converter para Polars DataFrame
                logger.info(
                    f"Cache HIT (old format) - Converting to Polars - {cache_time:.3f}s"
                )
                df = pl.DataFrame(raw_data)
                return df, True, None
        else:
            # 2. Cache MISS - fetch from BigQuery (retorna Polars via Arrow)
            logger.info("❌ Cache MISS - Fetching from BigQuery")
            bq_start = time.perf_counter()
            df = execute_query(query, return_polars=True)  # Polars via Arrow!
            bq_time = time.perf_counter() - bq_start
            logger.info(f"BigQuery fetch time: {bq_time:.3f}s")

            if df.is_empty():
                return pl.DataFrame(), False, None

            # NOTA: Polars não precisa de otimização category como Pandas
            # Polars já usa representação eficiente internamente

            # 4. PRÉ-COMPUTAR FILTER OPTIONS (durante cache write)
            filter_options_cache = {}
            if filter_columns_config:
                precompute_start = time.perf_counter()
                filter_options_cache = DataManager._precompute_filter_options(
                    df, filter_columns_config
                )
                precompute_time = time.perf_counter() - precompute_start
                logger.info(
                    f"📊 Precomputed filter options: {precompute_time:.3f}s"
                )

            # 5. Criar CachedDataset otimizado
            cached_dataset = CachedDataset(
                df=df,
                filter_options_cache=filter_options_cache,
            )

            # 6. Salvar no cache
            cache_write_start = time.perf_counter()
            query_cache.set(query, cached_dataset)
            cache_write_time = time.perf_counter() - cache_write_start
            logger.info(
                f"💾 Cache write (CachedDataset): {cache_write_time:.3f}s"
            )

            total_time = time.perf_counter() - start_time
            logger.info(
                f"get_dataset completed (CACHE MISS) - total: {total_time:.3f}s, rows: {len(df)}"
            )

            return df, False, filter_options_cache

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
                unique_values = DataManager._extract_unique_from_array_polars(
                    df, column, array_field
                )
                options = [
                    {"id": str(v), "label": str(v)}
                    for v in sorted(unique_values)
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

            options = []
            for value in unique_values:
                value_str = str(value).strip()
                if value_str:
                    options.append({
                        "id": value_str,
                        "label": str(label_map.get(value, value))
                    })

            options.sort(key=lambda x: x["label"])
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

        # Estratégia: explode, filtrar, pegar índices únicos
        # 1. Adicionar índice temporário
        df_with_idx = df.with_row_index("_temp_idx")

        # 2. Explodir a coluna de array (cada item do array vira uma linha)
        try:
            df_exploded = df_with_idx.explode(array_col)
        except Exception:
            # Se falhar (coluna não é lista), retornar df original
            return df

        # 3. Extrair o campo do struct e filtrar
        try:
            # Tentar acessar como struct field
            field_expr = pl.col(array_col).struct.field(field_name)
            matching_idx = (
                df_exploded
                .filter(
                    field_expr.cast(pl.Utf8).str.to_lowercase().is_in(normalized_values)
                )
                .select("_temp_idx")
                .unique()
            )
        except Exception:
            # Fallback: retornar df original se estrutura não suportada
            return df

        # 4. Filtrar df original pelos índices que deram match
        result = df_with_idx.filter(
            pl.col("_temp_idx").is_in(matching_idx["_temp_idx"])
        ).drop("_temp_idx")

        return result

    @staticmethod
    def apply_filters(df: pl.DataFrame, filters_dict: Dict[str, Any]) -> pl.DataFrame:
        """
        Aplica filtros case-insensitive ao Polars DataFrame.

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

        for col, filter_value in filters_dict.items():
            filter_start = time.perf_counter()

            # Converter para lista se não for
            if not isinstance(filter_value, list):
                filter_value = [filter_value]

            # Pular valores vazios ou valores especiais (todos, todas)
            filter_value = [
                v
                for v in filter_value
                if v and str(v).strip() and str(v) not in config.FILTER_IGNORE_VALUES
            ]
            if not filter_value:
                continue

            before_filter = df.filter(filter_expr).height

            # Detectar filtros de array via dot notation
            if "." in col:
                array_col, field_name = col.split(".", 1)

                if array_col not in df.columns:
                    logger.warning(f"Array filter column '{array_col}' not found in DataFrame")
                    continue

                # Aplicar filtro de array (usa explode nativo - muito rápido)
                df = DataManager._filter_array_column_polars(
                    df, array_col, field_name, filter_value
                )

                filter_time = time.perf_counter() - filter_start
                filter_times[col] = filter_time
                logger.info(
                    f"Filter (array) '{col}': {before_filter} -> {len(df)} rows in {filter_time:.3f}s"
                )
                continue

            # Pular se coluna não existe
            if col not in df.columns:
                logger.warning(f"Filter column '{col}' not found in DataFrame")
                continue

            # Normalizar valores de filtro (apenas lowercase - sem remover acentos)
            # NOTA: Não usamos TextNormalizer aqui porque map_elements é muito lento
            # Os valores vêm do dropdown então já estão corretos
            normalized_filter_values = [
                str(v).lower().strip() for v in filter_value
            ]

            # Polars: filtro case-insensitive nativo (muito rápido)
            col_expr = pl.col(col).cast(pl.Utf8).str.to_lowercase()
            filter_expr = filter_expr & col_expr.is_in(normalized_filter_values)

            filter_time = time.perf_counter() - filter_start
            filter_times[col] = filter_time

        # Aplicar filtro final
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
    def _extract_unique_from_array_polars(df: pl.DataFrame, array_col: str, field_name: str) -> set:
        """
        Extrai valores únicos de um campo específico dentro de uma coluna de arrays (POLARS).

        OTIMIZAÇÃO: Usa explode + struct.field nativo do Polars (muito mais rápido que iteração).

        Args:
            df: DataFrame com a coluna de arrays
            array_col: Nome da coluna contendo arrays de structs ou dicts
            field_name: Campo a extrair (ex: "descricao", "status")

        Returns:
            Set de valores únicos encontrados
        """
        if df.is_empty() or array_col not in df.columns:
            logger.info(f"Array column '{array_col}' not found or df empty")
            return set()

        unique_values = set()

        # Método 1: Usar explode + struct.field nativo (RÁPIDO)
        try:
            # Explodir array para linhas individuais
            df_exploded = df.select(array_col).drop_nulls().explode(array_col)

            if df_exploded.is_empty():
                logger.info(f"No data after explode for {array_col}")
                return set()

            # Extrair campo do struct
            field_values = (
                df_exploded
                .select(pl.col(array_col).struct.field(field_name).alias("value"))
                .drop_nulls()
                .unique()
            )

            for row in field_values.to_dicts():
                value = row.get("value")
                if value and str(value).strip():
                    unique_values.add(str(value).strip())

            logger.info(f"Extracted {len(unique_values)} unique values from {array_col}.{field_name} (explode method)")
            return unique_values

        except Exception as e:
            logger.warning(f"Explode method failed for {array_col}.{field_name}: {e}, trying fallback...")

        # Método 2: Fallback - iterar sobre os valores (funciona para qualquer estrutura)
        try:
            for arr in df[array_col].drop_nulls().to_list():
                if arr is None:
                    continue
                if not isinstance(arr, (list, tuple)):
                    continue
                for item in arr:
                    if isinstance(item, dict):
                        value = item.get(field_name)
                        if value and str(value).strip():
                            unique_values.add(str(value).strip())
        except Exception as e:
            logger.warning(f"Fallback method also failed for {array_col}.{field_name}: {e}")

        logger.info(f"Extracted {len(unique_values)} unique values from {array_col}.{field_name} (fallback method)")
        return unique_values

    @staticmethod
    def calculate_filter_options_fast(
        df_original: pl.DataFrame,
        filter_columns_config: Dict[str, Dict[str, str]],
        active_filters: Dict[str, Any],
    ) -> SmartFilterOptions:
        """
        VERSÃO V4 POLARS de calculate_filter_options.

        OTIMIZAÇÕES:
        1. Usa Polars que é muito mais rápido que Pandas
        2. Operações vetorizadas nativas
        3. Pré-calcula expressões de filtro uma vez

        Performance: ~0.05-0.1s para 180k rows.
        """
        start_time = time.perf_counter()

        if df_original.is_empty():
            return SmartFilterOptions()

        # Construir expressão de filtro combinada
        filter_exprs = {}

        for k, v in active_filters.items():
            if v in [None, "", "todos", "todas"]:
                continue

            # Pular filtros de array (dot notation)
            if "." in k:
                continue

            if k not in df_original.columns:
                continue

            # Normalizar valor do filtro (apenas lowercase - consistente com apply_filters)
            filter_normalized = str(v).lower().strip()

            # Polars: expressão de filtro case-insensitive nativo (muito rápido)
            filter_exprs[k] = pl.col(k).cast(pl.Utf8).str.to_lowercase() == filter_normalized

        filter_options_dict = {}

        for result_key, cfg in filter_columns_config.items():
            column = cfg.get("column")
            label_column = cfg.get("label_column")
            config_type = cfg.get("type")
            array_field = cfg.get("array_field")

            if not column or column not in df_original.columns:
                filter_options_dict[result_key] = []
                continue

            # Combinar TODAS as expressões EXCETO a do filtro atual
            combined_expr = pl.lit(True)
            for filter_key, expr in filter_exprs.items():
                if filter_key == column:
                    continue
                combined_expr = combined_expr & expr

            # Aplicar filtro
            df_filtered = df_original.filter(combined_expr)

            # Tratar extração de array
            if config_type == "array_extract" and array_field:
                unique_values = DataManager._extract_unique_from_array_polars(
                    df_filtered, column, array_field
                )
                options = [
                    FilterOptionItem(id=str(v), label=str(v))
                    for v in sorted(unique_values)
                    if v and str(v).strip()
                ]
                filter_options_dict[result_key] = options
                continue

            # Pegar valores únicos - Polars
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

            # Criar opções
            options = []
            for value in unique_values:
                value_str = str(value).strip()
                if value_str:
                    options.append(
                        FilterOptionItem(
                            id=value_str, label=str(label_map.get(value, value))
                        )
                    )

            options.sort(key=lambda x: x.label)
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
    def get_user_permissions(cpf: str):
        """
        Fetch permissions for a specific CPF from cached governance table (POLARS).

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
            UserPermissions,
            PermissionDeniedError,
        )

        # Buscar tabela completa (do cache) - agora retorna Polars
        governance_df, _, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)

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
        ]:
            ids = user_permissions.get_filter_ids(id_type)
            if ids:
                filter_expr = filter_expr | pl.col(id_type).is_in(ids)

        df_filtered = df.filter(filter_expr)

        logger.info(
            f"Governance filters applied: {len(df)} -> {len(df_filtered)} rows "
            f"(CPF: {user_permissions.cpf})"
        )

        return df_filtered
