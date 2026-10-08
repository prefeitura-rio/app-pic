"""Busca ativa event CSV export use case.

Streams one CSV row per busca ativa event of every participant matching the
active filters. The participant identity/address comes from the wide table
(streamed page by page via `export_busca_ativa_rows`), and the events are
joined in-app with a bulk `id_membro_familia=in.(...)` read
(`get_busca_ativa_for_members`) — never one query per participant. The events
and their columns are scoped to the intersection of the user's secretaria
access and the selected `busca_ativa` filter. The same lazy-streaming contract
as `ExportParticipantsUseCase` applies: the first page is fetched eagerly so
403/422/502 errors surface before the HTTP response starts.
"""

from collections.abc import AsyncIterator
from typing import Any

from src.pic.application.ports.busca_ativa_repository import (
    BuscaAtivaRepository,
)
from src.pic.application.ports.participant_repository import ParticipantRepository
from src.pic.application.use_cases.export_participants import ExportOutput
from src.pic.domain.models.busca_ativa import BuscaAtivaEvento
from src.pic.domain.models.filters import FilterCriteria
from src.pic.domain.models.pagination import SortParams
from src.pic.infrastructure.export.busca_ativa_columns import (
    build_busca_ativa_header,
    selected_fontes_from_filter,
)


async def _empty_pages() -> AsyncIterator[list[dict[str, Any]]]:
    return
    yield  # pragma: no cover


class ExportBuscaAtivaUseCase:
    """Export busca ativa events for the filtered participants as CSV."""

    def __init__(
        self,
        participant_repository: ParticipantRepository,
        busca_ativa_repository: BuscaAtivaRepository,
    ):
        self._participants = participant_repository
        self._busca_ativa = busca_ativa_repository

    async def execute(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any = None,
        user_token: str | None = None,
        bypass_cache: bool = False,
    ) -> ExportOutput:
        """Prepare the busca ativa CSV export stream.

        `bypass_cache` is accepted for API compatibility (the export never
        reads the cache).
        """
        fontes = selected_fontes_from_filter(filters.busca_ativa)
        columns = build_busca_ativa_header(permissions, fontes)
        pages = self._stream(filters, sort, permissions, user_token, fontes)

        try:
            first_page = await anext(pages)
        except StopAsyncIteration:
            return ExportOutput(columns=columns, pages=_empty_pages())

        async def _all_pages() -> AsyncIterator[list[dict[str, Any]]]:
            if first_page:
                yield first_page
            async for page in pages:
                yield page

        return ExportOutput(columns=columns, pages=_all_pages())

    async def _stream(
        self,
        filters: FilterCriteria,
        sort: SortParams,
        permissions: Any,
        user_token: str | None,
        fontes: list[str] | None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        async for page in self._participants.export_busca_ativa_rows(
            filters, sort, permissions=permissions, user_token=user_token
        ):
            ids = [
                str(row["id_membro_familia"])
                for row in page
                if row.get("id_membro_familia") is not None
            ]
            if not ids:
                continue

            eventos = await self._busca_ativa.get_busca_ativa_for_members(
                ids, user_token=user_token, permissions=permissions, fontes=fontes
            )
            by_member: dict[str, list[BuscaAtivaEvento]] = {}
            for member_id, evento in eventos:
                by_member.setdefault(member_id, []).append(evento)

            merged: list[dict[str, Any]] = []
            for row in page:
                member_id_raw = row.get("id_membro_familia")
                if member_id_raw is None:
                    continue
                member_id = str(member_id_raw)
                for evento in by_member.get(member_id, []):
                    merged.append(self._merge_row(row, evento))
            if merged:
                yield merged

    @staticmethod
    def _merge_row(row: dict[str, Any], evento: BuscaAtivaEvento) -> dict[str, Any]:
        merged = dict(row)
        merged["fonte"] = evento.fonte
        merged["data"] = evento.data
        merged["sms_tipo_publico"] = evento.sms_tipo_publico
        merged["smas_tipo"] = evento.smas_tipo
        merged["smas_familia_localizada_indicador"] = (
            evento.smas_familia_localizada_indicador
        )
        merged["smas_protocolo_violado"] = evento.smas_protocolo_violado
        merged["smas_motivo_nao_localizada"] = evento.smas_motivo_nao_localizada

        unidade = evento.unidade_referenciada
        sms = unidade.sms if unidade else None
        smas = unidade.smas if unidade else None
        merged["unidade_sms_nome"] = sms.nome if sms else None
        merged["unidade_sms_equipe"] = sms.equipe_nome if sms else None
        merged["unidade_sms_regional"] = sms.regional if sms else None
        merged["unidade_smas_nome"] = smas.nome if smas else None
        merged["unidade_smas_regional"] = smas.regional if smas else None
        return merged
