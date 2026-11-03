"""Use case dos detalhes da região clicada (fases 3j/3k).

Retorna, para uma região de uma camada territorial (bairro, RA, CAS, CRE
ou AP) e os filtros ativos (status/cohortes — mesmo padrão da Visão Geral):

- ``geral``: métrica de regularidade geral da região (mesma fonte do mapa
  sem protocolo — reusa os agregados do consolidado, cujo cache já foi
  aquecido pela consulta do mapa);
- ``protocolos``: métrica de CADA protocolo na região (fonte
  ``endpoint_participante_visao_geral_protocolos``, filtrada por ``eq`` na
  coluna da camada com o valor RAW descoberto nos agregados gerais);
- ``protocolo_geral`` (3k): quando ``protocolo_id`` é informado, a métrica
  do MESMO protocolo em TODAS as regiões (média geral) — base do
  comparativo "acima/abaixo da média" do card de detalhes.

O frontend usa ``geral`` + ``protocolos`` no modo sem protocolo; com
protocolo selecionado usa ``protocolo_geral`` para o comparativo.
"""

import asyncio

from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.application.use_cases.get_regularidade_por_camada import (
    _CAMADAS_SUPORTADAS,
    _NORMALIZERS,
)
from src.pic.domain.models.geospatial import (
    RegiaoDetalhes,
    RegiaoRegularidadeResumo,
)
from src.utils.log import logger


def _resumo(
    total_participantes: int, total_regulares: int, total_irregulares: int
) -> RegiaoRegularidadeResumo:
    taxa = (
        round(total_regulares / total_participantes * 100, 1)
        if total_participantes > 0
        else None
    )
    return RegiaoRegularidadeResumo(
        total_participantes=total_participantes,
        total_regulares=total_regulares,
        total_irregulares=total_irregulares,
        taxa_regularidade=taxa,
    )


class GetDetalhesRegiaoUseCase:
    def __init__(self, repository: IGeospatialRepository):
        self._repository = repository

    async def execute(
        self,
        camada: str,
        regiao: str,
        user_token: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
        status: list[str] | None = None,
        cohortes: list[str] | None = None,
        protocolo_id: str | None = None,
    ) -> RegiaoDetalhes:
        if camada not in _CAMADAS_SUPORTADAS:
            raise ValueError(
                f"Camada {camada!r} não suportada (esperado: {_CAMADAS_SUPORTADAS})"
            )

        normalize = _NORMALIZERS[camada]
        key = normalize(regiao)
        if not key:
            raise ValueError(
                f"Região inválida para a camada {camada!r}: {regiao!r}"
            )

        # 1) Métrica geral da região: reusa os agregados do consolidado
        # (mesma query/cache do mapa sem protocolo) e localiza o valor RAW
        # da coluna da camada pelo join normalizado (mesma chave do merge).
        # Em paralelo (3k): média geral do protocolo selecionado — independe
        # da região.
        if protocolo_id:
            aggregates, protocolo_geral = await asyncio.gather(
                self._repository.fetch_regularidade_por_camada(
                    camada=camada,
                    user_token=user_token,
                    user_id=user_id,
                    bypass_cache=bypass_cache,
                    status=status,
                    cohortes=cohortes,
                    protocolo_id=None,
                ),
                self._repository.fetch_protocolo_geral(
                    protocolo_id=protocolo_id,
                    user_token=user_token,
                    user_id=user_id,
                    bypass_cache=bypass_cache,
                    status=status,
                    cohortes=cohortes,
                ),
            )
        else:
            aggregates = await self._repository.fetch_regularidade_por_camada(
                camada=camada,
                user_token=user_token,
                user_id=user_id,
                bypass_cache=bypass_cache,
                status=status,
                cohortes=cohortes,
                protocolo_id=None,
            )
            protocolo_geral = None

        geral: RegiaoRegularidadeResumo | None = None
        regiao_raw: str | None = None
        for agg in aggregates:
            if normalize(agg.regiao) == key:
                regiao_raw = agg.regiao
                geral = _resumo(
                    agg.total_participantes,
                    agg.total_regulares,
                    agg.total_irregulares,
                )
                break

        # 2) Protocolos da região (só se a região tem dados no consolidado —
        # sem o valor raw não há como filtrar com eq; região sem dados não
        # tem participantes no escopo RLS, então protocolos vazios é o
        # resultado correto).
        protocolos = []
        if regiao_raw is not None:
            protocolos = await self._repository.fetch_protocolos_por_regiao(
                camada=camada,
                regiao=regiao_raw,
                user_token=user_token,
                user_id=user_id,
                bypass_cache=bypass_cache,
                status=status,
                cohortes=cohortes,
            )
        protocolos.sort(
            key=lambda p: (p.protocolo_secretaria or "", p.protocolo_descricao or "")
        )

        logger.info(
            f"[geospatial] detalhes da região camada={camada!r} "
            f"regiao={regiao!r}: geral={'ok' if geral else 'sem dados'}, "
            f"{len(protocolos)} protocolos, protocolo_geral="
            f"{'ok' if protocolo_geral else 'sem dados' if protocolo_id else 'n/a'} "
            f"user_id={user_id!r}"
        )
        return RegiaoDetalhes(
            camada=camada,
            regiao=regiao,
            geral=geral,
            protocolo_geral=protocolo_geral,
            protocolos=protocolos,
        )
