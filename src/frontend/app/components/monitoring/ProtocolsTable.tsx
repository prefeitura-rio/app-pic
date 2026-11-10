"use client";

/**
 * Tabela de todos os protocolos na semana selecionada (Fase 4) — a "visão
 * geral" possível na v1. Uma linha por protocolo (NUNCA somar entre eles);
 * clique na linha seleciona o protocolo para o gráfico da série.
 */

import { memo, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowUpDown, Loader2 } from "lucide-react";
import { apiService } from "@/app/services/api";
import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";
import { Skeleton } from "@/app/components/ui/skeleton";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import type {
	CamadaTerritorial,
	MonitoringProtocolSummary,
} from "@/app/types";
import {
	formatarNumero,
	formatarTaxa,
	semanaLabel,
} from "./format";

interface ProtocolsTableProps {
	statuses: string[];
	cohortes: string[];
	grupos: string[];
	hasBolsaFamilia: boolean | undefined;
	camada: CamadaTerritorial;
	regiao: string | null;
	bypassCache: boolean;
	/** Semanas disponíveis (meta do grupo), da mais antiga para a mais nova. */
	availableWeeks: string[];
	latestWeek: string | null;
	latestIsPartial: boolean;
	/** Total do grupo (âncora) por semana — para a coluna de cobertura. */
	grupoTotalPorSemana: Map<string, number>;
	onSelectProtocolo: (id: string) => void;
}

type CampoOrdenacao = "protocolo" | "regular_pct" | "cobertura";

function cobertura(
	p: MonitoringProtocolSummary,
	grupoTotal: number | undefined,
): number | null {
	if (grupoTotal === undefined || grupoTotal <= 0) {
		return null;
	}
	return (p.total / grupoTotal) * 100;
}

