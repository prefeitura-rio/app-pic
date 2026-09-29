from datetime import datetime

from src.pic.domain.models.dashboard import (
    Dashboard,
    DistribuicaoMotivoSaida,
    DistribuicaoSafra,
    DistribuicaoTempoIrregularidade,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
    TaxaResolucaoMensalPoint,
    TempoMedioIrregularidade,
)


def test_dashboard_defaults_empty():
    d = Dashboard()
    assert d.total_participantes == 0
    assert d.total_regulares == 0
    assert d.total_irregulares == 0
    assert d.percentual_regular == 0.0
    assert d.percentual_irregular == 0.0
    assert d.protocolos == []
    assert d.resultado_programa == []
    assert d.distribuicao_por_safra == []
    assert d.distribuicao_motivo_saida == []
    assert d.tempo_medio_irregularidade == []
    assert d.distribuicao_tempo_irregularidade == []
    assert d.taxa_resolucao_mensal == []
    assert d.data_atualizacao is None


def test_dashboard_minimal():
    d = Dashboard(total_participantes=100, total_regulares=80, total_irregulares=20)
    assert d.total_participantes == 100
    assert d.total_regulares == 80
    assert d.total_irregulares == 20
    assert d.protocolos == []


def test_dashboard_with_protocolos():
    d = Dashboard(
        total_participantes=10,
        protocolos=[
            ProtocoloIndicador(
                protocolo_id="sms_vacinacao",
                protocolo_descricao="Vacinacao",
                protocolo_secretaria="SMS",
                numerador=8,
                denominador=10,
                percentual_regular=80.0,
                percentual_irregular=20.0,
            )
        ],
    )
    assert len(d.protocolos) == 1
    assert d.protocolos[0].protocolo_id == "sms_vacinacao"
    assert d.protocolos[0].numerador == 8
    assert d.protocolos[0].percentual_regular == 80.0


def test_dashboard_serialization():
    d = Dashboard(total_participantes=5, total_regulares=3)
    data = d.model_dump()
    assert data["total_participantes"] == 5
    assert data["total_regulares"] == 3
    assert data["protocolos"] == []
    assert data["data_atualizacao"] is None


def test_dashboard_ignores_extra_fields():
    d = Dashboard(**{"total_participantes": 1, "unknown_section": "x"})
    assert d.total_participantes == 1
    assert not hasattr(d, "unknown_section")


def test_protocolo_indicador_defaults():
    pi = ProtocoloIndicador(
        protocolo_id="test",
        protocolo_descricao="Test Protocol",
        protocolo_secretaria="SMS",
    )
    assert pi.numerador == 0
    assert pi.denominador == 0
    assert pi.percentual_regular == 0.0
    assert pi.percentual_irregular == 0.0


def test_resultado_programa_point():
    rp = ResultadoProgramaPoint(
        mes="2025-12",
        mes_label="Dez/25",
        todos=75.5,
        saude=80.0,
        educacao=70.0,
        assistencia=65.0,
    )
    assert rp.mes == "2025-12"
    assert rp.mes_label == "Dez/25"
    assert rp.todos == 75.5
    assert rp.saude == 80.0
    assert rp.educacao == 70.0
    assert rp.assistencia == 65.0


def test_resultado_programa_point_defaults():
    rp = ResultadoProgramaPoint(mes="2025-01")
    assert rp.mes == "2025-01"
    assert rp.mes_label == ""
    assert rp.todos == 0.0


def test_distribuicao_safra():
    ds = DistribuicaoSafra(
        safra="Jan/25",
        total_participantes=200,
        total_ativos=180,
        total_inativos=20,
    )
    assert ds.safra == "Jan/25"
    assert ds.total_participantes == 200
    assert ds.total_ativos == 180
    assert ds.total_inativos == 20


def test_distribuicao_safra_defaults():
    ds = DistribuicaoSafra()
    assert ds.safra is None
    assert ds.total_participantes is None


def test_distribuicao_motivo_saida():
    dm = DistribuicaoMotivoSaida(motivo="Mudanca de municipio", total=15)
    assert dm.motivo == "Mudanca de municipio"
    assert dm.total == 15


def test_distribuicao_motivo_saida_nulls():
    dm = DistribuicaoMotivoSaida()
    assert dm.motivo is None
    assert dm.total is None


def test_distribuicao_tempo_irregularidade():
    dt = DistribuicaoTempoIrregularidade(
        faixa="0-30", faixa_label="0-30 dias", count=50, percentual=45.5
    )
    assert dt.faixa == "0-30"
    assert dt.faixa_label == "0-30 dias"
    assert dt.count == 50
    assert dt.percentual == 45.5


def test_distribuicao_tempo_irregularidade_defaults():
    dt = DistribuicaoTempoIrregularidade(faixa="90+")
    assert dt.faixa == "90+"
    assert dt.faixa_label == ""
    assert dt.count == 0
    assert dt.percentual == 0.0


def test_tempo_medio_irregularidade():
    tm = TempoMedioIrregularidade(
        secretaria="sms",
        secretaria_label="Saude",
        tempo_medio_dias=45.3,
        total_irregulares=120,
    )
    assert tm.secretaria == "sms"
    assert tm.secretaria_label == "Saude"
    assert tm.tempo_medio_dias == 45.3
    assert tm.total_irregulares == 120


def test_taxa_resolucao_mensal_point():
    tr = TaxaResolucaoMensalPoint(
        mes="2025-06",
        mes_label="Jun/25",
        todos=60.0,
        saude=65.0,
        educacao=55.0,
        assistencia=50.0,
    )
    assert tr.mes == "2025-06"
    assert tr.mes_label == "Jun/25"
    assert tr.todos == 60.0
    assert tr.saude == 65.0


def test_dashboard_with_full_sections():
    d = Dashboard(
        total_participantes=1000,
        total_regulares=800,
        total_irregulares=200,
        percentual_regular=80.0,
        percentual_irregular=20.0,
        protocolos=[
            ProtocoloIndicador(
                protocolo_id="p1",
                protocolo_descricao="Protocol 1",
                protocolo_secretaria="SMS",
            )
        ],
        resultado_programa=[
            ResultadoProgramaPoint(mes="2025-01", mes_label="Jan/25", todos=75.0)
        ],
        distribuicao_por_safra=[
            DistribuicaoSafra(safra="Jan/25", total_participantes=500)
        ],
        distribuicao_motivo_saida=[
            DistribuicaoMotivoSaida(motivo="Obito", total=5)
        ],
        tempo_medio_irregularidade=[
            TempoMedioIrregularidade(secretaria="geral")
        ],
        distribuicao_tempo_irregularidade=[
            DistribuicaoTempoIrregularidade(faixa="0-30", count=100)
        ],
        taxa_resolucao_mensal=[
            TaxaResolucaoMensalPoint(mes="2025-01")
        ],
        data_atualizacao=datetime(2025, 7, 15, 10, 30, 0),
    )
    assert len(d.protocolos) == 1
    assert len(d.resultado_programa) == 1
    assert len(d.distribuicao_por_safra) == 1
    assert len(d.distribuicao_motivo_saida) == 1
    assert len(d.tempo_medio_irregularidade) == 1
    assert len(d.distribuicao_tempo_irregularidade) == 1
    assert len(d.taxa_resolucao_mensal) == 1
    assert d.data_atualizacao == datetime(2025, 7, 15, 10, 30, 0)
