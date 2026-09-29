"use client";

import {
	CheckCircle2,
	Clock,
	Send,
	XCircle,
	AlertTriangle,
} from "lucide-react";
import { Badge } from "@/app/components/ui/badge";
import type { Disparo } from "@/app/types";

type BadgeVariant =
	| "default"
	| "secondary"
	| "destructive"
	| "outline"
	| "success"
	| "warning";

const STATUS_BADGE: Record<string, BadgeVariant> = {
	ENTREGUE: "success",
	RESPONDIDO: "success",
	LIDO: "success",
	ENVIADO: "secondary",
	SEM_RETORNO: "warning",
	FALHOU: "destructive",
};

const SECRETARIA_LABELS: Record<string, string> = {
	SMS: "Saúde (SMS)",
	SMAS: "Assistência (SMAS)",
	SME: "Educação (SME)",
	PGM: "PGM",
};

function statusVariant(status?: string | null): BadgeVariant {
	if (!status) return "secondary";
	return STATUS_BADGE[status] ?? "secondary";
}

function StatusIcon({ status }: { status?: string | null }) {
	switch (status) {
		case "ENTREGUE":
		case "RESPONDIDO":
		case "LIDO":
			return <CheckCircle2 className="h-3.5 w-3.5 mr-1" />;
		case "ENVIADO":
			return <Send className="h-3.5 w-3.5 mr-1" />;
		case "FALHOU":
			return <XCircle className="h-3.5 w-3.5 mr-1" />;
		case "SEM_RETORNO":
			return <Clock className="h-3.5 w-3.5 mr-1" />;
		default:
			return <AlertTriangle className="h-3.5 w-3.5 mr-1" />;
	}
}

function formatDatahora(
	datahora?: string | null,
	data?: string | null,
): string | null {
	if (datahora) {
		const parsed = new Date(datahora);
		if (!Number.isNaN(parsed.getTime())) {
			return parsed.toLocaleString("pt-BR", {
				day: "2-digit",
				month: "2-digit",
				year: "numeric",
				hour: "2-digit",
				minute: "2-digit",
			});
		}
	}
	if (data) {
		const parsed = new Date(`${data}T12:00:00`);
		if (!Number.isNaN(parsed.getTime())) {
			return parsed.toLocaleDateString("pt-BR");
		}
	}
	return null;
}

export function WhatsAppDisparosCard({ disparo }: { disparo: Disparo }) {
	const status = disparo.status;
	const datahora = formatDatahora(disparo.datahora, disparo.data);
	const secretariaLabel = disparo.secretaria
		? (SECRETARIA_LABELS[disparo.secretaria] ?? disparo.secretaria)
		: null;
	const metadados = disparo.metadados;

	return (
		<div className="bg-muted/30 rounded p-3 space-y-2">
			<div className="flex items-center justify-between gap-3">
				<span className="text-base font-medium flex-1 min-w-0">
					{disparo.campanha || "Campanha não identificada"}
				</span>
				<Badge
					variant={statusVariant(status)}
					className="whitespace-nowrap shrink-0"
				>
					<StatusIcon status={status} />
					{status || "Sem status"}
				</Badge>
			</div>
			{(secretariaLabel || datahora) && (
				<div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
					{secretariaLabel && <span>{secretariaLabel}</span>}
					<span className="whitespace-nowrap">{datahora ?? "-"}</span>
				</div>
			)}
			{metadados && (
				<div className="grid grid-cols-3 gap-2 text-center text-xs pt-2 border-t border-border/50">
					<div>
						<p className="text-lg font-bold text-foreground">
							{metadados.total_ultimos_30d ?? "-"}
						</p>
						<p className="text-muted-foreground">Total (30d)</p>
					</div>
					<div>
						<p className="text-lg font-bold text-green-600 dark:text-green-400">
							{metadados.entregues_30d ?? "-"}
						</p>
						<p className="text-muted-foreground">Entregues</p>
					</div>
					<div>
						<p className="text-lg font-bold text-destructive">
							{metadados.falhas_30d ?? "-"}
						</p>
						<p className="text-muted-foreground">Falhas</p>
					</div>
				</div>
			)}
		</div>
	);
}
