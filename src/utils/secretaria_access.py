"""
Módulo para filtragem e recálculo de protocolos baseado em secretaria_acesso.
Centraliza toda a lógica de governança por secretaria em um único local.
"""
import polars as pl
from typing import Optional, List
from src.utils.log import logger
from src.utils.constants import (
    SECRETARIA_TODOS,
    SECRETARIA_NULL,
    SECRETARIA_SME,
    SECRETARIA_SMS,
    SECRETARIA_SMAS,
    SECRETARIA_COLUMN_PREFIX,
)

# ============================================================================
# CONSTANTES LOCAIS
# ============================================================================

# Tipos de contadores (NOTA: coluna total é "total_protocolos", sem sufixo _total)
COUNTER_SUFFIXES = ["", "_irregular", "_atencao", "_regular"]

# ============================================================================
# FUNÇÕES PÚBLICAS
# ============================================================================


def get_allowed_secretaria_options(
    user_is_super_admin: bool,
    user_secretaria_acesso: Optional[str]
) -> List[str]:
    """
    Retorna lista de valores de secretaria_acesso que o usuário pode atribuir.

    Args:
        user_is_super_admin: Se o usuário é super admin
        user_secretaria_acesso: Valor de secretaria_acesso do usuário

    Returns:
        Lista de valores permitidos (NULL, TODOS, SME, SMS, SMAS)
    """
    # Super admin pode atribuir tudo
    if user_is_super_admin:
        return [SECRETARIA_NULL, SECRETARIA_TODOS, SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS]

    # Admin com TODOS pode atribuir tudo
    if user_secretaria_acesso == SECRETARIA_TODOS:
        return [SECRETARIA_NULL, SECRETARIA_TODOS, SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS]

    # Admin com secretaria específica pode atribuir NULL ou sua secretaria
    if user_secretaria_acesso in SECRETARIA_COLUMN_PREFIX:
        return [SECRETARIA_NULL, user_secretaria_acesso]

    # Admin sem secretaria_acesso pode atribuir apenas NULL
    return [SECRETARIA_NULL]


def filter_and_recalculate_by_secretaria(
    df: pl.DataFrame,
    secretaria_acesso: str
) -> pl.DataFrame:
    """
    Filtra protocolo_listagem por secretaria e recalcula todos os contadores.

    Args:
        df: DataFrame com coluna protocolo_listagem
        secretaria_acesso: SME, SMS, SMAS, TODOS, ou NULL

    Returns:
        DataFrame filtrado com contadores recalculados
    """
    # TODOS = vê tudo (sem filtragem)
    if secretaria_acesso == SECRETARIA_TODOS:
        return df

    # IMPORTANTE: Só aplicar se o DataFrame tiver protocolo_listagem (tabela dashboard não tem)
    if "protocolo_listagem" not in df.columns:
        logger.warning(f"⚠️ DataFrame não tem coluna protocolo_listagem - skip filtro de protocolos")
        return df

    # NULL ou vazio = sem acesso a protocolos (remover TODOS)
    if not secretaria_acesso or secretaria_acesso == SECRETARIA_NULL:
        logger.info(f"🚫 Usuário sem acesso a protocolos - removendo todos os protocolos")
        # Esvaziar lista de protocolos mantendo o schema (filtrar com condição impossível)
        df_filtered = df.with_columns([
            pl.when(pl.col("protocolo_listagem").is_not_null())
            .then(
                pl.col("protocolo_listagem").list.eval(
                    pl.element().filter(
                        pl.element().struct.field("id") == "__IMPOSSIVEL__"  # Condição impossível = lista vazia
                    )
                )
            )
            .otherwise(pl.lit([]))
            .alias("protocolo_listagem")
        ])
        # Não remover participantes (diferente de secretaria específica)
        # Apenas recalcular contadores (todos vão para null)
        df_filtered = _recalculate_secretaria_counters(df_filtered, secretaria_acesso)
        # Recalcular frações (todas null)
        df_filtered = _recalculate_fractions(df_filtered)
        # Recalcular situacao (null)
        df_filtered = df_filtered.with_columns([
            pl.lit(None).alias("situacao")
        ])
        logger.info(f"✅ Removidos todos os protocolos: {len(df_filtered)} participantes")
        return df_filtered

    logger.info(f"🔒 Filtrando protocolos por secretaria: {secretaria_acesso}")

    # 1. Filtrar array protocolo_listagem por secretaria
    df_filtered = df.with_columns([
        pl.when(pl.col("protocolo_listagem").is_not_null())
        .then(
            pl.col("protocolo_listagem").list.eval(
                pl.element().filter(
                    pl.element().struct.field("secretaria") == secretaria_acesso
                )
            )
        )
        .otherwise(pl.lit([]))
        .alias("protocolo_listagem")
    ])

    # 2. Remover participantes sem protocolos da secretaria
    df_filtered = df_filtered.filter(
        pl.col("protocolo_listagem").list.len() > 0
    )

    # 3. Recalcular contadores totais
    df_filtered = _recalculate_total_counters(df_filtered)

    # 4. Recalcular situacao (ANTES de dropar colunas total_*)
    df_filtered = _recalculate_situacao(df_filtered)

    # 5. Recalcular contadores por secretaria (NÃO dropa mais, apenas recalcula)
    df_filtered = _recalculate_secretaria_counters(df_filtered, secretaria_acesso)

    # 6. Recalcular frações
    df_filtered = _recalculate_fractions(df_filtered)

    logger.info(f"✅ Filtrado: {len(df_filtered)} participantes com protocolos {secretaria_acesso}")

    return df_filtered


