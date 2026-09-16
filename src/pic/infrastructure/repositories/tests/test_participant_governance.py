from src.pic.infrastructure.repositories.helpers import (
    participant_governance as governance,
)

ALL = ["SME", "SMS", "SMAS"]


def make_row(**overrides):
    row = {
        "id_membro_familia": "MEM1",
        "nome": "Maria",
        "protocolo_listagem": [
            {
                "id": "sms_a",
                "secretaria": "SMS",
                "descricao": "a",
                "status": "regular",
                "irregular_indicador": "false",
                "protocolo_status_label": "Regular",
            },
            {
                "id": "sms_b",
                "secretaria": "SMS",
                "descricao": "b",
                "status": "atencao",
                "irregular_indicador": "true",
                "protocolo_status_label": "Atenção",
            },
            {
                "id": "sme_a",
                "secretaria": "SME",
                "descricao": "c",
                "status": "regular",
                "irregular_indicador": "false",
                "protocolo_status_label": "Regular",
            },
        ],
        "total_protocolos": 3,
        "total_protocolos_irregular": 1,
        "total_protocolos_atencao": 1,
        "total_protocolos_regular": 2,
        "situacao": "Atenção",
        "total_fracao": "2/3",
        "assistencia_protocolos_total": 3,
        "assistencia_fracao": "2/3",
        "educacao_protocolos_total": 3,
        "educacao_fracao": "2/3",
        "saude_protocolos_total": 3,
        "saude_fracao": "2/3",
    }
    row.update(overrides)
    return row


def test_has_full_protocol_access():
    assert governance.has_full_protocol_access(ALL)
    assert not governance.has_full_protocol_access(["SMS"])
    assert not governance.has_full_protocol_access([])


def test_full_access_returns_row_unchanged():
    row = make_row()
    result = governance.apply_secretaria_governance(row, ALL)
    assert result is row


def test_partial_access_filters_and_recalculates():
    row = make_row()
    result = governance.apply_secretaria_governance(row, ["SMS"])

    assert result is not None
    assert [p["id"] for p in result["protocolo_listagem"]] == ["sms_a", "sms_b"]
    # Recomputed from the 2 SMS protocols: 1 regular, 1 atencao(irregular)
    assert result["total_protocolos"] == 2
    assert result["total_protocolos_irregular"] == 1
    assert result["total_protocolos_atencao"] == 1
    assert result["total_protocolos_regular"] == 1
    assert result["situacao"] == "Atenção"
    assert result["total_fracao"] == "1/2"
    # SMS (saude) recomputed; others nulled out
    assert result["saude_protocolos_total"] == 2
    assert result["saude_protocolos_irregular"] == 1
    assert result["saude_fracao"] == "1/2"
    assert result["educacao_protocolos_total"] is None
    assert result["educacao_fracao"] is None
    assert result["assistencia_protocolos_total"] is None
    assert result["assistencia_fracao"] is None
    # Input row untouched
    assert row["total_protocolos"] == 3


def test_partial_access_drops_row_without_matching_protocols():
    row = make_row()
    row["protocolo_listagem"] = [
        {
            "id": "sme_a",
            "secretaria": "SME",
            "irregular_indicador": "false",
            "protocolo_status_label": "Regular",
        }
    ]
    assert governance.apply_secretaria_governance(row, ["SMS"]) is None


def test_no_access_keeps_row_but_nulls_everything():
    row = make_row()
    result = governance.apply_secretaria_governance(row, [])

    assert result is not None
    assert result["protocolo_listagem"] == []
    assert result["total_protocolos"] is None
    assert result["total_protocolos_irregular"] is None
    assert result["total_protocolos_atencao"] is None
    assert result["total_protocolos_regular"] is None
    assert result["situacao"] is None
    assert result["total_fracao"] is None
    assert result["saude_protocolos_total"] is None
    assert result["saude_fracao"] is None
    assert result["educacao_protocolos_total"] is None
    assert result["assistencia_protocolos_total"] is None


def test_governance_handles_boolean_irregular_indicador():
    row = make_row()
    for protocolo in row["protocolo_listagem"]:
        protocolo["irregular_indicador"] = protocolo["irregular_indicador"] == "true"
    result = governance.apply_secretaria_governance(row, ["SMS"])
    assert result["total_protocolos_irregular"] == 1


