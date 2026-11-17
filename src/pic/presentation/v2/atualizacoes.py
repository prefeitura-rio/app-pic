"""Endpoint do Painel de Atualizações (``/api/v2/dashboard/atualizacoes-regionais``).

Painel de Atualizações = resumo da última semana fechada do escopo do usuário
ou de uma região explícita (``camada`` + ``regiao`` — o valor exibido no mapa,
resolvido pelo use case para o valor RAW da coluna; convenção do monitoring):
regularidade geral, extremos por protocolo, volume de irregulares/regulares e
foco geográfico, com o lineup fixo dos cards da linha 2 em ``meta.cards``.
As variações comparam W−1 com **W−(N+1)** (``semanas_comparacao`` ∈ 1|2|4,
default 4 semanas); a série desenha ``min(N+1, 4)`` pontos, descartando
snapshots anômalos (decisão E). Os extremos por protocolo respeitam as
**secretarias de acesso** do usuário (a RLS recorta unidade, não secretaria).

Sem ``camada``/``regiao``, as consultas rodam **sem recorte territorial** — a
RLS do data-proxy entrega exatamente o escopo de acessos do usuário (o painel
segue os acessos, não os filtros da busca).

Permissão (gate b): super admin, acesso geral (3 secretarias) ou qualquer
policy de unidade — caso contrário, ``200`` com ``can_view_atualizacoes =
false`` e ``data = null`` (o frontend não renderiza o painel).
"""

import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from src.core.security.jwt import CurrentUserPermissionsV2, security, verify_jwt
from src.pic.application.use_cases.get_atualizacoes_regionais import (
    GetAtualizacoesRegionaisUseCase,
)
from src.pic.infrastructure.postgrest_client.errors import PostgrestError
from src.pic.presentation.di import get_atualizacoes_regionais_use_case
from src.pic.presentation.v2._helpers import (
    data_proxy_user_token,
    log_postgrest_error,
)
from src.pic.presentation.v2.atualizacoes_schemas import (
    AtualizacoesRegionaisResponse,
)
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Dashboard V2"])


@router.get(
    "/dashboard/atualizacoes-regionais",
    summary="Painel de Atualizações da Busca Individual (linha 1 + linha 2)",
    response_model=AtualizacoesRegionaisResponse,
)
async def get_atualizacoes_regionais(
    permissions: CurrentUserPermissionsV2,
    camada: str | None = Query(
        None,
        description=(
            "Camada territorial da região (bairro|ra|cas|cre|ap). Omitir (com "
            "regiao) para o painel seguir o escopo de acessos do usuário (RLS)"
        ),
    ),
    regiao: str | None = Query(
        None,
        description=(
            "Região selecionada no mapa (valor exibido; o backend resolve o "
            "valor RAW da coluna da camada). Omitir (com camada) para o escopo "
            "do usuário"
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
    semana: str | None = Query(
        None,
        description=(
            "Semana de referência no formato ISO week-start (ex.: "
            "'2026-11-02') — debug/histórico; default: última semana fechada"
        ),
    ),
    semanas_comparacao: Literal["1", "2", "4"] = Query(
        "4",
        description=(
            "Janela de comparação em semanas: 1, 2 ou 4 (default 4). "
            "Deltas comparam W−1 com W−(N+1); o sparkline desenha "
            "min(N+1, 4) pontos"
        ),
    ),
    bypass_cache: bool = Query(False, description="Forcar refresh do cache"),
    use_case: GetAtualizacoesRegionaisUseCase = Depends(
        get_atualizacoes_regionais_use_case
    ),
):
    endpoint_start = time.perf_counter()
    try:
        result = await use_case.execute(
            camada=camada,
            regiao=regiao,
            permissions=permissions,
            user_token=data_proxy_user_token(data_proxy_token, credentials.credentials),
            user_id=permissions.cpf if permissions else None,
            semana=semana,
            semanas_comparacao=int(semanas_comparacao),
            bypass_cache=bypass_cache,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PostgrestError as e:
        log_postgrest_error(e)
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"[atualizacoes] endpoint completed in {elapsed:.3f}s")
    return result
