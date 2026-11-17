"""Use case do Painel de Atualizações (aba Busca Individual).

Uma operação: ``GetAtualizacoesRegionaisUseCase`` — resumo da última semana
fechada de uma região: regularidade geral, extremos por protocolo, volume de
irregulares/regulares e foco geográfico — além do lineup fixo dos cards da
linha 2 (``meta.cards``).

Regras centrais (doc ``docs/atualizacoes-painel.md``):

- **Janela selecionável** (§5.1): semanas **domingo–sábado** (o
  `data_referencia_semana_inicio` da tabela é domingo — B1); referência W−1,
  comparação **W−(N+1)** com ``semanas_comparacao`` ∈ {1, 2, 4} (default 4
  semanas); série = **min(N+1, 4) pontos** (as últimas semanas válidas
  terminando em W−1); a semana em curso nunca entra nos números. Janela
  estável de 12 semanas: sem dados em W−1, recua até a última fechada com
  dados.
- **Sanidade da série** (decisão E, §5.1): a mediana é da **própria janela
  de ``pontos + 1`` domingos**, sobre a **base de ativos** (`qtd − inativos`)
  — uma mudança de nível legítima não vira anomalia. Semana fora de ±3% da
  mediana é pulada na série (ex.: 18/10/2026); os endpoints (W−1, W−pontos e
  W−(N+1)) nunca são descartados.
- **Gate (b)** (§6): super admin, acesso geral (3 secretarias) ou qualquer
  policy de unidade; sem permissão → ``can_view_atualizacoes=False``.
- **Foco pelo acesso** (§5.3 regra 6): geral → RA; policy parcial → bairro; se
  o nível coincidir com a camada do contexto desce um nível; contexto bairro
  omite o card. Escolha pelo **estoque de W−1**; ``delta_irregulares``
  (vs. W−(N+1)) acompanha a janela do seletor.
- **Extremos por Δpp** (§5.3 regra 10): maior alta + maior queda em **pontos
  percentuais**, entre W−(N+1) e W−1; um sinal só → duas maiores |Δpp|; piso
  de ``_PISO_BASE_PROTOCOLO`` participantes em W−1 (relaxa se esvaziar);
  ``delta_abs`` continua no payload como informativo.
- **Secretarias de acesso** (§5.3 regra 7): a RLS do data-proxy recorta
  **unidade**, não secretaria — os extremos por protocolo são filtrados por
  ``secretarias_acesso`` (``protocol_secretarias_filter``: None = acesso
  total, ``[]`` = sem protocolos, lista = subset).
- **Regularidade = taxa dos ATIVOS** (§5.3 regra 9): ``taxa = regulares /
  ativos`` (``ativos = base − inativos``) — a mesma métrica da Visão Geral com
  filtro Ativo; a variação usa W−(N+1) com a mesma base. A partição
  ``base = regulares + irregulares + inativos`` continua para o strip do card.
- **Lineup fixo** (decisão E, §5.4): irregulares → regulares → foco — definido
  pelo produto, sem ranking; ``meta.cards`` já vem na ordem.
- **RLS**: token do usuário sempre; agregados do mesmo escopo.
- **Escopo**: sem ``camada``/``regiao`` (ambas omitidas), as consultas rodam
  sem recorte territorial — a RLS entrega o escopo de acessos do usuário; o
  painel segue os acessos, não os filtros da busca.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.pic.application.ports.atualizacoes_repository import (
    IAtualizacoesRepository,
)
from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.domain.models.atualizacoes import (
    UNIT_LIST_ATTRS,
    AtualizacoesMeta,
    AtualizacoesPainelData,
    AtualizacoesRegionaisResponse,
    Contexto,
    FocoIrregularidade,
    MetaCard,
    MetricaVariacao,
    ProtocoloSemanaRow,
    ProtocoloVariacao,
    Regularidade,
    SeriePonto,
    Tone,
)
from src.pic.domain.models.territorio import CAMADAS_SUPORTADAS, NORMALIZERS
from src.utils.log import logger

_FUSO = ZoneInfo("America/Sao_Paulo")

_JANELA_SEMANAS = 12
_SERIE_PONTOS_TETO = 4  # máximo de pontos desenhados no sparkline
_SEMANAS_COMPARACAO_PERMITIDAS = (1, 2, 4)  # opções do seletor
_COMPARACAO_PADRAO = 4  # delta padrão = W−1 vs W−5
_SEMANA_DIAS = 7
_SANIDADE_DESVIO = 0.03  # base de ativos fora de ±3% da mediana → semana fora da série
_PISO_BASE_PROTOCOLO = 100  # Q2: piso de participantes em W−1 para os extremos por Δpp


def _pontos_serie(semanas_comparacao: int) -> int:
    """Pontos do sparkline para a janela escolhida: ``min(N + 1, 4)``."""
    return min(semanas_comparacao + 1, _SERIE_PONTOS_TETO)


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


def _hoje() -> date:
    """Data corrente em America/Sao_Paulo (o pod roda em UTC)."""
    return datetime.now(_FUSO).date()


def _inicio_semana_corrente(hoje: date) -> date:
    """Domingo da semana em curso (a tabela semanal é domingo–sábado)."""
    return hoje - timedelta(days=(hoje.weekday() + 1) % 7)


def _ultima_semana_fechada(hoje: date) -> date:
    """Domingo da última semana fechada: ``semana_inicio + 6 < hoje``.

    No domingo a semana em curso recém começou e ainda não fechou (regra de
    fuso — V5); no sábado ela também não fechou (termina no próprio sábado).
    """
    return _inicio_semana_corrente(hoje) - timedelta(days=_SEMANA_DIAS)


def _semanas_janela(hoje: date) -> list[str]:
    """12 domingos fechados mais recentes (ascendente), terminando em W−1."""
    ultima = _ultima_semana_fechada(hoje)
    return [
        (ultima - timedelta(weeks=offset)).isoformat()
        for offset in range(_JANELA_SEMANAS - 1, -1, -1)
    ]


def _acesso_geral(permissions) -> bool:
    if permissions is None:
        return False
    return bool(permissions.is_super_admin) or permissions.secretaria_acesso == "TODOS"


def _tem_policy_unidade(permissions) -> bool:
    if permissions is None:
        return False
    return any(getattr(permissions, attr) for attr in UNIT_LIST_ATTRS)


def _can_view_atualizacoes(permissions) -> bool:
    """Gate (b): super admin, acesso geral ou qualquer policy de unidade."""
    if permissions is None:
        return True
    return _acesso_geral(permissions) or _tem_policy_unidade(permissions)


def _tone(delta: int | float | None, melhor_quando_positivo: bool) -> Tone:
    """``tone`` é semântico: a direção "boa" depende da métrica.

    Sem variação (ou sem comparativo) → ``success`` (neutro, sem alerta).
    """
    if delta is None or delta == 0:
        return "success"
    positivo = delta > 0
    return "success" if positivo == melhor_quando_positivo else "danger"


def _taxa_semana(bucket: dict[str, int]) -> float | None:
    """Taxa de regularidade da semana: (regular + atenção) sobre os ATIVOS.

    ``qtd`` inclui todos os status; ``inativos_qtd`` (quando presente) sai do
    denominador — a taxa é a regularidade dos ativos, a mesma métrica da Visão
    Geral com filtro Ativo. Buckets de protocolo (só Ativos) não têm a chave.
    """
    ativos = bucket["qtd"] - bucket.get("inativos_qtd", 0)
    if ativos <= 0:
        return None
    return (bucket["regular"] + bucket["atencao"]) / ativos * 100


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class GetAtualizacoesRegionaisUseCase:
    def __init__(
        self,
        repository: IAtualizacoesRepository,
        geo_repository: IGeospatialRepository,
    ):
        self._repository = repository
        self._geo_repository = geo_repository

    async def _resolve_regiao(
        self,
        camada: str,
        regiao: str,
        user_token: str | None,
        user_id: str | None,
    ) -> str | None:
        """Valor exibido → RAW da coluna da camada (padrão do monitoring).

        Join normalizado sobre os agregados do consolidado — a mesma
        query/cache do mapa. ``None`` = região sem dados no escopo do usuário.
        """
        normalize = NORMALIZERS[camada]
        key = normalize(regiao)
        if not key:
            raise ValueError(f"Região inválida para a camada {camada!r}: {regiao!r}")
        aggregates = await self._geo_repository.fetch_regularidade_por_camada(
            camada=camada,
            user_token=user_token,
            user_id=user_id,
            # bypass_cache SEMPRE False: o valor RAW da região é estável — o
            # bypass do usuário vale para a tabela semanal, não para esta
            # resolução (mesmo critério do monitoring).
            bypass_cache=False,
        )
        for agg in aggregates:
            if normalize(agg.regiao) == key:
                return agg.regiao
        return None

    @staticmethod
    def _resolver_label(rows_q1, raw: str) -> str:
        """Rótulo exibido da região — vindo da tabela (decisão Q6, §7).

        ``nome_cas``/``nome_cre``/``nome_ap`` chegam nas linhas da Q1 (só
        essas camadas); ``ra``/``bairro`` usam o próprio RAW, que já é o nome.
        Sem GeoJSON no painel.
        """
        for row in rows_q1:
            if row.regiao_label:
                return row.regiao_label
        return raw

    # ------------------------------------------------------------------
    # Agregações
    # ------------------------------------------------------------------

    @staticmethod
    def _agregar_q1(rows) -> dict[str, dict[str, int]]:
        """Q1 → bucket por semana: qtd, inativos, regular, atencao, irregular.

        A tabela classifica TODO participante por status E por regularidade
        (linhas Inativo também têm regular/irregular — V1, §7). As contagens
        de regular/atenção/irregular somam SÓ as linhas Ativo; inativos =
        ``qtd`` das linhas Inativo. Assim ``base = regulares + irregulares +
        inativos`` fecha (partição do design).
        """
        by_week: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "qtd": 0,
                "inativos_qtd": 0,
                "regular": 0,
                "atencao": 0,
                "irregular": 0,
            }
        )
        for row in rows:
            bucket = by_week[row.week_start]
            bucket["qtd"] += row.qtd
            if row.status == "Inativo":
                bucket["inativos_qtd"] += row.qtd
            else:
                bucket["regular"] += row.regular
                bucket["atencao"] += row.atencao
                bucket["irregular"] += row.irregular
        resultado = dict(by_week)
        for bucket in resultado.values():
            # Chave derivada do card "Participantes regulares" (regular + atenção).
            bucket["regulares"] = bucket["regular"] + bucket["atencao"]
        return resultado

    @staticmethod
    def _semanas_validas(
        ref: date,
        by_week: dict[str, dict[str, int]],
        semanas_comparacao: int,
    ) -> set[str]:
        """Sanidade da série: mediana da base de ATIVOS na janela da série.

        A janela é ``pontos + 1`` domingos terminando em W−1 (os ``pontos``
        desenhados + 1 semana de folga para pular uma anômala) — **não** as 12
        semanas nem a janela de comparação: uma mudança de nível legítima não
        vira anomalia e a série nunca encolhe por causa do seletor. A base é
        a de ativos (``qtd − inativos``), o denominador dos cards. Os
        endpoints (W−1, W−pontos e W−(N+1)) nunca são descartados.
        """
        pontos = _pontos_serie(semanas_comparacao)
        janela: list[tuple[str, int]] = []
        cursor = ref
        for _ in range(pontos + 1):
            iso = cursor.isoformat()
            bucket = by_week.get(iso)
            if bucket is not None:
                janela.append((iso, bucket["qtd"] - bucket.get("inativos_qtd", 0)))
            cursor -= timedelta(days=_SEMANA_DIAS)
        if not janela:
            return set()
        bases = sorted(base for _, base in janela)
        meio = len(bases) // 2
        mediana = bases[meio] if len(bases) % 2 else (bases[meio - 1] + bases[meio]) / 2
        validas = {
            iso
            for iso, base in janela
            if mediana > 0 and abs(base - mediana) / mediana <= _SANIDADE_DESVIO
        }
        # Endpoints nunca saem: referência, início nominal da série e base da
        # comparação (para N<4, o início nominal e a base coincidem).
        validas.add(ref.isoformat())
        inicio_serie = (ref - timedelta(days=_SEMANA_DIAS * pontos)).isoformat()
        if inicio_serie in by_week:
            validas.add(inicio_serie)
        cmp_iso = (
            ref - timedelta(days=_SEMANA_DIAS * semanas_comparacao)
        ).isoformat()
        if cmp_iso in by_week:
            validas.add(cmp_iso)
        return validas

    @staticmethod
    def _serie_weeks(
        ref: date,
        by_week: dict[str, dict[str, int]],
        validas: set[str],
        pontos: int,
    ) -> list[str]:
        """Série de ``pontos``: as últimas semanas VÁLIDAS terminando em W−1.

        Para na primeira LACUNA (semana sem linhas); semanas ANÔMALAS são
        puladas — a janela recua até completar os pontos (máx. 12 semanas).
        """
        weeks: list[str] = []
        cursor = ref
        for _ in range(_JANELA_SEMANAS):
            iso = cursor.isoformat()
            if iso not in by_week:
                break  # lacuna de dados — para a série
            if iso in validas:
                weeks.append(iso)
                if len(weeks) == pontos:
                    break
            cursor -= timedelta(days=_SEMANA_DIAS)
        return list(reversed(weeks))

    @staticmethod
    def _metrica_variacao(
        chave: str,
        ref_bucket: dict[str, int],
        cmp_bucket: dict[str, int] | None,
        tem_comparativo: bool,
        serie_weeks: list[str],
        by_week: dict[str, dict[str, int]],
        melhor_quando_positivo: bool,
    ) -> MetricaVariacao:
        total = ref_bucket[chave]
        variacao_abs: int | None = None
        variacao_pct: float | None = None
        tone: Tone = "success"
        if tem_comparativo and cmp_bucket is not None:
            base_cmp = cmp_bucket[chave]
            variacao_abs = total - base_cmp
            if base_cmp > 0:
                variacao_pct = round(variacao_abs / base_cmp * 100, 1)
            tone = _tone(variacao_abs, melhor_quando_positivo)
        serie = [
            SeriePonto(semana=week, valor=by_week[week][chave]) for week in serie_weeks
        ]
        return MetricaVariacao(
            total=total,
            variacao_pct=variacao_pct,
            variacao_abs=variacao_abs,
            tone=tone,
            serie=serie,
        )

    @staticmethod
    def _protocolos_extremos(
        rows,
        ref_iso: str,
        cmp_iso: str,
    ) -> list[ProtocoloVariacao]:
        """Q2 → maior alta + maior queda por **Δpp** (pontos percentuais).

        O critério é o p.p. — a mesma unidade do chip e da trilha (±10 p.p.).
        Δabs (participantes) continua no payload como informativo, mas cresce
        junto com a base e degenera o ranking em ranking de volume (todas as
        altas positivas → o card vira "os 2 maiores protocolos"). Piso de
        ``_PISO_BASE_PROTOCOLO`` participantes em W−1 evita que um protocolo
        minúsculo domine o p.p.; se o piso deixar menos de 1 protocolo, a
        seleção reavalia sem piso. Um sinal só → duas maiores |Δpp| daquele
        sinal. Empate em p.p. → maior qtd. Exibição: alta primeiro, depois
        queda. ``tone`` vem do p.p.
        """
        by_protocolo: dict[str, dict[str, ProtocoloSemanaRow]] = {}
        for row in rows:
            by_protocolo.setdefault(row.protocolo_id, {})[row.week_start] = row

        apurados: list[dict[str, object]] = []
        for protocolo_id, por_semana in by_protocolo.items():
            atual = por_semana.get(ref_iso)
            anterior = por_semana.get(cmp_iso)
            if atual is None or anterior is None:
                continue
            regulares_atual = atual.regular + atual.atencao
            regulares_anterior = anterior.regular + anterior.atencao
            taxa_atual = _taxa_semana(
                {"qtd": atual.qtd, "regular": regulares_atual, "atencao": 0}
            )
            taxa_anterior = _taxa_semana(
                {"qtd": anterior.qtd, "regular": regulares_anterior, "atencao": 0}
            )
            delta_abs = regulares_atual - regulares_anterior
            delta_pp_raw = (
                taxa_atual - taxa_anterior
                if taxa_atual is not None and taxa_anterior is not None
                else None
            )
            apurados.append(
                {
                    "protocolo_id": protocolo_id,
                    "descricao": atual.protocolo_descricao,
                    "qtd": atual.qtd,
                    "de": round(taxa_anterior, 1)
                    if taxa_anterior is not None
                    else None,
                    "para": round(taxa_atual, 1) if taxa_atual is not None else None,
                    "delta_abs": delta_abs,
                    "delta_pp_raw": delta_pp_raw,
                }
            )

        comparaveis = [a for a in apurados if a["delta_pp_raw"] is not None]
        # Piso de base na semana de referência; relaxa se esvaziar a seleção.
        dentro_do_piso = [a for a in comparaveis if a["qtd"] >= _PISO_BASE_PROTOCOLO]
        if len(dentro_do_piso) >= 1:
            comparaveis = dentro_do_piso

        altas = [a for a in comparaveis if a["delta_pp_raw"] > 0]
        quedas = [a for a in comparaveis if a["delta_pp_raw"] < 0]
        if altas and quedas:
            selecionados = [
                max(altas, key=lambda a: (a["delta_pp_raw"], a["qtd"])),
                min(quedas, key=lambda a: (a["delta_pp_raw"], -a["qtd"])),
            ]
        elif altas:
            selecionados = sorted(
                altas, key=lambda a: (abs(a["delta_pp_raw"]), a["qtd"]), reverse=True
            )[:2]
        elif quedas:
            selecionados = sorted(
                quedas, key=lambda a: (abs(a["delta_pp_raw"]), a["qtd"]), reverse=True
            )[:2]
        else:
            return []
        # Ordem de exibição: alta primeiro, depois queda; com um sinal só,
        # os ``sorted`` acima já entregam |Δpp| desc (extremo primeiro) —
        # nenhum sort adicional para não inverter o caso de só quedas.

        resultado: list[ProtocoloVariacao] = []
        for item in selecionados:
            # Exibição só com a DESCRIÇÃO do protocolo (sem o id prefixado);
            # o id vira fallback apenas se a descrição vier vazia.
            descricao = item["descricao"]
            nome = descricao or str(item["protocolo_id"])
            resultado.append(
                ProtocoloVariacao(
                    protocolo_id=item["protocolo_id"],
                    nome=nome,
                    de=item["de"],
                    para=item["para"],
                    delta_abs=item["delta_abs"],
                    delta_pp=round(item["delta_pp_raw"], 1),
                    tone=_tone(item["delta_pp_raw"], melhor_quando_positivo=True),
                )
            )
        return resultado

    @staticmethod
    def _ranking_cards(
        irregulares: MetricaVariacao | None,
        regulares: MetricaVariacao | None,
        foco: FocoIrregularidade | None,
    ) -> list[MetaCard]:
        """Lineup FIXO da linha 2 — ``meta.cards`` já na ordem (decisão E).

        irregulares → regulares → foco (fixo, 3º slot) — definido pelo
        produto, sem ranking. Card sem dados não entra na lista. O front
        consome a ordem do array — não reordena.
        """
        cards: list[MetaCard] = []
        if irregulares is not None:
            cards.append(MetaCard(tipo="irregulares", valor=irregulares.total))
        if regulares is not None:
            cards.append(MetaCard(tipo="regulares", valor=regulares.total))
        if foco is not None:
            cards.append(MetaCard(tipo="foco", valor=foco.irregulares, fixo=True))
        if not cards:
            return []
        max_valor = max(card.valor for card in cards)
        return [
            card.model_copy(
                update={
                    "relevancia": (
                        round(card.valor / max_valor, 2) if max_valor > 0 else 0.0
                    )
                }
            )
            for card in cards
        ]

    # ------------------------------------------------------------------
    # Operação
    # ------------------------------------------------------------------

    async def execute(
        self,
        camada: str | None = None,
        regiao: str | None = None,
        permissions=None,
        user_token: str | None = None,
        user_id: str | None = None,
        semana: str | None = None,
        semanas_comparacao: int = _COMPARACAO_PADRAO,
        bypass_cache: bool = False,
    ) -> AtualizacoesRegionaisResponse:
        if semanas_comparacao not in _SEMANAS_COMPARACAO_PERMITIDAS:
            raise ValueError(
                "semanas_comparacao deve ser 1, 2 ou 4 "
                f"(recebido: {semanas_comparacao!r})"
            )
        pontos = _pontos_serie(semanas_comparacao)
        meta = AtualizacoesMeta(
            escopo_restrito=not _acesso_geral(permissions),
            semana_em_curso=_inicio_semana_corrente(_hoje()).isoformat(),
            semanas_comparacao=semanas_comparacao,
        )
        if not _can_view_atualizacoes(permissions):
            return AtualizacoesRegionaisResponse(
                can_view_atualizacoes=False, meta=meta, data=None
            )
        if (camada is None) != (regiao is None):
            raise ValueError("camada e regiao devem ser passadas juntas (ou ambas omitidas)")
        if camada is not None and camada not in CAMADAS_SUPORTADAS:
            raise ValueError(
                f"Camada {camada!r} não suportada (esperado: {CAMADAS_SUPORTADAS})"
            )

        # Sem camada/região: o painel segue o escopo do usuário (RLS recorta
        # as unidades) — nenhum filtro territorial nas consultas.
        if regiao:
            raw = await self._resolve_regiao(camada, regiao, user_token, user_id)
            if raw is None:
                # Região sem dados no escopo do usuário — barra "Sem indicadores".
                return AtualizacoesRegionaisResponse(
                    can_view_atualizacoes=True, meta=meta, data=None
                )
        else:
            raw = None

        # Janela: referência/comparação/série (§5.1). A janela pedida ao
        # repositório cobre a comparação escolhida E a série (que pode recuar
        # além do delta para completar os pontos).
        if semana:
            ref_date = date.fromisoformat(semana)
            # Debug/histórico: janela mínima = max(N, pontos) + 1 domingos.
            semanas_q1 = [
                ref_date - timedelta(days=_SEMANA_DIAS * offset)
                for offset in range(max(semanas_comparacao, pontos), -1, -1)
            ]
        else:
            semanas_q1 = [date.fromisoformat(iso) for iso in _semanas_janela(_hoje())]

        rows_q1 = await self._repository.fetch_semanas_status(
            camada=camada,
            regiao=raw,
            semanas=[d.isoformat() for d in semanas_q1],
            user_token=user_token,
            user_id=user_id,
            bypass_cache=bypass_cache,
        )
        by_week = self._agregar_q1(rows_q1)
        if not by_week:
            return AtualizacoesRegionaisResponse(
                can_view_atualizacoes=True, meta=meta, data=None
            )

        # Referência = última semana fechada com dados (recua se W−1 faltar);
        # comparação = N semanas antes (W−(N+1)). Sanidade da série (decisão E).
        ref_date = max(date.fromisoformat(iso) for iso in by_week)
        cmp_date = ref_date - timedelta(days=_SEMANA_DIAS * semanas_comparacao)
        ref_iso = ref_date.isoformat()
        cmp_iso = cmp_date.isoformat()
        tem_comparativo = cmp_iso in by_week
        validas = self._semanas_validas(ref_date, by_week, semanas_comparacao)
        serie_weeks = self._serie_weeks(ref_date, by_week, validas, pontos)

        ref_bucket = by_week[ref_iso]
        cmp_bucket = by_week.get(cmp_iso)

        # --- Regularidade geral (Q1) — taxa sobre os ATIVOS ---
        # A taxa é a regularidade dos ativos (mesma métrica da Visão Geral com
        # filtro Ativo): os inativos ficam fora do denominador. A partição
        # ``base = regulares + irregulares + inativos`` permanece (strip do card).
        base = ref_bucket["qtd"]
        ativos = base - ref_bucket["inativos_qtd"]
        regulares = ref_bucket["regular"] + ref_bucket["atencao"]
        taxa_bruta = regulares / ativos * 100 if ativos > 0 else None
        variacao_pp: float | None = None
        tone_reg: Tone = "success"
        if tem_comparativo and cmp_bucket is not None:
            taxa_cmp = _taxa_semana(cmp_bucket)
            if taxa_bruta is not None and taxa_cmp is not None:
                variacao_pp = round(taxa_bruta - taxa_cmp, 1)
                tone_reg = _tone(variacao_pp, melhor_quando_positivo=True)
        regularidade = Regularidade(
            taxa=round(taxa_bruta, 1) if taxa_bruta is not None else None,
            variacao_pp=variacao_pp,
            tone=tone_reg,
            regulares=regulares,
            irregulares=ref_bucket["irregular"],
            inativos=ref_bucket["inativos_qtd"],
            ativos=ativos,
            base=base,
        )

        # --- Métricas de variação (Q1) — comparação de N semanas (W−(N+1)) ---
        irregulares = self._metrica_variacao(
            "irregular",
            ref_bucket,
            cmp_bucket,
            tem_comparativo,
            serie_weeks,
            by_week,
            melhor_quando_positivo=False,
        )
        regulares = self._metrica_variacao(
            "regulares",
            ref_bucket,
            cmp_bucket,
            tem_comparativo,
            serie_weeks,
            by_week,
            melhor_quando_positivo=True,
        )

        # --- Foco (Q3) — nível pelo acesso (regra 6) ---
        # Estoque (W−1) escolhe o local; o delta vs. W−(N+1) só acompanha a
        # janela do seletor — o card reage a N sem mudar de significado.
        nivel_foco = "ra" if not meta.escopo_restrito else "bairro"
        if camada == nivel_foco and nivel_foco == "ra":
            nivel_foco = "bairro"  # mesmo nível do contexto → desce
        omitir_foco = camada == "bairro"
        foco: FocoIrregularidade | None = None
        if not omitir_foco:
            sub_camada = "regiao_administrativa" if nivel_foco == "ra" else "bairro"
            foco_rows = await self._repository.fetch_foco(
                camada=camada,
                regiao=raw,
                sub_camada=sub_camada,
                semanas=([cmp_iso, ref_iso] if tem_comparativo else [ref_iso]),
                user_token=user_token,
                user_id=user_id,
                bypass_cache=bypass_cache,
            )
            total_irregulares = ref_bucket["irregular"]
            # Pivot por local: o estoque em W−1 escolhe (maior primeiro,
            # empate → ordem alfabética); o delta vem da semana de comparação
            # quando o local existe nela. O PostgREST não ordena por alias
            # agregado (42703) — o máximo é escolhido aqui.
            por_local: dict[str, dict[str, int]] = {}
            for row in foco_rows:
                por_local.setdefault(row.local, {})[row.week_start] = row.irregular
            melhor = (
                sorted(
                    (
                        (local, por_semana.get(ref_iso, 0))
                        for local, por_semana in por_local.items()
                    ),
                    key=lambda t: (-t[1], t[0]),
                )[0]
                if por_local
                else None
            )
            if melhor is not None and melhor[1] > 0 and total_irregulares > 0:
                local, estoque = melhor
                anterior = por_local[local].get(cmp_iso)
                delta = estoque - anterior if anterior is not None else None
                foco = FocoIrregularidade(
                    nivel=nivel_foco,
                    local=local,
                    irregulares=estoque,
                    participacao_pct=round(estoque / total_irregulares * 100, 1),
                    demais=total_irregulares - estoque,
                    delta_irregulares=delta,
                )

        # --- Extremos por protocolo (Q2) — comparação de N semanas ---
        # A RLS recorta UNIDADE, não secretaria: o filtro de protocolos pelas
        # secretarias de acesso do usuário é responsabilidade do backend
        # (§5.3 regra 7). None = acesso total; [] = sem protocolos.
        secretarias = (
            permissions.protocol_secretarias_filter()
            if permissions is not None
            else None
        )
        if tem_comparativo:
            protocolos_rows = await self._repository.fetch_protocolos(
                camada=camada,
                regiao=raw,
                semanas=[cmp_iso, ref_iso],
                secretarias=secretarias,
                user_token=user_token,
                user_id=user_id,
                bypass_cache=bypass_cache,
            )
            protocolos = self._protocolos_extremos(protocolos_rows, ref_iso, cmp_iso)
        else:
            protocolos = []

        meta.semana_referencia = ref_iso
        meta.semana_comparacao = cmp_iso if tem_comparativo else None
        meta.tem_comparativo = tem_comparativo
        meta.cards = self._ranking_cards(irregulares, regulares, foco)

        label = (
            self._resolver_label(rows_q1, raw)
            if raw
            else (
                "Seu escopo de acesso"
                if meta.escopo_restrito
                else "Cidade do Rio de Janeiro"
            )
        )
        data = AtualizacoesPainelData(
            contexto=Contexto(
                camada=camada,
                regiao_id=raw,
                regiao_label=label,
                semana_em_curso=meta.semana_em_curso,
                semana_referencia=ref_iso,
                semana_comparacao=meta.semana_comparacao,
                participantes=base,
            ),
            regularidade=regularidade,
            protocolos=protocolos,
            irregulares=irregulares,
            regulares=regulares,
            foco=foco,
        )
        logger.info(
            f"[atualizacoes] camada={camada!r} regiao={regiao!r} "
            f"ref={ref_iso} cmp={cmp_iso} cards={len(meta.cards)} "
            f"user_id={user_id!r}"
        )
        return AtualizacoesRegionaisResponse(
            can_view_atualizacoes=True, meta=meta, data=data
        )