def test_situacao_variants():
    row = make_row()
    row["protocolo_listagem"] = [
        {
            "id": "p1",
            "secretaria": "SMS",
            "irregular_indicador": "false",
            "protocolo_status_label": "Regular",
        }
    ]
    result = governance.apply_secretaria_governance(row, ["SMS"])
    assert result["situacao"] == "Regular"

    row["protocolo_listagem"] = [
        {
            "id": "p1",
            "secretaria": "SMS",
            "irregular_indicador": "true",
            "protocolo_status_label": "Irregular",
        }
    ]
    result = governance.apply_secretaria_governance(row, ["SMS"])
    assert result["situacao"] == "Irregular"


def detail_items():
    return [
        {
            "id": "sms_a",
            "secretaria": "SMS",
            "descricao": "a",
            "status": "regular",
            "irregular_indicador": False,
            "protocolo_status_label": "Regular",
        },
        {
            "id": "sms_b",
            "secretaria": "SMS",
            "descricao": "b",
            "status": "atencao",
            "irregular_indicador": True,
            "protocolo_status_label": "Atenção",
        },
        {
            "id": "sme_a",
            "secretaria": "SME",
            "descricao": "c",
            "status": "regular",
            "irregular_indicador": False,
            "protocolo_status_label": "Regular",
        },
    ]


def resumo_detail_row(**overrides):
    row = {
        "id_membro_familia": "MEM1",
        "nome": "Maria",
        "total_protocolos": 9,
        "total_protocolos_irregular": 9,
        "total_protocolos_atencao": 9,
        "total_protocolos_regular": 9,
        "situacao": "Irregular",
        "total_fracao": "0/9",
        "assistencia_protocolos_total": 9,
        "assistencia_fracao": "0/9",
        "educacao_protocolos_total": 9,
        "educacao_fracao": "0/9",
        "saude_protocolos_total": 9,
        "saude_fracao": "0/9",
    }
    row.update(overrides)
    return row


class TestComputeDetailView:
    def test_full_access_recomputes_from_items(self):
        resumo = resumo_detail_row()
        result = governance.compute_detail_view(resumo, detail_items(), [], full_access=True)

        assert result is not None
        assert [p["id"] for p in result["protocolo_listagem"]] == [
            "sms_a",
            "sms_b",
            "sme_a",
        ]
        assert result["total_protocolos"] == 3
        assert result["total_protocolos_irregular"] == 1
        assert result["total_protocolos_atencao"] == 1
        assert result["total_protocolos_regular"] == 2
        assert result["situacao"] == "Atenção"
        assert result["total_fracao"] == "2/3"
        assert result["saude_protocolos_total"] == 2
        assert result["saude_protocolos_irregular"] == 1
        assert result["saude_fracao"] == "1/2"
        assert result["educacao_protocolos_total"] == 1
        assert result["educacao_fracao"] == "1/1"
        assert result["assistencia_protocolos_total"] == 0
        assert result["assistencia_fracao"] == "0/0"
        # Pre-aggregated resumo counters were overwritten, not trusted.
        assert resumo["total_protocolos"] == 9

    def test_partial_access_filters_and_recalculates(self):
        resumo = resumo_detail_row()
        result = governance.compute_detail_view(
            resumo, detail_items(), ["SMS"], full_access=False
        )

        assert result is not None
        assert [p["id"] for p in result["protocolo_listagem"]] == ["sms_a", "sms_b"]
        assert result["total_protocolos"] == 2
        assert result["total_protocolos_irregular"] == 1
        assert result["total_protocolos_atencao"] == 1
        assert result["total_protocolos_regular"] == 1
        assert result["situacao"] == "Atenção"
        assert result["total_fracao"] == "1/2"
        assert result["saude_protocolos_total"] == 2
        assert result["saude_fracao"] == "1/2"
        assert result["educacao_protocolos_total"] is None
        assert result["educacao_fracao"] is None
        assert result["assistencia_protocolos_total"] is None
        assert result["assistencia_fracao"] is None

    def test_partial_access_drops_row_without_matching_protocols(self):
        resumo = resumo_detail_row()
        assert (
            governance.compute_detail_view(
                resumo, detail_items(), ["SMAS"], full_access=False
            )
            is None
        )

    def test_no_access_keeps_row_but_nulls_everything(self):
        resumo = resumo_detail_row()
        result = governance.compute_detail_view(
            resumo, detail_items(), [], full_access=False
        )

        assert result is not None
        assert result["protocolo_listagem"] == []
        assert result["total_protocolos"] is None
        assert result["total_protocolos_irregular"] is None
        assert result["total_protocolos_atencao"] is None
        assert result["total_protocolos_regular"] is None
        assert result["situacao"] is None
        assert result["total_fracao"] is None
        assert result["saude_protocolos_total"] is None
        assert result["saude_fracao"] is None
        assert result["educacao_protocolos_total"] is None
        assert result["assistencia_protocolos_total"] is None

    def test_does_not_mutate_inputs(self):
        resumo = resumo_detail_row()
        items = detail_items()
        result = governance.compute_detail_view(
            resumo, items, ["SMS"], full_access=False
        )

        assert result is not None
        assert [p["id"] for p in items] == ["sms_a", "sms_b", "sme_a"]
        assert resumo["total_protocolos"] == 9
        assert "protocolo_listagem" not in resumo


