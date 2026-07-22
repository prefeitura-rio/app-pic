import time

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.pic.application.use_cases.get_dashboard import GetDashboardUseCase
from src.pic.presentation.di import get_dashboard_use_case
from src.pic.presentation.v2.schemas import DashboardV2Response
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Dashboard V2"])


@router.get(
    "/dashboard",
    summary="Metricas do Dashboard (V2 — hexagonal)",
    response_model=DashboardV2Response,
)
async def get_dashboard(
    permissions: CurrentUserPermissions,
    grupo: str | None = Query(None),
    cohort: str | None = Query(None),
    status: str | None = Query(None),
    secretaria: str | None = Query(None),
    subprefeitura: str | None = Query(None),
    regiao_administrativa: str | None = Query(None),
    bairro: str | None = Query(None),
    cre: str | None = Query(None),
    ap: str | None = Query(None),
    cas: str | None = Query(None),
    cras: str | None = Query(None),
    escola: str | None = Query(None),
    unidade_saude: str | None = Query(None),
    equipe_saude: str | None = Query(None),
    has_bolsa_familia: bool | None = Query(None),
    bypass_cache: bool = Query(False),
    use_case: GetDashboardUseCase = Depends(get_dashboard_use_case),
):
    endpoint_start = time.perf_counter()
    logger.info("V2 dashboard endpoint started")

    try:
        result = await use_case.execute(
            permissions=permissions,
            grupo=grupo,
            cohort=cohort,
            status=status,
            secretaria=secretaria,
            subprefeitura=subprefeitura,
            regiao_administrativa=regiao_administrativa,
            bairro=bairro,
            cre=cre,
            ap=ap,
            cas=cas,
            cras=cras,
            escola=escola,
            unidade_saude=unidade_saude,
            equipe_saude=equipe_saude,
            has_bolsa_familia=has_bolsa_familia,
            bypass_cache=bypass_cache,
        )
    except Exception as e:
        logger.error(f"Error in dashboard endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 dashboard endpoint completed in {elapsed:.3f}s")

    return DashboardV2Response(data=result.data, can_view_dashboard=result.can_view_dashboard)
