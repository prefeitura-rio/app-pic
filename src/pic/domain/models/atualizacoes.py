"""Modelos de domínio do Painel de Atualizações (Busca Individual).

Fonte de dados: ``endpoint_participante_visao_geral_semanal_protocolos`` no
data-proxy (PostgREST), com RLS aplicada pelo token do usuário ANTES das
agregações — todo número sai do mesmo escopo.

**Contrato congelado** (etapa B2): ``presentation/v2/atualizacoes_schemas.py``
re-exporta estes modelos como contrato HTTP; ``types.ts`` do frontend é um
espelho. Mudanças entram apenas como campos novos opcionais — nunca renomeação.

Convenções:
- "regular" inclui atenção: ``regular + atencao``.
- Percentuais com denominador zero são ``None`` (não 0).
- ``tone`` é SEMÂNTICO, calculado no use case — o frontend nunca deriva do sinal.
"""

from typing import Literal

from pydantic import BaseModel, Field

Tone = Literal["success", "danger"]
NivelFoco = Literal["ra", "bairro"]
TipoCard = Literal["irregulares", "regulares", "foco"]

# Colunas de unidade de ``UserPermissions`` — base do gate (b) e do
# ``escopo_restrito`` (qualquer lista não-vazia = policy de unidade).
UNIT_LIST_ATTRS = (
    "id_cras_list",
    "id_escola_list",
    "id_cre_list",
    "id_ap_list",
    "id_cas_list",
    "id_clinica_familia_list",
    "id_equipe_familia_list",
)


# ---------------------------------------------------------------------------
# Linhas do repositório (não agregadas — a aritmética é do use case)
# ---------------------------------------------------------------------------


class SemanaStatusRow(BaseModel):
    """Q1 — uma linha por semana × ``pic_status`` (``nivel='geral'``)."""

    week_start: str
    status: str
    qtd: int = 0
    regular: int = 0
    atencao: int = 0
    irregular: int = 0
    regiao_label: str | None = None  # nome_cas/nome_cre/nome_ap (só essas camadas)


class ProtocoloSemanaRow(BaseModel):
    """Q2 — uma linha por semana × protocolo (``nivel≠'geral'``, só Ativo)."""

    week_start: str
    protocolo_id: str
    protocolo_descricao: str | None = None
    qtd: int = 0
    regular: int = 0
    atencao: int = 0


class FocoRow(BaseModel):
    """Q3 — uma linha por semana × valor da sub-camada (irregulares de Ativos)."""

    week_start: str
    local: str
    irregular: int = 0


# ---------------------------------------------------------------------------
# Contrato de resposta (espelho de ``types.ts`` — §4 da doc)
# ---------------------------------------------------------------------------


class Contexto(BaseModel):
    camada: str | None = None  # null quando o painel segue o escopo do usuário (RLS)
    regiao_id: str | None = None  # valor RAW da coluna da camada — ex.: "01ª CAS"
    regiao_label: str  # rótulo do dado — ex.: "01ª CAS" (nome_cas); sem região: "Cidade do Rio de Janeiro" | "Seu escopo de acesso"
    semana_em_curso: str | None = None  # ISO week-start de W — rótulo do header
    semana_referencia: str | None = None  # ISO week-start de W−1 — valores exibidos
    semana_comparacao: str | None = None  # ISO week-start de W−5 (4 semanas antes) — base dos deltas
    participantes: int = 0  # base da semana de referência


class Regularidade(BaseModel):
    taxa: float | None = None  # % dos ATIVOS (regulares / ativos)
    variacao_pp: float | None = None  # vs semana_comparacao (W−5, mesma base de ativos)
    tone: Tone = "success"
    regulares: int = 0  # Regular + Atenção (só linhas Ativo)
    irregulares: int = 0  # só linhas Ativo
    inativos: int = 0
    ativos: int = 0  # base − inativos — denominador da taxa
    base: int = 0  # == contexto.participantes (Ativo + Inativo)


class ProtocoloVariacao(BaseModel):
    protocolo_id: str
    nome: str  # só a descrição — ex.: "Busca ativa" (fallback: protocolo_id)
    de: float | None = None  # taxa na semana_comparacao (%)
    para: float | None = None  # taxa na semana_referencia (%)
    delta_abs: int = 0  # informativo — variação em PARTICIPANTES (não é o critério)
    delta_pp: float | None = None  # CRITÉRIO de seleção e exibição do chip (p.p.)
    tone: Tone = "success"  # regularidade subiu ⇒ success (calculado pelo p.p.)


class SeriePonto(BaseModel):
    semana: str  # ISO week-start
    valor: int = 0


class MetricaVariacao(BaseModel):
    total: int = 0
    variacao_pct: float | None = None  # sinal explícito no dado
    variacao_abs: int | None = None  # vs semana_comparacao (W−5)
    tone: Tone = "success"
    serie: list[SeriePonto] = Field(default_factory=list)  # 4 pontos — últimas semanas válidas


class FocoIrregularidade(BaseModel):
    nivel: NivelFoco  # sub-camada do foco (pelo acesso — regra 6 da §5.3)
    local: str  # rótulo cru da tabela — ex.: "3ª Rio Comprido" | "Tijuca"
    irregulares: int = 0
    participacao_pct: float | None = None  # % dos irregulares da região
    demais: int = 0  # = total − local
    # Estoque do local em W−1 menos o da semana de comparação — a escolha do
    # local continua pelo ESTOQUE (maior concentração); o delta só acompanha
    # a janela do seletor. None quando não há comparativo ou linha do local.
    delta_irregulares: int | None = None


class AtualizacoesPainelData(BaseModel):
    contexto: Contexto
    regularidade: Regularidade
    protocolos: list[ProtocoloVariacao] = Field(
        default_factory=list
    )  # maior alta + maior queda (pode vir vazio)
    irregulares: MetricaVariacao | None = None  # null sem dados
    regulares: MetricaVariacao | None = None  # regular + atenção (Ativo)
    foco: FocoIrregularidade | None = None


class MetaCard(BaseModel):
    tipo: TipoCard
    valor: int = 0  # participantes (unidade dos cards de volume)
    relevancia: float = 0.0  # 0..1 — informativa (valor / max)
    fixo: bool = False  # true somente para foco (3º slot)


class AtualizacoesMeta(BaseModel):
    semana_em_curso: str | None = None
    semana_referencia: str | None = None
    semana_comparacao: str | None = None  # W−(N+1) — base dos deltas (default N=4)
    semanas_comparacao: int = 4  # janela escolhida (1 | 2 | 4) — eco para o front
    tem_comparativo: bool = False  # false ⇒ deltas None, protocolos vazio
    escopo_restrito: bool = False  # usuário não vê a região inteira (RLS)
    cards: list[MetaCard] = Field(default_factory=list)  # lineup FIXO (decisão E)


class AtualizacoesRegionaisResponse(BaseModel):
    can_view_atualizacoes: bool = True  # gate (b) — §6
    meta: AtualizacoesMeta = Field(default_factory=AtualizacoesMeta)
    data: AtualizacoesPainelData | None = None  # null sem permissão/sem dados
