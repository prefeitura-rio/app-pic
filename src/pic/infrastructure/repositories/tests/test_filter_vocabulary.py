"""Unit tests for the pure-Python filter option computation."""

from src.pic.infrastructure.repositories.helpers.filter_vocabulary import (
    FILTER_OPTION_CONFIGS,
    PROTOCOLO_DESCRICOES,
    build_options,
)


def test_scalar_options_sort_naturally_and_drop_empty():
    rows = [
        {"bairro": "10 de Maio", "count": 1},
        {"bairro": "3 de Outubro", "count": 2},
        {"bairro": None, "count": 1},
        {"bairro": "", "count": 1},
    ]
    options = build_options(FILTER_OPTION_CONFIGS["bairros"], rows)
    assert [(o.id, o.label) for o in options] == [
        ("3 de Outubro", "3 de Outubro"),
        ("10 de Maio", "10 de Maio"),
    ]


def test_unit_options_group_ids_by_label_with_pipe():
    rows = [
        {"id_cras": "1", "nome_cras": "CRAS Centro", "count": 3},
        {"id_cras": "2", "nome_cras": "CRAS Centro", "count": 5},
        {"id_cras": "3", "nome_cras": "CRAS Zona Sul", "count": 1},
        {"id_cras": None, "nome_cras": "Sem ID", "count": 1},
        {"id_cras": "4", "nome_cras": None, "count": 2},
    ]
    options = build_options(FILTER_OPTION_CONFIGS["cras"], rows)
    # v1 parity: natural sort puts labels starting with digits first ("4").
    assert [(o.id, o.label) for o in options] == [
        ("4", "4"),  # nome null falls back to the id (v1 parity)
        ("1|2", "CRAS Centro"),
        ("3", "CRAS Zona Sul"),
    ]


def test_wide_counts_options_use_backend_labels_and_drop_zeros():
    row = {
        "sms_vacinacao_pentavalente": 3,
        "sme_frequencia_escolar": 2,
        "smas_acesso_alimentacao": 0,
        "sms_consulta_puerperal": None,
    }
    options = build_options(
        FILTER_OPTION_CONFIGS["protocolo_descricoes"], [row]
    )
    ids = {o.id for o in options}
    assert ids == {"sms_vacinacao_pentavalente", "sme_frequencia_escolar"}
    assert all(o.label == PROTOCOLO_DESCRICOES[o.id] for o in options)
    labels = [o.label for o in options]
    assert labels == sorted(labels)


def test_wide_counts_options_empty_when_nothing_present():
    options = build_options(
        FILTER_OPTION_CONFIGS["protocolo_descricoes"], []
    )
    assert options == []


def test_wide_counts_options_restricted_to_allowed_secretarias():
    row = {
        "sms_vacinacao_pentavalente": 3,
        "sme_frequencia_escolar": 2,
        "smas_acesso_alimentacao": 5,
    }
    restricted = build_options(
        FILTER_OPTION_CONFIGS["protocolo_descricoes"],
        [row],
        allowed_secretarias={"SMAS"},
    )
    assert [o.id for o in restricted] == ["smas_acesso_alimentacao"]


def test_wide_counts_options_empty_when_restriction_matches_nothing():
    row = {"sms_vacinacao_pentavalente": 3}
    options = build_options(
        FILTER_OPTION_CONFIGS["protocolo_descricoes"],
        [row],
        allowed_secretarias={"SMAS"},
    )
    assert options == []


def test_static_status_options():
    options = build_options(FILTER_OPTION_CONFIGS["protocolo_status_list"], [])
    assert [o.id for o in options] == ["Atenção", "Irregular", "Regular"]


def test_bool_options_fixed_order_and_labels():
    rows = [
        {"has_bolsa_familia": False, "count": 4},
        {"has_bolsa_familia": True, "count": 9},
    ]
    options = build_options(FILTER_OPTION_CONFIGS["bolsa_familia"], rows)
    assert [(o.id, o.label) for o in options] == [
        ("true", "Com Bolsa Família"),
        ("false", "Sem Bolsa Família"),
    ]

    only_false = build_options(
        FILTER_OPTION_CONFIGS["bolsa_familia"], rows[:1]
    )
    assert [(o.id, o.label) for o in only_false] == [
        ("false", "Sem Bolsa Família")
    ]


def test_wide_secretaria_options_intersect_access_and_fixed_order():
    row = {
        "saude_protocolos_total": 2,
        "assistencia_protocolos_total": 1,
        "educacao_protocolos_total": 0,
    }
    options = build_options(
        FILTER_OPTION_CONFIGS["protocolo_secretarias"], [row]
    )
    assert [(o.id, o.label) for o in options] == [
        ("SMAS", "Assistência (SMAS)"),
        ("SMS", "Saúde (SMS)"),
    ]

    restricted = build_options(
        FILTER_OPTION_CONFIGS["protocolo_secretarias"],
        [row],
        allowed_secretarias={"SMS"},
    )
    assert [(o.id, o.label) for o in restricted] == [("SMS", "Saúde (SMS)")]
