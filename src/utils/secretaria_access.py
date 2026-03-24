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
        secretaria_acesso: SME, SMS, SMAS, TODOS, ou NULL

    Returns:
        DataFrame filtrado com contadores recalculados
    """
    # TODOS = vê tudo (sem filtragem)
    if secretaria_acesso == "TODOS":
        return df

    # IMPORTANTE: Só aplicar se o DataFrame tiver protocolo_listagem (tabela dashboard não tem)
    if "protocolo_listagem" not in df.columns:
        logger.warning(f"⚠️ DataFrame não tem coluna protocolo_listagem - skip filtro de protocolos")
        return df

    # NULL ou vazio = sem acesso a protocolos (remover TODOS)
    if not secretaria_acesso or secretaria_acesso == "NULL":
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

    # 2. MANTER participantes mesmo sem protocolos da secretaria
    # Motivo: Usuário pode ter acesso via equipamento (ex: escola) a participantes
    # que não têm protocolos da secretaria dele (ex: SME vê escola com aluno só com protocolo SMS)
    # Os contadores ficarão zerados mas o participante continua visível

    # 3. Recalcular contadores totais (podem ser 0 se não houver protocolos da secretaria)
    df_filtered = _recalculate_total_counters(df_filtered)

    # 4. Recalcular situacao (ANTES de dropar colunas total_*)
    df_filtered = _recalculate_situacao(df_filtered)

    # 5. Recalcular contadores por secretaria (NÃO dropa mais, apenas recalcula)
    df_filtered = _recalculate_secretaria_counters(df_filtered, secretaria_acesso)

    # 6. Recalcular frações
    df_filtered = _recalculate_fractions(df_filtered)

    logger.info(f"✅ Filtrado: {len(df_filtered)} participantes (protocolos filtrados para {secretaria_acesso})")

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
    # Mapeamento de secretaria_acesso para prefixo de coluna
    SECRETARIA_MAP = {
        "SME": "educacao",
        "SMS": "saude",
        "SMAS": "assistencia",
    }

    # Tipos de contadores (NOTA: coluna total é "total_protocolos", sem sufixo _total)
    COUNTER_SUFFIXES = ["", "_irregular", "_atencao", "_regular"]

    # Se TODOS, não fazer nada - mantém todas as colunas
    if secretaria_acesso == "TODOS":
        return df

    # Construir lista de colunas dinamicamente
    columns = []

    # Se NULL (sem acesso), setar TODAS as colunas como null
    if not secretaria_acesso or secretaria_acesso == "NULL":
        # Setar contadores totais como null
        for suffix in COUNTER_SUFFIXES:
            columns.append(pl.lit(None).cast(pl.Int64).alias(f"total_protocolos{suffix}"))

        # Setar todas as secretarias como null
        for prefix in SECRETARIA_MAP.values():
            for suffix in COUNTER_SUFFIXES:
                # Para secretarias, o primeiro é sempre _total
                sec_suffix = "_total" if suffix == "" else suffix
                columns.append(pl.lit(None).cast(pl.Int64).alias(f"{prefix}_protocolos{sec_suffix}"))

    # Secretaria específica (SME, SMS, SMAS)
    elif secretaria_acesso in SECRETARIA_MAP:
        active_prefix = SECRETARIA_MAP[secretaria_acesso]

        # Renomear total_protocolos* para a secretaria ativa
        for suffix in COUNTER_SUFFIXES:
            # Para secretarias, o primeiro é sempre _total (não vazio)
            sec_suffix = "_total" if suffix == "" else suffix
            columns.append(pl.col(f"total_protocolos{suffix}").alias(f"{active_prefix}_protocolos{sec_suffix}"))

        # Setar outras secretarias como null
        for sec_code, prefix in SECRETARIA_MAP.items():
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
    return df.with_columns([
        # Total
        pl.when(pl.col("total_protocolos").is_not_null())
        .then(
            pl.col("total_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("total_protocolos").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None).cast(pl.Utf8))
        .alias("total_fracao"),

        # Educação
        pl.when(pl.col("educacao_protocolos_total").is_not_null())
        .then(
            pl.col("educacao_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("educacao_protocolos_total").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None).cast(pl.Utf8))
        .alias("educacao_fracao"),

        # Saúde
        pl.when(pl.col("saude_protocolos_total").is_not_null())
        .then(
            pl.col("saude_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("saude_protocolos_total").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None).cast(pl.Utf8))
        .alias("saude_fracao"),

        # Assistência
        pl.when(pl.col("assistencia_protocolos_total").is_not_null())
        .then(
            pl.col("assistencia_protocolos_regular").cast(pl.Utf8) + "/" +
            pl.col("assistencia_protocolos_total").cast(pl.Utf8)
        )
        .otherwise(pl.lit(None).cast(pl.Utf8))
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
