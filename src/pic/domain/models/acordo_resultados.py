"""Modelos de domínio do Acordo de Resultados 2026.

Métricas dos cohorts do acordo (cohort <= ACORDO_COHORT_CUTOFF) servidas por
GET /api/v2/acordo-resultados. Reusa os modelos de ponto/motivo/protocolo do
dashboard para manter consistência com a Visão Geral.
"""

from pydantic import BaseModel

from src.pic.domain.models.dashboard import (
    DistribuicaoMotivoSaida,
    ProtocoloIndicador,
    ResultadoProgramaPoint,
)


class StatusResumo(BaseModel):
    total: int = 0
    regulares: int = 0
    irregulares: int = 0
    percentual_regular: float = 0.0
    percentual_irregular: float = 0.0


class DistribuicaoPublico(BaseModel):
    """Distribuição por categoria (raça, grupo ou Região Administrativa)."""

    categoria: str
    total: int = 0


class AcordoResultados(BaseModel):
    total_participantes: int = 0
    ativos: StatusResumo = StatusResumo()
    inativos: StatusResumo = StatusResumo()
    protocolos: list[ProtocoloIndicador] = []
    evolucao_mensal: list[ResultadoProgramaPoint] = []
    motivos_saida: list[DistribuicaoMotivoSaida] = []
    distribuicao_raca: list[DistribuicaoPublico] = []
    distribuicao_grupo: list[DistribuicaoPublico] = []
    distribuicao_ra: list[DistribuicaoPublico] = []
    distribuicao_cartao_pic: list[DistribuicaoPublico] = []
    distribuicao_bolsa_familia: list[DistribuicaoPublico] = []
    meta_regularidade: float = 30.5

    @classmethod
    def empty(cls) -> "AcordoResultados":
        """Modelo zerado (usado quando o usuário não pode ver o acordo)."""
        return cls()
