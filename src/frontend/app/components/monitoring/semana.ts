import type { MonitoringProtocolPoint } from "@/app/types";

/**
 * Métricas da tabela semanal (valores + variações) e o cabeçalho do CSV —
 * compartilhados entre a tabela (`WeeklyTable`) e o export no cabeçalho da
 * seção (`EvolucaoSemanal`), para a tela e o CSV nunca divergirem.
 */

export const ativoReg = (p: MonitoringProtocolPoint) =>
	p.by_status["Ativo"]?.regular_total ?? 0;
export const ativoIrr = (p: MonitoringProtocolPoint) =>
	p.by_status["Ativo"]?.irregular ?? 0;
export const inativos = (p: MonitoringProtocolPoint) =>
	p.by_status["Inativo"]?.total ?? 0;
export const pctDe = (numerador: number, denominador: number) =>
	denominador > 0 ? (numerador / denominador) * 100 : null;

export interface LinhaSemana {
	p: MonitoringProtocolPoint;
	prev: MonitoringProtocolPoint | null;
}

/** Linhas do período selecionado, cada uma com a semana anterior disponível. */
export function linhasDoPeriodo(
	serieCompleta: MonitoringProtocolPoint[],
	de: string,
	ate: string,
): LinhaSemana[] {
	const anteriores = new Map<string, MonitoringProtocolPoint>();
	for (let i = 1; i < serieCompleta.length; i++) {
		anteriores.set(serieCompleta[i].week_start, serieCompleta[i - 1]);
	}
	return serieCompleta
		.filter((p) => p.week_start >= de && p.week_start <= ate)
		.map((p) => ({ p, prev: anteriores.get(p.week_start) ?? null }));
}

/** Valores + variações vs a semana anterior disponível. */
export interface MetricasLinha {
	ar: number;
	ai: number;
	inat: number;
	pctAR: number | null;
	pctAI: number | null;
	dTotal: number | null;
	dAR: number | null;
	dAI: number | null;
	dInat: number | null;
	dPctAR: number | null;
	dPctAI: number | null;
}

export function metricas(
	p: MonitoringProtocolPoint,
	prev: MonitoringProtocolPoint | null,
): MetricasLinha {
	const ar = ativoReg(p);
	const ai = ativoIrr(p);
	const inat = inativos(p);
	const pctAR = pctDe(ar, p.total);
	const pctAI = pctDe(ai, p.total);
	return {
		ar,
		ai,
		inat,
		pctAR,
		pctAI,
		dTotal: prev ? p.total - prev.total : null,
		dAR: prev ? ar - ativoReg(prev) : null,
		dAI: prev ? ai - ativoIrr(prev) : null,
		dInat: prev ? inat - inativos(prev) : null,
		dPctAR:
			prev !== null && pctAR !== null
				? pctAR - (pctDe(ativoReg(prev), prev.total) ?? 0)
				: null,
		dPctAI:
			prev !== null && pctAI !== null
				? pctAI - (pctDe(ativoIrr(prev), prev.total) ?? 0)
				: null,
	};
}

/** Duas casas decimais (percentuais/p.p. do CSV). */
export function num2(valor: number | null): number | null {
	return valor === null ? null : Math.round(valor * 100) / 100;
}

/** Cabeçalho do CSV: as variações são colunas próprias. */
export const CABECALHO_CSV = [
	"Avaliação",
	"Semana de início",
	"Total",
	"Variação total",
	"Ativos regulares",
	"Variação ativos regulares",
	"% ativos regulares",
	"Variação % ativos regulares (p.p.)",
	"Ativos irregulares",
	"Variação ativos irregulares",
	"% ativos irregulares",
	"Variação % ativos irregulares (p.p.)",
	"Inativos",
	"Variação inativos",
];
