"""Pure-Python helpers for the WhatsApp disparo filters of the Busca Individual.

The disparo filters (`disparo_jornada` campaign + `disparo_status`) read
`endpoint_whatsapp_disparo` (one row per participant × window; the
`disparo_*` columns describe the participant's MOST RECENT disparo, canonical
window `DISPARO_JANELA_DIAS`), while the participant list reads
`endpoint_participante_protocolos_wide`. PostgREST cannot filter one table by
another without a foreign key, so the filter runs in two steps:

1. resolve the `id_membro_familia` of every participant whose most recent
   disparo matches the selected campaigns/statuses (this module's builders);
2. restrict the wide query with `id_membro_familia=in.(...)`.

Both reads carry the end user's JWT so the data-proxy applies RLS to each
one. Access control by secretaria is enforced at the query level: the
disparos read is restricted to `disparo_secretaria_sigla=in.(...)` with the
user's accessible secretarias (full access = no restriction).
"""

from typing import Any

from postgrest import AsyncSelectRequestBuilder

from src.pic.domain.errors import ValidationError
from src.pic.domain.models.filters import FilterCriteria
from src.pic.infrastructure.postgrest_client.client import PostgrestClient
from src.pic.infrastructure.repositories.helpers.participant_filtering import (
    apply_scalar_filter,
    clean_values,
    search_or_term,
    split_values,
)

# Disparos table (BigQuery exposed by the data-proxy).
TABLE_DISPAROS = "endpoint_whatsapp_disparo"

# Canonical window of the product (same as the participant detail and the
# dashboard): `disparo_*` describes the most recent disparo and
# `disparo_na_janela_indicador=true` keeps only the rows whose most recent
# disparo falls inside this window.
DISPARO_JANELA_DIAS = 240

# Fixed status vocabulary (UI order as specified). `SEM_RETORNO` exists in the
# data but is intentionally not offered.
DISPARO_STATUS_IDS = ["LIDO", "ENTREGUE", "RESPONDIDO", "ENVIADO", "FALHOU"]

DISPARO_STATUS_LABELS = {
    "LIDO": "Lida",
    "ENTREGUE": "Entregue",
    "RESPONDIDO": "Respondido",
    "ENVIADO": "Enviado",
    "FALHOU": "Falha",
}

# Wide-table columns (already mapped by `split_filters`) that also exist on
# `endpoint_whatsapp_disparo` — the "cascade when possible" for the campaign
# options. Filters without a matching column there (situacao, raca, status,
# bolsa familia, cartao pic, protocolos, busca ativa, equipe de saude) are
# ignored.
DISPARO_SCALAR_CASCADE_COLUMNS = frozenset(
    {
        "grupo",
        "cohort",
        "subprefeitura",
        "regiao_administrativa",
        "bairro",
        "id_cas",
        "id_cras",
        "id_cre",
        "id_escola",
        "id_ap",
        "id_clinica_familia",
    }
)


def split_disparo_filters(
    filters: FilterCriteria,
) -> tuple[list[str] | None, list[str] | None]:
    """Split `(jornadas, statuses)` from one `FilterCriteria`.

    Validations (mirroring the strictness of the protocol filters):

    - unknown `disparo_status` value -> `ValidationError` (422);
    - `disparo_status` without `disparo_jornada` -> `ValidationError` (422):
      the status filter only makes sense combined with a campaign (the UI
      only unlocks it after a campaign is selected).
    """
    jornadas: list[str] | None = None
    statuses: list[str] | None = None

    if filters.disparo_jornada:
        values = clean_values(
            [str(value) for value in split_values(filters.disparo_jornada)]
        )
        if values:
            jornadas = values

    if filters.disparo_status:
        raw = clean_values(
            [str(value).upper() for value in split_values(filters.disparo_status)]
        )
        if raw:
            unknown = set(raw) - set(DISPARO_STATUS_IDS)
            if unknown:
                raise ValidationError(
                    "Valor inválido para disparo_status: "
                    + ", ".join(sorted(unknown))
                )
            if not jornadas:
                raise ValidationError(
                    "O filtro disparo_status exige o filtro disparo_jornada"
                )
            statuses = raw

    return jornadas, statuses


def apply_disparo_cascade(
    query: AsyncSelectRequestBuilder,
    column_filters: dict[str, list[Any]],
    *,
    search_term: str | None = None,
) -> AsyncSelectRequestBuilder:
    """Apply the wide-column filters that also exist on the disparos table.

    Used by the campaign options query so the offered campaigns follow the
    other active filters when possible (`DISPARO_SCALAR_CASCADE_COLUMNS`);
    everything else (protocols, status, situacao, busca ativa...) has no
    equivalent column there and is ignored.
    """
    for column, values in column_filters.items():
        if column in DISPARO_SCALAR_CASCADE_COLUMNS:
            query = apply_scalar_filter(query, column, values)
    if search_term:
        query = query.or_(search_or_term(search_term))
    return query


def build_disparo_ids_query(
    client: PostgrestClient,
    *,
    jornadas: list[str],
    statuses: list[str] | None,
    allowed_secretarias: set[str] | None,
) -> AsyncSelectRequestBuilder:
    """Ids of participants whose most recent disparo matches the filters.

    Campaign and status match the SAME row (the most recent disparo of the
    participant). Partial access restricts the query to the accessible
    secretarias; a campaign outside them matches nothing (empty list).
    """
    query = (
        client.table(TABLE_DISPAROS)
        .select("id_membro_familia")
        .eq("janela_dias", DISPARO_JANELA_DIAS)
        .filter("disparo_na_janela_indicador", "is", "true")
        .filter("disparo_jornada", "in", f"({','.join(jornadas)})")
    )
    if statuses:
        query = query.filter("disparo_status", "in", f"({','.join(statuses)})")
    if allowed_secretarias:
        query = query.filter(
            "disparo_secretaria_sigla",
            "in",
            f"({','.join(sorted(allowed_secretarias))})",
        )
    return query


def build_disparo_campaigns_query(
    client: PostgrestClient,
    *,
    statuses: list[str] | None,
    allowed_secretarias: set[str] | None,
    column_filters: dict[str, list[Any]],
    search_term: str | None,
) -> AsyncSelectRequestBuilder:
    """Aggregate query feeding the campaign options.

    PostgREST groups by the non-aggregate columns
    (`disparo_jornada, disparo_secretaria_sigla`) restricted to the canonical
    window and to the accessible secretarias. The campaign's own filter is
    excluded by the caller (it is not part of `column_filters`), while the
    section's status filter cascades like any other active filter.
    """
    query = (
        client.table(TABLE_DISPAROS)
        .select("disparo_jornada,disparo_secretaria_sigla,count()")
        .eq("janela_dias", DISPARO_JANELA_DIAS)
        .filter("disparo_na_janela_indicador", "is", "true")
        .not_.is_("disparo_jornada", "null")
    )
    if statuses:
        query = query.filter("disparo_status", "in", f"({','.join(statuses)})")
    if allowed_secretarias:
        query = query.filter(
            "disparo_secretaria_sigla",
            "in",
            f"({','.join(sorted(allowed_secretarias))})",
        )
    return apply_disparo_cascade(query, column_filters, search_term=search_term)
