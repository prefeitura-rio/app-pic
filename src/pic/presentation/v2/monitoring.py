"""Endpoint do Acompanhamento semanal (``/api/v2/monitoring/*``).

Acompanhamento = evolução temporal do grupo definido pelos filtros da
Monitoramento (status, safra, grupo, Bolsa Família) com recorte territorial
vindo da seleção do mapa (``camada`` + ``regiao`` — os valores exibidos no
mapa, resolvidos pelo use case para os valores RAW da coluna; repetir o
parâmetro ``regiao`` soma as regiões selecionadas — OR no ``in`` da coluna).
O pseudo-protocolo ``geral`` seleciona a regularidade geral (linhas
``nivel='geral'``).

Permissão: mesma regra do dashboard (``is_super_admin`` ou
``secretaria_acesso == TODOS``) — caso contrário, ``200`` com
``can_view_monitoring = false`` e série vazia (o frontend não renderiza a
seção para esses usuários; a RLS do data-proxy também limita).
"""

import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_monitoring import (
    GetMonitoringProtocolSeriesUseCase,
)
from src.pic.domain.models.monitoring import MonitoringFilters
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import get_monitoring_protocol_series_use_case
from src.pic.presentation.v2._helpers import (
    data_proxy_user_token,
    log_postgrest_error,
)
from src.pic.presentation.v2.monitoring_schemas import MonitoringSeriesResponse
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Monitoring V2"])


def _monitoring_filters(
    grupo: list[str] | None,
    cohortes: list[str] | None,
    status: list[str] | None,
    has_bolsa_familia: bool | None,
    camada: str | None,
    regiao: list[str] | None,
) -> MonitoringFilters:
    return MonitoringFilters(
        grupo=list(grupo) if grupo else None,
        cohort=list(cohortes) if cohortes else None,
        status=list(status) if status else None,
        has_bolsa_familia=has_bolsa_familia,
        camada=camada,
        regiao=list(regiao) if regiao else None,
    )


@router.get(
    "/monitoring/series",
    summary="Evolução semanal de UM protocolo (desfechos por status)",
    response_model=MonitoringSeriesResponse,
)
async def get_monitoring_series(
    permissions: CurrentUserPermissionsV2,
    protocolo: str = Query(
        ...,
        min_length=1,
        description=(
            "Protocolo (obrigatório) — ex.: 'sms_vacinacao_pentavalente'; "
            "'geral' para a regularidade geral (linhas nivel='geral' da "
            "tabela semanal)"
        ),
    ),
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    grupo: list[str] | None = Query(
        None, description="Grupos do participante (pic_grupo=in) — multiselect"
    ),
    cohortes: list[str] | None = Query(
        None, description="Safras de ingresso (pic_cohort=in) — multiselect"
    ),
    status: list[Literal["Ativo", "Inativo"]] | None = Query(
        None, description="Status (pic_status=in) — ex.: Ativo, Inativo"
    ),
    has_bolsa_familia: bool | None = Query(
        None, description="Beneficiários do Bolsa Família (has_bolsa_familia=eq)"
    ),
    camada: str | None = Query(
        None, description="Camada territorial da região selecionada no mapa"
    ),
    regiao: list[str] | None = Query(
        None,
        description=(
            "Regiões selecionadas no mapa (valor exibido; o backend resolve o "
            "valor RAW da coluna da camada). Repita o parâmetro para somar "
            "múltiplas regiões (OR na coluna)"
        ),
    ),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetMonitoringProtocolSeriesUseCase = Depends(
        get_monitoring_protocol_series_use_case
    ),
):
    endpoint_start = time.perf_counter()
    filters = _monitoring_filters(
        grupo, cohortes, status, has_bolsa_familia, camada, regiao
    )
    try:
        result = await use_case.execute(
            protocolo_id=protocolo,
            filters=filters,
            permissions=permissions,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"[monitoring] series endpoint completed in {elapsed:.3f}s")
    return result
