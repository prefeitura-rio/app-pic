import asyncio
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.use_cases.export_participants import ExportParticipantsUseCase
from src.pic.application.use_cases.get_participant_detail import (
    GetParticipantDetailUseCase,
)
from src.pic.application.use_cases.list_participants import ListParticipantsUseCase
from src.pic.domain.errors import ForbiddenError, NotFoundError
from src.pic.domain.errors import ValidationError as DomainValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.infrastructure.export.csv_generator import rows_to_csv_chunks
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_admin_repo,
    get_export_participants_use_case,
    get_list_participants_use_case,
    get_participant_detail_use_case,
)
from src.pic.presentation.v2._helpers import (
    data_proxy_user_token,
    log_postgrest_error,
    self_heal_policy_sync,
)
from src.pic.presentation.v2.schemas import (
    ParticipantDetailResponse,
    ParticipantListResponse,
)
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Participantes V2"])

# Small concurrency gate for CSV exports: the wide table is materialized, so
# a handful of concurrent exports is cheap; beyond it, requests queue. The
# semaphore is per-process (the API runs a single replica).
_EXPORT_MAX_CONCURRENT = 3
_EXPORT_SEMAPHORE = asyncio.Semaphore(_EXPORT_MAX_CONCURRENT)


@router.get(
    "/participants",
    summary="Listar participantes (V2 enxuta)",
    response_model=ParticipantListResponse,
)
async def get_participants(
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    filters: FilterCriteria = Depends(),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    admin_repo: IAdminRepository = Depends(get_admin_repo),
    use_case: ListParticipantsUseCase = Depends(get_list_participants_use_case),
):
    endpoint_start = time.perf_counter()
    logger.info("V2 participants endpoint started (after auth/permissions)")

    if pagination.page_size == -1:
        logger.warning(
            f"V2 DOWNLOAD MODE: Fetching ALL participants. "
            f"Filters active: {len(filters.model_dump(exclude_none=True))}"
        )

    await self_heal_policy_sync(admin_repo, permissions.cpf)

    try:
        result = await use_case.execute(
            filters=filters,
            pagination=pagination,
            sort=sort,
            permissions=permissions,
            bypass_cache=bypass_cache,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

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
    credentials: HTTPAuthorizationCredentials = Security(security),
    filters: FilterCriteria = Depends(),
    sort: SortParams = Depends(),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    admin_repo: IAdminRepository = Depends(get_admin_repo),
    use_case: ExportParticipantsUseCase = Depends(get_export_participants_use_case),
):
    export_start = time.perf_counter()
    logger.info("V2 CSV export started")

    await self_heal_policy_sync(admin_repo, permissions.cpf)

    await _EXPORT_SEMAPHORE.acquire()

    try:
        result = await use_case.execute(
            filters=filters,
            sort=sort,
            permissions=permissions,
            bypass_cache=bypass_cache,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except DomainValidationError as e:
        _EXPORT_SEMAPHORE.release()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ForbiddenError as e:
        _EXPORT_SEMAPHORE.release()
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        _EXPORT_SEMAPHORE.release()
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        _EXPORT_SEMAPHORE.release()
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    fetch_time = time.perf_counter() - export_start
    logger.info(f"V2 export ready to stream in {fetch_time:.2f}s ({len(result.columns)} columns)")

    async def _stream():
        try:
            async for chunk in rows_to_csv_chunks(result.pages, result.columns):
                yield chunk
        finally:
            _EXPORT_SEMAPHORE.release()

    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"participantes_{timestamp}.csv"

    return StreamingResponse(
        _stream(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/participants/{id_membro_familia}",
    summary="Detalhes de um participante (V2)",
    response_model=ParticipantDetailResponse,
)
async def get_participant_detail(
    id_membro_familia: str,
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    admin_repo: IAdminRepository = Depends(get_admin_repo),
    use_case: GetParticipantDetailUseCase = Depends(get_participant_detail_use_case),
):
    endpoint_start = time.perf_counter()
    logger.info(f"V2 participant detail endpoint started: {id_membro_familia}")

    await self_heal_policy_sync(admin_repo, permissions.cpf)

    try:
        result = await use_case.execute(
            id_membro_familia=id_membro_familia,
            permissions=permissions,
            bypass_cache=bypass_cache,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 participant detail endpoint completed in {elapsed:.3f}s")

    return ParticipantDetailResponse(data=result)
