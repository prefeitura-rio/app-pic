"use client";

import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";

import { TONE_CORES } from "./cores";
import type { SeriePonto, Tone } from "./types";

interface SparklineProps {
	/** min(N+1, 4) pontos — últimas semanas válidas (anômalas puladas; pode ter menos — lacunas). */
	serie: SeriePonto[];
	tone: Tone;
	ariaLabel: string;
}

/**
 * Sparkline sem eixos (recharts), preenchendo o slot de 60px do rodapé
 * padronizado (decisão B, §3.5 da doc). Linha suavizada só como leitura de
 * tendência — os pontos são as apurações semanais.
 *
 * Domínio Y **justo** (min/max da série + folga), nunca `[0, 'auto']`: os
 * totais são grandes (~3,7 mil) e a variação real (~100–200) ficaria
 * esmagada no topo do gráfico — a linha pareceria reta.
 */
export function Sparkline({ serie, tone, ariaLabel }: SparklineProps) {
	const gradienteId = useId();
	const cor = TONE_CORES[tone];
	const pontos = serie.map((p) => ({ semana: p.semana, valor: p.valor }));

	if (pontos.length === 0) {
		return null;
	}

	const valores = pontos.map((p) => p.valor);
	const minimo = Math.min(...valores);
	const maximo = Math.max(...valores);
	const faixa = maximo - minimo;
	// Série plana (faixa 0) → folga mínima para o domínio não colapsar.
	const folga = faixa > 0 ? faixa * 0.35 : Math.max(1, Math.abs(maximo) * 0.02);
	const dom: [number, number] = [minimo - folga, maximo + folga];

	return (
		<div className="h-full w-full" role="img" aria-label={ariaLabel}>
			<ResponsiveContainer width="100%" height="100%">
				<AreaChart
					data={pontos}
					margin={{ top: 4, right: 2, bottom: 2, left: 2 }}
				>
					<defs>
						<linearGradient id={gradienteId} x1="0" y1="0" x2="0" y2="1">
							<stop offset="0%" stopColor={cor} stopOpacity={0.35} />
							<stop offset="100%" stopColor={cor} stopOpacity={0} />
						</linearGradient>
					</defs>
					<YAxis hide domain={dom} />
					<Area
						type="monotone"
						dataKey="valor"
						stroke={cor}
						strokeWidth={2.5}
						fill={`url(#${gradienteId})`}
						// Base explícita no FUNDO do domínio: o `'auto'` do recharts
						// vira `max(domínioMin, 0)` — com domínio positivo o 0 fica
						// ~590px abaixo do slot, o path da área sai do quadro e o
						// gradiente é mapeado sobre uma caixa de ~650px (a área
						// "some"). Ancorado aqui, o gradiente cobre os ~54px úteis.
						baseValue={dom[0]}
						dot={false}
						isAnimationActive={false}
					/>
				</AreaChart>
			</ResponsiveContainer>
		</div>
	);
}
