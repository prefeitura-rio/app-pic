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


class DisparoStatusDistribuicao(BaseModel):
    status: str | None = None
    total: int = 0


class DisparoJornadaResumo(BaseModel):
    jornada: str | None = None
    participantes: int = 0
    entregues_30d: int = 0
    falhas_30d: int = 0
    taxa_falha: float = 0.0
    status_distribuicao: list[DisparoStatusDistribuicao] = []


class DisparosDashboard(BaseModel):
    """Métricas agregadas de disparos de WhatsApp (snapshot últimos 30 dias)."""

    alcancados: int = 0
    cobertura_percentual: float = 0.0
    total_30d: int = 0
    entregues_30d: int = 0
    falhas_30d: int = 0
    taxa_entrega: float = 0.0
    taxa_falha: float = 0.0
    engajados: int = 0
    taxa_engajamento: float = 0.0
    status_distribuicao: list[DisparoStatusDistribuicao] = []
    por_jornada: list[DisparoJornadaResumo] = []


class BuscaAtivaTotais(BaseModel):
    """Totais da busca ativa: buscas acumuladas e participantes no mês mais
    recente (max data_referencia_mensal) do recorte filtrado."""

    buscas: int = 0
    participantes: int = 0


class BuscaAtivaPontoMensal(BaseModel):
    """Série mensal de busca ativa por fonte (SMS/SMAS)."""

    mes: str
    mes_label: str = ""
    smas: int = 0
    sms: int = 0
    total: int = 0


class BuscaAtivaDesfechoMensal(BaseModel):
    """Resultado SMAS por mês, quebrado por desfecho."""

    mes: str
    mes_label: str = ""
    desfecho: str
    total: int = 0


class BuscaAtivaCategoria(BaseModel):
    """Distribuição por categoria (tipo SMAS / público SMS)."""

    categoria: str
    total: int = 0


class BuscaAtivaDashboard(BaseModel):
    """Seção "Busca Ativa" da Visão Geral (agregada via PostgREST)."""

    totais: BuscaAtivaTotais = BuscaAtivaTotais()
    evolucao_mensal: list[BuscaAtivaPontoMensal] = []
    smas_desfecho_mensal: list[BuscaAtivaDesfechoMensal] = []
    smas_tipos: list[BuscaAtivaCategoria] = []
    sms_publicos: list[BuscaAtivaCategoria] = []


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
    disparos: DisparosDashboard | None = None
    busca_ativa: BuscaAtivaDashboard | None = None
    data_atualizacao: datetime | None = None

    @classmethod
    def empty(cls) -> "Dashboard":
        """Fully zeroed dashboard (used when the user cannot view it)."""
        return cls()
