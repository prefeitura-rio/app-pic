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

# Protocolo filters match a column of `endpoint_participante_protocolos`
# (produto table, joined by id_membro_familia). Values keep the v1 semantics
# where `protocolo_descricao` carries the protocol *id* (label is UI-only).
PROTOCOLO_FILTER_FIELDS = {
    "protocolo_descricao": "protocolo_id",
    "protocolo_status": "protocolo_status_label",
    "protocolo_secretaria": "protocolo_secretaria",
}

# One status column per protocol on `endpoint_participante_protocolos_wide`
# (column name == protocolo_id; NULL when the participant lacks the
# protocol). Kept in sync with `filter_vocabulary.PROTOCOLO_DESCRICOES`.
PROTOCOLO_STATUS_COLUMNS = [
    "smas_acesso_alimentacao",
    "smas_acesso_cpf_certidao_nascimento",
    "smas_cadunico_atualizado",
    "sme_frequencia_escolar",
    "sme_matriculado_creche",
    "sme_matriculado_pre_escola",
    "sms_consulta_puerperal",
    "sms_consultas_minimas_infantil",
    "sms_consultas_pre_natal",
    "sms_gestantes_testes_rapidos",
    "sms_possui_equipe_familia",
    "sms_vacinacao_pentavalente",
    "sms_visitas_domiciliares_infantil",
    "sms_visitas_domiciliares_puerperio",
]

# protocolo_id -> secretaria (SMAS/SME/SMS). Used to restrict the protocol
# options to the user's secretaria access and to reject forced filters
# outside it. Kept in sync with PROTOCOLO_STATUS_COLUMNS.
PROTOCOLO_SECRETARIA = {
    "smas_acesso_alimentacao": "SMAS",
    "smas_acesso_cpf_certidao_nascimento": "SMAS",
    "smas_cadunico_atualizado": "SMAS",
    "sme_frequencia_escolar": "SME",
    "sme_matriculado_creche": "SME",
    "sme_matriculado_pre_escola": "SME",
    "sms_consulta_puerperal": "SMS",
    "sms_consultas_minimas_infantil": "SMS",
    "sms_consultas_pre_natal": "SMS",
    "sms_gestantes_testes_rapidos": "SMS",
    "sms_possui_equipe_familia": "SMS",
    "sms_vacinacao_pentavalente": "SMS",
    "sms_visitas_domiciliares_infantil": "SMS",
    "sms_visitas_domiciliares_puerperio": "SMS",
}

# Sort request key -> column used for ordering.
SORTABLE_COLUMNS = {
    "nome": "nome",
    "cpf": "cpf",
    "grupo": "grupo",
    "bairro": "bairro",
    "idade": "idade",
    "status": "status",
    # "Total" sorts by the irregularidade count (fewer = better first),
    # a single column PostgREST can order directly.
    "total_fracao": "total_protocolos_irregular",
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
