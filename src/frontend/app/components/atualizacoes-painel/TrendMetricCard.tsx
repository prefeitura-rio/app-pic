import { CardCorpo, CardFrame, CardRodape } from "./CardFrame";
import { DeltaBadge } from "./DeltaBadge";
import { diaCurto, formatarNumero, formatarVariacao } from "./format";
import { Sparkline } from "./Sparkline";
import type { JanelaComparacao, MetricaVariacao } from "./types";

const TITULOS = {
	irregulares: "Participantes irregulares",
	regulares: "Participantes regulares",
} as const;

interface TrendMetricCardProps {
	tipo: keyof typeof TITULOS;
	dados: MetricaVariacao;
	temComparativo: boolean;
	janelaComparacao: JanelaComparacao;
}

/**
 * Card de tendência — um componente, dois usos (irregulares e regulares;
 * padrão repetido do design, §3.6 da doc). Número grande + chip percentual
 * + frase de variação na janela escolhida + sparkline no rodapé de 101px.
 */
export function TrendMetricCard({
	tipo,
	dados,
	temComparativo,
	janelaComparacao,
}: TrendMetricCardProps) {
	const frase =
		temComparativo && dados.variacao_abs !== null
			? `${formatarVariacao(dados.variacao_abs, 0)} participantes ${janelaComparacao === 1 ? "vs. semana anterior" : `vs. ${janelaComparacao} semanas atrás`}`
			: null;
	const eixo =
		dados.serie.length > 0
			? {
					de: diaCurto(dados.serie[0].semana),
					ate: diaCurto(dados.serie[dados.serie.length - 1].semana),
				}
			: null;
	const ariaSparkline = `${TITULOS[tipo]}: ${formatarNumero(dados.total)}`;

	return (
		<CardFrame className="font-inter flex h-full flex-col gap-16 rounded-xl border shadow-sm text-foreground">
			<CardCorpo className="space-y-2">
				<div className="flex items-start justify-between gap-2">
					<h3 className="text-sm font-medium text-foreground">
						{TITULOS[tipo]}
					</h3>
					{temComparativo && dados.variacao_pct !== null && (
						<DeltaBadge
							valor={dados.variacao_pct}
							tone={dados.tone}
							unidade="%"
						/>
					)}
				</div>
				<div className="text-3xl font-bold">{formatarNumero(dados.total)}</div>
				{frase && <p className="text-xs text-muted-foreground">{frase}</p>}
			</CardCorpo>
			<CardRodape>
				<div className="h-15 w-full">
					<Sparkline
						serie={dados.serie}
						tone={dados.tone}
						ariaLabel={ariaSparkline}
					/>
				</div>
				{eixo && (
					<div className="flex h-3.25 items-center justify-between text-[11px] text-muted-foreground">
						<span>{eixo.de}</span>
						<span>{eixo.ate}</span>
					</div>
				)}
			</CardRodape>
		</CardFrame>
	);
}
