"""
Módulo para filtragem e recálculo de protocolos baseado em secretaria_acesso.
Centraliza toda a lógica de governança por secretaria em um único local.
"""
import polars as pl
from typing import Optional, Dict, Any, List
from src.utils.log import logger


def filter_and_recalculate_by_secretaria(
    df: pl.DataFrame,
    secretaria_acesso: str
) -> pl.DataFrame:
    """
    Filtra protocolo_listagem por secretaria e recalcula todos os contadores.

    Args:
        df: DataFrame com coluna protocolo_listagem
        secretaria_acesso: SME, SMS, SMAS, ou TODOS

    Returns:
        DataFrame filtrado com contadores recalculados
    """
    if not secretaria_acesso or secretaria_acesso == "TODOS":
        # Sem filtragem - retorna DataFrame original
        return df

    # IMPORTANTE: Só aplicar se o DataFrame tiver protocolo_listagem (tabela dashboard não tem)
    if "protocolo_listagem" not in df.columns:
        logger.warning(f"⚠️ DataFrame não tem coluna protocolo_listagem - aplicando apenas filtro de equipamentos")
        # Aplicar apenas filtro de equipamentos
        return _drop_equipment_columns(df, secretaria_acesso)

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
    if secretaria_acesso == "TODOS":
        return df

    if secretaria_acesso == "SME":
        # Renomear total_* para educacao_* e setar outras secretarias como null
        df = df.with_columns([
            pl.col("total_protocolos").alias("educacao_protocolos_total"),
            pl.col("total_protocolos_irregular").alias("educacao_protocolos_irregular"),
            pl.col("total_protocolos_atencao").alias("educacao_protocolos_atencao"),
            pl.col("total_protocolos_regular").alias("educacao_protocolos_regular"),
            # Setar outras secretarias como null
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_total"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_regular"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_total"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_regular"),
            # Setar total como null também
            pl.lit(None).cast(pl.Int64).alias("total_protocolos"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_regular"),
        ])

    elif secretaria_acesso == "SMS":
        # Renomear total_* para saude_* e setar outras secretarias como null
        df = df.with_columns([
            pl.col("total_protocolos").alias("saude_protocolos_total"),
            pl.col("total_protocolos_irregular").alias("saude_protocolos_irregular"),
            pl.col("total_protocolos_atencao").alias("saude_protocolos_atencao"),
            pl.col("total_protocolos_regular").alias("saude_protocolos_regular"),
            # Setar outras secretarias como null
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_total"),
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_regular"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_total"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("assistencia_protocolos_regular"),
            # Setar total como null também
            pl.lit(None).cast(pl.Int64).alias("total_protocolos"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_regular"),
        ])

    elif secretaria_acesso == "SMAS":
        # Renomear total_* para assistencia_* e setar outras secretarias como null
        df = df.with_columns([
            pl.col("total_protocolos").alias("assistencia_protocolos_total"),
            pl.col("total_protocolos_irregular").alias("assistencia_protocolos_irregular"),
            pl.col("total_protocolos_atencao").alias("assistencia_protocolos_atencao"),
            pl.col("total_protocolos_regular").alias("assistencia_protocolos_regular"),
            # Setar outras secretarias como null
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_total"),
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("educacao_protocolos_regular"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_total"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("saude_protocolos_regular"),
            # Setar total como null também
            pl.lit(None).cast(pl.Int64).alias("total_protocolos"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_irregular"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_atencao"),
            pl.lit(None).cast(pl.Int64).alias("total_protocolos_regular"),
        ])

    return df


def _recalculate_fractions(df: pl.DataFrame) -> pl.DataFrame:
    """
    Recalcula frações (ex: '2/5') para todas as secretarias.
    Se a coluna for null, a fração também será null.
    """
    return df.with_columns([
        # Total
        pl.when(pl.col("total_protocolos").is_not_null())
        .then(
            pl.col("total_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("total_protocolos").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None))
        .alias("total_fracao"),

        # Educação
        pl.when(pl.col("educacao_protocolos_total").is_not_null())
        .then(
            pl.col("educacao_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("educacao_protocolos_total").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None))
        .alias("educacao_fracao"),

        # Saúde
        pl.when(pl.col("saude_protocolos_total").is_not_null())
        .then(
            pl.col("saude_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("saude_protocolos_total").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None))
        .alias("saude_fracao"),

        # Assistência
        pl.when(pl.col("assistencia_protocolos_total").is_not_null())
        .then(
            pl.col("assistencia_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("assistencia_protocolos_total").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None))
        .alias("assistencia_fracao"),
    ])


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


def filter_equipment_options_by_secretaria(
    filter_options: Dict[str, List[Any]],
    secretaria_acesso: Optional[str]
) -> Dict[str, List[Any]]:
    """
    NÃO filtra mais equipamentos por secretaria.

    PM confirmou que usuários podem ver filtros de todas as secretarias.
    Esta função agora apenas retorna as opções sem modificá-las.

    Args:
        filter_options: Dicionário com as opções de filtros
        secretaria_acesso: SME, SMS, SMAS, TODOS, ou None

    Returns:
        Dicionário sem modificações
    """
    # Retornar sem modificações
    return filter_options
