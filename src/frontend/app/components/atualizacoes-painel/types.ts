/**
 * Contrato de dados do Painel de Atualizações (snake_case — convenção do projeto).
 *
 * ESPELHO do contrato congelado no backend:
 * `src/pic/presentation/v2/atualizacoes_schemas.py` é a fonte da verdade
 * (etapa B2). Campo novo no front só entra passando pelo backend, e mudança
 * de contrato congelado entra apenas como campo novo opcional — nunca
 * renomeação.
 *
 * Semanas **domingo–sábado** (o `data_referencia_semana_inicio` da tabela
 * semanal é domingo): as ISO week-starts são domingos.
 */

/** Janela de comparação selecionável (1 | 2 | 4 semanas) — default 4. */
export type JanelaComparacao = 1 | 2 | 4;

/** Variação na janela escolhida (W−1 × W−(N+1)). `tone` é SEMÂNTICO — nunca derivar do sinal. */
export type Tone = "success" | "danger";

export interface Contexto {
  camada: string; // "cas" (uma de bairro|ra|cas|cre|ap)
  regiao_id: string; // valor RAW da coluna da camada — ex.: "01ª CAS"
  regiao_label: string; // rótulo da TABELA (nome_cas/nome_cre/nome_ap ou o RAW de ra/bairro)
  semana_em_curso: string | null; // ISO week-start (domingo) de W — rótulo do header
  semana_referencia: string | null; // ISO week-start de W-1 — TODOS os valores exibidos
  semana_comparacao: string | null; // ISO week-start de W-(N+1) — base dos deltas e do rodapé
  participantes: number; // base da semana de referência
}

export interface Regularidade {
  taxa: number | null; // % dos ATIVOS (regulares / ativos) — mesma métrica da Visão Geral (Ativo)
  variacao_pp: number | null; // vs semana_comparacao (W-(N+1)), mesma base de ativos
  tone: Tone;
  regulares: number; // Regular + Atenção (só linhas Ativo — V1)
  irregulares: number;
  inativos: number;
  ativos: number; // base - inativos — denominador da taxa
  base: number; // == contexto.participantes (Ativo + Inativo)
}

export interface ProtocoloVariacao {
  protocolo_id: string;
  nome: string; // só a descrição — ex.: "Busca ativa" (fallback: id; quebra livre)
  de: number | null; // taxa na semana_comparacao (%) — ex.: 71.2
  para: number | null; // taxa na semana_referencia (%) — ex.: 79.8
  delta_abs: number; // informativo — variação em PARTICIPANTES (ex.: +43 / −126)
  delta_pp: number | null; // CRITÉRIO de seleção + exibição do chip (ex.: +8.6 p.p.)
  tone: Tone; // regularidade subiu ⇒ success
}

export interface SeriePonto {
  semana: string; // ISO week-start domingo (últimas semanas válidas até W-1)
  valor: number;
}

export interface MetricaVariacao {
  total: number;
  variacao_pct: number | null; // sinal explícito no dado
  variacao_abs: number | null; // vs semana_comparacao (W-(N+1))
  tone: Tone;
  serie: SeriePonto[]; // min(N+1, 4) pontos — últimas semanas válidas (anômalas puladas; decisão E)
}

export interface FocoIrregularidade {
  nivel: "ra" | "bairro"; // sub-camada do foco (pelo acesso — regra 6 da §5.3)
  local: string; // rótulo cru da tabela — ex.: "13ª Meier" (ra) | "Meier" (bairro)
  irregulares: number;
  participacao_pct: number | null; // % dos irregulares da região
  demais: number; // = total - local
  // Estoque W−1 − W−(N+1) do LOCAL escolhido (a escolha continua pelo
  // estoque); null quando sem comparativo ou sem linha do local.
  delta_irregulares: number | null;
}

export interface AtualizacoesPainelData {
  contexto: Contexto;
  regularidade: Regularidade;
  protocolos: ProtocoloVariacao[]; // maior alta + maior queda (pode vir vazio)
  irregulares: MetricaVariacao | null; // null sem dados na referência
  regulares: MetricaVariacao | null; // regular + atenção (só linhas Ativo)
  foco: FocoIrregularidade | null;
}

/** Envelope da resposta (`GET /api/v2/dashboard/atualizacoes-regionais`). */

export interface MetaCard {
  tipo: "irregulares" | "regulares" | "foco";
  valor: number; // participantes (unidade dos cards de volume)
  relevancia: number; // 0..1 — informativa (valor / max); a ORDEM do array é o lineup
  fixo?: boolean; // true somente para foco (3º slot)
}

export interface AtualizacoesRegionaisResponse {
  can_view_atualizacoes: boolean; // gate (b) — §6
  meta: {
    semana_em_curso: string | null;
    semana_referencia: string | null;
    semana_comparacao: string | null; // W-(N+1) — base dos deltas
    semanas_comparacao: JanelaComparacao; // janela escolhida (echo do backend)
    tem_comparativo: boolean; // false ⇒ deltas/percentuais null e protocolos vazio;
    // cards de volume continuam válidos (§5.4)
    escopo_restrito: boolean; // true quando o usuário não vê a região inteira (RLS)
    /**
     * Lineup FIXO da linha 2 (decisão E), já em ordem (backend):
     * irregulares → regulares → foco (fixo: true).
     * O front consome a ordem — não reordena.
     */
    cards: MetaCard[];
  };
  data: AtualizacoesPainelData | null; // null quando sem permissão ou sem dados
}
