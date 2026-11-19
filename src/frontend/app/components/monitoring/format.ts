"use client";

/**
 * Formatadores pt-BR compartilhados do Acompanhamento semanal.
 *
 * Extraídos de ``ProtocolSeriesChart`` para as tabelas/gráficos importarem
 * de um lugar neutro (um gráfico não deve exportar formatação).
 * ``Intl.*Format`` são criados uma vez — mais rápido que recriar o
 * ``toLocaleDateString`` a cada rótulo.
 */

const numero = new Intl.NumberFormat("pt-BR");

const dataCurta = new Intl.DateTimeFormat("pt-BR", {
	day: "2-digit",
	month: "2-digit",
	year: "2-digit",
});

const dataCompleta = new Intl.DateTimeFormat("pt-BR", {
	day: "2-digit",
	month: "2-digit",
	year: "numeric",
});

/** 1234 → "1.234"; null/undefined → "—". */
export function formatarNumero(valor: number | null | undefined): string {
	return valor === null || valor === undefined ? "—" : numero.format(valor);
}

/** Percentual com precisão dinâmica: 2 casas quando 0 < v < 0,1; senão 1. */
export function formatarTaxa(valor: number | null | undefined): string {
	if (valor === null || valor === undefined) {
		return "—";
	}
	const casas = valor > 0 && valor < 0.1 ? 2 : 1;
	return `${valor.toFixed(casas).replace(".", ",")}%`;
}

/** Percentual com número fixo de casas (eixos ampliados). */
export function formatarTaxaCom(
	valor: number | null | undefined,
	casas: number,
): string {
	if (valor === null || valor === undefined) {
		return "—";
	}
	return `${valor.toFixed(casas).replace(".", ",")}%`;
}

/** "2026-07-19" → "19/07/26" */
export function semanaLabel(weekStart: string): string {
	return dataCurta.format(new Date(`${weekStart}T12:00:00`));
}

/** "2026-07-25" → "25/07/2026" */
export function snapshotLabel(snapshot: string): string {
	return dataCompleta.format(new Date(`${snapshot}T12:00:00`));
}
