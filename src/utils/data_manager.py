import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
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


class DataManager:
    """
    Centralized manager for fetching, caching, filtering, and paginating data.
    Genérico - não conhece as colunas específicas, recebe tudo via parâmetros.
    """

    @staticmethod
    def df_to_json(df: pd.DataFrame) -> list[dict]:
        """
        Converte DataFrame para lista de dicts, convertendo NaN/Inf para None.

        SOLUÇÃO: Usa JSON round-trip que converte NaN → null automaticamente.
        Pandas .to_json() com orient='records' já faz a conversão correta.

        Args:
            df: DataFrame para converter

        Returns:
            Lista de dicts pronta para JSON serialization (NaN viram None)

        Example:
            >>> df = pd.DataFrame({'a': [1, np.nan], 'b': ['x', 'y']})
            >>> DataManager.df_to_json(df)
            [{'a': 1.0, 'b': None}, {'a': None, 'b': 'y'}]
        """
        if df.empty:
            return []

        # SOLUÇÃO ROBUSTA: to_json() converte NaN → null automaticamente
        # json.loads() converte null → None
        import json

        json_str = df.to_json(orient="records", date_format="iso")
        return json.loads(json_str)

    @staticmethod
    def df_to_json_string(df: pd.DataFrame) -> str:
        """
        Converte DataFrame diretamente para string JSON, muito mais rápido que df_to_json.

        OTIMIZAÇÃO: Retorna a string JSON direta do Pandas, evitando:
        1. df.to_json() -> string JSON (CPU intensive)
        2. json.loads(string) -> dict (CPU intensive + memória x2)
        3. FastAPI json.dumps(dict) -> string JSON (CPU intensive + memória x2)

        Com df_to_json_string, fazemos apenas:
        1. df.to_json() -> string JSON (CPU intensive)
        2. FastAPI retorna string diretamente (sem serialização extra)

        Economia: ~40-50% de CPU e memória para grandes datasets.

        Args:
            df: DataFrame para converter

        Returns:
            String JSON pronta para enviar ao cliente (NaN já convertidos para null)

        Example:
            >>> df = pd.DataFrame({'a': [1, np.nan], 'b': ['x', 'y']})
            >>> DataManager.df_to_json_string(df)
            '[{"a":1.0,"b":null},{"a":null,"b":"y"}]'
        """
        if df.empty:
            return "[]"

        # Pandas já converte NaN → null na string JSON
        return df.to_json(orient="records", date_format="iso")

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
    ) -> tuple[pd.DataFrame, PaginationMeta, Optional[SmartFilterOptions]]:
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

        # 1. GET DATASET (cache + DataFrame conversion)
        get_start = time.perf_counter()
        df, cache_hit = DataManager.get_dataset(query, bypass_cache=bypass_cache)
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

        # 4. CALCULATE FILTER OPTIONS (sobre dados filtrados COMPLETOS)
        filter_options_dict = None
        if filter_columns_config:
            filter_opts_start = time.perf_counter()
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
            df_clean = df_filtered
            clean_time = 0.0
            logger.info(f"Returning ALL {total_rows} rows (no pagination)")
        else:
            total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            # Slice
            df_page = df_filtered.iloc[start_idx:end_idx]

            # Clean (NaN/Inf)
            clean_start = time.perf_counter()

            # IMPORTANTE: replace() falha em colunas com arrays (object dtype com listas)
            # Precisamos processar apenas colunas sem arrays
            object_cols = df_page.select_dtypes(include=["object"]).columns.tolist()
            array_cols = []

            # Identificar colunas que contêm arrays/listas
            for col in object_cols:
                sample = df_page[col].iloc[0] if len(df_page) > 0 else None
                if sample is not None and isinstance(sample, (list, np.ndarray)):
                    array_cols.append(col)

            # Colunas seguras para replace (não arrays)
            safe_cols = [c for c in df_page.columns if c not in array_cols]

            # Replace apenas em colunas seguras
            if safe_cols:
                df_clean = df_page.copy()
                df_clean[safe_cols] = df_clean[safe_cols].replace(
                    [np.inf, -np.inf, np.nan], None
                )
            else:
                df_clean = df_page.copy()

            df_clean.columns = df_clean.columns.astype(str)
            clean_time = time.perf_counter() - clean_start

        profiling.clean_s = round(clean_time, config.PROFILING_DECIMAL_PLACES)
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
                "returned_rows": len(df_clean),
            },
        )
        logger.info(f"Profiling: {profiling}")

        # RETORNA DATAFRAME, não lista de dicts!
        return (
            df_clean,
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
        query: str, bypass_cache: bool = False
    ) -> tuple[pd.DataFrame, bool]:
        """
        Busca dataset completo do cache ou BigQuery.

        Fluxo:
            1. Tenta buscar do cache persistente (~0.001s se hit)
            2. Se miss (ou bypass_cache=True), busca do BigQuery (~2-3s)
            3. Armazena no cache para próximas requests
            4. Converte para DataFrame

        Args:
            query: SQL completa para buscar dados
            bypass_cache: Se True, ignora cache e força query no BigQuery

        Returns:
            Tuple de (DataFrame, cache_hit: bool)

        Example:
            >>> df, cache_hit = DataManager.get_dataset(
            ...     "SELECT * FROM participants"
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
            # OTIMIZAÇÃO: Cache agora retorna DataFrame DIRETO (Pickle)
            # Verificar se é DataFrame (cache novo) ou List[Dict] (cache antigo)
            if isinstance(raw_data, pd.DataFrame):
                logger.info(
                    f"✅ Cache HIT - Returning optimized DataFrame - {cache_time:.3f}s"
                )
                return raw_data, True
            else:
                # Fallback: cache antigo (JSON) - converter para DataFrame
                logger.info(
                    f"Cache HIT (old format) - Converting to DataFrame - {cache_time:.3f}s"
                )
                df = pd.DataFrame(raw_data)
                return df, True
        else:
            # 2. Cache MISS - fetch from BigQuery
            logger.info("❌ Cache MISS - Fetching from BigQuery")
            bq_start = time.perf_counter()
            df = execute_query(query)  # OTIMIZAÇÃO: Já retorna DataFrame!
            bq_time = time.perf_counter() - bq_start
            logger.info(f"BigQuery fetch time: {bq_time:.3f}s")

            if df.empty:
                return pd.DataFrame(), False

            # 3. OTIMIZAÇÃO CRÍTICA: Converter colunas para 'category'
            # Isso acelera filtros em até 100x
            optimize_start = time.perf_counter()

            for col in df.select_dtypes(include=["object"]).columns:
                # Skip columns with numpy arrays (from BigQuery ARRAY columns)
                # Arrays are unhashable and can't be converted to category
                if len(df) > 0:
                    sample_value = df[col].iloc[0]
                    if isinstance(sample_value, np.ndarray):
                        logger.info(
                            f"⏭️  Skipping category optimization for array column '{col}'"
                        )
                        continue

                # Converter para category se a cardinalidade for baixa (< 50% unique)
                try:
                    num_unique = df[col].nunique()
                    num_total = len(df)

                    if num_total > 0 and (num_unique / num_total) < 0.5:
                        df[col] = df[col].astype("category")
                        logger.info(
                            f"Converted '{col}' to category ({num_unique} unique values)"
                        )
                except TypeError as e:
                    # Catch any unhashable type errors (e.g., lists, dicts, arrays)
                    logger.warning(
                        f"⏭️  Skipping category optimization for '{col}': unhashable type ({e})"
                    )
                    continue

            optimize_time = time.perf_counter() - optimize_start
            logger.info(f"Category optimization: {optimize_time:.3f}s")

            # 4. Salvar DataFrame OTIMIZADO no cache (Pickle preserva dtypes)
            cache_write_start = time.perf_counter()
            query_cache.set(query, df)
            cache_write_time = time.perf_counter() - cache_write_start
            logger.info(
                f"💾 Cache write (optimized DataFrame): {cache_write_time:.3f}s"
            )

            total_time = time.perf_counter() - start_time
            logger.info(
                f"get_dataset completed (CACHE MISS) - total: {total_time:.3f}s, rows: {len(df)}"
            )

            return df, False

    @staticmethod
    def apply_filters(df: pd.DataFrame, filters_dict: Dict[str, Any]) -> pd.DataFrame:
        """
        Aplica filtros case-insensitive e sem acentos ao DataFrame.

        Otimizações:
            - Usa máscara booleana acumulativa (evita múltiplas cópias)
            - Normalização vetorizada do pandas (~10-50x mais rápido que .apply())
            - Cache de normalização via TextNormalizer (valores repetidos)
            - Suporta valores únicos ou listas

        Performance:
            - ~0.05s para 179k rows com 2-3 filtros ativos

        Args:
            df: DataFrame a ser filtrado
            filters_dict: {nome_coluna: valor_ou_lista_de_valores}
                         Valores são normalizados (sem acentos, lowercase)

        Returns:
            DataFrame filtrado

        Example:
            >>> df_filtered = DataManager.apply_filters(
            ...     df,
            ...     {'grupo': 'gestante', 'bairro': ['46', '47']}
            ... )
            >>> # 'Gestante' e 'gestante' fazem match
            >>> # 'Criança' e 'crianca' fazem match
        """
        start_time = time.perf_counter()

        if df.empty:
            return df

        initial_rows = len(df)
        filter_times = {}

        # Criar máscara booleana acumulativa (mais eficiente que múltiplas cópias)
        mask = pd.Series([True] * len(df), index=df.index)

        # Aplicar cada filtro usando .isin()
        for col, filter_value in filters_dict.items():
            filter_start = time.perf_counter()

            # Pular se coluna não existe (ou lançar exceção se estrito)
            if col not in df.columns:
                # Por enquanto apenas warning, mas pode ser configurado para raise
                logger.warning(f"Filter column '{col}' not found in DataFrame")
                continue

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

            # Aplicar filtro usando .isin() - case-insensitive e sem acentos
            # OTIMIZAÇÃO: usar str.lower() e str.replace() vetorizadas ao invés de .apply()
            before_filter = mask.sum()

            # Normalizar valores de filtro usando TextNormalizer (com cache)
            normalized_filter_values = [
                TextNormalizer.normalize(str(v)) for v in filter_value
            ]

            # Normalizar coluna usando operações vetorizadas do pandas (muito mais rápido)
            col_normalized = (
                df[col]
                .astype(str)
                .str.normalize("NFD")  # Decompor acentos (vetorizado)
                .str.replace(
                    r"[\u0300-\u036f]", "", regex=True
                )  # Remover acentos (vetorizado)
                .str.lower()  # Lowercase (vetorizado)
            )

            col_mask = col_normalized.isin(normalized_filter_values)
            mask = mask & col_mask
            after_filter = mask.sum()

            filter_time = time.perf_counter() - filter_start
            filter_times[col] = filter_time
            logger.info(
                f"Filter '{col}': {before_filter} -> {after_filter} rows in {filter_time:.3f}s"
            )

        # Aplicar máscara uma única vez no final
        df_filtered = df[mask]

        total_time = time.perf_counter() - start_time
        logger.info(
            f"apply_filters completed - filters: {sum(filter_times.values()):.3f}s, total: {total_time:.3f}s, result: {initial_rows} -> {len(df_filtered)} rows"
        )

        return df_filtered

    @staticmethod
    def apply_search(
        df: pd.DataFrame, search_term: str, search_columns: list[str]
    ) -> pd.DataFrame:
        """
        Aplica busca parcial (contains) em múltiplas colunas.

        A busca é case-insensitive e sem acentos, similar aos filtros.
        Retorna linhas onde o termo aparece em QUALQUER uma das colunas.

        Otimizações:
            - Normalização vetorizada do pandas
            - Busca usando .str.contains() (regex otimizado)
            - OR entre colunas usando | (operador de máscara)

        Performance:
            - ~0.02s para buscar em 2 colunas em 179k rows

        Args:
            df: DataFrame a ser pesquisado
            search_term: Termo de busca (ex: "maria", "123.456")
            search_columns: Lista de colunas para buscar (ex: ['nome', 'cpf'])

        Returns:
            DataFrame filtrado com linhas que contêm o termo

        Example:
            >>> df_searched = DataManager.apply_search(
            ...     df,
            ...     'maria',
            ...     ['nome', 'cpf']
            ... )
            >>> # Encontra "Maria Silva", "Ana Maria", etc
        """
        start_time = time.perf_counter()

        if df.empty or not search_term or not search_columns:
            return df

        # Normalizar termo de busca
        search_normalized = TextNormalizer.normalize(search_term.strip())

        if not search_normalized:
            return df

        logger.info(
            f"Searching for '{search_term}' (normalized: '{search_normalized}') in columns: {search_columns}"
        )

        # Criar máscara OR (qualquer coluna match = True)
        search_mask = pd.Series([False] * len(df), index=df.index)

        for col in search_columns:
            if col not in df.columns:
                logger.warning(f"Search column '{col}' not found in DataFrame")
                continue

            # Normalizar coluna (mesma lógica que apply_filters)
            col_normalized = (
                df[col]
                .astype(str)
                .str.normalize("NFD")
                .str.replace(r"[\u0300-\u036f]", "", regex=True)
                .str.lower()
            )

            # Buscar termo usando contains (partial match)
            col_mask = col_normalized.str.contains(
                search_normalized, na=False, regex=False
            )
            search_mask = search_mask | col_mask

        df_searched = df[search_mask]

        total_time = time.perf_counter() - start_time
        logger.info(
            f"apply_search completed in {total_time:.3f}s - result: {len(df)} -> {len(df_searched)} rows"
        )

        return df_searched

    @staticmethod
    def calculate_filter_options_fast(
        df_original: pd.DataFrame,
        filter_columns_config: Dict[str, Dict[str, str]],
        active_filters: Dict[str, Any],
    ) -> SmartFilterOptions:
        """
        VERSÃO ULTRA-OTIMIZADA de calculate_filter_options.

        OTIMIZAÇÃO: Em vez de chamar apply_filters() N vezes (lento),
        criar UMA máscara booleana para cada filtro e reutilizar.

        Performance: ~100x mais rápido que a versão anterior.
        """
        start_time = time.perf_counter()

        if df_original.empty:
            return SmartFilterOptions()

        # PRÉ-CALCULAR máscaras booleanas para cada filtro ativo
        # Isso evita recalcular a mesma máscara N vezes
        filter_masks = {}
        text_normalizer = TextNormalizer()

        for k, v in active_filters.items():
            if v in [None, "", "todos", "todas"]:
                continue

            # Encontrar coluna correspondente
            if k not in df_original.columns:
                continue

            # OTIMIZAÇÃO: Se a coluna for category, comparação é ~100x mais rápida
            if df_original[k].dtype.name == "category":
                # Category dtype: comparação direta (já está otimizado internamente)
                # Mas ainda precisa normalizar o valor do filtro
                filter_normalized = text_normalizer.normalize(str(v))
                # Normalizar categories também
                col_normalized = (
                    df_original[k].astype(str).apply(text_normalizer.normalize)
                )
                filter_masks[k] = col_normalized == filter_normalized
            else:
                # Object dtype: normalização completa
                col_values = df_original[k].astype(str)
                col_normalized = col_values.apply(text_normalizer.normalize)
                filter_normalized = text_normalizer.normalize(str(v))
                filter_masks[k] = col_normalized == filter_normalized

        filter_options_dict = {}

        for result_key, config in filter_columns_config.items():
            column = config.get("column")
            label_column = config.get("label_column")

            if not column or column not in df_original.columns:
                filter_options_dict[result_key] = []
                continue

            # APLICAR MÁSCARAS: combinar TODAS as máscaras EXCETO a do filtro atual
            combined_mask = pd.Series(
                [True] * len(df_original), index=df_original.index
            )

            for filter_key, mask in filter_masks.items():
                # Pular se for o filtro atual (comparar pela coluna)
                if filter_key == column:
                    continue
                # Aplicar máscara com AND
                combined_mask = combined_mask & mask

            # Aplicar máscara combinada UMA VEZ
            df_filtered = df_original[combined_mask]

            # Pegar valores únicos
            unique_values = df_filtered[column].dropna().unique()

            # Criar label map se necessário
            label_map = {}
            if label_column and label_column in df_filtered.columns:
                label_map = (
                    df_filtered[[column, label_column]]
                    .dropna()
                    .drop_duplicates(column)
                    .set_index(column)[label_column]
                    .to_dict()
                )

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
            f"calculate_filter_options_fast completed in {total_time:.3f}s (OPTIMIZED)"
        )

        return SmartFilterOptions(**filter_options_dict)

    # ========================================================================
    # GOVERNANCE METHODS
    # ========================================================================

    @staticmethod
    def get_user_permissions(cpf: str):
        """
        Fetch permissions for a specific CPF from cached governance table.

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

        # Buscar tabela completa (do cache)
        governance_df, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)

        # DEBUG LOGGING START
        logger.info(f"Auth Check for CPF: '{cpf}'")
        if not governance_df.empty:
            logger.info(
                f"Governance Table Stats: {len(governance_df)} rows. CPF Col Type: {governance_df['cpf'].dtype}"
            )
            # Log sample CPFs to check format (masked for security logs if needed, but safe here for debug)
            # Check for exact match count
            match_count = len(governance_df[governance_df["cpf"] == cpf])
            logger.info(f"Exact matches found: {match_count}")
        else:
            logger.warning("Governance DataFrame is EMPTY!")
        # DEBUG LOGGING END

        # Ensure active column is boolean for robust comparison
        # This handles 'true', 'True', 1, 1.0, etc.
        if "active" in governance_df.columns:
            # Converter para string, lower, comparar com 'true' ou 1
            # Maneira vetorizada e segura
            active_col = governance_df["active"].astype(str).str.lower()
            governance_df["_active_bool"] = active_col.isin(["true", "1", "1.0", "yes"])
        else:
            # Se não tiver coluna active, assumir True (ou False dependendo da regra de negócio)
            # Por segurança, melhor assumir False ou logar erro
            logger.warning(
                "Column 'active' not found in governance table. Defaulting to False."
            )
            governance_df["_active_bool"] = False

        # Filter by CPF only first
        user_rows = governance_df[governance_df["cpf"] == cpf]

        if user_rows.empty:
            # Tentar limpar CPF (remover pontuação) caso o token venha limpo e o banco sujo, ou vice-versa
            # Mas idealmente ambos devem ser apenas números string
            raise PermissionDeniedError(f"CPF {cpf} não cadastrado na base de acessos")

        # Check active status
        user_row = user_rows.iloc[0]
        if not user_row["_active_bool"]:
            raise PermissionDeniedError(f"Usuário {cpf} está inativo")

        # Convert to UserPermissions
        row_dict = user_row.to_dict()

        # Sanitizar valores NaN/NA do pandas (converte para None)
        for key, value in row_dict.items():
            if not isinstance(value, (list, dict)):
                try:
                    if pd.isna(value):
                        row_dict[key] = None
                except (ValueError, TypeError):
                    pass

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
    def apply_governance_filters(df: pd.DataFrame, user_permissions) -> pd.DataFrame:
        """
        Apply governance filters IN MEMORY over cached data.

        CRITICAL: Applied AFTER get_dataset() to not affect shared cache.

        Args:
            df: Complete DataFrame from cache (all participants)
            user_permissions: Current user's permissions

        Returns:
            DataFrame filtered to only data the user can see
        """
        if user_permissions.has_full_access():
            logger.info("Super admin - no governance filters")
            return df

        # Create boolean mask (OR between all authorized IDs)
        mask = pd.Series([False] * len(df), index=df.index)

        # Check each ID type
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
                mask |= df[id_type].isin(ids)

        df_filtered = df[mask]

        logger.info(
            f"Governance filters applied: {len(df)} -> {len(df_filtered)} rows "
            f"(CPF: {user_permissions.cpf})"
        )

        return df_filtered
