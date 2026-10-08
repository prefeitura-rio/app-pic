import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.infrastructure.export.busca_ativa_columns import (
    BUSCA_ATIVA_CSV_COLUMNS,
    BUSCA_ATIVA_SECRETARIA_COLUMNS,
    build_busca_ativa_header,
    selected_fontes_from_filter,
    transform_busca_ativa_row,
)
from src.pic.infrastructure.export.csv_generator import rows_to_csv_chunks

SUPER_ADMIN = UserPermissions(
    cpf="11111111111", is_admin=True, is_super_admin=True, secretarias_acesso=[]
)
PARTIAL_SMAS = UserPermissions(
    cpf="22222222222", is_admin=False, is_super_admin=False, secretarias_acesso=["SMAS"]
)
PARTIAL_SMS = UserPermissions(
    cpf="33333333333", is_admin=False, is_super_admin=False, secretarias_acesso=["SMS"]
)
SME_ONLY = UserPermissions(
    cpf="44444444444", is_admin=False, is_super_admin=False, secretarias_acesso=["SME"]
)

_SMS_COLUMNS = set(BUSCA_ATIVA_SECRETARIA_COLUMNS["SMS"])
_SMAS_COLUMNS = set(BUSCA_ATIVA_SECRETARIA_COLUMNS["SMAS"])


def _values(row, headers):
    return dict(zip(headers, transform_busca_ativa_row(row, headers), strict=True))


def test_selected_fontes_from_filter_parses_and_normalizes():
    assert selected_fontes_from_filter(None) is None
    assert selected_fontes_from_filter("") is None
    assert selected_fontes_from_filter("SMAS") == ["SMAS"]
    assert selected_fontes_from_filter("smas|sms") == ["SMAS", "SMS"]
    assert selected_fontes_from_filter("SMAS,SMS") == ["SMAS", "SMS"]
    assert selected_fontes_from_filter("SME") == []
    assert selected_fontes_from_filter("SMAS|SME") == ["SMAS"]
    assert selected_fontes_from_filter("FOO") == []


def test_header_full_access_keeps_every_column():
    assert build_busca_ativa_header() == BUSCA_ATIVA_CSV_COLUMNS
    assert build_busca_ativa_header(SUPER_ADMIN) == BUSCA_ATIVA_CSV_COLUMNS


def test_header_smas_only_hides_sms_columns():
    headers = build_busca_ativa_header(PARTIAL_SMAS)
    assert "smas_tipo" in headers
    assert "unidade_smas_nome" in headers
    assert "sms_tipo_publico" not in headers
    assert "unidade_sms_nome" not in headers
    assert set(headers) & _SMS_COLUMNS == set()
    # Common columns stay.
    assert "id_membro_familia" in headers
    assert "fonte" in headers
    assert "data_busca_ativa" in headers


def test_header_sms_only_hides_smas_columns():
    headers = build_busca_ativa_header(PARTIAL_SMS)
    assert "sms_tipo_publico" in headers
    assert "unidade_sms_nome" in headers
    assert "smas_tipo" not in headers
    assert "unidade_smas_nome" not in headers
    assert set(headers) & _SMAS_COLUMNS == set()


def test_header_no_sms_smas_access_keeps_only_common_columns():
    headers = build_busca_ativa_header(SME_ONLY)
    assert set(headers) & _SMS_COLUMNS == set()
    assert set(headers) & _SMAS_COLUMNS == set()
    assert "id_membro_familia" in headers
    assert "fonte" in headers
    assert "data_busca_ativa" in headers


def test_header_filter_fontes_prunes_columns_under_full_access():
    # Full access, but the filter selected only SMAS -> SMS columns hidden.
    headers = build_busca_ativa_header(SUPER_ADMIN, ["SMAS"])
    assert "smas_tipo" in headers
    assert "unidade_smas_nome" in headers
    assert set(headers) & _SMS_COLUMNS == set()

    # SMS-only selection -> SMAS columns hidden.
    headers = build_busca_ativa_header(SUPER_ADMIN, ["SMS"])
    assert "sms_tipo_publico" in headers
    assert set(headers) & _SMAS_COLUMNS == set()


