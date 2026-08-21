import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.core.security.jwt import CurrentUserPermissionsV2, verify_jwt
from src.pic.application.use_cases.export_participants import ExportParticipantsUseCase
from src.pic.application.use_cases.get_participant_detail import (
    GetParticipantDetailUseCase,
)
from src.pic.application.use_cases.list_participants import ListParticipantsUseCase
from src.pic.domain.errors import NotFoundError
from src.pic.domain.errors import ValidationError as DomainValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.infrastructure.export.csv_generator import _df_to_csv_stream
from src.pic.presentation.di import (
    get_export_participants_use_case,
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
    permissions: CurrentUserPermissionsV2,
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
    "/participants/export",
    summary="Exportar participantes filtrados como CSV via streaming (V2)",
)
async def export_participants_csv_v2(
    permissions: CurrentUserPermissionsV2,
    filters: FilterCriteria = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: ExportParticipantsUseCase = Depends(get_export_participants_use_case),
):
    export_start = time.perf_counter()
    logger.info("V2 CSV export started")

    try:
        result = await use_case.execute(
            filters=filters,
            sort=sort,
            permissions=permissions,
            bypass_cache=bypass_cache,
        )

        fetch_time = time.perf_counter() - export_start
        total_rows = len(result.df)
        logger.info(
            f"V2 export dataset ready: {total_rows} rows in {fetch_time:.2f}s"
        )

        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"participantes_{timestamp}.csv"

        return StreamingResponse(
            _df_to_csv_stream(result.df),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/participants/{id_membro_familia}",
    summary="Detalhes de um participante (V2)",
    response_model=ParticipantDetailResponse,
)
async def get_participant_detail(
    id_membro_familia: str,
    permissions: CurrentUserPermissionsV2,
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
