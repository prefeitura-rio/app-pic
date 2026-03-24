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

    # 5. Recalcular contadores por secretaria (renomeia e dropa colunas)
    df_filtered = _recalculate_secretaria_counters(df_filtered, secretaria_acesso)

    # 6. Recalcular frações (apenas para colunas que sobraram)
    df_filtered = _recalculate_fractions(df_filtered)

    # 7. Dropar colunas de equipamentos não-autorizados
    df_filtered = _drop_equipment_columns(df_filtered, secretaria_acesso)

    # LOG: Colunas finais (INFO level para garantir que aparece)
    logger.info(f"📋 Colunas finais após filtragem SME: {df_filtered.columns}")
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
    Mantém apenas colunas da secretaria autorizada, dropa o resto.

    Para usuários com secretaria específica (SME, SMS, SMAS):
    - SME: mantém apenas educacao_*, dropa saude_*, assistencia_*, total_*
    - SMS: mantém apenas saude_*, dropa educacao_*, assistencia_*, total_*
    - SMAS: mantém apenas assistencia_*, dropa educacao_*, saude_*, total_*

    Para admin (TODOS), mantém todas as colunas.
    """
    # Se TODOS, não fazer nada - mantém todas as colunas
    if secretaria_acesso == "TODOS":
        return df

    # Definir colunas de cada secretaria
    educacao_cols = [
        "educacao_protocolos_total", "educacao_protocolos_irregular",
        "educacao_protocolos_atencao", "educacao_protocolos_regular",
        "educacao_fracao"
    ]
    saude_cols = [
        "saude_protocolos_total", "saude_protocolos_irregular",
        "saude_protocolos_atencao", "saude_protocolos_regular",
        "saude_fracao"
    ]
    assistencia_cols = [
        "assistencia_protocolos_total", "assistencia_protocolos_irregular",
        "assistencia_protocolos_atencao", "assistencia_protocolos_regular",
        "assistencia_fracao"
    ]

    # Colunas totais que serão dropadas para usuários de secretaria específica
    total_cols = [
        "total_protocolos", "total_protocolos_irregular",
        "total_protocolos_atencao", "total_protocolos_regular",
        "total_fracao"
    ]

    if secretaria_acesso == "SME":
        logger.debug(f"📋 Colunas ANTES do processamento SME: {df.columns}")

        # Renomear total_* para educacao_* (os valores já foram filtrados)
        df = df.with_columns([
            pl.col("total_protocolos").alias("educacao_protocolos_total"),
            pl.col("total_protocolos_irregular").alias("educacao_protocolos_irregular"),
            pl.col("total_protocolos_atencao").alias("educacao_protocolos_atencao"),
            pl.col("total_protocolos_regular").alias("educacao_protocolos_regular"),
        ])

        # Selecionar apenas colunas permitidas (exclui saude, assistencia, total)
        cols_to_exclude = set(saude_cols + assistencia_cols + total_cols)
        cols_to_keep = [c for c in df.columns if c not in cols_to_exclude]
        logger.debug(f"📋 Mantendo {len(cols_to_keep)} colunas, excluindo {len(cols_to_exclude)} para SME")

        df = df.select(cols_to_keep)
        logger.debug(f"📋 Colunas DEPOIS do select SME: {df.columns}")

    elif secretaria_acesso == "SMS":
        logger.debug(f"📋 Colunas ANTES do processamento SMS: {df.columns}")

        # Renomear total_* para saude_*
        df = df.with_columns([
            pl.col("total_protocolos").alias("saude_protocolos_total"),
            pl.col("total_protocolos_irregular").alias("saude_protocolos_irregular"),
            pl.col("total_protocolos_atencao").alias("saude_protocolos_atencao"),
            pl.col("total_protocolos_regular").alias("saude_protocolos_regular"),
        ])

        # Selecionar apenas colunas permitidas (exclui educacao, assistencia, total)
        cols_to_exclude = set(educacao_cols + assistencia_cols + total_cols)
        cols_to_keep = [c for c in df.columns if c not in cols_to_exclude]
        logger.debug(f"📋 Mantendo {len(cols_to_keep)} colunas, excluindo {len(cols_to_exclude)} para SMS")

        df = df.select(cols_to_keep)
        logger.debug(f"📋 Colunas DEPOIS do select SMS: {df.columns}")

    elif secretaria_acesso == "SMAS":
        logger.debug(f"📋 Colunas ANTES do processamento SMAS: {df.columns}")

        # Renomear total_* para assistencia_*
        df = df.with_columns([
            pl.col("total_protocolos").alias("assistencia_protocolos_total"),
            pl.col("total_protocolos_irregular").alias("assistencia_protocolos_irregular"),
            pl.col("total_protocolos_atencao").alias("assistencia_protocolos_atencao"),
            pl.col("total_protocolos_regular").alias("assistencia_protocolos_regular"),
        ])

        # Selecionar apenas colunas permitidas (exclui educacao, saude, total)
        cols_to_exclude = set(educacao_cols + saude_cols + total_cols)
        cols_to_keep = [c for c in df.columns if c not in cols_to_exclude]
        logger.debug(f"📋 Mantendo {len(cols_to_keep)} colunas, excluindo {len(cols_to_exclude)} para SMAS")

        df = df.select(cols_to_keep)
        logger.debug(f"📋 Colunas DEPOIS do select SMAS: {df.columns}")

    return df


def _recalculate_fractions(df: pl.DataFrame) -> pl.DataFrame:
    """
    Recalcula frações (ex: '2/5') apenas para colunas presentes no DataFrame.

    Para usuários de secretaria específica, apenas a fração da secretaria
    será calculada (ex: SME vê educacao_fracao, não total_fracao).

    Para admin (TODOS), calcula todas as frações.
    """
    fractions_to_add = []

    # Total - só calcular se a coluna existir (admin TODOS)
    if "total_protocolos" in df.columns:
        fractions_to_add.append(
            (pl.col("total_protocolos_regular").cast(pl.Utf8) + "/" +
             pl.col("total_protocolos").cast(pl.Utf8)).alias("total_fracao")
        )

    # Educação - só calcular se a coluna existir
    if "educacao_protocolos_total" in df.columns:
        fractions_to_add.append(
            (pl.col("educacao_protocolos_regular").cast(pl.Utf8) + "/" +
             pl.col("educacao_protocolos_total").cast(pl.Utf8)).alias("educacao_fracao")
        )

    # Saúde - só calcular se a coluna existir
    if "saude_protocolos_total" in df.columns:
        fractions_to_add.append(
            (pl.col("saude_protocolos_regular").cast(pl.Utf8) + "/" +
             pl.col("saude_protocolos_total").cast(pl.Utf8)).alias("saude_fracao")
        )

    # Assistência - só calcular se a coluna existir
    if "assistencia_protocolos_total" in df.columns:
        fractions_to_add.append(
            (pl.col("assistencia_protocolos_regular").cast(pl.Utf8) + "/" +
             pl.col("assistencia_protocolos_total").cast(pl.Utf8)).alias("assistencia_fracao")
        )

    return df.with_columns(fractions_to_add)


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


def _drop_equipment_columns(
    df: pl.DataFrame,
    secretaria_acesso: str
) -> pl.DataFrame:
    """
    Dropa colunas de equipamentos que não pertencem à secretaria do usuário.

    Para usuários com secretaria específica (SME, SMS, SMAS):
    - SME: mantém apenas id_cre, nome_cre, id_escola, nome_escola
    - SMS: mantém apenas id_ap, nome_ap, id_clinica_familia, nome_clinica_familia
    - SMAS: mantém apenas id_cras, nome_cras, id_cas, nome_cas

    Para admin (TODOS), mantém todas as colunas.
    """
    if secretaria_acesso == "TODOS":
        return df

    logger.debug(f"📋 Colunas ANTES do drop de equipamentos: {df.columns}")

    # Colunas de equipamentos por secretaria
    educacao_equipment = ["id_cre", "nome_cre", "id_escola", "nome_escola"]
    saude_equipment = ["id_ap", "nome_ap", "id_clinica_familia", "nome_clinica_familia"]
    assistencia_equipment = ["id_cras", "nome_cras", "id_cas", "nome_cas"]

    cols_to_drop = []

    if secretaria_acesso == "SME":
        # Dropar equipamentos de saúde e assistência
        cols_to_drop = [c for c in saude_equipment + assistencia_equipment if c in df.columns]
    elif secretaria_acesso == "SMS":
        # Dropar equipamentos de educação e assistência
        cols_to_drop = [c for c in educacao_equipment + assistencia_equipment if c in df.columns]
    elif secretaria_acesso == "SMAS":
        # Dropar equipamentos de educação e saúde
        cols_to_drop = [c for c in educacao_equipment + saude_equipment if c in df.columns]

    logger.debug(f"📋 Colunas de equipamentos a excluir para {secretaria_acesso}: {cols_to_drop}")

    if cols_to_drop:
        # Usar select para garantir que as colunas sejam removidas do schema
        cols_to_exclude = set(cols_to_drop)
        cols_to_keep = [c for c in df.columns if c not in cols_to_exclude]
        df = df.select(cols_to_keep)
        logger.debug(f"🗑️  Removed {len(cols_to_drop)} equipment columns for {secretaria_acesso} user")

    logger.debug(f"📋 Colunas DEPOIS da remoção de equipamentos: {df.columns}")

    return df


def filter_equipment_options_by_secretaria(
    filter_options: Dict[str, List[Any]],
    secretaria_acesso: Optional[str]
) -> Dict[str, List[Any]]:
    """
    Filtra as opções de equipamentos baseado na secretaria_acesso do usuário.

    Retorna listas vazias para equipamentos que não pertencem à secretaria:
    - SME: mantém apenas cres, escolas
    - SMS: mantém apenas aps, clinicas
    - SMAS: mantém apenas cras, cas_list
    - TODOS ou None: mantém todos

    Args:
        filter_options: Dicionário com as opções de filtros
        secretaria_acesso: SME, SMS, SMAS, TODOS, ou None

    Returns:
        Dicionário filtrado com listas vazias para equipamentos não-relacionados
    """
    if not secretaria_acesso or secretaria_acesso == "TODOS":
        # Sem filtragem - retorna tudo
        return filter_options

    # Mapeamento de secretaria para equipamentos permitidos
    equipment_mapping = {
        "SME": {"cres", "escolas"},
        "SMS": {"aps", "clinicas"},
        "SMAS": {"cras", "cas_list"},
    }

    allowed_equipment = equipment_mapping.get(secretaria_acesso, set())

    # Lista de todos os equipamentos possíveis
    all_equipment = {"cres", "escolas", "aps", "clinicas", "cras", "cas_list"}

    # Equipamentos a serem zerados
    equipment_to_clear = all_equipment - allowed_equipment

    # Criar cópia do dict original
    filtered_options = filter_options.copy()

    # Setar para None equipamentos não-relacionados (serão excluídos da API)
    for equipment in equipment_to_clear:
        if equipment in filtered_options:
            filtered_options[equipment] = None
            logger.debug(f"🚫 Set {equipment} to None (not allowed for {secretaria_acesso})")

    logger.info(
        f"🔧 Equipment filters adjusted for {secretaria_acesso}: "
        f"allowed={allowed_equipment}, cleared={equipment_to_clear}"
    )

    return filtered_options