def test_header_filter_fontes_empty_keeps_only_common_columns():
    headers = build_busca_ativa_header(SUPER_ADMIN, [])
    assert set(headers) & _SMS_COLUMNS == set()
    assert set(headers) & _SMAS_COLUMNS == set()
    assert "fonte" in headers
    assert "data_busca_ativa" in headers


def test_header_filter_fontes_intersects_access():
    # SMAS-only user cannot gain SMS columns via the filter.
    headers = build_busca_ativa_header(PARTIAL_SMAS, ["SMS", "SMAS"])
    assert "smas_tipo" in headers
    assert set(headers) & _SMS_COLUMNS == set()


def test_row_maps_identity_and_address_in_existing_csv_shape():
    headers = build_busca_ativa_header()
    row = {
        "id_membro_familia": "1",
        "cpf": "111",
        "nome": "Ana",
        "nascimento_data": "2020-01-31",
        "endereco": "Rua A",
        "complemento": "Apto 1",
        "bairro": "Centro",
        "endereco_sms": {
            "endereco": "Rua SMS",
            "complemento": "Casa",
            "bairro": "Bairro SMS",
        },
    }
    values = _values(row, headers)
    assert values["nascimento_data"] == "31/01/2020"
    assert values["endereco_smas"] == "Rua A"
    assert values["complemento_endereco_smas"] == "Apto 1"
    assert values["bairro_endereco_smas"] == "Centro"
    assert values["endereco_sms"] == "Rua SMS"
    assert values["complemento_endereco_sms"] == "Casa"
    assert values["bairro_endereco_sms"] == "Bairro SMS"


def test_row_maps_event_fields():
    headers = build_busca_ativa_header()
    row = {
        "fonte": "SMAS",
        "data": "2026-07-14",
        "sms_tipo_publico": None,
        "smas_tipo": ["Por telefone", "Domicílio"],
        "smas_familia_localizada_indicador": False,
        "smas_protocolo_violado": ["Acesso a alimentos"],
        "smas_motivo_nao_localizada": ["Mudou de endereço"],
        "unidade_smas_nome": "CRAS Madureira",
        "unidade_smas_regional": "AP 3.3",
    }
    values = _values(row, headers)
    assert values["fonte"] == "SMAS"
    assert values["data_busca_ativa"] == "14/07/2026"
    assert values["smas_tipo"] == "Por telefone; Domicílio"
    assert values["smas_familia_localizada_indicador"] == "não"
    assert values["smas_protocolo_violado"] == "Acesso a alimentos"
    assert values["smas_motivo_nao_localizada"] == "Mudou de endereço"
    assert values["unidade_smas_nome"] == "CRAS Madureira"
    assert values["unidade_smas_regional"] == "AP 3.3"


def test_row_empty_arrays_and_nulls_map_to_none():
    headers = build_busca_ativa_header()
    values = _values(
        {
            "smas_tipo": [],
            "smas_familia_localizada_indicador": None,
            "smas_protocolo_violado": [],
            "smas_motivo_nao_localizada": [],
        },
        headers,
    )
    assert values["smas_tipo"] is None
    assert values["smas_familia_localizada_indicador"] == "-"
    assert values["smas_protocolo_violado"] is None
    assert values["smas_motivo_nao_localizada"] is None


@pytest.mark.asyncio
async def test_stream_uses_busca_ativa_transform():
    async def pages():
        yield [
            {
                "id_membro_familia": "1",
                "nome": "Ana",
                "fonte": "SMS",
                "data": "2024-06-19",
                "smas_tipo": [],
            }
        ]

    columns = build_busca_ativa_header()
    chunks = rows_to_csv_chunks(
        pages(), columns, transform=transform_busca_ativa_row
    )
    data = b""
    async for chunk in chunks:
        data += chunk

    text = data.decode("utf-8")
    assert text.startswith("\ufeff" + ";".join(columns))
    cells = dict(zip(columns, text.split("\n")[1].split(";"), strict=True))
    assert cells["nome"] == '"Ana"'
    assert cells["fonte"] == '"SMS"'
    assert cells["data_busca_ativa"] == '"19/06/2024"'
