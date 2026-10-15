import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_acordo_resultados import (
    GetAcordoResultadosUseCase,
)
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import get_acordo_resultados_use_case
from src.pic.presentation.v2.schemas import AcordoResultadosResponse
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Acordo de Resultados V2"])


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
    "/acordo-resultados",
    summary="Métricas do Acordo de Resultados 2026 (V2 — hexagonal)",
    response_model=AcordoResultadosResponse,
)
async def get_acordo_resultados(
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
    bypass_cache: bool = Query(False),
    use_case: GetAcordoResultadosUseCase = Depends(get_acordo_resultados_use_case),
):
    endpoint_start = time.perf_counter()
    logger.info("V2 acordo-resultados endpoint started")

    try:
        result = await use_case.execute(
            permissions=permissions,
            user_token=_data_proxy_user_token(
                data_proxy_token, credentials.credentials
            ),
            bypass_cache=bypass_cache,
        )
    except PostgrestError as e:
        logger.error(
            f"PostgREST (data-proxy) error: message={e.message} "
            f"code={e.code} hint={e.hint} details={e.details}"
        )
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error in acordo-resultados endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 acordo-resultados endpoint completed in {elapsed:.3f}s")

    return AcordoResultadosResponse(
        data=result.data, can_view_acordo=result.can_view_acordo
    )
