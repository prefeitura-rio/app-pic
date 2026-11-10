"""Endpoints do Acompanhamento semanal (``/api/v2/monitoring/*``).

Acompanhamento = evolução temporal do grupo definido pelos filtros da
Monitoramento (status, safra, grupo, Bolsa Família) com recorte territorial
vindo da seleção do mapa (``camada`` + ``regiao`` — os valores exibidos no
mapa, resolvidos pelo use case para os valores RAW da coluna; repetir o
parâmetro ``regiao`` soma as regiões selecionadas — OR no ``in`` da coluna).

Permissão: mesma regra do dashboard (``is_super_admin`` ou
``secretaria_acesso == TODOS``) — caso contrário, ``200`` com
``can_view_monitoring = false`` e séries vazias (o frontend não renderiza a
seção para esses usuários; a RLS do data-proxy também limita).
"""

import datetime
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_monitoring import (
    GetMonitoringFiltersUseCase,
    GetMonitoringGroupUseCase,
    GetMonitoringProtocolSeriesUseCase,
    GetMonitoringProtocolsUseCase,
)
from src.pic.domain.models.monitoring import MonitoringFilters
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import (
    get_monitoring_filters_use_case,
    get_monitoring_group_use_case,
    get_monitoring_protocol_series_use_case,
    get_monitoring_protocols_use_case,
)
from src.pic.presentation.v2._helpers import (
    data_proxy_user_token,
    log_postgrest_error,
)
from src.pic.presentation.v2.monitoring_schemas import (
    MonitoringFiltersResponse,
    MonitoringGroupResponse,
    MonitoringProtocolsResponse,
    MonitoringSeriesResponse,
)
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Monitoring V2"])


def _monitoring_filters(
    grupo: list[str] | None,
    cohort: list[str] | None,
    status: list[str] | None,
    has_bolsa_familia: bool | None,
    camada: str | None,
    regiao: list[str] | None,
) -> MonitoringFilters:
    return MonitoringFilters(
        grupo=list(grupo) if grupo else None,
        cohort=list(cohort) if cohort else None,
        status=list(status) if status else None,
        has_bolsa_familia=has_bolsa_familia,
        camada=camada,
        regiao=list(regiao) if regiao else None,
    )


@router.get(
    "/monitoring/filters",
    summary="Opções do card de filtros do Acompanhamento",
    response_model=MonitoringFiltersResponse,
)
async def get_monitoring_filters(
    credentials: HTTPAuthorizationCredentials = Security(security),
    data_proxy_token: str | None = Header(
        None,
        alias="X-Access-Token",
        description=(
            "Access token (Keycloak) repassado ao data-proxy (PostgREST); "
            "sem ele, usa o id_token do Authorization"
        ),
    ),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetMonitoringFiltersUseCase = Depends(get_monitoring_filters_use_case),
):
    try:
        result = await use_case.execute(
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            bypass_cache=bypass_cache,
        )
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e
    return result


@router.get(
    "/monitoring/group",
    summary="Evolução semanal do grupo (total/ativos/inativos + motivos)",
    response_model=MonitoringGroupResponse,
)
async def get_monitoring_group(
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
    grupo: list[str] | None = Query(
        None, description="Grupos do participante (pic_grupo=in) — multiselect"
    ),
    cohort: list[str] | None = Query(
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
    use_case: GetMonitoringGroupUseCase = Depends(get_monitoring_group_use_case),
):
    endpoint_start = time.perf_counter()
    filters = _monitoring_filters(
        grupo, cohort, status, has_bolsa_familia, camada, regiao
    )
    try:
        result = await use_case.execute(
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
    logger.info(f"[monitoring] group endpoint completed in {elapsed:.3f}s")
    return result


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
    cohort: list[str] | None = Query(
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
        grupo, cohort, status, has_bolsa_familia, camada, regiao
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


@router.get(
    "/monitoring/protocols",
    summary="Tabela de todos os protocolos na semana selecionada",
    response_model=MonitoringProtocolsResponse,
)
async def get_monitoring_protocols(
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
    week_start: datetime.date | None = Query(
        None,
        description=(
            "Semana (data_referencia_semana_inicio, 'YYYY-MM-DD'); "
            "default = mais recente com dados"
        ),
    ),
    secretaria: str | None = Query(
        None, description="Filtra a tabela por secretaria (ex.: 'SMS')"
    ),
    grupo: list[str] | None = Query(
        None, description="Grupos do participante (pic_grupo=in) — multiselect"
    ),
    cohort: list[str] | None = Query(
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
    use_case: GetMonitoringProtocolsUseCase = Depends(
        get_monitoring_protocols_use_case
    ),
):
    endpoint_start = time.perf_counter()
    filters = _monitoring_filters(
        grupo, cohort, status, has_bolsa_familia, camada, regiao
    )
    try:
        result = await use_case.execute(
            filters=filters,
            permissions=permissions,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
            week_start=week_start.isoformat() if week_start else None,
            secretaria=secretaria,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"[monitoring] protocols endpoint completed in {elapsed:.3f}s")
    return result
