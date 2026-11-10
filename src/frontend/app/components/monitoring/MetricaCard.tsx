"use client";

/**
 * Mini-card de métrica com faixa lateral na cor da região/métrica.
 * ``trend`` adiciona a linha de variação — seta + delta colorido + rótulo.
 * Compartilhado entre o painel da região (MonitoramentoTab) e os cards do
 * Acompanhamento semanal (EvolucaoSemanal).
 */

import { memo } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";

export const MetricaCard = memo(function MetricaCard({
	rotulo,
	valor,
	detalhe,
	cor,
	trend,
}: {
	rotulo: string;
	valor: string;
	detalhe?: string;
	cor: string;
	trend?: {
		valor: string;
		positivo: boolean;
		label?: string;
		/** Direção da seta (default: cima quando positivo). Separada de
		 *  ``positivo`` porque "melhorou" nem sempre é "subiu" (ex.: queda
		 *  de irregularidade é boa, mas o número desceu). */
		direcao?: "up" | "down";
	};
}) {
	const direcao = trend?.direcao ?? (trend?.positivo ? "up" : "down");
	return (
		<div
			className="flex flex-col justify-center rounded-lg border bg-muted/40 p-3"
			style={{ borderLeft: `4px solid ${cor}` }}
		>
			<p className="text-xs font-medium text-muted-foreground">{rotulo}</p>
			<p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
				{valor}
			</p>
			{trend && (
				<p
					className={`mt-1 flex items-center gap-1 text-xs font-semibold ${
						trend.positivo ? "text-emerald-600" : "text-red-600"
					}`}
				>
					{direcao === "up" ? (
						<TrendingUp className="h-3.5 w-3.5 shrink-0" />
					) : (
						<TrendingDown className="h-3.5 w-3.5 shrink-0" />
					)}
					{trend.valor}
					{trend.label && (
						<span className="ml-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
							{trend.label}
						</span>
					)}
				</p>
			)}
			{detalhe && (
				<p className="mt-1 text-xs text-muted-foreground">{detalhe}</p>
			)}
		</div>
	);
});
