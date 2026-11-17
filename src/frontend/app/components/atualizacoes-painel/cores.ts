/**
 * Cores dos gráficos do Painel de Atualizações — tokens do design (§8 da
 * doc), não a paleta do `monitoring/cores.ts` (unificação fica como tarefa
 * separada).
 */

import type { Tone } from "./types";

export const COR_SUCCESS = "#77C63F"; // success do design
export const COR_DESTRUCTIVE = "#EF4343"; // destructive do design
export const COR_ACCENT = "#FFCC00"; // accent do design
export const COR_BRAND = "#003366"; // navy institucional (card fixo)
export const COR_BRAND_MID = "#355D85"; // tom intermediário (donut no navy)
export const COR_TRILHA = "#DAE0E7"; // trilhas/faixas neutras do design

/** Cor semântica por tone — o front só renderiza, nunca deriva o tone. */
export const TONE_CORES: Record<Tone, string> = {
	success: COR_SUCCESS,
	danger: COR_DESTRUCTIVE,
};
