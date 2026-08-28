import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_dashboard import GetDashboardUseCase
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import get_dashboard_use_case
from src.pic.presentation.v2.schemas import DashboardV2Response
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Dashboard V2"])


def _data_proxy_user_token(data_proxy_token: str | None, id_token: str) -> str:
    """Seleciona o token repassado ao data-proxy (PostgREST).

    Prefere o header ``X-Access-Token`` (access token do Keycloak, que carrega
    as claims ``role``/``schemas`` que o PostgREST precisa para RLS); usa o
    id_token do Authorization como fallback para sessões mais antigas.
    """
    if data_proxy_token:
        token = data_proxy_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if token:
            return token
    return id_token


@router.get(
    "/dashboard",
    summary="Metricas do Dashboard (V2 — hexagonal)",
    response_model=DashboardV2Response,
)
async def get_dashboard(
    permissions: CurrentUserPermissionsV2,
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
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
            user_token=_data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
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
    except PostgrestError as e:
        logger.error(
            f"PostgREST (data-proxy) error: message={e.message} "
            f"code={e.code} hint={e.hint} details={e.details}"
        )
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error in dashboard endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 dashboard endpoint completed in {elapsed:.3f}s")

    return DashboardV2Response(data=result.data, can_view_dashboard=result.can_view_dashboard)