def _recalculate_total_counters(df: pl.DataFrame) -> pl.DataFrame:
    """Recalcula contadores totais baseado no array protocolo_listagem filtrado."""
    # IMPORTANTE: irregular_indicador vem como STRING ("true"/"false"), não boolean
    return df.with_columns([
        # Total geral
        pl.col("protocolo_listagem").list.len().cast(pl.Int64).alias("total_protocolos"),

        # Contar irregulares (irregular_indicador == "true")
        pl.col("protocolo_listagem").list.eval(
            pl.element().struct.field("irregular_indicador") == "true"
        ).list.sum().cast(pl.Int64).alias("total_protocolos_irregular"),

        # Contar atenção (protocolo_status_label == "Atenção")
        pl.col("protocolo_listagem").list.eval(
            pl.element().struct.field("protocolo_status_label") == "Atenção"
        ).list.sum().cast(pl.Int64).alias("total_protocolos_atencao"),

        # Contar regulares (protocolo_status_label == "Regular")
        pl.col("protocolo_listagem").list.eval(
            pl.element().struct.field("protocolo_status_label") == "Regular"
        ).list.sum().cast(pl.Int64).alias("total_protocolos_regular"),
    ])


def _recalculate_secretaria_counters(
    df: pl.DataFrame,
    secretaria_acesso: str
) -> pl.DataFrame:
    """
    Recalcula contadores por secretaria e seta outras secretarias como null.

    PM confirmou que não há problema em usuários verem colunas null de outras secretarias.
    """
    # Se TODOS, não fazer nada - mantém todas as colunas
    if secretaria_acesso == SECRETARIA_TODOS:
        return df

    # Construir lista de colunas dinamicamente
    columns = []

    # Se NULL (sem acesso), setar TODAS as colunas como null
    if not secretaria_acesso or secretaria_acesso == SECRETARIA_NULL:
        # Setar contadores totais como null
        for suffix in COUNTER_SUFFIXES:
            columns.append(pl.lit(None).cast(pl.Int64).alias(f"total_protocolos{suffix}"))

        # Setar todas as secretarias como null
        for prefix in SECRETARIA_COLUMN_PREFIX.values():
            for suffix in COUNTER_SUFFIXES:
                # Para secretarias, o primeiro é sempre _total
                sec_suffix = "_total" if suffix == "" else suffix
                columns.append(pl.lit(None).cast(pl.Int64).alias(f"{prefix}_protocolos{sec_suffix}"))

    # Secretaria específica (SME, SMS, SMAS)
    elif secretaria_acesso in SECRETARIA_COLUMN_PREFIX:
        active_prefix = SECRETARIA_COLUMN_PREFIX[secretaria_acesso]

        # Renomear total_protocolos* para a secretaria ativa
        for suffix in COUNTER_SUFFIXES:
            # Para secretarias, o primeiro é sempre _total (não vazio)
            sec_suffix = "_total" if suffix == "" else suffix
            columns.append(pl.col(f"total_protocolos{suffix}").alias(f"{active_prefix}_protocolos{sec_suffix}"))

        # Setar outras secretarias como null
        for sec_code, prefix in SECRETARIA_COLUMN_PREFIX.items():
            if sec_code != secretaria_acesso:  # Pular a secretaria ativa
                for suffix in COUNTER_SUFFIXES:
                    sec_suffix = "_total" if suffix == "" else suffix
                    columns.append(pl.lit(None).cast(pl.Int64).alias(f"{prefix}_protocolos{sec_suffix}"))

        # Setar total como null
        for suffix in COUNTER_SUFFIXES:
            columns.append(pl.lit(None).cast(pl.Int64).alias(f"total_protocolos{suffix}"))

    return df.with_columns(columns)


def _recalculate_fractions(df: pl.DataFrame) -> pl.DataFrame:
    """
    Recalcula frações (ex: '2/5') para todas as secretarias.
    Se a coluna for null, a fração também será null.
    """
    # Construir colunas de fração dinamicamente para evitar repetição
    fraction_columns = []

    # Total
    fraction_columns.append(
        pl.when(pl.col("total_protocolos").is_not_null())
        .then(
            pl.col("total_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("total_protocolos").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None).cast(pl.Utf8))
        .alias("total_fracao")
    )

    # Frações por secretaria (usando loop para evitar repetição)
    for prefix in SECRETARIA_COLUMN_PREFIX.values():
        fraction_columns.append(
            pl.when(pl.col(f"{prefix}_protocolos_total").is_not_null())
            .then(
                pl.col(f"{prefix}_protocolos_regular").cast(pl.Utf8) + "/" +
                pl.col(f"{prefix}_protocolos_total").cast(pl.Utf8)
            )
            .otherwise(pl.lit(None).cast(pl.Utf8))
            .alias(f"{prefix}_fracao")
        )

    return df.with_columns(fraction_columns)


def _recalculate_situacao(df: pl.DataFrame) -> pl.DataFrame:
    """Recalcula coluna situacao baseado nos contadores filtrados."""
    return df.with_columns([
        pl.when(pl.col("total_protocolos") == 0)
        .then(pl.lit("Sem protocolos"))
        .when(pl.col("total_protocolos_irregular") == 0)
        .then(pl.lit("Regular"))
        .when((pl.col("total_protocolos_irregular") > 0) & (pl.col("total_protocolos_atencao") == 0))
        .then(pl.lit("Irregular"))
        .otherwise(pl.lit("Atenção"))
        .alias("situacao")
    ])
