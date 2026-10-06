import json

import pytest

from src.pic.infrastructure.export.csv_columns import (
    EXPORT_CSV_COLUMNS,
    PROTOCOL_CSV_RENAMES,
    build_export_header,
    transform_row,
)
from src.pic.infrastructure.export.csv_generator import rows_to_csv_chunks
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    PROTOCOLO_STATUS_COLUMNS,
)

_PROTOCOL_HEADERS = [PROTOCOL_CSV_RENAMES.get(p, p) for p in PROTOCOLO_STATUS_COLUMNS]


def _values(row, headers):
    return dict(zip(headers, transform_row(row, headers), strict=True))


async def _collect(chunks) -> str:
    data = b""
    async for chunk in chunks:
        data += chunk
    return data.decode("utf-8")


def test_row_transforms_address_renames():
    headers = build_export_header(set())
    row = {"endereco": "Rua A", "complemento": "Apto 1", "bairro": "Centro"}
    values = _values(row, headers)
    assert values["endereco_smas"] == "Rua A"
    assert values["complemento_endereco_smas"] == "Apto 1"
    assert values["bairro_endereco_smas"] == "Centro"
    assert "endereco" not in values
    assert "complemento" not in values
    assert "bairro" not in values


def test_row_extracts_endereco_sms_columns_from_dict():
    headers = build_export_header(set())
    row = {
        "endereco_sms": {
            "endereco": "Rua SMS",
            "complemento": "Casa",
            "bairro": "Bairro SMS",
        }
    }
    values = _values(row, headers)
    assert values["endereco_sms"] == "Rua SMS"
    assert values["complemento_endereco_sms"] == "Casa"
    assert values["bairro_endereco_sms"] == "Bairro SMS"


def test_row_extracts_endereco_sms_columns_from_json_string():
    headers = build_export_header(set())
    row = {
        "endereco_sms": json.dumps(
            {"endereco": "Rua J", "complemento": None, "bairro": "B"}
        )
    }
    values = _values(row, headers)
    assert values["endereco_sms"] == "Rua J"
    assert values["complemento_endereco_sms"] is None
    assert values["bairro_endereco_sms"] == "B"


def test_row_extracts_endereco_sms_missing_keys_as_none():
    headers = build_export_header(set())
    for value in (None, {}, "", "not-json", 123):
        values = _values({"endereco_sms": value}, headers)
        assert values["endereco_sms"] is None
        assert values["complemento_endereco_sms"] is None
        assert values["bairro_endereco_sms"] is None


def test_row_translates_boolean_columns():
    headers = build_export_header(set())

    assert _values({"has_cartao_pic": True}, headers)["status_cartao_pic"] == "retirado"
    assert (
        _values({"has_cartao_pic": False}, headers)["status_cartao_pic"]
        == "não retirado"
    )
    assert (
        _values({"has_cartao_pic": None}, headers)["status_cartao_pic"] == "sem direito"
    )

    assert (
        _values({"has_bolsa_familia": True}, headers)["status_bolsa_familia"]
        == "beneficiário"
    )
    assert (
        _values({"has_bolsa_familia": False}, headers)["status_bolsa_familia"]
        == "não beneficiário"
    )
    assert _values({"has_bolsa_familia": None}, headers)["status_bolsa_familia"] == "-"

    for origin, header in (
        ("has_cobertura_equipe_familia", "possui_cobertura_equipe_de_familia"),
        ("has_cobertura_clinica_familia", "possui_cobertura_clinica_da_familia"),
    ):
        assert _values({origin: True}, headers)[header] == "SIM"
        assert _values({origin: False}, headers)[header] == "NÃO"
        assert _values({origin: None}, headers)[header] == "-"

    assert _values({"has_cartao_pic": "yes"}, headers)["status_cartao_pic"] is None


def test_row_formats_dates_dd_mm_yyyy():
    headers = build_export_header(set())
    values = _values({"nascimento_data": "2020-01-31", "cohort": "2025-03-01"}, headers)
    assert values["nascimento_data"] == "31/01/2020"
    assert values["cohort"] == "01/03/2025"


def test_row_formats_dates_invalid_becomes_none():
    headers = build_export_header(set())
    values = _values({"nascimento_data": "not-a-date", "cohort": None}, headers)
    assert values["nascimento_data"] is None
    assert values["cohort"] is None


def test_row_drops_cpf_particao_and_unmapped_columns():
    headers = build_export_header(set())
    row = {"id_membro_familia": "1", "nome": "A", "cpf_particao": 7, "future_col": "x"}
    values = _values(row, headers)
    assert list(values.keys()) == headers
    assert "cpf_particao" not in headers
    assert "future_col" not in headers
    assert values["nome"] == "A"


def test_header_is_fixed_and_deterministic():
    assert build_export_header(set()) == build_export_header(set())
    assert build_export_header(set()) == EXPORT_CSV_COLUMNS + _PROTOCOL_HEADERS


def test_protocol_columns_appended_in_fixed_order():
    headers = build_export_header(set())
    assert headers[-len(_PROTOCOL_HEADERS) :] == _PROTOCOL_HEADERS


def test_protocol_column_rename_sme_frequencia_escolar():
    headers = build_export_header(set())
    # The CSV header is renamed; the DB column name never leaks.
    assert "sme_frequencia_creche_escola" in headers
    assert "sme_frequencia_escolar" not in headers
    # The value is read from the wide-table column name.
    values = _values({"sme_frequencia_escolar": "Regular"}, headers)
    assert values["sme_frequencia_creche_escola"] == "Regular"


def test_hidden_columns_filtered_from_header():
    headers = build_export_header(
        {
            "situacao",
            "total_fracao",
            "saude_fracao",
            "assistencia_protocolos_total",
            "sms_vacinacao_pentavalente",
            "latitude",
            "longitude",
        }
    )
    for hidden in (
        "situacao",
        "total_fracao",
        "saude_fracao",
        "assistencia_protocolos_total",
        "sms_vacinacao_pentavalente",
        "latitude",
        "longitude",
    ):
        assert hidden not in headers
    # Base participant columns stay.
    assert "nome" in headers
    assert "endereco_smas" in headers
    assert "bairro_endereco_sms" in headers


@pytest.mark.asyncio
async def test_empty_pages_emit_header_only():
    async def pages():
        return
        yield []  # pragma: no cover

    columns = build_export_header(set())
    data = await _collect(rows_to_csv_chunks(pages(), columns))
    assert data == "\ufeff" + ";".join(columns) + "\n"


@pytest.mark.asyncio
async def test_stream_transforms_rows_with_delimiter_and_quoting():
    async def pages():
        yield [
            {
                "nome": "Ana",
                "endereco": "Rua A",
                "has_cartao_pic": True,
                "nascimento_data": "2020-01-31",
                "cpf_particao": 1,
            }
        ]

    columns = build_export_header(set())
    data = await _collect(rows_to_csv_chunks(pages(), columns))
    lines = data.split("\n")
    assert lines[0] == "\ufeff" + ";".join(columns)
    cells = dict(zip(columns, lines[1].split(";"), strict=True))
    assert cells["nome"] == '"Ana"'
    assert cells["endereco_smas"] == '"Rua A"'
    assert cells["status_cartao_pic"] == '"retirado"'
    assert cells["nascimento_data"] == '"31/01/2020"'
