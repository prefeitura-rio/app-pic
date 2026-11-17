/**
 * Formatadores pt-BR do Painel de Atualizações.
 *
 * Padrões: `toLocaleString("pt-BR")` para números; percentuais com vírgula
 * (mesmo padrão do `formatPercentual` do projeto); semana **domingo–sábado**
 * rotulada a partir de `semana_inicio + 6 dias` (B1 — o dado, não a copy
 * segunda–domingo do design).
 */

const numero = new Intl.NumberFormat("pt-BR");

const MESES_CURTOS = [
  "jan.",
  "fev.",
  "mar.",
  "abr.",
  "mai.",
  "jun.",
  "jul.",
  "ago.",
  "set.",
  "out.",
  "nov.",
  "dez.",
];

const dia = (d: Date): string => d.getDate().toString().padStart(2, "0");

/** 1234 → "1.234"; null/undefined → "—". */
export function formatarNumero(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : numero.format(valor);
}

/** 31.9 → "31,9"; null/undefined → "—". */
export function formatarTaxa(
  valor: number | null | undefined,
  casas: number = 1,
): string {
  if (valor === null || valor === undefined) {
    return "—";
  }
  return valor.toFixed(casas).replace(".", ",");
}

/**
 * Variação com sinal explícito: 2.4 → "+2,4"; -6.3 → "-6,3".
 * null/undefined → null (o chamador omite o trecho).
 */
export function formatarVariacao(
  valor: number | null | undefined,
  casas: number = 1,
): string | null {
  if (valor === null || valor === undefined) {
    return null;
  }
  const sinal = valor > 0 ? "+" : valor < 0 ? "-" : "";
  return `${sinal}${Math.abs(valor).toFixed(casas).replace(".", ",")}`;
}

/**
 * Magnitude sem sinal: -6.4 → "6,4" — para chips em que a direção já vem da
 * seta (DeltaBadge). null/undefined → null.
 */
export function formatarMagnitude(
  valor: number | null | undefined,
  casas: number = 1,
): string | null {
  if (valor === null || valor === undefined) {
    return null;
  }
  return formatarTaxa(Math.abs(valor), casas);
}

/**
 * "2026-11-08" (domingo) → "08–14 nov. 2026".
 * Virada de mês: "29 nov. – 05 dez. 2026".
 */
export function semanaFaixaLabel(
  weekStart: string | null | undefined,
): string | null {
  if (!weekStart) {
    return null;
  }
  const inicio = new Date(`${weekStart}T12:00:00`);
  const fim = new Date(inicio);
  fim.setDate(fim.getDate() + 6);
  const mesmoMes =
    inicio.getMonth() === fim.getMonth() &&
    inicio.getFullYear() === fim.getFullYear();
  if (mesmoMes) {
    return `${dia(inicio)}–${dia(fim)} ${MESES_CURTOS[fim.getMonth()]} ${fim.getFullYear()}`;
  }
  return `${dia(inicio)} ${MESES_CURTOS[inicio.getMonth()]} – ${dia(fim)} ${MESES_CURTOS[fim.getMonth()]} ${fim.getFullYear()}`;
}

/** "2026-11-01" → "01 nov." (eixos do sparkline). */
export function diaCurto(weekStart: string): string {
  const d = new Date(`${weekStart}T12:00:00`);
  return `${dia(d)} ${MESES_CURTOS[d.getMonth()]}`;
}
