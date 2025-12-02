from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Union

from src.core.security.jwt import verify_jwt
from src.config import env
from src.utils.log import logger
from src.api.v1.schemas import (
    Participante,
    ProtocoloDetalhes,
    PaginatedResponse,
    CommonFilters,
    PaginationParams,
    SmartFilterOptions,
    FilterOptionItem,
    FilterOptionCounts,
)
from src.utils.data_manager import DataManager

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    dependencies=[Depends(verify_jwt)],
)


@router.get(
    "/filter-options",
    summary="Opções de filtros com contadores (otimizado com SQL)",
    response_model=SmartFilterOptions,
)
async def get_filter_options() -> Any:
    """
    Retorna opções de filtros com contadores calculados diretamente no BigQuery.
    Muito mais rápido que calcular no Python.
    """
    # Query agregada que calcula contadores no BQ
    query = f"""
    WITH base_data AS (
        SELECT
            bairro,
            grupo,
            CAST(cohort AS STRING) as cohort,
            status,
            id_cre,
            id_cras,
            id_escola,
            nome_escola,
            id_clinica_familia,
            nome_clinica_familia,
            nome_cras
        FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    )

    -- Contadores por bairro
    SELECT
        'bairro' as tipo,
        bairro as id,
        bairro as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE bairro IS NOT NULL AND TRIM(bairro) != ''
    GROUP BY bairro

    UNION ALL

    -- Contadores por grupo
    SELECT
        'grupo' as tipo,
        grupo as id,
        grupo as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE grupo IS NOT NULL AND TRIM(grupo) != ''
    GROUP BY grupo

    UNION ALL

    -- Contadores por cohort
    SELECT
        'cohort' as tipo,
        cohort as id,
        cohort as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE cohort IS NOT NULL AND TRIM(cohort) != ''
    GROUP BY cohort

    UNION ALL

    -- Contadores por status
    SELECT
        'status' as tipo,
        status as id,
        status as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE status IS NOT NULL AND TRIM(status) != ''
    GROUP BY status

    UNION ALL

    -- Contadores por CRE
    SELECT
        'cre' as tipo,
        id_cre as id,
        id_cre as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE id_cre IS NOT NULL AND TRIM(id_cre) != ''
    GROUP BY id_cre

    UNION ALL

    -- Contadores por CRAS
    SELECT
        'cras' as tipo,
        id_cras as id,
        COALESCE(nome_cras, id_cras) as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE id_cras IS NOT NULL AND TRIM(id_cras) != ''
    GROUP BY id_cras, nome_cras

    UNION ALL

    -- Contadores por escola
    SELECT
        'escola' as tipo,
        id_escola as id,
        COALESCE(nome_escola, id_escola) as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE id_escola IS NOT NULL AND TRIM(id_escola) != ''
    GROUP BY id_escola, nome_escola

    UNION ALL

    -- Contadores por clínica
    SELECT
        'clinica' as tipo,
        id_clinica_familia as id,
        COALESCE(nome_clinica_familia, id_clinica_familia) as label,
        COUNT(*) as total,
        COUNTIF(LOWER(grupo) LIKE '%crianca%') as crianca,
        COUNTIF(LOWER(grupo) LIKE '%gestante%') as gestante,
        COUNTIF(status = 'ativo') as ativo,
        COUNTIF(status = 'inativo') as inativo
    FROM base_data
    WHERE id_clinica_familia IS NOT NULL AND TRIM(id_clinica_familia) != ''
    GROUP BY id_clinica_familia, nome_clinica_familia

    ORDER BY tipo, label
    """

    logger.info("Fetching filter options with SQL aggregation")

    try:
        df = DataManager.get_dataset(query)

        if df.empty:
            return SmartFilterOptions()

        # Organizar dados por tipo
        result = SmartFilterOptions(
            bairros=[],
            grupos=[],
            cohorts=[],
            status_list=[],
            cres=[],
            cras=[],
            escolas=[],
            clinicas=[],
            total_participantes=0
        )

        for _, row in df.iterrows():
            item = FilterOptionItem(
                id=str(row['id']),
                label=str(row['label']),
                counts=FilterOptionCounts(
                    total=int(row['total']),
                    crianca=int(row['crianca']),
                    gestante=int(row['gestante']),
                    ativo=int(row['ativo']),
                    inativo=int(row['inativo'])
                )
            )

            tipo = row['tipo']
            if tipo == 'bairro':
                result.bairros.append(item)
            elif tipo == 'grupo':
                result.grupos.append(item)
            elif tipo == 'cohort':
                result.cohorts.append(item)
            elif tipo == 'status':
                result.status_list.append(item)
            elif tipo == 'cre':
                result.cres.append(item)
            elif tipo == 'cras':
                result.cras.append(item)
            elif tipo == 'escola':
                result.escolas.append(item)
            elif tipo == 'clinica':
                result.clinicas.append(item)

        # Calcular total de participantes
        if result.status_list:
            result.total_participantes = sum(s.counts.total for s in result.status_list)

        logger.info(f"Filter options: {len(result.bairros)} bairros, {len(result.grupos)} grupos, {result.total_participantes} total")

        return result

    except Exception as e:
        logger.error(f"Error fetching filter options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/",
    summary="Listar participantes com filtros e paginação",
    response_model=PaginatedResponse[Participante],
)
async def get_participants(
    filters: CommonFilters = Depends(), pagination: PaginationParams = Depends()
) -> Any:
    """
    Retorna participantes com suporte a filtros e paginação.
    Filtros aplicados no backend, paginação eficiente.
    """
    query = f"""
    SELECT
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY nome ASC
    """

    logger.info(
        f"Fetching participants - Page: {pagination.page}, Size: {pagination.page_size}"
    )
    logger.debug(f"Filters: {filters.model_dump(exclude_none=True)}")

    try:
        # Get DataFrame from cache
        df = DataManager.get_dataset(query)

        # Apply filters using DataManager
        df = DataManager.apply_filters(df, filters)

        logger.info(f"Total after filters: {len(df)} participants")

        # Paginate and return
        return DataManager.paginate_data(df, pagination.page, pagination.page_size)

    except Exception as e:
        logger.error(f"Error fetching participants: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{cpf}",
    summary="Detalhes do participante",
    response_model=PaginatedResponse[Participante],
)
async def get_participant_details(cpf: str) -> Any:
    """
    Busca detalhes de um participante específico pelo CPF.
    """
    # Sanitização básica do CPF (apenas números)
    cpf_clean = "".join(filter(str.isdigit, cpf))

    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_participante`
    ORDER BY cpf DESC
    """
    try:
        df = DataManager.get_dataset(query)

        # Filter by CPF partition/column
        if "cpf" in df.columns:
            result = df[df["cpf"] == cpf]
            if result.empty and "cpf_particao" in df.columns:
                try:
                    result = df[df["cpf_particao"] == int(cpf_clean)]
                except ValueError:
                    pass
        else:
            # Fallback (unlikely)
            result = df[0:0]

        if result.empty:
            raise HTTPException(status_code=404, detail="Participante não encontrado")

        # Use DataManager to package the single result
        return DataManager.paginate_data(result, page=1, page_size=1)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching participant details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{cpf}/protocols",
    summary="Protocolos do participante",
    response_model=PaginatedResponse[ProtocoloDetalhes],
)
async def get_participant_protocols(cpf: str) -> Any:
    """
    Lista os protocolos de um participante específico.
    """
    cpf_clean = "".join(filter(str.isdigit, cpf))

    # This is a different table, so it needs its own dataset cache
    query = f"""
    SELECT 
        *
    FROM `{PROJECT_ID}.{DATASET_ID}.endpoint_protocolo_detalhes`
    ORDER BY protocolo_secretaria, protocolo_id
    """
    logger.debug(f"Fetching cached data for protocols: {query}")
    try:
        df = DataManager.get_dataset(query)

        # Filter by CPF
        if "cpf_particao" in df.columns:
            try:
                df = df[df["cpf_particao"] == int(cpf_clean)]
            except ValueError:
                df = df[0:0]  # Empty
        elif "cpf" in df.columns:
            df = df[df["cpf"] == cpf]

        # Use DataManager to package all results
        return DataManager.paginate_data(
            df, page=1, page_size=len(df) if not df.empty else 1
        )

    except Exception as e:
        logger.error(f"Error fetching participant protocols: {e}")
        raise HTTPException(status_code=500, detail=str(e))
