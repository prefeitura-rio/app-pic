"use client";

import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/app/components/ui/collapsible";
import type { BuscaAtivaEvento } from "@/app/types";
import { buscaAtivaTitulo, FONTE_LABELS, formatBuscaAtivaData } from "./utils";

/**
 * Linha do tempo da busca ativa, do evento mais recente (topo, logo abaixo
 * do nó "Hoje") ao mais antigo. O resumo de cada nó segue a ordem data →
 * secretaria (sigla) → título; todos os nós são colapsáveis ("Ver mais"/
 * "Ver menos"). A bolinha fica ancorada à primeira linha (não se move ao
 * expandir) e o conector é contínuo de bolinha a bolinha, centralizado na
 * coluna das bolinhas.
 */

function BuscaAtivaDetalhes({ evento }: { evento: BuscaAtivaEvento }) {
	const protocolos = (evento.smas_protocolo_violado ?? []).filter(Boolean);
	const motivos = (evento.smas_motivo_nao_localizada ?? []).filter(Boolean);
	const localizada = evento.smas_familia_localizada_indicador;

	const unidadeSms = evento.unidade_referenciada?.sms;
	const unidadeSmas = evento.unidade_referenciada?.smas;

	return (
		<div className="pt-2 pl-3 pb-1 space-y-2">
			{evento.fonte === "SMS" && unidadeSms && (
				<div className="text-sm space-y-1">
					{unidadeSms.nome && (
						<p>
							<span className="text-muted-foreground">
								Clínica da família:{" "}
							</span>
							{unidadeSms.nome}
						</p>
					)}
					{unidadeSms.equipe_nome && (
						<p>
							<span className="text-muted-foreground">Equipe: </span>
							{unidadeSms.equipe_nome}
						</p>
					)}
					{unidadeSms.regional && (
						<p>
							<span className="text-muted-foreground">Regional: </span>
							{unidadeSms.regional}
						</p>
					)}
				</div>
			)}

			{evento.fonte === "SMAS" && (
				<>
					{unidadeSmas && (
						<div className="text-sm space-y-1">
							{unidadeSmas.nome && (
								<p>
									<span className="text-muted-foreground">Equipamento: </span>
									{unidadeSmas.nome}
								</p>
							)}
							{unidadeSmas.regional && (
								<p>
									<span className="text-muted-foreground">Regional: </span>
									{unidadeSmas.regional}
								</p>
							)}
						</div>
					)}
					{localizada === true && (
						<Badge
							variant="success"
							className="text-xs bg-green-700 hover:bg-green-700/80"
						>
							<CheckCircle2 className="h-3.5 w-3.5 mr-1" />
							Família localizada
						</Badge>
					)}
					{localizada === false && (
						<Badge variant="destructive" className="text-xs">
							<XCircle className="h-3.5 w-3.5 mr-1" />
							Família não localizada
						</Badge>
					)}
					{protocolos.length > 0 && (
						<div>
							<p className="text-xs text-muted-foreground mb-1">
								Protocolos vinculados à busca ativa
							</p>
							<ul className="space-y-1">
								{protocolos.map((protocolo) => (
									<li
										key={protocolo}
										className="text-sm flex items-start gap-2"
									>
										<AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
										{protocolo}
									</li>
								))}
							</ul>
						</div>
					)}
					{localizada === false && motivos.length > 0 && (
						<div>
							<p className="text-xs text-muted-foreground mb-1">
								Motivo da não localização
							</p>
							<ul className="space-y-1">
								{motivos.map((motivo) => (
									<li key={motivo} className="text-sm flex items-start gap-2">
										<XCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
										{motivo}
									</li>
								))}
							</ul>
						</div>
					)}
				</>
			)}
		</div>
	);
}

function BuscaAtivaTimelineNode({ evento }: { evento: BuscaAtivaEvento }) {
	const [open, setOpen] = useState(false);
	const dataLabel = formatBuscaAtivaData(evento.data);
	const fonteLabel = evento.fonte
		? (FONTE_LABELS[evento.fonte] ?? evento.fonte)
		: "Busca ativa";

	const resumo = (
		<div className="flex items-center gap-2 flex-wrap text-left">
			{dataLabel && (
				<span className="text-xs text-muted-foreground whitespace-nowrap tabular-nums">
					{dataLabel}
				</span>
			)}
			<Badge
				variant={evento.fonte === "SMAS" ? "warning" : "secondary"}
				className="text-xs"
			>
				{fonteLabel}
			</Badge>
			<span className="text-sm font-medium">{buscaAtivaTitulo(evento)}</span>
		</div>
	);

	return (
		<div className="min-w-0 flex-1">
			<Collapsible open={open} onOpenChange={setOpen} className="w-full">
				<CollapsibleTrigger asChild>
					<Button
						variant="ghost"
						className="w-full h-auto justify-start px-2 py-1 rounded-md hover:bg-muted/60"
					>
						{resumo}
						<span className="ml-auto shrink-0 text-xs font-medium text-primary/80">
							{open ? "Ver menos" : "Ver mais"}
						</span>
					</Button>
				</CollapsibleTrigger>
				<CollapsibleContent>
					<BuscaAtivaDetalhes evento={evento} />
				</CollapsibleContent>
			</Collapsible>
		</div>
	);
}

export function BuscaAtivaTimeline({
	eventos,
}: {
	eventos: BuscaAtivaEvento[];
}) {
	return (
		<ol className="relative space-y-4">
			{/* Âncora do presente: nó "Hoje" no topo (ponto oco). */}
			<li className="relative">
				<span
					aria-hidden
					className="absolute left-[5.5px] top-5 -bottom-6 w-px bg-border/60"
				/>
				<div className="flex items-start gap-3">
					<span className="mt-2 h-3 w-3 shrink-0 rounded-full border-2 border-primary bg-background" />
					<span className="px-2 py-1 text-sm font-medium text-muted-foreground">
						Hoje
					</span>
				</div>
			</li>

			{eventos.map((evento, idx) => {
				const isLast = idx === eventos.length - 1;
				return (
					<li
						key={`${evento.id_busca_ativa ?? "evento"}-${idx}`}
						className="relative"
					>
						{!isLast && (
							<span
								aria-hidden
								className="absolute left-[5.5px] top-5 -bottom-6 w-px bg-border/60"
							/>
						)}
						<div className="flex items-start gap-3">
							<span
								className={`mt-2 h-3 w-3 shrink-0 rounded-full border-2 border-background ${
									evento.fonte === "SMAS" ? "bg-amber-500" : "bg-primary"
								}`}
							/>
							<BuscaAtivaTimelineNode evento={evento} />
						</div>
					</li>
				);
			})}
		</ol>
	);
}