export const ProtocolsTable = memo(function ProtocolsTable({
	statuses,
	cohortes,
	grupos,
	hasBolsaFamilia,
	camada,
	regiao,
	bypassCache,
	availableWeeks,
	latestWeek,
	latestIsPartial,
	grupoTotalPorSemana,
	onSelectProtocolo,
}: ProtocolsTableProps) {
	// null = "última semana". Evita prender a tabela numa semana antiga
	// quando uma nova entra (o estado inicial capturava latestWeek).
	const [semana, setSemana] = useState<string | null>(null);
	const [ordenacao, setOrdenacao] = useState<{
		campo: CampoOrdenacao;
		dir: 1 | -1;
	}>({ campo: "protocolo", dir: 1 });

	// Semana escolhida pelo usuário, ou a última se nenhuma (ou se a
	// escolhida saiu da janela estável).
	const semanaEfetiva = useMemo(() => {
		if (semana && availableWeeks.includes(semana)) {
			return semana;
		}
		return latestWeek;
	}, [semana, availableWeeks, latestWeek]);

	const { data, isFetching, isError, refetch } =
		useQuery({
			queryKey: [
				"monitoringProtocols",
				camada,
				regiao,
				statuses,
				cohortes,
				grupos,
				hasBolsaFamilia,
				semanaEfetiva,
				bypassCache,
			],
			queryFn: ({ signal }) =>
				apiService.getMonitoringProtocols(
					{
						statuses: statuses.length > 0 ? statuses : undefined,
						cohortes: cohortes.length > 0 ? cohortes : undefined,
						grupo: grupos.length > 0 ? grupos : undefined,
						hasBolsaFamilia,
						camada,
						regiao: regiao ?? undefined,
						weekStart: semanaEfetiva ?? undefined,
					},
					bypassCache,
					signal,
				),
			enabled: semanaEfetiva !== null,
			staleTime: 5 * 60 * 1000,
			placeholderData: keepPreviousData,
			refetchOnWindowFocus: false,
		});

	const semanaOpcoes: { id: string; label: string }[] = useMemo(
		() =>
			[...availableWeeks].reverse().map((w) => ({
				id: w,
				label: semanaLabel(w),
			})),
		[availableWeeks],
	);

	const linhas = useMemo(() => {
		const protocolos = [...(data?.protocols ?? [])];
		const grupoTotal = semanaEfetiva
			? grupoTotalPorSemana.get(semanaEfetiva)
			: undefined;
		protocolos.sort((a, b) => {
			let cmp = 0;
			if (ordenacao.campo === "protocolo") {
				cmp = `${a.protocolo_secretaria ?? ""} ${a.protocolo_descricao ?? a.protocolo_id}`.localeCompare(
					`${b.protocolo_secretaria ?? ""} ${b.protocolo_descricao ?? b.protocolo_id}`,
					"pt-BR",
				);
			} else if (ordenacao.campo === "regular_pct") {
				cmp = (a.regular_pct ?? -1) - (b.regular_pct ?? -1);
			} else {
				const ca = cobertura(a, grupoTotal) ?? -1;
				const cb = cobertura(b, grupoTotal) ?? -1;
				cmp = ca - cb;
			}
			return cmp * ordenacao.dir;
		});
		return protocolos.map((p) => ({
			...p,
			cob: cobertura(p, grupoTotal),
		}));
	}, [data, ordenacao, grupoTotalPorSemana, semanaEfetiva]);

	const toggleOrdenacao = (campo: CampoOrdenacao) => {
		setOrdenacao((atual) =>
			atual.campo === campo
				? { campo, dir: atual.dir === 1 ? -1 : 1 }
				: { campo, dir: 1 },
		);
	};

	const cabecalhoOrdenavel = (
		rotulo: string,
		campo: CampoOrdenacao,
		alinhamento: "left" | "right" = "right",
	) => (
		<th
			className={`px-3 py-2 font-medium ${alinhamento === "right" ? "text-right" : ""}`}
		>
			<button
				type="button"
				onClick={() => toggleOrdenacao(campo)}
				className={`inline-flex items-center gap-1 hover:text-foreground ${
					ordenacao.campo === campo ? "text-foreground" : ""
				}`}
				aria-label={`Ordenar por ${rotulo}`}
			>
				{rotulo}
				<ArrowUpDown className="h-3 w-3" />
			</button>
		</th>
	);

	return (
		<div className="space-y-3">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<div className="flex items-center gap-2">
					<h3 className="text-sm font-semibold text-foreground">
						Todos os protocolos
					</h3>
					{semanaEfetiva === latestWeek && latestIsPartial ? (
						<Badge variant="secondary" className="text-xs">
							Semana em curso
						</Badge>
					) : null}
				</div>
				<div className="w-44">
					<VirtualizedSelect
						value={semanaEfetiva ?? ""}
						onSelect={(v) => setSemana(v || null)}
						disabled={isFetching || availableWeeks.length === 0}
						placeholder="Semana"
						defaultLabel="Última semana"
						options={semanaOpcoes}
						showAllOption={false}
					/>
				</div>
			</div>

			{isError ? (
				<div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600">
					Não foi possível carregar a tabela de protocolos.
					<Button
						variant="outline"
						size="sm"
						className="ml-3 h-7 text-xs"
						onClick={() => refetch()}
					>
						Tentar novamente
					</Button>
				</div>
			) : isFetching && !data ? (
				<Skeleton className="h-64 rounded-lg" />
			) : (data?.protocols ?? []).length === 0 ? (
				<p className="py-4 text-sm text-muted-foreground">
					Sem dados de protocolo para os filtros nesta semana.
				</p>
			) : (
				<>
					<div className="overflow-x-auto rounded-lg border">
						<table className="w-full text-sm">
							<thead>
								<tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
									{cabecalhoOrdenavel("Protocolo", "protocolo", "left")}
									<th className="px-3 py-2 text-right font-medium">
										Total aplicável
									</th>
									<th className="px-3 py-2 text-right font-medium">
										Regular total
									</th>
									{cabecalhoOrdenavel("% Regular", "regular_pct")}
									<th className="px-3 py-2 text-right font-medium">
										Irregular
									</th>
									<th className="px-3 py-2 text-right font-medium">
										% Irregular
									</th>
									{cabecalhoOrdenavel("Cobertura", "cobertura")}
								</tr>
							</thead>
							<tbody>
								{linhas.map((p) => (
									<tr
										key={p.protocolo_id}
										tabIndex={0}
										role="button"
										aria-label={`Ver evolução do protocolo ${p.protocolo_descricao ?? p.protocolo_id}`}
										onClick={() => onSelectProtocolo(p.protocolo_id)}
										onKeyDown={(e) => {
											if (e.key === "Enter" || e.key === " ") {
												e.preventDefault();
												onSelectProtocolo(p.protocolo_id);
											}
										}}
										className="cursor-pointer border-b transition-colors last:border-b-0 hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
									>
										<td className="px-3 py-2">
											<p className="font-medium">
												{p.protocolo_descricao ?? p.protocolo_id}
											</p>
											<p className="text-xs text-muted-foreground">
												{p.protocolo_secretaria ?? "—"}
											</p>
										</td>
										<td className="px-3 py-2 text-right tabular-nums">
											{formatarNumero(p.total)}
										</td>
										<td className="px-3 py-2 text-right tabular-nums">
											{formatarNumero(p.regular_total)}
										</td>
										<td className="px-3 py-2 text-right tabular-nums">
											{formatarTaxa(p.regular_pct)}
										</td>
										<td className="px-3 py-2 text-right tabular-nums">
											{formatarNumero(p.irregular)}
										</td>
										<td className="px-3 py-2 text-right tabular-nums">
											{formatarTaxa(p.irregular_pct)}
										</td>
										<td className="px-3 py-2 text-right tabular-nums">
											{p.cob === null
												? "—"
												: formatarTaxa(p.cob)}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
					{isFetching ? (
						<p className="flex items-center gap-2 text-xs text-muted-foreground">
							<Loader2 className="h-3 w-3 animate-spin" />
							Atualizando…
						</p>
					) : null}
					<p className="text-xs text-muted-foreground">
						Valores por protocolo — não somar entre protocolos (o
						mesmo participante aparece uma vez por protocolo
						aplicável). Clique numa linha para ver a evolução do
						protocolo.
					</p>
				</>
			)}
		</div>
	);
});
