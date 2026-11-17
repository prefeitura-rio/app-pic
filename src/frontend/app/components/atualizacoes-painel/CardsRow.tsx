import { FocoIrregularidadeCard } from "./FocoIrregularidadeCard";
import { TrendMetricCard } from "./TrendMetricCard";
import type {
  AtualizacoesPainelData,
  JanelaComparacao,
  MetaCard,
} from "./types";

interface CardsRowProps {
  data: AtualizacoesPainelData;
  /** Lineup FIXO vindo do backend (§5.4 da doc) — consumir a ORDEM do array. */
  cards: MetaCard[];
  temComparativo: boolean;
  janelaComparacao: JanelaComparacao;
}

/**
 * Linha 2 (grid 3 colunas, items-stretch). Nenhuma regra de ranking no
 * cliente: o lineup é fixo do produto (irregulares → regulares → foco) e vem
 * na ordem do `meta.cards`; o fixo (foco) ocupa o 3º slot.
 */
export function CardsRow({
  data,
  cards,
  temComparativo,
  janelaComparacao,
}: CardsRowProps) {
  const naoFixos = cards.filter((card) => !card.fixo);
  const fixo = cards.find((card) => card.fixo);
  const linha = [...naoFixos, ...(fixo ? [fixo] : [])].slice(0, 3);

  if (linha.length === 0) {
    return null;
  }

  return (
    <div className="grid items-stretch gap-5 lg:grid-cols-3">
      {linha.map((card) => (
        <CardPorTipo
          key={card.tipo}
          card={card}
          data={data}
          temComparativo={temComparativo}
          janelaComparacao={janelaComparacao}
        />
      ))}
    </div>
  );
}

function CardPorTipo({
  card,
  data,
  temComparativo,
  janelaComparacao,
}: {
  card: MetaCard;
  data: AtualizacoesPainelData;
  temComparativo: boolean;
  janelaComparacao: JanelaComparacao;
}) {
  switch (card.tipo) {
    case "irregulares":
      return data.irregulares ? (
        <TrendMetricCard
          tipo="irregulares"
          dados={data.irregulares}
          temComparativo={temComparativo}
          janelaComparacao={janelaComparacao}
        />
      ) : null;
    case "regulares":
      return data.regulares ? (
        <TrendMetricCard
          tipo="regulares"
          dados={data.regulares}
          temComparativo={temComparativo}
          janelaComparacao={janelaComparacao}
        />
      ) : null;
    case "foco":
      return data.foco ? (
        <FocoIrregularidadeCard
          dados={data.foco}
          semanaReferencia={data.contexto.semana_referencia}
          janelaComparacao={janelaComparacao}
          temComparativo={temComparativo}
        />
      ) : null;
  }
}
