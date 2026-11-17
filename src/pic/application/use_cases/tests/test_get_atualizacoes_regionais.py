"""Unit tests for the atualizações use case (Painel de Atualizações).

Covers:
    - fixture realista (CAS 01, semanas domingo–sábado): aritmética com linhas
      Inativo com regular/irregular NÃO-zero (V1) e lineup FIXO (decisão E)
    - gate (b): super admin, acesso geral, policy de unidade, sem permissão
    - escopo_restrito e foco pelo acesso (RA × bairro, camada bairro omite)
    - janela domingo-start: recuo da referência, debug ``semana``, sem comparativo
    - seletor de janela (1|2|4 semanas): delta W−(N+1) + série min(N+1, 4)
      pontos com sanidade (semana anômala sai da série)
    - secretarias de acesso: Q2 filtrada por ``secretarias_acesso``
    - extremos por Δabs (um sinal só → duas maiores |Δabs|)
    - labels vindos da tabela (``nome_cas`` / RAW para RA)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.security.permissions_models import UserPermissions
from src.pic.application.use_cases.get_atualizacoes_regionais import (
    GetAtualizacoesRegionaisUseCase,
    _semanas_janela,
    _ultima_semana_fechada,
)
from src.pic.domain.models.admin import IdWithName
from src.pic.domain.models.atualizacoes import (
    FocoRow,
    ProtocoloSemanaRow,
    SemanaStatusRow,
)
from src.pic.domain.models.geospatial import CamadaRegularidadeAggregate

_REF = "2026-11-01"  # domingo — semana 01–07 nov (W−1)
_CMP = "2026-10-25"  # domingo — semana 25–31 out (W−2)
_W3 = "2026-10-18"  # W−3
_W4 = "2026-10-11"  # W−4
_CMP4 = "2026-10-04"  # domingo — semana 04–10 out (W−5, base dos deltas)

# Data de teste fixa: qui 2026-11-12 → semana em curso = domingo 2026-11-08,
# última fechada = 2026-11-01.
_HOJE = date(2026, 11, 12)


@pytest.fixture(autouse=True)
def _hoje_fixo(monkeypatch):
    monkeypatch.setattr(
        "src.pic.application.use_cases.get_atualizacoes_regionais._hoje",
        lambda: _HOJE,
    )


# ---------------------------------------------------------------------------
# Fixture realista (CAS 01 — números observados em staging, B1)
# ---------------------------------------------------------------------------


def _q1_rows(label: str | None = "01ª CAS"):
    """Janela W−5..W−1 (5 domingos, comparação de 4 semanas)."""
    return [
        # W−5 (comparação): Ativo 6.900 = 3.050 regular + 3.850 irregular
        SemanaStatusRow(
            week_start=_CMP4,
            status="Ativo",
            qtd=6900,
            regular=3050,
            atencao=0,
            irregular=3850,
            regiao_label=label,
        ),
        SemanaStatusRow(
            week_start=_CMP4,
            status="Inativo",
            qtd=3390,
            regular=2800,
            atencao=0,
            irregular=590,
            regiao_label=label,
        ),
        # W−4 (série)
        SemanaStatusRow(
            week_start=_W4,
            status="Ativo",
            qtd=6940,
            regular=3100,
            atencao=0,
            irregular=3840,
            regiao_label=label,
        ),
        SemanaStatusRow(
            week_start=_W4,
            status="Inativo",
            qtd=3330,
            regular=2900,
            atencao=0,
            irregular=430,
            regiao_label=label,
        ),
        # W−3 (série)
        SemanaStatusRow(
            week_start=_W3,
            status="Ativo",
            qtd=7100,
            regular=3350,
            atencao=0,
            irregular=3750,
            regiao_label=label,
        ),
        SemanaStatusRow(
            week_start=_W3,
            status="Inativo",
            qtd=3300,
            regular=3000,
            atencao=0,
            irregular=300,
            regiao_label=label,
        ),
        # W−2 (série)
        SemanaStatusRow(
            week_start=_CMP,
            status="Ativo",
            qtd=6996,
            regular=3100,
            atencao=0,
            irregular=3896,
            regiao_label=label,
        ),
        SemanaStatusRow(
            week_start=_CMP,
            status="Inativo",
            qtd=3200,
            regular=3000,
            atencao=0,
            irregular=200,
            regiao_label=label,
        ),
        # W−1 (referência): Ativo 6.980 = 3.276 regular + 3.704 irregular
        SemanaStatusRow(
            week_start=_REF,
            status="Ativo",
            qtd=6980,
            regular=3276,
            atencao=0,
            irregular=3704,
            regiao_label=label,
        ),
        # Inativo com regular/irregular NÃO-zero (V1) — NÃO podem entrar nas
        # contagens de regular/irregular do painel
        SemanaStatusRow(
            week_start=_REF,
            status="Inativo",
            qtd=3277,
            regular=2411,
            atencao=0,
            irregular=866,
            regiao_label=label,
        ),
    ]


def _q2_rows():
    return [
        # PR-014: 71,2% → 79,8% — Δabs +43, p.p. +8,6 (maior alta em 4 semanas)
        ProtocoloSemanaRow(
            week_start=_CMP4,
            protocolo_id="PR-014",
            protocolo_descricao="Busca ativa",
            qtd=500,
            regular=350,
            atencao=6,
        ),
        ProtocoloSemanaRow(
            week_start=_REF,
            protocolo_id="PR-014",
            protocolo_descricao="Busca ativa",
            qtd=500,
            regular=393,
            atencao=6,
        ),
        # PR-008: 81,5% → 75,2% — Δabs −126, p.p. −6,3 (maior queda)
        ProtocoloSemanaRow(
            week_start=_CMP4,
            protocolo_id="PR-008",
            protocolo_descricao="Acompanhamento",
            qtd=2000,
            regular=1600,
            atencao=30,
        ),
        ProtocoloSemanaRow(
            week_start=_REF,
            protocolo_id="PR-008",
            protocolo_descricao="Acompanhamento",
            qtd=2000,
            regular=1474,
            atencao=30,
        ),
        # PR-030: Δabs +30 — não entra (perde para PR-014)
        ProtocoloSemanaRow(
            week_start=_CMP4,
            protocolo_id="PR-030",
            protocolo_descricao="Imunização",
            qtd=1000,
            regular=900,
        ),
        ProtocoloSemanaRow(
            week_start=_REF,
            protocolo_id="PR-030",
            protocolo_descricao="Imunização",
            qtd=1000,
            regular=930,
        ),
    ]


def _q3_rows():
    return [
        # 13ª Meier: estoque W−1 312, comparação (W−5) 272 → delta +40
        FocoRow(week_start=_CMP4, local="13ª Meier", irregular=272),
        FocoRow(week_start=_REF, local="13ª Meier", irregular=312),
        FocoRow(week_start=_REF, local="Santa Teresa", irregular=200),
        FocoRow(week_start=_REF, local="Centro", irregular=100),
    ]


class FakeRepo:
    def __init__(self, q1=None, q2=None, q3=None):
        self.q1 = q1 or []
        self.q2 = q2 or []
        self.q3 = q3 or []
        self.calls: dict[str, list] = {}

    def _record(self, name, kwargs):
        self.calls.setdefault(name, []).append(kwargs)

    async def fetch_semanas_status(self, **kwargs):
        self._record("q1", kwargs)
        return self.q1

    async def fetch_protocolos(self, **kwargs):
        self._record("q2", kwargs)
        return self.q2

    async def fetch_foco(self, **kwargs):
        self._record("q3", kwargs)
        return self.q3


def _geo(regioes=("01ª CAS",)):
    geo = MagicMock()
    geo.fetch_regularidade_por_camada = AsyncMock(
        return_value=[
            CamadaRegularidadeAggregate(regiao=r, total_participantes=10257)
            for r in regioes
        ]
    )
    return geo


def _super_admin():
    return UserPermissions(
        cpf="00000000000",
        is_super_admin=True,
        secretarias_acesso=["SME", "SMS", "SMAS"],
    )


def _make_uc(repo=None, geo=None):
    repo = repo or FakeRepo()
    geo = geo or _geo()
    return GetAtualizacoesRegionaisUseCase(repository=repo, geo_repository=geo), repo


async def _execute(
    uc,
    *,
    camada="cas",
    regiao="01ª CAS",
    permissions=None,
    semana=_REF,
    semanas_comparacao=4,
):
    return await uc.execute(
        camada=camada,
        regiao=regiao,
        permissions=permissions if permissions is not None else _super_admin(),
        user_token="token",
        user_id="00000000000",
        semana=semana,
        semanas_comparacao=semanas_comparacao,
    )


# ---------------------------------------------------------------------------
# Fixture realista (aritmética + ranking + labels da tabela)
# ---------------------------------------------------------------------------


class TestFixture:
    @pytest.mark.asyncio
    async def test_aritmetica_e_lineup_completos(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)

        assert result.can_view_atualizacoes is True
        assert result.meta.escopo_restrito is False
        assert result.meta.tem_comparativo is True
        assert result.meta.semana_referencia == _REF
        assert result.meta.semana_comparacao == _CMP4
        data = result.data
        assert data is not None

        # Contexto: label da TABELA (nome_cas), não do GeoJSON
        assert data.contexto.camada == "cas"
        assert data.contexto.regiao_id == "01ª CAS"
        assert data.contexto.regiao_label == "01ª CAS"
        assert data.contexto.participantes == 10257

        # Regularidade SÓ com linhas Ativo (V1: Inativo tem regular/irregular
        # não-zero e não pode contaminar a partição); a TAXA é dos ativos —
        # mesma métrica da Visão Geral com filtro Ativo (46,9% vs 31,9% da base).
        # Variação de 4 semanas: 46,93 − 44,20 = +2,7 p.p.
        reg = data.regularidade
        assert reg.base == 10257
        assert reg.ativos == 6980
        assert reg.regulares == 3276
        assert reg.irregulares == 3704
        assert reg.inativos == 3277
        assert reg.taxa == 46.9
        assert reg.variacao_pp == 2.7
        assert reg.tone == "success"

        # Extremos por Δabs em 4 semanas: PR-014 (+43) e PR-008 (−126)
        assert [p.protocolo_id for p in data.protocolos] == ["PR-014", "PR-008"]
        pr14, pr08 = data.protocolos
        assert pr14.nome == "Busca ativa"
        assert pr14.de == 71.2 and pr14.para == 79.8
        assert pr14.delta_abs == 43 and pr14.delta_pp == 8.6
        assert pr14.tone == "success"
        assert pr08.de == 81.5 and pr08.para == 75.2
        assert pr08.delta_abs == -126 and pr08.delta_pp == -6.3
        assert pr08.tone == "danger"

        # Irregulares: 3.704 − 3.850 = −146 / 3.850 = −3,8% — caiu → success
        irr = data.irregulares
        assert irr is not None
        assert irr.total == 3704
        assert irr.variacao_abs == -146
        assert irr.variacao_pct == -3.8
        assert irr.tone == "success"
        # série de 4 pontos (últimas 4 semanas válidas: W−4..W−1)
        assert [p.semana for p in irr.serie] == [_W4, _W3, _CMP, _REF]
        assert [p.valor for p in irr.serie] == [3840, 3750, 3896, 3704]

        # Regulares: 3.276 − 3.050 = +226 / 3.050 = +7,4% — subiu → success
        regs = data.regulares
        assert regs is not None
        assert regs.total == 3276
        assert regs.variacao_abs == 226
        assert regs.variacao_pct == 7.4
        assert regs.tone == "success"
        assert [p.valor for p in regs.serie] == [3100, 3350, 3100, 3276]

        # Foco: 312 / 3.704 = 8,4%; demais = 3.392; delta vs. W−5 = +40
        foco = data.foco
        assert foco is not None
        assert foco.nivel == "ra"
        assert foco.local == "13ª Meier"
        assert foco.irregulares == 312
        assert foco.participacao_pct == 8.4
        assert foco.demais == 3392
        assert foco.delta_irregulares == 40

        # Lineup FIXO (decisão E): irregulares → regulares → foco (3º slot)
        cards = result.meta.cards
        assert [c.tipo for c in cards] == ["irregulares", "regulares", "foco"]
        assert [c.valor for c in cards] == [3704, 3276, 312]
        assert [c.relevancia for c in cards] == [1.0, 0.88, 0.08]
        assert cards[2].fixo is True
        assert all(not c.fixo for i, c in enumerate(cards) if i != 2)

    @pytest.mark.asyncio
    async def test_serie_com_lacuna_usa_o_que_houver(self):
        rows = [r for r in _q1_rows() if r.week_start in (_REF, _CMP)]
        uc, _ = _make_uc(FakeRepo(q1=rows))
        result = await _execute(uc)
        assert [p.semana for p in result.data.irregulares.serie] == [_CMP, _REF]
        assert result.data.regulares.total == 3276


# ---------------------------------------------------------------------------
# Gate (b) e escopo_restrito
# ---------------------------------------------------------------------------


class TestGate:
    @pytest.mark.asyncio
    async def test_sem_permissao(self):
        repo = FakeRepo(q1=_q1_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(
            uc,
            permissions=UserPermissions(cpf="1", secretarias_acesso=["SMS"]),
        )
        assert result.can_view_atualizacoes is False
        assert result.data is None
        assert "q1" not in repo.calls

    @pytest.mark.asyncio
    async def test_policy_unidade_ve_e_fica_restrito(self):
        repo = FakeRepo(q1=_q1_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(
            uc,
            permissions=UserPermissions(
                cpf="1",
                id_cre_list=[IdWithName(id="01", nome="1ª CRE")],
            ),
        )
        assert result.can_view_atualizacoes is True
        assert result.meta.escopo_restrito is True
        assert result.data.foco.nivel == "bairro"
        assert repo.calls["q3"][0]["sub_camada"] == "bairro"

    @pytest.mark.asyncio
    async def test_super_admin_nao_e_restrito(self):
        repo = FakeRepo(q1=_q1_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc, permissions=_super_admin())
        assert result.can_view_atualizacoes is True
        assert result.meta.escopo_restrito is False


# ---------------------------------------------------------------------------
# Foco (regra 6)
# ---------------------------------------------------------------------------


class TestFoco:
    @pytest.mark.asyncio
    async def test_camada_ra_com_acesso_geral_desce_para_bairro(self):
        repo = FakeRepo(q1=_q1_rows(label=None), q3=_q3_rows())
        uc, _ = _make_uc(repo, _geo(regioes=("13ª Meier",)))
        result = await uc.execute(
            camada="ra",
            regiao="Meier",
            permissions=_super_admin(),
            user_token="token",
            user_id="x",
            semana=_REF,
        )
        assert result.data is not None
        assert result.data.foco.nivel == "bairro"
        assert repo.calls["q3"][0]["sub_camada"] == "bairro"
        assert repo.calls["q1"][0]["regiao"] == "13ª Meier"
        # Rótulo é o RAW da tabela (não o nome sem ordinal do mapa)
        assert result.data.contexto.regiao_label == "13ª Meier"

    @pytest.mark.asyncio
    async def test_camada_bairro_omite_o_card(self):
        repo = FakeRepo(q1=_q1_rows(label=None))
        uc, _ = _make_uc(repo, _geo(regioes=("Tijuca",)))
        result = await uc.execute(
            camada="bairro",
            regiao="Tijuca",
            permissions=_super_admin(),
            user_token="token",
            user_id="x",
            semana=_REF,
        )
        assert result.data is not None
        assert result.data.foco is None
        assert "q3" not in repo.calls

    @pytest.mark.asyncio
    async def test_foco_sem_irregulares_vira_none(self):
        repo = FakeRepo(
            q1=_q1_rows(), q3=[FocoRow(week_start=_REF, local="X", irregular=0)]
        )
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.data.foco is None

    @pytest.mark.asyncio
    async def test_foco_empate_escolhe_ordem_alfabetica(self):
        repo = FakeRepo(
            q1=_q1_rows(),
            q3=[
                FocoRow(week_start=_REF, local="Bairro B", irregular=100),
                FocoRow(week_start=_REF, local="Bairro A", irregular=100),
            ],
        )
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.data.foco.local == "Bairro A"

    @pytest.mark.asyncio
    async def test_foco_pede_as_duas_semanas_quando_tem_comparativo(self):
        repo = FakeRepo(q1=_q1_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        await _execute(uc)
        assert repo.calls["q3"][0]["semanas"] == [_CMP4, _REF]

    @pytest.mark.asyncio
    async def test_foco_delta_none_sem_linha_na_comparacao(self):
        # Local existe só em W−1 → o card omite a frase de delta.
        repo = FakeRepo(
            q1=_q1_rows(),
            q3=[FocoRow(week_start=_REF, local="Bairro A", irregular=312)],
        )
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.data.foco is not None
        assert result.data.foco.delta_irregulares is None

    @pytest.mark.asyncio
    async def test_foco_seleciona_por_estoque_nao_por_delta(self):
        # B cresceu mais (+150 vs. +10), mas A tem o maior estoque em W−1 —
        # a escolha continua pela concentração, não pelo crescimento.
        repo = FakeRepo(
            q1=_q1_rows(),
            q3=[
                FocoRow(week_start=_CMP4, local="Bairro B", irregular=50),
                FocoRow(week_start=_REF, local="Bairro B", irregular=200),
                FocoRow(week_start=_CMP4, local="Bairro A", irregular=302),
                FocoRow(week_start=_REF, local="Bairro A", irregular=312),
            ],
        )
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.data.foco.local == "Bairro A"
        assert result.data.foco.delta_irregulares == 10


# ---------------------------------------------------------------------------
# Janela (domingo–sábado)
# ---------------------------------------------------------------------------


class TestJanela:
    @pytest.mark.asyncio
    async def test_recua_referencia_quando_w1_sem_dados(self):
        rows = [r for r in _q1_rows() if r.week_start in (_CMP, _W3)]
        repo = FakeRepo(q1=rows)
        uc, _ = _make_uc(repo)
        result = await uc.execute(
            camada="cas",
            regiao="01ª CAS",
            permissions=_super_admin(),
            user_token="token",
            user_id="x",
        )
        assert result.meta.semana_referencia == _CMP
        # comparação = 4 semanas antes (2026-09-27) — sem dados → sem comparativo
        assert result.meta.semana_comparacao is None
        assert result.meta.tem_comparativo is False
        # a janela pedida ao repositório tem 12 semanas fechadas, terminando
        # na última fechada (W−1 = 2026-11-01), mesmo sem dados nela
        semanas = repo.calls["q1"][0]["semanas"]
        assert len(semanas) == 12
        assert semanas[-1] == "2026-11-01"

    @pytest.mark.asyncio
    async def test_sem_comparativo_desliga_deltas(self):
        rows = [r for r in _q1_rows() if r.week_start == _REF]
        repo = FakeRepo(q1=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.meta.tem_comparativo is False
        assert result.meta.semana_comparacao is None
        assert result.data.protocolos == []
        assert "q2" not in repo.calls
        assert result.data.regularidade.variacao_pp is None
        assert result.data.irregulares.variacao_abs is None
        assert result.data.regulares.variacao_abs is None
        # cards de volume continuam válidos (total independe do comparativo)
        assert result.data.regulares.total == 3276
        assert [c.tipo for c in result.meta.cards] == ["irregulares", "regulares", "foco"]

    @pytest.mark.asyncio
    async def test_semana_debug_restringe_a_janela(self):
        repo = FakeRepo(q1=_q1_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        await _execute(uc, semana=_REF)
        # janela mínima para a comparação de 4 semanas: W−5..W−1
        assert repo.calls["q1"][0]["semanas"] == [_CMP4, _W4, _W3, _CMP, _REF]

    @pytest.mark.asyncio
    async def test_semana_anomala_sai_da_serie(self):
        # W−3 com base de ativos fora de ±3% da mediana (~14.200 vs mediana
        # ~6.980): é pulada — a janela recua até completar os 4 pontos.
        rows = []
        for r in _q1_rows():
            if r.week_start == _W3:
                r.qtd = r.qtd * 2  # ativos de W−3 viram ~14.200
            rows.append(r)
        repo = FakeRepo(q1=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        irr = result.data.irregulares
        assert [p.semana for p in irr.serie] == [_CMP4, _W4, _CMP, _REF]
        assert [p.valor for p in irr.serie] == [3850, 3840, 3896, 3704]
        # comparação usa W−5 mesmo assim
        assert result.meta.semana_comparacao == _CMP4
        assert result.data.regularidade.variacao_pp == 2.7

    @pytest.mark.asyncio
    async def test_mudanca_de_nivel_nas_12_semanas_nao_encolhe_a_serie(self):
        # Bug real: a base cresceu de patamar nas últimas semanas — a mediana
        # das 12 semanas marcaria as recentes como anômalas. A sanidade usa a
        # janela da série (W−5..W−1), então os 4 pontos continuam.
        antigas = [
            SemanaStatusRow(week_start=iso, status="Ativo", qtd=6600, regular=3000, irregular=3600)
            for iso in ["2026-08-16", "2026-08-23", "2026-08-30", "2026-09-06",
                        "2026-09-13", "2026-09-20", "2026-09-27"]
        ]
        antigas += [
            SemanaStatusRow(week_start=iso, status="Inativo", qtd=3100, regular=2000, irregular=1100)
            for iso in ["2026-08-16", "2026-08-23", "2026-08-30", "2026-09-06",
                        "2026-09-13", "2026-09-20", "2026-09-27"]
        ]
        repo = FakeRepo(q1=antigas + _q1_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        irr = result.data.irregulares
        # 4 pontos — as recentes não são descartadas por estarem ~5% acima
        # da base antiga
        assert [p.semana for p in irr.serie] == [_W4, _W3, _CMP, _REF]
        assert result.meta.semana_comparacao == _CMP4

    @pytest.mark.asyncio
    async def test_sem_dados_q1_devolve_data_none(self):
        repo = FakeRepo(q1=[])
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.can_view_atualizacoes is True
        assert result.data is None
        assert result.meta.cards == []
        assert result.meta.semana_em_curso == "2026-11-08"

    @pytest.mark.asyncio
    async def test_regiao_inexistente_nao_consulta_semanal(self):
        repo = FakeRepo(q1=_q1_rows())
        uc, _ = _make_uc(repo, _geo(regioes=("03ª CAS",)))
        result = await _execute(uc, regiao="09ª CAS")
        assert result.data is None
        assert "q1" not in repo.calls

    @pytest.mark.asyncio
    async def test_camada_invalida_raises(self):
        uc, _ = _make_uc()
        with pytest.raises(ValueError):
            await _execute(uc, camada="estado")

    @pytest.mark.asyncio
    async def test_camada_sem_regiao_raises(self):
        uc, _ = _make_uc()
        with pytest.raises(ValueError):
            await uc.execute(
                camada="cas",
                regiao=None,
                permissions=_super_admin(),
                semana=_REF,
            )

    @pytest.mark.asyncio
    async def test_regiao_em_branco_raises(self):
        uc, _ = _make_uc()
        with pytest.raises(ValueError):
            await _execute(uc, regiao="   ")


# ---------------------------------------------------------------------------
# Seletor de janela (1 | 2 | 4 semanas)
# ---------------------------------------------------------------------------


class TestSeletorJanela:
    @pytest.mark.asyncio
    async def test_n1_compara_com_w2_e_desenha_2_pontos(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc, semanas_comparacao=1)

        assert result.meta.semanas_comparacao == 1
        assert result.meta.semana_comparacao == _CMP
        irr = result.data.irregulares
        assert [p.semana for p in irr.serie] == [_CMP, _REF]
        assert [p.valor for p in irr.serie] == [3896, 3704]
        assert irr.variacao_abs == -192
        assert irr.variacao_pct == -4.9
        # regulares vs W−2: 3.276 − 3.100 = +176 (+5,7%)
        assert result.data.regulares.variacao_abs == 176
        assert result.data.regulares.variacao_pct == 5.7
        # janela mínima pedida ao repositório: 3 domingos (W−3..W−1)
        assert repo.calls["q1"][0]["semanas"] == [_W3, _CMP, _REF]
        # Q2 compara W−2 × W−1
        assert repo.calls["q2"][0]["semanas"] == [_CMP, _REF]

    @pytest.mark.asyncio
    async def test_n2_compara_com_w3_e_desenha_3_pontos(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc, semanas_comparacao=2)

        assert result.meta.semanas_comparacao == 2
        assert result.meta.semana_comparacao == _W3
        irr = result.data.irregulares
        assert [p.semana for p in irr.serie] == [_W3, _CMP, _REF]
        assert [p.valor for p in irr.serie] == [3750, 3896, 3704]
        assert irr.variacao_abs == -46
        assert irr.variacao_pct == -1.2
        # regulares vs W−3: 3.276 − 3.350 = −74 (−2,2%) — caiu → danger
        assert result.data.regulares.variacao_abs == -74
        assert result.data.regulares.variacao_pct == -2.2
        assert result.data.regulares.tone == "danger"
        # janela mínima: 4 domingos (W−4..W−1)
        assert repo.calls["q1"][0]["semanas"] == [_W4, _W3, _CMP, _REF]
        assert repo.calls["q2"][0]["semanas"] == [_W3, _REF]

    @pytest.mark.asyncio
    async def test_n4_eh_o_padrao(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.meta.semanas_comparacao == 4
        assert result.meta.semana_comparacao == _CMP4
        assert [p.semana for p in result.data.irregulares.serie] == [
            _W4, _W3, _CMP, _REF,
        ]

    @pytest.mark.asyncio
    async def test_n_invalido_raises(self):
        uc, _ = _make_uc()
        with pytest.raises(ValueError):
            await _execute(uc, semanas_comparacao=3)

    @pytest.mark.asyncio
    async def test_n1_com_anomala_preserva_os_2_pontos(self):
        # W−2 anômalo É a base da comparação em N=1 → preservado como endpoint;
        # a série continua com 2 pontos (o bug dos 2 pontos não volta).
        rows = []
        for r in _q1_rows():
            if r.week_start == _CMP:
                r.qtd = r.qtd * 2  # base de W−2 vira ~20.400
            rows.append(r)
        repo = FakeRepo(q1=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc, semanas_comparacao=1)
        irr = result.data.irregulares
        assert [p.semana for p in irr.serie] == [_CMP, _REF]
        assert result.meta.semana_comparacao == _CMP


# ---------------------------------------------------------------------------
# Escopo do usuário (sem camada/região — RLS)
# ---------------------------------------------------------------------------


class TestEscopoUsuario:
    @pytest.mark.asyncio
    async def test_super_admin_ve_a_cidade_inteira(self):
        repo = FakeRepo(q1=_q1_rows(label=None), q2=_q2_rows(), q3=_q3_rows())
        geo = _geo()
        uc, _ = _make_uc(repo, geo)
        result = await uc.execute(
            permissions=_super_admin(),
            user_token="token",
            user_id="x",
            semana=_REF,
        )
        assert result.data is not None
        assert result.data.contexto.camada is None
        assert result.data.contexto.regiao_id is None
        assert result.data.contexto.regiao_label == "Cidade do Rio de Janeiro"
        # nenhuma resolução territorial; consultas sem filtro de região
        assert repo.calls["q1"][0]["regiao"] is None
        geo.fetch_regularidade_por_camada.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_usuario_restrito_ve_o_proprio_escopo(self):
        repo = FakeRepo(q1=_q1_rows(label=None), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await uc.execute(
            permissions=UserPermissions(
                cpf="1",
                id_cre_list=[IdWithName(id="01", nome="1ª CRE")],
            ),
            user_token="token",
            user_id="x",
            semana=_REF,
        )
        assert result.data is not None
        assert result.meta.escopo_restrito is True
        assert result.data.contexto.camada is None
        assert result.data.contexto.regiao_label == "Seu escopo de acesso"
        # foco desce para bairro mesmo sem contexto territorial
        assert result.data.foco.nivel == "bairro"
        assert repo.calls["q3"][0]["sub_camada"] == "bairro"


# ---------------------------------------------------------------------------
# Extremos (regra 10)
# ---------------------------------------------------------------------------


class TestExtremos:
    def _linhas(self, protocolos):
        rows = []
        for pid, desc, cmp_taxa, ref_taxa in protocolos:
            for week, taxa in ((_CMP4, cmp_taxa), (_REF, ref_taxa)):
                rows.append(
                    ProtocoloSemanaRow(
                        week_start=week,
                        protocolo_id=pid,
                        protocolo_descricao=desc,
                        qtd=1000,
                        regular=int(1000 * taxa / 100),
                    )
                )
        return rows

    def _linhas_var(self, protocolos):
        """Linhas com qtd própria por semana: (pid, desc, taxa_cmp, taxa_ref, qtd_cmp, qtd_ref)."""
        rows = []
        for pid, desc, cmp_taxa, ref_taxa, qtd_cmp, qtd_ref in protocolos:
            for week, taxa, qtd in (
                (_CMP4, cmp_taxa, qtd_cmp),
                (_REF, ref_taxa, qtd_ref),
            ):
                rows.append(
                    ProtocoloSemanaRow(
                        week_start=week,
                        protocolo_id=pid,
                        protocolo_descricao=desc,
                        qtd=qtd,
                        regular=int(qtd * taxa / 100),
                    )
                )
        return rows

    @pytest.mark.asyncio
    async def test_um_sinal_so_pega_duas_maiores_variacoes(self):
        rows = self._linhas(
            [
                ("PR-A", "A", 50.0, 60.0),  # Δabs +100
                ("PR-B", "B", 50.0, 55.0),  # Δabs +50
                ("PR-C", "C", 50.0, 52.0),  # Δabs +20
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-A", "PR-B"]
        assert all(p.tone == "success" for p in result.data.protocolos)

    @pytest.mark.asyncio
    async def test_sem_protocolos_vazio(self):
        repo = FakeRepo(q1=_q1_rows(), q2=[], q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert result.data.protocolos == []

    @pytest.mark.asyncio
    async def test_nome_exibido_eh_so_a_descricao_sem_id(self):
        rows = self._linhas(
            [
                ("PR-A", "Busca ativa", 50.0, 60.0),
                ("PR-B", "", 50.0, 55.0),  # descrição vazia → fallback no id
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.nome for p in result.data.protocolos] == ["Busca ativa", "PR-B"]

    @pytest.mark.asyncio
    async def test_selecao_eh_por_pp_e_nao_por_volume(self):
        # Mesmo Δabs (+100) nos dois — o antigo critério empatava e escolhia
        # por qtd; o novo escolhe o de maior Δpp (o pequeno).
        rows = self._linhas_var(
            [
                ("PR-G", "Grande", 90.0, 91.0, 10000, 10000),  # Δabs +100, Δpp +1,0
                ("PR-P", "Pequeno", 50.0, 70.0, 500, 500),  # Δabs +100, Δpp +20,0
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-P", "PR-G"]
        assert result.data.protocolos[0].delta_pp == 20.0

    @pytest.mark.asyncio
    async def test_piso_de_100_exclui_protocolo_pequeno(self):
        # PR-X tem Δpp +30 mas só 40 participantes → fora pelo piso.
        rows = self._linhas_var(
            [
                ("PR-X", "Minúsculo", 10.0, 40.0, 40, 40),  # Δpp +30,0
                ("PR-Y", "Y", 50.0, 55.0, 1000, 1000),  # Δpp +5,0
                ("PR-Z", "Z", 60.0, 52.0, 1000, 1000),  # Δpp −8,0
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-Y", "PR-Z"]

    @pytest.mark.asyncio
    async def test_piso_relaxa_quando_todos_abaixo(self):
        rows = self._linhas_var(
            [
                ("PR-A", "A", 50.0, 60.0, 40, 40),  # Δpp +10,0
                ("PR-B", "B", 50.0, 45.0, 40, 40),  # Δpp −5,0
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-A", "PR-B"]

    @pytest.mark.asyncio
    async def test_tone_vem_do_pp_nao_do_abs(self):
        # PR-A cresceu +700 participantes mas a taxa caiu (base dobrou) —
        # o tone é DANGER porque o critério é o p.p.
        rows = self._linhas_var(
            [
                ("PR-A", "A", 80.0, 75.0, 1000, 2000),  # Δabs +700, Δpp −5,0
                ("PR-B", "B", 90.0, 80.0, 1000, 1000),  # Δabs −100, Δpp −10,0
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-B", "PR-A"]
        a = result.data.protocolos[1]
        assert a.delta_abs > 0 and a.tone == "danger"

    @pytest.mark.asyncio
    async def test_empate_em_pp_desempata_por_qtd(self):
        rows = self._linhas_var(
            [
                ("PR-A", "A", 50.0, 55.0, 1000, 1000),  # Δpp +5,0
                ("PR-B", "B", 50.0, 55.0, 2000, 2000),  # Δpp +5,0, base maior
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-B", "PR-A"]

    @pytest.mark.asyncio
    async def test_alta_e_queda_por_pp(self):
        # Δabs: PR-C (+200) > PR-A (+43) — o antigo critério daria C e A;
        # por p.p. a alta é PR-A (+8,6) e a queda é PR-B (−6,3).
        rows = self._linhas_var(
            [
                ("PR-A", "A", 71.2, 79.8, 500, 500),  # Δabs +43, Δpp +8,6
                ("PR-B", "B", 81.5, 75.2, 2000, 2000),  # Δabs −126, Δpp −6,3
                ("PR-C", "C", 90.0, 92.0, 10000, 10000),  # Δabs +200, Δpp +2,0
            ]
        )
        repo = FakeRepo(q1=_q1_rows(), q2=rows, q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [p.protocolo_id for p in result.data.protocolos] == ["PR-A", "PR-B"]
        assert result.data.protocolos[0].tone == "success"
        assert result.data.protocolos[1].tone == "danger"


# ---------------------------------------------------------------------------
# Secretarias de acesso (regra 7) — RLS recorta unidade, não secretaria
# ---------------------------------------------------------------------------


def _usuario_restrito_smas(**kwargs):
    base = {
        "cpf": "1",
        "secretarias_acesso": ["SMAS"],
        "id_cas_list": [IdWithName(id="05ª CAS", nome="05ª CAS")],
    }
    base.update(kwargs)
    return UserPermissions(**base)


class TestSecretarias:
    @pytest.mark.asyncio
    async def test_usuario_smas_passa_filtro_para_q2(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc, permissions=_usuario_restrito_smas())
        assert result.can_view_atualizacoes is True
        assert repo.calls["q2"][0]["secretarias"] == ["SMAS"]

    @pytest.mark.asyncio
    async def test_duas_secretarias_viram_lista_e_nao_none(self):
        # O shim secretaria_acesso devolve "TODOS" para 2 de 3 — o filtro
        # usa a LISTA, então um usuário SME+SMAS NÃO vê SMS.
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(
            uc,
            permissions=_usuario_restrito_smas(secretarias_acesso=["SME", "SMAS"]),
        )
        assert result.can_view_atualizacoes is True
        assert repo.calls["q2"][0]["secretarias"] == ["SME", "SMAS"]

    @pytest.mark.asyncio
    async def test_super_admin_sem_filtro(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        await _execute(uc, permissions=_super_admin())
        assert repo.calls["q2"][0]["secretarias"] is None

    @pytest.mark.asyncio
    async def test_tres_secretarias_sem_filtro(self):
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        await _execute(
            uc,
            permissions=_usuario_restrito_smas(
                secretarias_acesso=["SME", "SMS", "SMAS"]
            ),
        )
        assert repo.calls["q2"][0]["secretarias"] is None

    @pytest.mark.asyncio
    async def test_sem_secretarias_passa_lista_vazia(self):
        # O repositório real nem consulta o PostgREST para lista vazia
        repo = FakeRepo(q1=_q1_rows(), q2=_q2_rows(), q3=_q3_rows())
        uc, _ = _make_uc(repo)
        await _execute(uc, permissions=_usuario_restrito_smas(secretarias_acesso=[]))
        assert repo.calls["q2"][0]["secretarias"] == []
        # o use case continua chamando; o corte é no repositório (sem HTTP)


# ---------------------------------------------------------------------------
# Lineup fixo (decisão E) — irregulares → regulares → foco
# ---------------------------------------------------------------------------


class TestLineup:
    @pytest.mark.asyncio
    async def test_ordem_fixa_independe_do_volume(self):
        # regulares com volume MAIOR não sobe: a ordem é fixa do produto
        rows = [
            SemanaStatusRow(
                week_start=_REF, status="Ativo", qtd=1000, regular=900, irregular=100
            ),
            SemanaStatusRow(week_start=_REF, status="Inativo", qtd=100),
        ]
        repo = FakeRepo(q1=rows)
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [c.tipo for c in result.meta.cards] == ["irregulares", "regulares"]
        # relevancia é informativa (valor / max) — regulares é o maior aqui
        assert result.meta.cards[1].relevancia == 1.0

    @pytest.mark.asyncio
    async def test_foco_ausente_nao_quebra_o_lineup(self):
        rows = [
            SemanaStatusRow(
                week_start=_REF, status="Ativo", qtd=1000, regular=900, irregular=100
            ),
            SemanaStatusRow(week_start=_REF, status="Inativo", qtd=100),
        ]
        repo = FakeRepo(q1=rows, q3=[])
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        assert [c.tipo for c in result.meta.cards] == ["irregulares", "regulares"]


# ---------------------------------------------------------------------------
# Regularidade = taxa dos ATIVOS (regra 9)
# ---------------------------------------------------------------------------


class TestRegularidadeTaxa:
    @pytest.mark.asyncio
    async def test_taxa_usa_ativos_no_denominador(self):
        # inativos com regular/irregular não-zero NÃO entram na taxa
        repo = FakeRepo(q1=_q1_rows())
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        reg = result.data.regularidade
        assert reg.taxa == 46.9  # 3.276 / 6.980 (não / 10.257)
        assert reg.ativos == 6980
        assert reg.variacao_pp == 2.7  # 46,93 − 44,20 (W−5, mesma base de ativos)

    @pytest.mark.asyncio
    async def test_taxa_none_quando_sem_ativos(self):
        rows = [
            SemanaStatusRow(
                week_start=_REF,
                status="Inativo",
                qtd=500,
                regular=400,
                irregular=100,
            ),
        ]
        repo = FakeRepo(q1=rows)
        uc, _ = _make_uc(repo)
        result = await _execute(uc)
        reg = result.data.regularidade
        assert reg.taxa is None
        assert reg.variacao_pp is None
        assert reg.base == 500
        assert reg.ativos == 0
        assert reg.inativos == 500


# ---------------------------------------------------------------------------
# Helpers de janela (fuso America/Sao_Paulo, domingo-start)
# ---------------------------------------------------------------------------


class TestHelpersJanela:
    def test_ultima_semana_fechada(self):
        # terça 2026-11-10 → última fechada é domingo 2026-11-01
        assert _ultima_semana_fechada(date(2026, 11, 10)) == date(2026, 11, 1)
        # domingo 2026-11-15: a semana que começou hoje ainda não fechou
        assert _ultima_semana_fechada(date(2026, 11, 15)) == date(2026, 11, 8)
        # sábado 2026-11-14: a semana termina hoje — ainda não fechou
        assert _ultima_semana_fechada(date(2026, 11, 14)) == date(2026, 11, 1)
        # segunda 2026-11-16: fechou a de 08–14
        assert _ultima_semana_fechada(date(2026, 11, 16)) == date(2026, 11, 8)

    def test_semanas_janela_doze_semanas_ascendentes(self):
        semanas = _semanas_janela(date(2026, 11, 16))
        assert len(semanas) == 12
        assert semanas[-1] == "2026-11-08"
        assert semanas[0] == "2026-08-23"
        assert semanas == sorted(semanas)
