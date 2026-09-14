from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Path,
    Query,
    Security,
    UploadFile,
)
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.admin.batch import (
    BatchImportUsersUseCase,
    BatchUpdatePermissionsUseCase,
)
from src.pic.application.use_cases.admin.read import (
    GetAvailableUnitIdsUseCase,
    GetCurrentUserUseCase,
)
from src.pic.application.use_cases.admin.write import (
    DeleteUserUseCase,
    ListUsersUseCase,
    UpsertUserUseCase,
)
from src.pic.domain.errors import ForbiddenError, NotFoundError
from src.pic.domain.errors import ValidationError as DomainValidationError
from src.pic.domain.models.admin import (
    UNIT_TYPE_REGISTRY,
    BatchImportResult,
    BatchPermissionsRequest,
    BatchPermissionsResult,
    IdWithName,
    UpsertUserRequest,
    UserAccessRecord,
)
from src.pic.domain.models.pagination import PaginationParams
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_available_unit_ids_use_case,
    get_batch_import_users_use_case,
    get_batch_update_permissions_use_case,
    get_current_user_use_case,
    get_delete_user_use_case,
    get_list_users_use_case,
    get_upsert_user_use_case,
)
from src.pic.presentation.v2._helpers import (
    data_proxy_user_token,
    log_postgrest_error,
)
from src.pic.presentation.v2.schemas import AdminUsersResponse
from src.utils.log import logger

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_jwt)], tags=["Admin V2"])

_UNIT_TYPE_PATTERN = "^(" + "|".join(UNIT_TYPE_REGISTRY.keys()) + ")$"


@router.get("/available-ids/{unit_type}", response_model=list[IdWithName])
async def get_available_unit_ids_v2(
    permissions: CurrentUserPermissionsV2,
    unit_type: str = Path(..., pattern=_UNIT_TYPE_PATTERN),
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    bypass_cache: bool = Query(False),
    use_case: GetAvailableUnitIdsUseCase = Depends(get_available_unit_ids_use_case),
):
    try:
        return await use_case.execute(
            permissions,
            unit_type,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
            bypass_cache=bypass_cache,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/me", response_model=UserAccessRecord)
async def get_current_user_v2(
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(None, alias="X-Access-Token"),
    force_sync: bool = Query(False, description="Force sync of ALL policies (set on fresh OAuth login via policy_force_sync cookie)."),
    use_case: GetCurrentUserUseCase = Depends(get_current_user_use_case),
):
    try:
        return await use_case.execute(
            permissions,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
            force_sync=force_sync,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/users", response_model=AdminUsersResponse)
async def list_users_v2(
    permissions: CurrentUserPermissionsV2,
    pagination: PaginationParams = Depends(),
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(None, alias="X-Access-Token"),
    active: bool | None = Query(None),
    ocupacao: str | None = Query(None),
    secretaria: str | None = Query(None),
    permission: str | None = Query(None),
    secretarias_acesso: list[str] | None = Query(None),
    search: str | None = Query(None),
    bypass_cache: bool = Query(False),
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
):
    try:
        users, meta, filter_options = await use_case.execute(
            permissions=permissions,
            pagination=pagination,
            active=active,
            ocupacao=ocupacao,
            secretaria=secretaria,
            permission=permission,
            secretarias_acesso=secretarias_acesso,
            search=search,
            bypass_cache=bypass_cache,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
        return AdminUsersResponse(meta=meta, data=users, filters=filter_options)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Erro ao listar usuarios: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/users/{cpf}", response_model=UserAccessRecord)
async def upsert_user_v2(
    request: UpsertUserRequest,
    permissions: CurrentUserPermissionsV2,
    cpf: str = Path(..., pattern=r"^\d{11}$"),
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(None, alias="X-Access-Token"),
    use_case: UpsertUserUseCase = Depends(get_upsert_user_use_case),
):
    try:
        return await use_case.execute(
            permissions,
            cpf,
            request,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.delete("/users/{cpf}", status_code=204)
async def delete_user_v2(
    permissions: CurrentUserPermissionsV2,
    cpf: str = Path(..., pattern=r"^\d{11}$"),
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(None, alias="X-Access-Token"),
    use_case: DeleteUserUseCase = Depends(get_delete_user_use_case),
):
    try:
        await use_case.execute(
            permissions,
            cpf,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/users-batch", response_model=BatchImportResult)
async def batch_import_users_v2(
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(None, alias="X-Access-Token"),
    file: UploadFile = File(...),
    use_case: BatchImportUsersUseCase = Depends(get_batch_import_users_use_case),
):
    content = await file.read()
    try:
        return await use_case.execute(
            permissions,
            filename=file.filename,
            content=content,
            user_token=data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.put("/users-batch/permissions", response_model=BatchPermissionsResult)
async def batch_update_permissions_v2(
    request: BatchPermissionsRequest,
    permissions: CurrentUserPermissionsV2,
    use_case: BatchUpdatePermissionsUseCase = Depends(
        get_batch_update_permissions_use_case
    ),
):
    try:
        return await use_case.execute(permissions, request)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DomainValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