class TestMatchProtocoloFilters:
    def _protocolos(self):
        return [
            {"id": "a", "protocolo_status_label": "Atenção", "secretaria": "SMS"},
            {"id": "b", "protocolo_status_label": "Regular", "secretaria": "SME"},
        ]

    def test_empty_filters_match(self):
        assert governance.match_protocolo_filters(self._protocolos(), {}) is True

    def test_single_field_matches_any_item(self):
        assert (
            governance.match_protocolo_filters(self._protocolos(), {"id": ["a"]})
            is True
        )

    def test_single_field_no_match(self):
        assert (
            governance.match_protocolo_filters(self._protocolos(), {"id": ["zzz"]})
            is False
        )

    def test_multi_value_same_field_is_and(self):
        # Row must have BOTH a and b.
        assert (
            governance.match_protocolo_filters(self._protocolos(), {"id": ["a", "b"]})
            is True
        )
        assert (
            governance.match_protocolo_filters(self._protocolos(), {"id": ["a", "zzz"]})
            is False
        )

    def test_cross_field_must_match_same_item(self):
        # (id=a, label=Atenção) is the same item -> match.
        assert (
            governance.match_protocolo_filters(
                self._protocolos(),
                {"id": ["a"], "protocolo_status_label": ["Atenção"]},
            )
            is True
        )
        # id=a lives in an item whose label is not Regular -> no match.
        assert (
            governance.match_protocolo_filters(
                self._protocolos(),
                {"id": ["a"], "protocolo_status_label": ["Regular"]},
            )
            is False
        )

    def test_case_insensitive(self):
        assert (
            governance.match_protocolo_filters(
                self._protocolos(), {"protocolo_status_label": ["ATENÇÃO"]}
            )
            is True
        )

    def test_multi_value_field_with_single_field_same_item(self):
        # Every value of the multi field must have an item also matching the
        # single-field filter.
        protocolos = [
            {"id": "a", "protocolo_status_label": "Atenção"},
            {"id": "b", "protocolo_status_label": "Atenção"},
        ]
        assert (
            governance.match_protocolo_filters(
                protocolos, {"id": ["a", "b"], "protocolo_status_label": ["Atenção"]}
            )
            is True
        )
        protocolos[1]["protocolo_status_label"] = "Regular"
        assert (
            governance.match_protocolo_filters(
                protocolos, {"id": ["a", "b"], "protocolo_status_label": ["Atenção"]}
            )
            is False
        )


class TestMatchSituacao:
    def test_case_insensitive_in(self):
        row = {"situacao": "Atenção"}
        assert governance.match_situacao(row, ["ATENÇÃO"]) is True
        assert governance.match_situacao(row, ["Regular"]) is False
        assert governance.match_situacao(row, ["Atenção", "Regular"]) is True

    def test_empty_values_match(self):
        assert governance.match_situacao({"situacao": "Atenção"}, []) is True


class TestSortRows:
    def test_asc_with_nulls_last(self):
        rows = [{"idade": 5}, {"idade": None}, {"idade": 1}]
        sorted_rows = governance.sort_rows(rows, "idade", descending=False)
        assert [r["idade"] for r in sorted_rows] == [1, 5, None]

    def test_desc_with_nulls_last(self):
        rows = [{"idade": 5}, {"idade": None}, {"idade": 1}]
        sorted_rows = governance.sort_rows(rows, "idade", descending=True)
        assert [r["idade"] for r in sorted_rows] == [5, 1, None]

    def test_does_not_mutate_input(self):
        rows = [{"idade": 5}, {"idade": 1}]
        governance.sort_rows(rows, "idade", descending=True)
        assert rows == [{"idade": 5}, {"idade": 1}]
