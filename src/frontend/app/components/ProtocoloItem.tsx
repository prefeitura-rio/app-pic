"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";
import {
	FONTE_TRADUTOR,
	MOTIVO_TRADUTOR,
} from "@/app/utils/irregularity-reasons-translator";
import type { ProtocoloListagemItem } from "../types";

const getProtocolBadgeVariant = (
	status?: string,
): "default" | "secondary" | "destructive" | "warning" => {
	if (!status) return "secondary";
	const lower = status.toLowerCase();
	if (lower === "irregular" || lower.includes("irregular"))
		return "destructive";
	if (lower === "regular") return "default";
	if (lower === "atencao" || lower.includes("atenção")) return "warning";
	if (
		lower === "n/a" ||
		lower === "nao_aplica" ||
		lower === "não aplicável" ||
		lower === "não se aplica"
	)
		return "secondary";
	return "secondary";
};

const formatProtocolStatus = (
	status?: string,
	protocolo_status_label?: string,
) => {
	const lower = status?.toLowerCase() || "";
	let icon = "";
	if (lower === "regular") icon = "✓ ";
	else if (lower === "atencao" || lower === "atenção") icon = "⚠ ";
	else if (lower === "irregular") icon = "✗ ";

	if (protocolo_status_label) {
		return `${icon}${protocolo_status_label}`;
	}

	if (lower === "regular") return "✓ Regular";
	if (lower === "atencao" || lower === "atenção") return "⚠ Atenção";
	if (lower === "irregular") return "✗ Irregular";
	if (lower === "nao_aplica" || lower === "n/a") return "N/A";
	return status || "N/A";
};

export const ProtocoloItem = ({
	protocolo,
}: {
	protocolo: ProtocoloListagemItem;
}) => {
	const [open, setOpen] = useState(false);
	const motivos = protocolo.protocolo_motivo;
	const hasMotivos =
		protocolo.irregular_indicador && motivos && motivos.motivos.length > 0;

	return (
		<div className="bg-muted/30 rounded">
			<div className="flex items-center justify-between gap-3 p-3">
				<span className="text-sm flex-1 min-w-0">
					{protocolo.descricao || "-"}
				</span>
				<div className="flex items-center gap-2 shrink-0">
					<Badge
						variant={getProtocolBadgeVariant(protocolo.status)}
						className="whitespace-nowrap"
					>
						{formatProtocolStatus(
							protocolo.status,
							protocolo.protocolo_status_label,
						)}
					</Badge>
					{hasMotivos && (
						<Button
							variant="ghost"
							size="sm"
							className="h-7 px-2 text-xs"
							onClick={() => setOpen(!open)}
						>
							{open ? "Ocultar" : "Ver Motivos"}
							<ChevronDown
								className={`h-3 w-3 ml-1 transition-transform ${open ? "rotate-180" : ""}`}
							/>
						</Button>
					)}
				</div>
			</div>
			{hasMotivos && open && (
				<div className="px-3 pb-3 border-t border-border/50">
					<div className="mt-2 space-y-1.5">
						{motivos.motivos.map((slug) => {
							const detalhe = motivos.detalhes[slug];
							return (
								<div key={slug} className="flex items-start gap-2 text-sm">
									<span className="text-muted-foreground mt-0.5">●</span>
									<div>
										<p className="text-foreground">
											{MOTIVO_TRADUTOR[slug] || slug}
										</p>
										{detalhe?.fonte && (
											<p className="text-xs text-muted-foreground">
												Fonte: {FONTE_TRADUTOR[detalhe.fonte] || detalhe.fonte}
												{detalhe.data_particao &&
													` (partição: ${detalhe.data_particao})`}
											</p>
										)}
									</div>
								</div>
							);
						})}
					</div>
				</div>
			)}
		</div>
	);
};
