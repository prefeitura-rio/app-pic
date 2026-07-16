import time

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.pic.application.use_cases.get_participant_detail import (
    GetParticipantDetailUseCase,
)
from src.pic.application.use_cases.list_participants import ListParticipantsUseCase
from src.pic.domain.errors import NotFoundError
from src.pic.domain.errors import ValidationError as DomainValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.presentation.di import (
    get_list_participants_use_case,
    get_participant_detail_use_case,
)
from src.pic.presentation.v2.schemas import (
    ParticipantDetailResponse,
    ParticipantListResponse,
)
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Participantes V2"])


@router.get(
    "/participants",
    summary="Listar participantes (V2 enxuta)",
    response_model=ParticipantListResponse,
)
async def get_participants(
    permissions: CurrentUserPermissions,
    filters: FilterCriteria = Depends(),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: ListParticipantsUseCase = Depends(get_list_participants_use_case),
):
    endpoint_start = time.perf_counter()
    logger.info("V2 participants endpoint started (after auth/permissions)")

    if pagination.page_size == -1:
        logger.warning(
            f"V2 DOWNLOAD MODE: Fetching ALL participants. "
            f"Filters active: {len(filters.model_dump(exclude_none=True))}"
        )

    try:
        result = await use_case.execute(
            filters=filters,
            pagination=pagination,
            sort=sort,
            permissions=permissions,
            bypass_cache=bypass_cache,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 participants endpoint completed in {elapsed:.3f}s")

    return ParticipantListResponse(
        meta=result.meta,
        data=result.data,
    )


@router.get(
    "/participants/{id_membro_familia}",
    summary="Detalhes de um participante (V2)",
    response_model=ParticipantDetailResponse,
)
async def get_participant_detail(
    id_membro_familia: str,
    permissions: CurrentUserPermissions,
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetParticipantDetailUseCase = Depends(
        get_participant_detail_use_case
    ),
):
    endpoint_start = time.perf_counter()
    logger.info(
        f"V2 participant detail endpoint started: {id_membro_familia}"
    )

    try:
        result = await use_case.execute(
            id_membro_familia=id_membro_familia,
            permissions=permissions,
            bypass_cache=bypass_cache,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 participant detail endpoint completed in {elapsed:.3f}s")

    return ParticipantDetailResponse(data=result)
