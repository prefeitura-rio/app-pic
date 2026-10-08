"""Column/constant vocabulary for the participant PostgREST repository.

The wide schema is owned by the data-proxy: `endpoint_participante_protocolos_wide`
is one row per participant with one status column per protocol (column name ==
protocolo_id, NULL when the participant lacks it). This module holds the table
names, per-operation select lists, cache TTLs and the CSV-export column policy
shared by `postgrest_participant_repository` and its helpers.
"""

from src.pic.infrastructure.export.csv_columns import build_export_header

TABLE_PROTOCOLOS = "endpoint_participante_protocolos_detalhe"
TABLE_PROTOCOLO_DETALHES = "protocolo_detalhes"
TABLE_PROTOCOLOS_WIDE = "endpoint_participante_protocolos_wide"

# PGRST_DB_MAX_ROWS of the data-proxy: every response is capped at this many
# rows, so "fetch everything" loops in pages of this size.
DB_MAX_ROWS = 1000

# Redis cache TTL in seconds (session lifetime).
CACHE_TTL_SECONDS = 1800

# TTL for EMPTY results: a zero-row list can be legitimate (filters without
# match) but can also be the symptom of a race — e.g. the read reaching the
# data-proxy before the RLS policy sync finished. Caching that for the full
# session would keep the list wrongly empty for 30 minutes; a short TTL
# self-heals within a minute.
EMPTY_CACHE_TTL_SECONDS = 60

CACHE_PREFIX = "participants_v2:"

VOCAB_CACHE_PREFIX = "filters_v2:"

DEFAULT_SORT_COLUMN = "nome"

# Columns filtered with exact equality instead of ILIKE: unit IDs may be
# numeric in Postgres (ILIKE needs text), and dates have no casing.
EXACT_COLUMNS = {
    "id_cre",
    "id_ap",
    "id_cas",
    "id_cras",
    "id_escola",
    "id_clinica_familia",
    "id_equipe_familia",
    "cohort",
}

# Columns every list view selects.
BASE_LIST_COLUMNS = [
    "id_familia",
    "id_membro_familia",
    "nome",
    "cpf",
    "grupo",
    "bairro",
    "idade",
    "status",
    "raca",
    "has_cartao_pic",
    "busca_ativa_smas_30d_indicador",
    "busca_ativa_sms_30d_indicador",
]

# Full-access extras returned verbatim from the resumo table.
FULL_ACCESS_COLUMNS = [
    "situacao",
    "total_fracao",
    "assistencia_fracao",
    "educacao_fracao",
    "saude_fracao",
    "total_protocolos_irregular",
]

# Busca ativa export: only the identity/address columns are needed from the
# wide table (the events come from `endpoint_busca_ativa`). Selecting just
# these keeps the payload tiny vs `select("*")` (hundreds of protocol columns).
BUSCA_ATIVA_EXPORT_COLUMNS = [
    "id_membro_familia",
    "cpf",
    "nome",
    "nascimento_data",
    "endereco",
    "complemento",
    "bairro",
    "endereco_sms",
]

# CSV export column policy: every export fetches `select("*")` and the
# disallowed columns are stripped per row in-app. The exact wide schema is
# owned by the data-proxy (materialized table); an explicit `select` built
# from a guessed column list would fail with 400 if any column name drifts.
# Columns outside the user's reach are the protocol-derived aggregates below
# (partial access) plus `latitude`/`longitude` (super-admin only).
EXPORT_GLOBAL_COLUMNS = [
    "situacao",
    "total_fracao",
    "total_protocolos",
    "total_protocolos_regular",
    "total_protocolos_irregular",
    "total_protocolos_atencao",
]

# Export prefetch window: how many pages are fetched concurrently
# (`asyncio.gather`), re-emitted in offset order.
EXPORT_PREFETCH_WINDOW = 3

# Header used when the export has zero rows (no data row to derive the
# column names from). Derived from the fixed CSV map (`csv_columns`), with no
# hidden columns: the full participant header + every protocol column.
EXPORT_FALLBACK_COLUMNS = build_export_header(set())
