"""Shared query mappings for participant filters/sorting.

Single source of truth for translating participant filter/sort query params
into column names. Used by both the BigQuery repository (vocabulary/export)
and the PostgREST repository (list/detail), which is why this lives in a
neutral module instead of inside one of the adapters.
"""

# Request filter key -> column name on the participants tables.
FILTER_COLUMN_MAP = {
    "subprefeitura": "subprefeitura",
    "regiao_administrativa": "regiao_administrativa",
    "bairro": "bairro",
    "cre": "id_cre",
    "ap": "id_ap",
    "cas": "id_cas",
    "cras": "id_cras",
    "escola": "id_escola",
    "clinica": "id_clinica_familia",
    "equipe_familia": "id_equipe_familia",
    "safra": "cohort",
    "grupo": "grupo",
    "status": "status",
    "situacao": "situacao",
    "has_bolsa_familia": "has_bolsa_familia",
    "raca": "raca",
}

# Protocolo filters match a field *inside* the `protocolo_listagem` array of
# objects. Values are the inner-object field names.
PROTOCOLO_FILTER_FIELDS = {
    "protocolo_descricao": "id",
    "protocolo_status": "protocolo_status_label",
    "protocolo_secretaria": "secretaria",
}

# Sort request key -> column used for ordering.
SORTABLE_COLUMNS = {
    "nome": "nome",
    "cpf": "cpf",
    "grupo": "grupo",
    "bairro": "bairro",
    "idade": "idade",
    "status": "status",
    "total_fracao": "total_protocolos_regular",
    "total_irregular": "total_protocolos_irregular",
    "assistencia_fracao": "assistencia_protocolos_regular",
    "educacao_fracao": "educacao_protocolos_regular",
    "saude_fracao": "saude_protocolos_regular",
    "situacao": "situacao",
}

# Columns matched by the free-text `search` query param (partial, case-insensitive).
SEARCH_COLUMNS = ["nome", "cpf", "id_membro_familia", "id_familia"]

# Fields of the lean participant list item (response envelope of GET /v2/participants).
LIST_ITEM_FIELDS = [
    "id_familia",
    "id_membro_familia",
    "nome",
    "cpf",
    "grupo",
    "bairro",
    "idade",
    "status",
    "situacao",
    "total_fracao",
    "assistencia_fracao",
    "educacao_fracao",
    "saude_fracao",
    "total_protocolos_irregular",
    "raca",
]
