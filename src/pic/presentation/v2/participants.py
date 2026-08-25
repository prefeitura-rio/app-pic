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
from src.pic.domain.errors import NotFoundError
from src.pic.domain.errors import ValidationError as DomainValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import PaginationParams, SortParams
from src.pic.infrastructure.export.csv_generator import _df_to_csv_stream
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_admin_repo,
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


def _data_proxy_user_token(data_proxy_token: str | None, id_token: str) -> str:
    """Pick the token forwarded to the data-proxy (PostgREST).

    Prefers the `X-Access-Token` header (Keycloak access token, which carries
    the `role`/`schemas` claims PostgREST needs); falls back to the id token
    used for backend auth when the header is absent (older sessions).
    """
    if data_proxy_token:
        token = data_proxy_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if token:
            return token
    return id_token


def _log_postgrest_error(error: PostgrestError) -> None:
    logger.error(
        f"PostgREST (data-proxy) error: message={error.message} "
        f"code={error.code} hint={error.hint} details={error.details}"
    )


async def _self_heal_policy_sync(admin_repo: IAdminRepository, cpf: str) -> None:
    """Best-effort push of pending policy grants before the data-proxy read.

    The frontend loads `/admin/me` (which runs the same self-heal) and
    `/participants` in parallel; on a first login with pending grants, the
    participant query could otherwise hit the data-proxy before the sync and
    return an empty list. Never blocks the read on failure.
    """
    try:
        await admin_repo.self_heal_policy_sync(cpf)
    except Exception:
        logger.exception(f"Self-heal de policy sync falhou para {cpf}")


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

    await _self_heal_policy_sync(admin_repo, permissions.cpf)

    try:
        result = await use_case.execute(
            filters=filters,
            pagination=pagination,
            sort=sort,
            permissions=permissions,
            bypass_cache=bypass_cache,
            user_token=_data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PostgrestError as e:
        _log_postgrest_error(e)
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
        logger.info(f"V2 export dataset ready: {total_rows} rows in {fetch_time:.2f}s")

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

    await _self_heal_policy_sync(admin_repo, permissions.cpf)

    try:
        result = await use_case.execute(
            id_membro_familia=id_membro_familia,
            permissions=permissions,
            bypass_cache=bypass_cache,
            user_token=_data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PostgrestError as e:
        _log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 participant detail endpoint completed in {elapsed:.3f}s")

    return ParticipantDetailResponse(data=result)
