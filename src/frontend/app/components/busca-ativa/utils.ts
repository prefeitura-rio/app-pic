import type { BuscaAtivaEvento } from "@/app/types";

/** Siglas das secretarias de origem do evento (SMS/SMAS). */
export const FONTE_LABELS: Record<string, string> = {
	SMS: "SMS",
	SMAS: "SMAS",
};

/** Data ISO (YYYY-MM-DD) em pt-BR (dd/mm/aaaa). */
export function formatBuscaAtivaData(data?: string | null): string | null {
	if (!data) return null;
	const parsed = new Date(`${data}T12:00:00`);
	if (Number.isNaN(parsed.getTime())) return null;
	return parsed.toLocaleDateString("pt-BR");
}

/** Nome da visita usado como título no card/timeline. */
export function buscaAtivaTitulo(evento: BuscaAtivaEvento): string {
	if (evento.fonte === "SMAS") {
		const tipos = (evento.smas_tipo ?? [])
			.map((tipo) => tipo.trim().toLowerCase())
			.filter(Boolean);
		if (tipos.some((tipo) => tipo.includes("telefone"))) {
			return "Busca Ativa por Telefone";
		}
		if (tipos.some((tipo) => tipo.includes("domic"))) {
			return "Busca Ativa em Domicílio";
		}
		return "Busca ativa SMAS";
	}
	return "Busca ativa";
}
