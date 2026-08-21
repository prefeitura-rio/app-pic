from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile

from src.api.v1.schemas import PaginatedResponse, PaginationParams
from src.core.security.jwt import CurrentUserPermissionsV2, verify_jwt
from src.pic.application.use_cases.admin_batch import (
    BatchImportUsersUseCase,
    BatchUpdatePermissionsUseCase,
)
from src.pic.application.use_cases.admin_read import (
    GetAvailableIdsUseCase,
    GetCurrentUserUseCase,
)
from src.pic.application.use_cases.admin_write import (
    DeleteUserUseCase,
    ListUsersUseCase,
    UpsertUserUseCase,
)
from src.pic.domain.models.admin import (
    AvailableIds,
    BatchImportResult,
    BatchPermissionsRequest,
    BatchPermissionsResult,
    UpsertUserRequest,
    UserAccessRecord,
)
from src.pic.presentation.di import (
    get_available_ids_use_case,
    get_batch_import_users_use_case,
    get_batch_update_permissions_use_case,
    get_current_user_use_case,
    get_delete_user_use_case,
    get_list_users_use_case,
    get_upsert_user_use_case,
)
from src.utils.log import logger

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_jwt)], tags=["Admin V2"])


@router.get("/available-ids", response_model=AvailableIds)
async def get_available_ids_v2(
    permissions: CurrentUserPermissionsV2,
    use_case: GetAvailableIdsUseCase = Depends(get_available_ids_use_case),
):
    return await use_case.execute(permissions)


@router.get("/me", response_model=UserAccessRecord)
async def get_current_user_v2(
    permissions: CurrentUserPermissionsV2,
    use_case: GetCurrentUserUseCase = Depends(get_current_user_use_case),
):
    return await use_case.execute(permissions)


@router.get("/users", response_model=PaginatedResponse[UserAccessRecord])
async def list_users_v2(
    permissions: CurrentUserPermissionsV2,
    pagination: PaginationParams = Depends(),
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
        )
        return PaginatedResponse(data=users, meta=meta, filters=filter_options)
    except Exception as e:
        logger.error(f"Erro ao listar usuarios: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/users/{cpf}", response_model=UserAccessRecord)
async def upsert_user_v2(
    request: UpsertUserRequest,
    permissions: CurrentUserPermissionsV2,
    cpf: str = Path(..., pattern=r"^\d{11}$"),
    use_case: UpsertUserUseCase = Depends(get_upsert_user_use_case),
):
    return await use_case.execute(permissions, cpf, request)


@router.delete("/users/{cpf}", status_code=204)
async def delete_user_v2(
    permissions: CurrentUserPermissionsV2,
    cpf: str = Path(..., pattern=r"^\d{11}$"),
    use_case: DeleteUserUseCase = Depends(get_delete_user_use_case),
):
    await use_case.execute(permissions, cpf)


@router.post("/users-batch", response_model=BatchImportResult)
async def batch_import_users_v2(
    permissions: CurrentUserPermissionsV2,
    file: UploadFile = File(...),
    use_case: BatchImportUsersUseCase = Depends(get_batch_import_users_use_case),
):
    return await use_case.execute(permissions, file)


@router.put("/users-batch/permissions", response_model=BatchPermissionsResult)
async def batch_update_permissions_v2(
    request: BatchPermissionsRequest,
    permissions: CurrentUserPermissionsV2,
    use_case: BatchUpdatePermissionsUseCase = Depends(get_batch_update_permissions_use_case),
):
    return await use_case.execute(permissions, request)
