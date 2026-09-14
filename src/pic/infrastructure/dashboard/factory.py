from src.pic.domain.models.dashboard import Dashboard


def _create_empty_dashboard() -> Dashboard:
    return Dashboard(
        total_participantes=0,
        total_regulares=0,
        total_irregulares=0,
        percentual_regular=0.0,
        percentual_irregular=0.0,
        protocolos=[],
        resultado_programa=[],
        distribuicao_por_safra=[],
        distribuicao_motivo_saida=[],
        tempo_medio_irregularidade=[],
        distribuicao_tempo_irregularidade=[],
        taxa_resolucao_mensal=[],
    )
