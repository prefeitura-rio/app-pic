from datetime import datetime

from pydantic import BaseModel


class DistribuicaoMotivoSaida(BaseModel):
    motivo: str | None = None
    total: int | None = None


class DistribuicaoSafra(BaseModel):
    safra: str | None = None
    total_participantes: int | None = None
    total_ativos: int | None = None
    total_inativos: int | None = None


class ResultadoProgramaPoint(BaseModel):
    mes: str
    mes_label: str = ""
    todos: float = 0.0
    saude: float = 0.0
    educacao: float = 0.0
    assistencia: float = 0.0


class DistribuicaoTempoIrregularidade(BaseModel):
    faixa: str
    faixa_label: str = ""
    count: int = 0
    percentual: float = 0.0


class TempoMedioIrregularidade(BaseModel):
    secretaria: str
    secretaria_label: str = ""
    tempo_medio_dias: float = 0.0
    total_irregulares: int = 0


class TaxaResolucaoMensalPoint(BaseModel):
    mes: str
    mes_label: str = ""
    todos: float = 0.0
    saude: float = 0.0
    educacao: float = 0.0
    assistencia: float = 0.0


class ProtocoloIndicador(BaseModel):
    protocolo_id: str
    protocolo_descricao: str
    protocolo_secretaria: str
    numerador: int = 0
    denominador: int = 0
    percentual_regular: float = 0.0
    percentual_irregular: float = 0.0


class Dashboard(BaseModel):
    total_participantes: int = 0
    total_regulares: int = 0
    total_irregulares: int = 0
    percentual_regular: float = 0.0
    percentual_irregular: float = 0.0
    protocolos: list[ProtocoloIndicador] = []
    resultado_programa: list[ResultadoProgramaPoint] = []
    distribuicao_por_safra: list[DistribuicaoSafra] = []
    distribuicao_motivo_saida: list[DistribuicaoMotivoSaida] = []
    tempo_medio_irregularidade: list[TempoMedioIrregularidade] = []
    distribuicao_tempo_irregularidade: list[DistribuicaoTempoIrregularidade] = []
    taxa_resolucao_mensal: list[TaxaResolucaoMensalPoint] = []
    data_atualizacao: datetime | None = None
