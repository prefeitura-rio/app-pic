import pandas as pd
import numpy as np
from typing import List, Dict, Any, TypeVar, Optional
from math import ceil
import time
import unicodedata

from src.utils.bigquery import execute_query
from src.utils.log import logger
from src.utils.cache_manager import query_cache
from src.api.v1.schemas import (
    PaginatedResponse,
    PaginationMeta,
    SmartFilterOptions,
    FilterOptionItem,
)

T = TypeVar("T")


def normalize_string(text: str) -> str:
    """
    Normaliza string removendo acentos e convertendo para lowercase.

    Exemplos:
        'Criança' -> 'crianca'
        'São Paulo' -> 'sao paulo'
        'GESTANTE' -> 'gestante'
    """
    # Normaliza para NFD (decompõe caracteres acentuados)
    nfd = unicodedata.normalize("NFD", text)
    # Remove marcas diacríticas (acentos)
    without_accents = "".join(
        char for char in nfd if unicodedata.category(char) != "Mn"
    )
    # Converte para lowercase
    return without_accents.lower()


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
        page_size: int,
        filter_columns_config: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> PaginatedResponse[Any]:
        """
        Método único que executa todo o pipeline: fetch -> filter -> filter_options -> paginate
        com profiling detalhado de cada etapa.

        Args:
            query: SQL query para buscar dados
            filters_dict: Filtros a aplicar {coluna: valor}
            page: Número da página
            page_size: Tamanho da página
            filter_columns_config: Config para calcular opções de filtros

        Returns:
            PaginatedResponse com dados paginados e profiling completo
        """
        pipeline_start = time.perf_counter()
        profiling = {}

        # 1. GET DATASET (cache + DataFrame conversion)
        get_start = time.perf_counter()
        df = DataManager.get_dataset(query)
        get_time = time.perf_counter() - get_start
        profiling["get_dataset_s"] = round(get_time, 3)

        # 2. APPLY FILTERS
        filter_start = time.perf_counter()
        df_filtered = DataManager.apply_filters(df, filters_dict)
        filter_time = time.perf_counter() - filter_start
        profiling["apply_filters_s"] = round(filter_time, 3)

        # 3. CALCULATE FILTER OPTIONS (sobre dados filtrados COMPLETOS)
        filter_options_dict = None
        if filter_columns_config:
            filter_opts_start = time.perf_counter()
            filter_options_dict = DataManager.calculate_filter_options(
                df_filtered, filter_columns_config
            )
            filter_opts_time = time.perf_counter() - filter_opts_start
            profiling["filter_options_s"] = round(filter_opts_time, 3)
        else:
            profiling["filter_options_s"] = 0

        # 4. PAGINATE (última etapa)
        paginate_start = time.perf_counter()

        total_rows = len(df_filtered)
        total_pages = ceil(total_rows / page_size) if total_rows > 0 else 0
        if page < 1:
            page = 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        # Slice
        df_page = df_filtered.iloc[start_idx:end_idx]

        # Clean (NaN/Inf)
        df_clean = df_page.replace([np.inf, -np.inf, np.nan], None)
        df_clean.columns = df_clean.columns.astype(str)

        # Convert to dict
        paginated_data = df_clean.to_dict("records")

        paginate_time = time.perf_counter() - paginate_start
        profiling["paginate_s"] = round(paginate_time, 3)

        # 5. TOTAL TIME
        pipeline_time = time.perf_counter() - pipeline_start
        profiling["total_pipeline_s"] = round(pipeline_time, 3)

        logger.info(
            f"fetch_filter_paginate completed in {pipeline_time:.3f}s - "
            f"get:{profiling['get_dataset_s']}s, filter:{profiling['apply_filters_s']}s, "
            f"filter_opts:{profiling['filter_options_s']}s, paginate:{profiling['paginate_s']}s - "
            f"returned {len(paginated_data)}/{total_rows} rows"
        )

        return PaginatedResponse(
            data=paginated_data,
            meta=PaginationMeta(
                page=page,
                page_size=page_size,
                total_rows=total_rows,
                total_pages=total_pages,
                cache_hit=True,
                profiling=profiling,
            ),
            filters=filter_options_dict,
        )

    @staticmethod
    def get_dataset(query: str) -> pd.DataFrame:
        """
        Retrieves the full dataset from cache or BigQuery and returns it as a Pandas DataFrame.
        """
        start_time = time.perf_counter()

        # 1. Try to get data from persistent cache
        cache_start = time.perf_counter()
        raw_data = query_cache.get(query)
        cache_time = time.perf_counter() - cache_start

        if raw_data is not None:
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
            return pd.DataFrame()

        df_convert_start = time.perf_counter()
        df = pd.DataFrame(raw_data)
        df_convert_time = time.perf_counter() - df_convert_start

        total_time = time.perf_counter() - start_time
        logger.info(
            f"get_dataset completed - df_conversion: {df_convert_time:.3f}s, total: {total_time:.3f}s, rows: {len(df)}"
        )

        return df

    @staticmethod
    def apply_filters(df: pd.DataFrame, filters_dict: Dict[str, Any]) -> pd.DataFrame:
        """
        Aplica filtros ao DataFrame usando .isin() do pandas.

        Args:
            df: DataFrame a ser filtrado
            filters_dict: {nome_coluna: valor_ou_lista_de_valores}
                         Ex: {'bairro': '46', 'grupo': 'Gestante'}
                         Ex: {'bairro': ['46', '47'], 'status': ['ativo']}

        Returns:
            DataFrame filtrado
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

            # Pular se coluna não existe
            if col not in df.columns:
                logger.warning(
                    f"Column '{col}' not found in DataFrame. Available columns: {list(df.columns)}"
                )
                continue

            # Converter para lista se não for
            if not isinstance(filter_value, list):
                filter_value = [filter_value]

            # Pular valores vazios
            filter_value = [
                v
                for v in filter_value
                if v and str(v).strip() and str(v) not in ("todos", "todas")
            ]
            if not filter_value:
                continue

            # Aplicar filtro usando .isin() - case-insensitive e sem acentos
            # Normalizar tanto os valores do DataFrame quanto os filtros
            before_filter = mask.sum()
            normalized_filter_values = [normalize_string(str(v)) for v in filter_value]
            col_mask = (
                df[col]
                .astype(str)
                .apply(normalize_string)
                .isin(normalized_filter_values)
            )
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
    def calculate_filter_options(
        df: pd.DataFrame, columns_config: Dict[str, Dict[str, str]]
    ) -> SmartFilterOptions:
        """
        Calcula opções de filtros disponíveis usando .unique() do pandas.

        Args:
            df: DataFrame com os dados
            columns_config: Configuração de colunas
                {
                    'bairros': {'column': 'bairro'},
                    'cras': {'column': 'id_cras', 'label_column': 'nome_cras'},
                }

        Returns:
            SmartFilterOptions com valores únicos por coluna
        """
        start_time = time.perf_counter()

        if df.empty:
            return SmartFilterOptions()

        filter_options_dict = {}
        column_times = {}

        for result_key, config in columns_config.items():
            col_start = time.perf_counter()

            column = config.get("column")
            label_column = config.get("label_column")

            # Pular se coluna não existe
            if not column or column not in df.columns:
                filter_options_dict[result_key] = []
                continue

            # Pegar valores únicos
            unique_values = df[column].dropna().unique()

            # Criar dict de labels se tiver coluna de label
            label_map = {}
            if label_column and label_column in df.columns:
                label_map = (
                    df[[column, label_column]]
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
            f"calculate_filter_options completed in {total_time:.3f}s - {len(column_times)} columns processed"
        )

        return SmartFilterOptions(**filter_options_dict)
