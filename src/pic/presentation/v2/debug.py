from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.security.jwt import CurrentUserPermissionsV2, verify_jwt
from src.pic.application.use_cases.get_debug_participant import (
    GetDebugParticipantUseCase,
)
from src.pic.domain.errors import ForbiddenError
from src.pic.domain.models.debug import DebugParticipantResponse
from src.pic.presentation.di import get_debug_participant_use_case
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Debug V2"])


@router.get(
    "/debug/participants",
    summary="Buscar dados de debug de participantes (SUPER ADMIN ONLY, V2)",
    response_model=DebugParticipantResponse,
)
async def get_debug_participants(
    permissions: CurrentUserPermissionsV2,
    search: str | None = Query(
        None, description="Buscar por CPF, nome ou ID membro familia"
    ),
    bypass_cache: bool = Query(
        False, description="Se true, forca dados frescos do BigQuery"
    ),
    use_case: GetDebugParticipantUseCase = Depends(get_debug_participant_use_case),
):
    try:
        return await use_case.execute(
            permissions=permissions,
            search=search,
            bypass_cache=bypass_cache,
        )
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
