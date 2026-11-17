import { Badge } from "@/app/components/ui/badge";

import { CardCorpo, CardFrame, CardRodape } from "./CardFrame";
import { COR_DESTRUCTIVE } from "./cores";
import {
	formatarNumero,
	formatarTaxa,
	formatarVariacao,
	semanaFaixaLabel,
} from "./format";
import type { FocoIrregularidade, JanelaComparacao } from "./types";

interface FocoIrregularidadeCardProps {
	dados: FocoIrregularidade;
	semanaReferencia: string | null;
	janelaComparacao: JanelaComparacao;
	temComparativo: boolean;
}

/**
 * Card de foco geográfico — o nível (RA × bairro) vem do ACESSO do usuário
 * (§5.3, regra 6 da doc); o rótulo do local é o valor cru da tabela (Q6).
 * A ESCOLHA do local é pelo estoque de W−1 (maior concentração); o delta
 * exibido ("+40 vs. 4 semanas atrás") acompanha a janela do seletor e a
 * semana é explicitada no subtítulo para o card não parecer travado.
 * Barra de participação em div CSS, ancorada na base do rodapé.
 */
export function FocoIrregularidadeCard({
	dados,
	semanaReferencia,
	janelaComparacao,
	temComparativo,
}: FocoIrregularidadeCardProps) {
	const pct = Math.min(dados.participacao_pct ?? 0, 100);
	const base =
		dados.nivel === "ra"
			? "Região administrativa com mais irregulares"
			: "Bairro com mais irregulares";
	const semana = semanaFaixaLabel(semanaReferencia);
	const subtitulo = semana ? `${base} · semana de ${semana}` : base;
	const delta =
		temComparativo && dados.delta_irregulares !== null
			? `${formatarVariacao(dados.delta_irregulares, 0)} irregulares ${
					janelaComparacao === 1
						? "vs. semana anterior"
						: `vs. ${janelaComparacao} semanas atrás`
				}`
			: null;
	const legendaDemais = dados.nivel === "ra" ? "Demais RAs" : "Demais bairros";
	const ariaBarra = `${dados.local}: ${formatarNumero(dados.irregulares)} participantes irregulares de ${formatarNumero(dados.irregulares + dados.demais)}`;

	return (
		<CardFrame>
			<CardCorpo className="font-inter space-y-3">
				<div className="flex items-start justify-between gap-2">
					<h3 className="text-sm font-medium text-foreground">
						Foco de irregularidade
					</h3>
					<Badge variant="warning">PRIORIDADE</Badge>
				</div>
				<div className="text-xl font-bold leading-tight">{dados.local}</div>
				<p className="text-xs text-muted-foreground">{subtitulo}</p>
				<div className="flex items-baseline gap-2">
					<span className="text-3xl font-bold">
						{formatarNumero(dados.irregulares)}
					</span>
					<span className="text-sm text-muted-foreground">
						participantes irregulares
					</span>
				</div>
				{delta && <p className="text-xs text-muted-foreground">{delta}</p>}
				<p className="text-xs text-muted-foreground">
					<span className="font-semibold text-foreground">
						{formatarTaxa(dados.participacao_pct)}%
					</span>{" "}
					do total regional
				</p>
			</CardCorpo>
			<CardRodape>
				<div
					className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
					role="img"
					aria-label={ariaBarra}
				>
					<div
						className="h-full rounded-full"
						style={{ width: `${pct}%`, backgroundColor: COR_DESTRUCTIVE }}
					/>
				</div>
				<div className="flex h-3.25 items-center justify-between gap-2 text-[11px] text-muted-foreground">
					<span className="truncate">{dados.local}</span>
					<span className="whitespace-nowrap">
						{legendaDemais} · {formatarNumero(dados.demais)}
					</span>
				</div>
			</CardRodape>
		</CardFrame>
	);
}
