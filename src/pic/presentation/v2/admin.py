
from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile

from src.api.v1.schemas import PaginatedResponse, PaginationParams
from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.pic.domain.models.admin import (
    AvailableIds,
    BatchImportResult,
    BatchPermissionsRequest,
    BatchPermissionsResult,
    UpsertUserRequest,
    UserAccessRecord,
)
from src.pic.infrastructure.admin.batch_ops import (
    batch_import_users_data,
    batch_update_permissions_data,
)
from src.pic.infrastructure.admin.user_read import (
    get_available_ids_data,
    get_current_user_info,
    list_users_data,
)
from src.pic.infrastructure.admin.user_write import delete_user_data, upsert_user_data
from src.utils.log import logger

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_jwt)], tags=["Admin V2"])


@router.get("/available-ids", response_model=AvailableIds)
async def get_available_ids_v2(permissions: CurrentUserPermissions):
    return await get_available_ids_data(permissions)


@router.get("/me", response_model=UserAccessRecord)
async def get_current_user_v2(permissions: CurrentUserPermissions):
    return await get_current_user_info(permissions)


@router.get("/users", response_model=PaginatedResponse[UserAccessRecord])
async def list_users_v2(
    permissions: CurrentUserPermissions,
    pagination: PaginationParams = Depends(),
    active: bool | None = Query(None),
    ocupacao: str | None = Query(None),
    secretaria: str | None = Query(None),
    permission: str | None = Query(None),
    secretaria_acesso: str | None = Query(None),
    search: str | None = Query(None),
    bypass_cache: bool = Query(False),
):
    try:
        users, meta, filter_options = await list_users_data(
            permissions=permissions,
            page=pagination.page,
            page_size=pagination.page_size,
            active=active,
            ocupacao=ocupacao,
            secretaria=secretaria,
            permission=permission,
            secretaria_acesso=secretaria_acesso,
            search=search,
            bypass_cache=bypass_cache,
        )
        return PaginatedResponse(data=users, meta=meta, filters=filter_options)
    except Exception as e:
        logger.error(f"Erro ao listar usuarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{cpf}", response_model=UserAccessRecord)
async def upsert_user_v2(
    request: UpsertUserRequest,
    permissions: CurrentUserPermissions,
    cpf: str = Path(..., pattern=r"^\d{11}$"),
):
    return await upsert_user_data(permissions, cpf, request)


@router.delete("/users/{cpf}", status_code=204)
async def delete_user_v2(
    permissions: CurrentUserPermissions,
    cpf: str = Path(..., pattern=r"^\d{11}$"),
):
    await delete_user_data(permissions, cpf)


@router.post("/users-batch", response_model=BatchImportResult)
async def batch_import_users_v2(
    permissions: CurrentUserPermissions,
    file: UploadFile = File(...),
):
    return await batch_import_users_data(permissions, file)


@router.put("/users-batch/permissions", response_model=BatchPermissionsResult)
async def batch_update_permissions_v2(
    request: BatchPermissionsRequest,
    permissions: CurrentUserPermissions,
):
    return await batch_update_permissions_data(permissions, request)
