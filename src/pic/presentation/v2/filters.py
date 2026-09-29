import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.use_cases.get_filter_options import (
    GetFilterOptionsUseCase,
)
from src.pic.domain.models.filters import FilterCriteria, FilterField
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_admin_repo,
    get_filter_options_use_case,
)
from src.pic.presentation.v2._helpers import (
    data_proxy_user_token,
    log_postgrest_error,
    self_heal_policy_sync,
)
from src.pic.presentation.v2.schemas import FilterFieldOptionsResponse
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Filtros V2"])


@router.get(
    "/filters",
    summary="Opcoes de um filtro (V2, lazy por campo)",
    response_model=FilterFieldOptionsResponse,
)
async def get_filters(
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    field: FilterField = Query(
        ...,
        description=(
            "Campo cujas opcoes devem ser retornadas (um unico por chamada)"
        ),
    ),
    filters: FilterCriteria = Depends(),
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
    use_case: GetFilterOptionsUseCase = Depends(get_filter_options_use_case),
):
    endpoint_start = time.perf_counter()
    logger.info(f"V2 filters endpoint started: field={field}")

    await self_heal_policy_sync(admin_repo, permissions.cpf)

    try:
        options = await use_case.execute(
            field=field,
            filters=filters,
            permissions=permissions,
            bypass_cache=bypass_cache,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 filters endpoint completed in {elapsed:.3f}s")

    return FilterFieldOptionsResponse(field=field, options=options)
