"""
Módulo para filtragem e recálculo de protocolos baseado em secretarias_acesso.
Centraliza toda a lógica de governança por secretaria em um único local.
"""
import polars as pl
from typing import List
from src.utils.log import logger
from src.utils.constants import (
    SECRETARIA_SME,
    SECRETARIA_SMS,
    SECRETARIA_SMAS,
    SECRETARIA_COLUMN_PREFIX,
)

# ============================================================================
# CONSTANTES LOCAIS
# ============================================================================

_ALL_SECRETARIAS = {SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS}

# Tipos de contadores (NOTA: coluna total é "total_protocolos", sem sufixo _total)
COUNTER_SUFFIXES = ["", "_irregular", "_atencao", "_regular"]

# ============================================================================
# FUNÇÕES PÚBLICAS
# ============================================================================


def get_allowed_secretaria_options(
    user_is_super_admin: bool,
    user_secretarias_acesso: List[str],
) -> List[str]:
    """
    Retorna lista de secretarias que o usuário pode atribuir a outros usuários.

    Args:
        user_is_super_admin: Se o usuário é super admin
        user_secretarias_acesso: Secretarias do usuário (subset de SME/SMS/SMAS)

    Returns:
        Lista de códigos permitidos (SME, SMS, SMAS). Uma lista vazia
        (= sem acesso a nenhuma) é sempre atribuível por qualquer admin,
        já que remover/zerar acesso nunca é um privilege escalation.
    """
    if user_is_super_admin:
        return [SECRETARIA_SME, SECRETARIA_SMS, SECRETARIA_SMAS]

    return list(user_secretarias_acesso)


def filter_and_recalculate_by_secretaria(
    df: pl.DataFrame,
    secretarias_acesso: List[str],
) -> pl.DataFrame:
    """
    Filtra protocolo_listagem pelas secretarias do usuário e recalcula
    todos os contadores.

    Args:
        df: DataFrame com coluna protocolo_listagem
        secretarias_acesso: Subset de {SME, SMS, SMAS}. Vazio = sem acesso
            a nenhum protocolo. As três = acesso total (sem filtragem).

    Returns:
        DataFrame filtrado com contadores recalculados
    """
    # Acesso total (as 3 secretarias) = vê tudo, sem filtragem
    if set(secretarias_acesso) >= _ALL_SECRETARIAS:
        return df

    # IMPORTANTE: Só aplicar se o DataFrame tiver protocolo_listagem (tabela dashboard não tem)
    if "protocolo_listagem" not in df.columns:
        logger.warning("⚠️ DataFrame não tem coluna protocolo_listagem - skip filtro de protocolos")
        return df

    # Vazio = sem acesso a nenhum protocolo (remover todos)
    if not secretarias_acesso:
        logger.info("🚫 Usuário sem acesso a protocolos - removendo todos os protocolos")
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
        df_filtered = _recalculate_secretaria_counters(df_filtered, secretarias_acesso)
        # Recalcular frações (todas null)
        df_filtered = _recalculate_fractions(df_filtered)
        # Recalcular situacao (null)
        df_filtered = df_filtered.with_columns([
            pl.lit(None).alias("situacao")
        ])
        logger.info(f"✅ Removidos todos os protocolos: {len(df_filtered)} participantes")
        return df_filtered

    logger.info(f"🔒 Filtrando protocolos por secretarias: {secretarias_acesso}")

    # 1. Filtrar array protocolo_listagem para manter só as secretarias permitidas
    df_filtered = df.with_columns([
        pl.when(pl.col("protocolo_listagem").is_not_null())
        .then(
            pl.col("protocolo_listagem").list.eval(
                pl.element().filter(
                    pl.element().struct.field("secretaria").is_in(secretarias_acesso)
                )
            )
        )
        .otherwise(pl.lit([]))
        .alias("protocolo_listagem")
    ])

    # 2. Remover participantes sem protocolos nas secretarias permitidas
    df_filtered = df_filtered.filter(
        pl.col("protocolo_listagem").list.len() > 0
    )

    # 3. Recalcular contadores totais (soma de todas as secretarias permitidas)
    df_filtered = _recalculate_total_counters(df_filtered)

    # 4. Recalcular situacao (ANTES de anular colunas total_*)
    df_filtered = _recalculate_situacao(df_filtered)

    # 5. Recalcular contadores por secretaria (uma coluna por secretaria permitida,
    #    demais anuladas)
    df_filtered = _recalculate_secretaria_counters(df_filtered, secretarias_acesso)

    # 6. Recalcular frações
    df_filtered = _recalculate_fractions(df_filtered)

    logger.info(f"✅ Filtrado: {len(df_filtered)} participantes com protocolos {secretarias_acesso}")

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
    secretarias_acesso: List[str],
) -> pl.DataFrame:
    """
    Recalcula contadores por secretaria e seta secretarias sem acesso como null.

    PM confirmou que não há problema em usuários verem colunas null de outras secretarias.
    """
    # Acesso total, não faz nada - mantém todas as colunas
    if set(secretarias_acesso) >= _ALL_SECRETARIAS:
        return df

    columns = []

    # Acesso parcial (0, 1 ou 2 secretarias): total_* não é exibido nesse caso
    # (só faz sentido com acesso total), então sempre anulamos.
    for suffix in COUNTER_SUFFIXES:
        columns.append(pl.lit(None).cast(pl.Int64).alias(f"total_protocolos{suffix}"))

    for sec_code, prefix in SECRETARIA_COLUMN_PREFIX.items():
        if sec_code in secretarias_acesso:
            sec_field = pl.element().struct.field("secretaria") == sec_code

            columns.append(
                pl.col("protocolo_listagem").list.eval(sec_field)
                .list.sum().cast(pl.Int64).alias(f"{prefix}_protocolos_total")
            )
            columns.append(
                pl.col("protocolo_listagem").list.eval(
                    sec_field & (pl.element().struct.field("irregular_indicador") == "true")
                ).list.sum().cast(pl.Int64).alias(f"{prefix}_protocolos_irregular")
            )
            columns.append(
                pl.col("protocolo_listagem").list.eval(
                    sec_field & (pl.element().struct.field("protocolo_status_label") == "Atenção")
                ).list.sum().cast(pl.Int64).alias(f"{prefix}_protocolos_atencao")
            )
            columns.append(
                pl.col("protocolo_listagem").list.eval(
                    sec_field & (pl.element().struct.field("protocolo_status_label") == "Regular")
                ).list.sum().cast(pl.Int64).alias(f"{prefix}_protocolos_regular")
            )
        else:
            for suffix in COUNTER_SUFFIXES:
                sec_suffix = "_total" if suffix == "" else suffix
                columns.append(pl.lit(None).cast(pl.Int64).alias(f"{prefix}_protocolos{sec_suffix}"))

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
