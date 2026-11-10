"use client";

/**
 * Tabela semanal do protocolo (Acompanhamento) — uma linha por avaliação,
 * em ordem cronológica (da mais antiga para a mais recente). Variação
 * sempre vs a semana anterior DISPONÍVEL (mesmo que fique fora do período
 * selecionado). Nas colunas de %, a variação é em pontos percentuais (p.p.).
 *
 * As colunas de ativos NÃO incluem inativos; o % Regular do topo e do
 * gráfico de regularidade inclui inativos com status regular no protocolo.
 *
 * As métricas (valores + variações) e o cabeçalho do CSV ficam em
 * ``semana.ts``, compartilhados com o export no cabeçalho da seção.
 */

import { memo, useMemo } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { MonitoringProtocolPoint } from "@/app/types";
import {
	formatarNumero,
	formatarTaxa,
	semanaLabel,
	snapshotLabel,
} from "./format";
import { linhasDoPeriodo, metricas } from "./semana";

/** Δ colorido. ``positivoBom`` decide se subir é verde; ``neutro`` tira a cor. */
function Delta({
	valor,
	positivoBom,
	casas = 0,
	sufixo = "",
	neutro = false,
}: {
	valor: number | null;
	positivoBom: boolean;
	casas?: number;
	sufixo?: string;
	neutro?: boolean;
}) {
	if (valor === null || valor === 0) {
		return null;
	}
	const subiu = valor > 0;
	const cor = neutro
		? "text-muted-foreground"
		: subiu === positivoBom
			? "text-emerald-600"
			: "text-red-500";
	const texto = `${subiu ? "+" : ""}${valor.toLocaleString("pt-BR", {
		minimumFractionDigits: casas,
		maximumFractionDigits: casas,
	})}${sufixo}`;
	return (
		<span
			className={`ml-1 inline-flex items-center gap-0.5 text-[10px] font-medium tabular-nums ${cor}`}
		>
			{subiu ? (
				<ArrowUpRight className="h-3 w-3" />
			) : (
				<ArrowDownRight className="h-3 w-3" />
			)}
			{texto}
		</span>
	);
}

interface WeeklyTableProps {
	/** Série completa da janela estável (para achar a semana anterior). */
	serieCompleta: MonitoringProtocolPoint[];
	/** Período selecionado (ISO de início/fim de semana). */
	de: string;
	ate: string;
	/** "geral" ajusta a nota metodológica para a regularidade geral. */
	modo?: "protocolo" | "geral";
}

export const WeeklyTable = memo(function WeeklyTable({
	serieCompleta,
	de,
	ate,
	modo = "protocolo",
}: WeeklyTableProps) {
	const linhas = useMemo(
		() => linhasDoPeriodo(serieCompleta, de, ate),
		[serieCompleta, de, ate],
	);

	return (
		<div className="space-y-3">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<h3 className="text-sm font-semibold text-foreground">
					Tabela semanal
				</h3>
				<p className="text-xs text-muted-foreground">
					mais antiga primeiro
				</p>
			</div>
			{linhas.length === 0 ? (
				<p className="py-4 text-sm text-muted-foreground">
					Sem dados para o período selecionado.
				</p>
			) : (
				<div className="overflow-x-auto rounded-lg border">
					<table className="w-full text-sm">
						<thead>
							<tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
								<th className="px-3 py-2 font-medium">Avaliação</th>
								<th className="px-3 py-2 text-right font-medium">
									Total
								</th>
								<th className="px-3 py-2 text-right font-medium">
									Ativos regulares
								</th>
								<th className="px-3 py-2 text-right font-medium">
									% ativos regulares
								</th>
								<th className="px-3 py-2 text-right font-medium">
									Ativos irregulares
								</th>
								<th className="px-3 py-2 text-right font-medium">
									% ativos irregulares
								</th>
								<th className="px-3 py-2 text-right font-medium">
									Inativos
								</th>
							</tr>
						</thead>
						<tbody>
							{linhas.map(({ p, prev }) => {
								const m = metricas(p, prev);
								return (
									<tr
										key={p.week_start}
										className="border-b last:border-b-0"
									>
										<td className="whitespace-nowrap px-3 py-2">
											<p className="tabular-nums">
												{p.snapshot_date
													? snapshotLabel(p.snapshot_date)
													: semanaLabel(p.week_start)}
											</p>
											<p className="text-xs text-muted-foreground">
												semana de {semanaLabel(p.week_start)}
											</p>
										</td>
										<td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
											{formatarNumero(p.total)}
											<Delta
												valor={m.dTotal}
												positivoBom
												neutro
											/>
										</td>
										<td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
											{formatarNumero(m.ar)}
											<Delta valor={m.dAR} positivoBom />
										</td>
										<td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
											{formatarTaxa(m.pctAR)}
											<Delta
												valor={m.dPctAR}
												positivoBom
												casas={
													m.dPctAR !== null &&
													Math.abs(m.dPctAR) < 0.1
														? 2
														: 1
												}
												sufixo=" p.p."
											/>
										</td>
										<td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
											{formatarNumero(m.ai)}
											<Delta
												valor={m.dAI}
												positivoBom={false}
											/>
										</td>
										<td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
											{formatarTaxa(m.pctAI)}
											<Delta
												valor={m.dPctAI}
												positivoBom={false}
												casas={
													m.dPctAI !== null &&
													Math.abs(m.dPctAI) < 0.1
														? 2
														: 1
												}
												sufixo=" p.p."
											/>
										</td>
										<td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
											{formatarNumero(m.inat)}
											<Delta
												valor={m.dInat}
												positivoBom={false}
											/>
										</td>
									</tr>
								);
							})}
						</tbody>
					</table>
				</div>
			)}
			<p className="text-xs leading-relaxed text-muted-foreground">
				{modo === "geral"
					? "Regularidade geral: participante regular em todos os protocolos aplicáveis. Ativos regulares/irregulares não incluem inativos; % sobre o total de participantes. O % Regular do topo e do gráfico de regularidade inclui inativos com regularidade geral. Δ em pontos percentuais (p.p.) nas colunas de %."
					: "Ativos regulares/irregulares não incluem inativos; % sobre o total aplicável. O % Regular do topo e do gráfico de regularidade inclui inativos com status regular no protocolo. Δ em pontos percentuais (p.p.) nas colunas de %."}
			</p>
		</div>
	);
});
