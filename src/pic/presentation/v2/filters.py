import time

from fastapi import APIRouter, Depends, Query

from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.pic.application.use_cases.get_filter_vocabulary import (
    GetFilterVocabularyUseCase,
)
from src.pic.presentation.di import get_filter_vocabulary_use_case
from src.pic.presentation.v2.schemas import FilterVocabularyResponse
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Filtros V2"])


@router.get(
    "/filters",
    summary="Vocabulario de filtros disponiveis (V2)",
    response_model=FilterVocabularyResponse,
)
async def get_filters(
    permissions: CurrentUserPermissions,
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetFilterVocabularyUseCase = Depends(
        get_filter_vocabulary_use_case
    ),
):
    endpoint_start = time.perf_counter()
    logger.info("V2 filters endpoint started")

    result = await use_case.execute(
        permissions=permissions,
        bypass_cache=bypass_cache,
    )

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 filters endpoint completed in {elapsed:.3f}s")

    return result
