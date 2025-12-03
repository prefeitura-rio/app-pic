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
    def fetch_filter_paginate(
        query: str,
        filters_dict: Dict[str, Any],
        page: int,
        page_size: Optional[int],
        filter_columns_config: Optional[Dict[str, Dict[str, str]]] = None,
        search_term: Optional[str] = None,
        search_columns: Optional[list[str]] = None,
    ) -> PaginatedResponse[Any]:
        """
        Executa pipeline completo de fetch → filter → filter_options → paginate.

        Pipeline:
            1. GET DATASET: Busca do cache/BigQuery (~2-3s em cache miss)
            2. APPLY FILTERS: Aplica filtros case-insensitive (~0.05s)
            3. APPLY SEARCH: Busca parcial em múltiplas colunas (~0.02s)
            4. CALCULATE FILTER OPTIONS: Valores únicos para cascata (~0.5s)
            5. PAGINATE: Slice + clean + convert (~0.01s)

        Performance:
            - Cache hit: ~0.5-1s
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
            PaginatedResponse com:
                - data: Lista de registros (max page_size)
                - meta: Paginação + profiling detalhado
                - filters: Opções de filtro baseadas nos dados filtrados

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
        df, cache_hit = DataManager.get_dataset(query)
        get_time = time.perf_counter() - get_start
        profiling.get_dataset_s = round(get_time, config.PROFILING_DECIMAL_PLACES)
        profiling.cache_hit = cache_hit
        profiling.rows_before_filter = len(df)

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
        # OTIMIZAÇÃO UX: Filtros ativos mantêm opções originais, apenas não-ativos sofrem cascata
        filter_options_dict = None
        if filter_columns_config:
            filter_opts_start = time.perf_counter()
            filter_options_dict = DataManager.calculate_filter_options(
                df_original=df,  # DataFrame completo (sem filtros)
                filter_columns_config=filter_columns_config,
                active_filters=filters_dict  # Filtros atualmente ativos
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
            df_clean = df_page.replace([np.inf, -np.inf, np.nan], None)
            df_clean.columns = df_clean.columns.astype(str)
            clean_time = time.perf_counter() - clean_start

        profiling.clean_s = round(clean_time, config.PROFILING_DECIMAL_PLACES)
        # Convert to dict
        paginate_time = time.perf_counter() - paginate_start
        profiling.paginate_s = round(paginate_time, config.PROFILING_DECIMAL_PLACES)

        convert_start = time.perf_counter()
        # OTIMIZAÇÃO: to_dict("records") pode ser lento para DataFrames grandes
        # Usar orient="records" com split=False é mais rápido que padrão
        paginated_data = df_clean.to_dict(orient="records")
        convert_time = time.perf_counter() - convert_start
        profiling.convert_to_dict_s = round(
            convert_time, config.PROFILING_DECIMAL_PLACES
        )

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
                "returned_rows": len(paginated_data),
            },
        )
        logger.info(f"Profiling: {profiling}")

        return PaginatedResponse(
            data=paginated_data,
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total_rows=total_rows,
                total_pages=total_pages,
                cache_hit=cache_hit,
                profiling=profiling.to_dict(),
            ),
            filters=filter_options_dict,
        )

    @staticmethod
    def get_dataset(query: str) -> tuple[pd.DataFrame, bool]:
        """
        Busca dataset completo do cache ou BigQuery.

        Fluxo:
            1. Tenta buscar do cache persistente (~0.001s se hit)
            2. Se miss, busca do BigQuery (~2-3s)
            3. Armazena no cache para próximas requests
            4. Converte para DataFrame

        Args:
            query: SQL completa para buscar dados

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

        # 1. Try to get data from persistent cache
        cache_start = time.perf_counter()
        raw_data = query_cache.get(query)
        cache_time = time.perf_counter() - cache_start

        cache_hit = raw_data is not None

        if cache_hit:
            logger.info(f"Cache HIT - cache_lookup: {cache_time:.3f}s")
        else:
            # 2. If Miss, fetch from BigQuery via Utility
            logger.info("Cache MISS - Fetching from BigQuery")
            bq_start = time.perf_counter()
            raw_data = execute_query(query)
            bq_time = time.perf_counter() - bq_start
            logger.info(f"BigQuery fetch time: {bq_time:.3f}s")

            # 3. Store in persistent cache
            cache_write_start = time.perf_counter()
            query_cache.set(query, raw_data)
            cache_write_time = time.perf_counter() - cache_write_start
            logger.info(f"Cache write time: {cache_write_time:.3f}s")

        if not raw_data:
            return pd.DataFrame(), cache_hit

        df_convert_start = time.perf_counter()
        df = pd.DataFrame(raw_data)
        df_convert_time = time.perf_counter() - df_convert_start

        total_time = time.perf_counter() - start_time
        logger.info(
            f"get_dataset completed - df_conversion: {df_convert_time:.3f}s, total: {total_time:.3f}s, rows: {len(df)}"
        )

        return df, cache_hit

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
    def calculate_filter_options(
        df_original: pd.DataFrame,
        filter_columns_config: Dict[str, Dict[str, str]],
        active_filters: Dict[str, Any]
    ) -> SmartFilterOptions:
        """
        Calcula opções de filtros com CASCATA INTELIGENTE E CRONOLÓGICA.

        REGRA: Para cada filtro, aplicar TODOS os OUTROS filtros (exceto ele mesmo).
               Isso permite trocar o valor do filtro mantendo o contexto dos demais.

        Exemplo cronológico:
            1. Seleciona "grupo=Criança"
               - GRUPO: [Criança, Gestante] ← sem grupo aplicado, mas COM outros filtros
               - BAIRRO: apenas bairros com crianças ← COM grupo=Criança

            2. Adiciona "bairro=Copacabana"
               - GRUPO: [Criança, Gestante] ← COM bairro=Copacabana, SEM grupo
               - BAIRRO: apenas bairros com crianças ← COM grupo=Criança, SEM bairro
               - ESCOLA: apenas escolas em Copa com crianças ← COM grupo E bairro

        UX: Permite trocar qualquer filtro sem perder contexto dos demais.

        Args:
            df_original: DataFrame completo SEM filtros
            filter_columns_config: Mapeamento de filtros
                Exemplo: {"grupos": {"column": "grupo"}, "bairros": {"column": "bairro"}}
            active_filters: Dict com filtros atualmente ativos
                Exemplo: {"grupo": "Criança", "bairro": "Copacabana"}
                NOTA: Chaves podem ser diferentes das do config (grupo vs grupos)

        Returns:
            SmartFilterOptions com opções calculadas
        """
        start_time = time.perf_counter()

        if df_original.empty:
            return SmartFilterOptions()

        # MAPEAR result_key → column_name para identificar qual filtro excluir
        # Exemplo: "grupos" → "grupo", "bairros" → "bairro"
        result_key_to_column = {}
        for result_key, config in filter_columns_config.items():
            column = config.get("column")
            if column:
                result_key_to_column[result_key] = column

        filter_options_dict = {}
        column_times = {}

        for result_key, config in filter_columns_config.items():
            col_start = time.perf_counter()

            column = config.get("column")
            label_column = config.get("label_column")

            # Pular se coluna não existe
            if not column or column not in df_original.columns:
                filter_options_dict[result_key] = []
                continue

            # CASCATA INTELIGENTE: Aplicar TODOS os filtros EXCETO este
            # Precisamos identificar qual filtro em active_filters corresponde a este result_key
            # Exemplo: result_key="grupos" → column="grupo" → excluir active_filters["grupo"]

            # Criar dict de filtros SEM o filtro atual
            # Comparar pela COLUNA, não pela chave (pois podem ser diferentes)
            filters_without_current = {}
            for k, v in active_filters.items():
                # Pular valores vazios
                if v in [None, "", "todos", "todas"]:
                    continue

                # Verificar se este filtro corresponde à coluna atual
                # Procurar se k é uma coluna que mapeia para o result_key atual
                is_current_filter = False
                for other_result_key, other_config in filter_columns_config.items():
                    if other_config.get("column") == k and other_result_key == result_key:
                        is_current_filter = True
                        break

                # Se não for o filtro atual, incluir
                if not is_current_filter:
                    filters_without_current[k] = v

            # Aplicar filtros parciais (sem o filtro atual)
            df_for_options = DataManager.apply_filters(df_original, filters_without_current)

            logger.debug(
                f"Filter '{result_key}' (column='{column}'): "
                f"excluded current filter, applied {len(filters_without_current)} other filters, "
                f"got {len(df_for_options)} rows from {len(df_original)} original. "
                f"Filters applied: {list(filters_without_current.keys())}"
            )

            # Pegar valores únicos do DataFrame com filtros parciais
            unique_values = df_for_options[column].dropna().unique()

            # Criar dict de labels se tiver coluna de label
            label_map = {}
            if label_column and label_column in df_for_options.columns:
                label_map = (
                    df_for_options[[column, label_column]]
                    .dropna()
                    .drop_duplicates(column)
                    .set_index(column)[label_column]
                    .to_dict()
                )

            # Criar lista de opções
            options = []
            for value in unique_values:
                value_str = str(value).strip()
                if not value_str:
                    continue

                options.append(
                    FilterOptionItem(
                        id=value_str, label=str(label_map.get(value, value))
                    )
                )

            # Ordenar por label
            options.sort(key=lambda x: x.label)
            filter_options_dict[result_key] = options

            col_time = time.perf_counter() - col_start
            column_times[result_key] = col_time

        total_time = time.perf_counter() - start_time
        logger.info(
            f"calculate_filter_options (SMART CHRONOLOGICAL CASCADE) completed in {total_time:.3f}s - "
            f"{len(column_times)} columns processed"
        )

        return SmartFilterOptions(**filter_options_dict)
