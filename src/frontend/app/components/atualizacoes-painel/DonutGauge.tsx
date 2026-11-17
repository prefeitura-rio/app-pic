"use client";

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

import { cn } from "@/app/utils/utils";

import { COR_ACCENT, COR_TRILHA } from "./cores";
import { formatarTaxa } from "./format";
import type { Tone } from "./types";

interface DonutGaugeProps {
	/** 0–100; null desenha o anel vazio. */
	taxa: number | null;
	tone: Tone;
	/** Cor do anel de fundo (o card navy usa `brand-mid`). */
	trilha?: string;
	tamanho?: number;
	className?: string;
}

/**
 * Donut de regularidade (recharts, sem interatividade) com o percentual
 * como rótulo central. `aria-label` resume o valor (§8 da doc).
 */
export function DonutGauge({
	taxa,
	tone,
	trilha = COR_TRILHA,
	tamanho = 112,
	className,
}: DonutGaugeProps) {
	const valor = taxa ?? 0;
	const dados = [
		{ nome: "regularidade", valor },
		{ nome: "restante", valor: Math.max(100 - valor, 0) },
	];
	return (
		<div
			className={cn("relative", className)}
			style={{ width: tamanho, height: tamanho }}
			role="img"
			aria-label={`Regularidade geral: ${formatarTaxa(taxa)}%`}
		>
			<ResponsiveContainer width="100%" height="100%">
				<PieChart>
					<Pie
						data={dados}
						dataKey="valor"
						nameKey="nome"
						startAngle={90}
						endAngle={-270}
						innerRadius="72%"
						outerRadius="96%"
						stroke="none"
						isAnimationActive={false}
					>
						<Cell fill={COR_ACCENT} />
						<Cell fill={trilha} />
					</Pie>
				</PieChart>
			</ResponsiveContainer>
		</div>
	);
}
