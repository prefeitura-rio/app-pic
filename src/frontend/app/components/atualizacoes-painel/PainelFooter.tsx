import { semanaFaixaLabel } from "./format";

interface PainelFooterProps {
  semanaComparacao: string | null;
  temComparativo: boolean;
  escopoRestrito: boolean;
}

/**
 * Bloco 7 (rodapé, §3.1/§10 da doc): nota derivada do `meta` — escopo
 * restrito ganha "dados do seu escopo de acesso"; sem comparativo, a frase
 * da semana anterior é omitida.
 */
export function PainelFooter({
  semanaComparacao,
  temComparativo,
  escopoRestrito,
}: PainelFooterProps) {
  const notas: string[] = [];
  if (escopoRestrito) {
    notas.push("dados do seu escopo de acesso");
  }
  if (temComparativo) {
    const faixa = semanaFaixaLabel(semanaComparacao);
    if (faixa) {
      notas.push(`Comparativos com a semana de ${faixa}`);
    }
  }
  if (notas.length === 0) {
    return null;
  }

  return (
    <footer className="flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground">
      <p>{notas.join(" • ")}</p>
      <p>p.p. = pontos percentuais</p>
    </footer>
  );
}
