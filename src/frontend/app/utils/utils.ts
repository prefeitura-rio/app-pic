import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formata uma data "YYYY-MM-DD" (date-only, sem fuso) como "DD/MM/YYYY".
 *
 * Não usa `new Date(...)`: strings date-only são parseadas como meia-noite
 * UTC e, em fusos negativos (America/Sao_Paulo), a exibição local desloca o
 * dia para trás (ex.: "2022-10-08" vira "07/10/2022").
 */
export function formatDateOnly(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value
}

/**
 * Converte uma data "YYYY-MM-DD" (date-only) em `Date` à meia-noite LOCAL.
 *
 * Contraparte de `formatDateOnly` para aritmética de datas (ex.: cálculo de
 * idade), evitando o deslocamento de -3h do parse UTC.
 */
export function parseDateOnlyLocal(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return null
  const [, ano, mes, dia] = match
  return new Date(Number(ano), Number(mes) - 1, Number(dia))
}