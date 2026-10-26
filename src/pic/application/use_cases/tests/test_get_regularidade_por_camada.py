"""Unit tests for GetRegularidadePorCamadaUseCase.

Covers:
    - merge bairro: join por nome normalizado, taxa e meta
    - merge RA: strip do ordinal ("3ª Rio Comprido") + alias Santa Tereza
    - agregados sem geometria reportados no meta
    - camada não suportada → ValueError
    - forward de user_token/user_id/bypass_cache ao repositório
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pic.application.use_cases.get_regularidade_por_camada import (
    GetRegularidadePorCamadaUseCase,
    normalize_bairro_nome,
    normalize_codigo,
    normalize_ra_nome,
)
from src.pic.domain.models.geospatial import CamadaRegularidadeAggregate


def _agg(regiao: str, regulares: int, irregulares: int) -> CamadaRegularidadeAggregate:
    return CamadaRegularidadeAggregate(
        regiao=regiao,
        total_participantes=regulares + irregulares,
        total_regulares=regulares,
        total_irregulares=irregulares,
    )


def _feature_bairro(nome: str, id_bairro: str = "1") -> dict:
    return {
        "type": "Feature",
        "properties": {
            "id_bairro": id_bairro,
            "nome": nome,
            "nome_regiao_administrativa": "Rio Comprido",
        },
        "geometry": {"type": "Polygon", "coordinates": []},
    }


def _feature_ra(nome: str, id_ra: str = "3") -> dict:
    return {
        "type": "Feature",
        "properties": {"id_regiao_administrativa": id_ra, "nome": nome},
        "geometry": {"type": "Polygon", "coordinates": []},
    }


def _feature_estatica(nome: str, id_valor: object = None, id_field: str = "codigo") -> dict:
    return {
        "type": "Feature",
        "properties": {id_field: id_valor, "nome": nome},
        "geometry": {"type": "Polygon", "coordinates": []},
    }


def _make_use_case(aggregates: list[CamadaRegularidadeAggregate]):
    fake_repo = MagicMock()
    fake_repo.fetch_regularidade_por_camada = AsyncMock(return_value=aggregates)
    return GetRegularidadePorCamadaUseCase(repository=fake_repo), fake_repo


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_bairro_sem_acento_e_case(self):
        assert normalize_bairro_nome("Santa Tereza") == "santa tereza"
        assert normalize_bairro_nome(" Freguesia (Ilha) ") == "freguesia (ilha)"

    def test_ra_remove_ordinal(self):
        assert normalize_ra_nome("3ª Rio Comprido") == "rio comprido"
        assert normalize_ra_nome("12ª Inhauma") == "inhauma"
        assert normalize_ra_nome("Sem Vínculo") == "sem vinculo"

    def test_ra_alias_santa_tereza(self):
        assert normalize_ra_nome("23ª Santa Tereza") == "santa teresa"

    def test_codigo_digitos_sem_zeros(self):
        assert normalize_codigo("01ª CAS") == "1"
        assert normalize_codigo("1ª CAS") == "1"
        assert normalize_codigo("AP 3.1") == "31"
        assert normalize_codigo("01") == "1"
        assert normalize_codigo("12") == "12"
        assert normalize_codigo("SEM VÍNCULO") == ""
        assert normalize_codigo("0") == ""
        assert normalize_codigo(None) == ""


# ---------------------------------------------------------------------------
# Merge por camada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bairro_merge_com_taxa_e_meta():
    use_case, fake_repo = _make_use_case(
        [_agg("Vargem Grande", regulares=327, irregulares=407)]
    )
    bairros = [
        _feature_bairro("Vargem Grande", "131"),
        _feature_bairro("Botafogo", "4"),
    ]

    with patch(
        "src.pic.application.use_cases.get_regularidade_por_camada."
        "fetch_geometria_estatica",
        new=MagicMock(return_value=bairros),
    ):
        output = await use_case.execute(
            camada="bairro", user_token="t", user_id="cpf", bypass_cache=True
        )

    assert len(output.features) == 2
    vg = output.features[0]["properties"]
    assert vg["id"] == "131"
    assert vg["nome"] == "Vargem Grande"
    assert vg["nome_regiao_administrativa"] == "Rio Comprido"
    assert vg["total_participantes"] == 734
    assert vg["taxa_regularidade"] == pytest.approx(44.6)
    assert output.features[1]["properties"]["taxa_regularidade"] is None

    assert output.meta == {
        "camada": "bairro",
        "total_regioes": 2,
        "regioes_com_dados": 1,
        "regioes_sem_dados": 1,
        "agregados_sem_geometria": [],
    }
    fake_repo.fetch_regularidade_por_camada.assert_awaited_once_with(
        camada="bairro",
        user_token="t",
        user_id="cpf",
        bypass_cache=True,
        status=None,
        cohortes=None,
        protocolo_id=None,
    )


@pytest.mark.asyncio
async def test_filtros_forwarded_ao_repositorio():
    use_case, fake_repo = _make_use_case([])

    with patch(
        "src.pic.application.use_cases.get_regularidade_por_camada."
        "fetch_geometria_estatica",
        new=MagicMock(return_value=[]),
    ):
        await use_case.execute(
            camada="bairro",
            status=["Ativo"],
            cohortes=["2025-03-01", "2026-07-01"],
            protocolo_id="sms_vacinacao_pentavalente",
        )

    fake_repo.fetch_regularidade_por_camada.assert_awaited_once_with(
        camada="bairro",
        user_token=None,
        user_id=None,
        bypass_cache=False,
        status=["Ativo"],
        cohortes=["2025-03-01", "2026-07-01"],
        protocolo_id="sms_vacinacao_pentavalente",
    )


@pytest.mark.asyncio
async def test_ra_merge_limpa_ordinal_e_alias():
    use_case, _ = _make_use_case(
        [
            _agg("3ª Rio Comprido", regulares=100, irregulares=50),
            _agg("23ª Santa Tereza", regulares=20, irregulares=30),
            _agg("Sem Vínculo", regulares=10, irregulares=90),
        ]
    )
    ras = [_feature_ra("Rio Comprido", "3"), _feature_ra("Santa Teresa", "23")]

    with patch(
        "src.pic.application.use_cases.get_regularidade_por_camada."
        "fetch_geometria_estatica",
        new=MagicMock(return_value=ras),
    ):
        output = await use_case.execute(camada="ra")

    props = [f["properties"] for f in output.features]
    assert props[0]["nome"] == "Rio Comprido"
    assert props[0]["taxa_regularidade"] == pytest.approx(66.7)
    # Alias: "Santa Tereza" (consolidado) casa com "Santa Teresa" (datario)
    assert props[1]["taxa_regularidade"] == 40.0
    assert output.meta["camada"] == "ra"
    assert output.meta["regioes_com_dados"] == 2
    assert output.meta["agregados_sem_geometria"] == ["Sem Vínculo"]


@pytest.mark.asyncio
async def test_camada_nao_suportada_levanta_value_error():
    use_case, _ = _make_use_case([])
    with pytest.raises(ValueError, match="não suportada"):
        await use_case.execute(camada="municipio")


# ---------------------------------------------------------------------------
# Camadas estáticas (cas/cre/ap) — join por código (dígitos)
# ---------------------------------------------------------------------------


def _patch_estatica(features: list[dict]):
    return patch(
        "src.pic.application.use_cases.get_regularidade_por_camada."
        "fetch_geometria_estatica",
        new=MagicMock(return_value=features),
    )


@pytest.mark.asyncio
async def test_cas_merge_por_digitos_e_sem_vinculo():
    use_case, _ = _make_use_case(
        [
            _agg("01ª CAS", regulares=10, irregulares=5),
            _agg("0", regulares=1, irregulares=9),
        ]
    )
    geometrias = [
        {
            "type": "Feature",
            "properties": {"cas": 1, "cas_label": "1ª CAS"},
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    ]

    with _patch_estatica(geometrias):
        output = await use_case.execute(camada="cas")

    props = output.features[0]["properties"]
    assert props["id"] == "1"
    assert props["nome"] == "1ª CAS"
    assert props["taxa_regularidade"] == pytest.approx(66.7)
    assert output.meta["camada"] == "cas"
    assert output.meta["regioes_com_dados"] == 1
    assert output.meta["agregados_sem_geometria"] == ["0"]


@pytest.mark.asyncio
async def test_cre_merge_e_12a_sem_poligono():
    use_case, _ = _make_use_case(
        [
            _agg("01", regulares=20, irregulares=10),
            _agg("12", regulares=5, irregulares=5),
        ]
    )
    geometrias = [
        {
            "type": "Feature",
            "properties": {"codigo": "01", "nome": "1ª CRE"},
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    ]

    with _patch_estatica(geometrias):
        output = await use_case.execute(camada="cre")

    props = output.features[0]["properties"]
    assert props["id"] == "01"
    assert props["nome"] == "1ª CRE"
    assert props["taxa_regularidade"] == pytest.approx(66.7)
    # 12ª CRE existe nos dados (58 linhas) mas não tem polígono na camada
    assert output.meta["agregados_sem_geometria"] == ["12"]


@pytest.mark.asyncio
async def test_ap_merge_por_digitos():
    use_case, _ = _make_use_case([_agg("31", regulares=30, irregulares=30)])
    geometrias = [
        {
            "type": "Feature",
            "properties": {"COD_AP_SMS": "AP 3.1"},
            "geometry": {"type": "Polygon", "coordinates": []},
        }
    ]

    with _patch_estatica(geometrias):
        output = await use_case.execute(camada="ap")

    props = output.features[0]["properties"]
    assert props["id"] == "AP 3.1"
    assert props["nome"] == "AP 3.1"
    assert props["taxa_regularidade"] == 50.0
    assert output.meta["regioes_com_dados"] == 1
