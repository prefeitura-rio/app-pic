"use client";

/**
 * Evolução semanal — seção do Acompanhamento dentro da aba Monitoramento.
 *
 * Consome o ESTADO do mapa: camada + regiões selecionadas e os filtros
 * compartilhados (status, safra, grupo, Bolsa Família, protocolo). Sem
 * região selecionada, a série é da cidade inteira; com várias, o backend
 * soma as regiões (OR na coluna da camada).
 *
 * Uma única fonte em ambos os modos — `GET /v2/monitoring/series`:
 * - **Modo protocolo**: ``protocolo`` = id do protocolo selecionado no mapa.
 * - **Modo "Regularidade geral"** (sem protocolo): ``protocolo`` = ``"geral"``
 *   — as linhas ``nivel='geral'`` da tabela semanal (``protocolo_id``/
 *   ``protocolo_secretaria`` = ``'geral'``), o número geral consolidado
 *   (participante regular em todos os protocolos aplicáveis).
 * Os dois modos renderizam a MESMA visão: 5 cards, gráfico de regularidade,
 * gráfico de ativos/inativos e a tabela semanal com variações.
 *
 * Os cards comparam a semana FINAL do período (Até) com o INÍCIO do período
 * (De). Período default = janela estável inteira. Overlay de loading cobre a
 * seção durante refetch (troca de protocolo/região/filtros), pois
 * `keepPreviousData` mantém os números antigos.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
	AlertTriangle,
	ArrowLeft,
	Download,
	Loader2,
	RefreshCw,
	Users,
} from "lucide-react";
import { memo, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
} from "@/app/components/ui/card";
import { Skeleton } from "@/app/components/ui/skeleton";
import { apiService } from "@/app/services/api";
import type { CamadaTerritorial } from "@/app/types";
import { downloadCsv } from "@/app/utils/csv";
import { formatDateOnly } from "@/app/utils/utils";
import { taxaToHex } from "./escala";
import {
	formatarNumero,
	formatarTaxa,
	semanaLabel,
	snapshotLabel,
} from "./format";
import { CalendarioSemanal } from "./CalendarioSemanal";
import { MetricaCard } from "./MetricaCard";
import {
	AtivosClassificacaoChart,
	TaxaSemanalChart,
} from "./ProtocolSeriesChart";
import { CABECALHO_CSV, linhasDoPeriodo, metricas, num2 } from "./semana";
import { WeeklyTable } from "./WeeklyTable";

/** Pseudo-protocolo da regularidade geral (linhas ``nivel='geral'``). */
const NIVEL_GERAL = "geral";

interface EvolucaoSemanalProps {
	camada: CamadaTerritorial;
	/** Regiões selecionadas no mapa (valores exibidos; [] = cidade inteira). */
	regioes: string[];
	statuses: string[];
	cohortes: string[];
	grupos: string[];
	hasBolsaFamilia: boolean | undefined;
	/** Protocolo selecionado no filtro do mapa ("" = Regularidade geral). */
	protocoloId: string;
	onClearProtocolo: () => void;
	bypassCache: boolean;
}

interface ProtocolRange {
	de: string | null;
	ate: string | null;
}

const RANGE_STORAGE_KEY = "pic:monitoring:protocol-range";

function rangeInicial(): ProtocolRange {
	if (typeof window === "undefined") {
		return { de: null, ate: null };
	}
	try {
		const bruto = window.sessionStorage.getItem(RANGE_STORAGE_KEY);
		if (bruto) {
			const parsed: unknown = JSON.parse(bruto);
			if (
				parsed &&
				typeof parsed === "object" &&
				"de" in parsed &&
				"ate" in parsed &&
				(typeof (parsed as ProtocolRange).de === "string" ||
					(parsed as ProtocolRange).de === null) &&
				(typeof (parsed as ProtocolRange).ate === "string" ||
					(parsed as ProtocolRange).ate === null)
			) {
				return parsed as ProtocolRange;
			}
		}
	} catch {
		// armazenamento corrompido: usa o default
	}
	return { de: null, ate: null };
}

/** "+0,4 p.p." / "-2,3 p.p." com precisão dinâmica (2 casas quando < 0,1). */
function rotuloDelta(valor: number): string {
	const casas = Math.abs(valor) < 0.1 ? 2 : 1;
	return `${valor > 0 ? "+" : ""}${valor.toLocaleString("pt-BR", {
		minimumFractionDigits: casas,
		maximumFractionDigits: casas,
	})} p.p.`;
}

export const EvolucaoSemanal = memo(function EvolucaoSemanal({
	camada,
	regioes,
	statuses,
	cohortes,
	grupos,
	hasBolsaFamilia,
	protocoloId,
	onClearProtocolo,
	bypassCache,
}: EvolucaoSemanalProps) {
	const [range, setRange] = useState<ProtocolRange>(rangeInicial);

	// Persistência do período selecionado (sessionStorage — padrão do app).
	useEffect(() => {
		try {
			window.sessionStorage.setItem(RANGE_STORAGE_KEY, JSON.stringify(range));
		} catch {
			// sem armazenamento: segue sem persistir
		}
	}, [range]);

	// Sempre série: o modo geral usa o pseudo-protocolo "geral".
	const protocoloSerieId = protocoloId || NIVEL_GERAL;
	const modo: "protocolo" | "geral" = protocoloId ? "protocolo" : "geral";

	const filtrosCompartilhados = useMemo(
		() => ({
			statuses: statuses.length > 0 ? statuses : undefined,
			cohortes: cohortes.length > 0 ? cohortes : undefined,
			grupo: grupos.length > 0 ? grupos : undefined,
			hasBolsaFamilia,
			camada,
			regioes: regioes.length > 0 ? regioes : undefined,
		}),
		[statuses, cohortes, grupos, hasBolsaFamilia, camada, regioes],
	);

	const {
		data: serieData,
		isFetching: serieFetching,
		isError: serieError,
		refetch: refetchSerie,
	} = useQuery({
		queryKey: [
			"monitoringSeries",
			camada,
			regioes,
			statuses,
			cohortes,
			grupos,
			hasBolsaFamilia,
			protocoloSerieId,
			bypassCache,
		],
		queryFn: ({ signal }) =>
			apiService.getMonitoringSeries(
				protocoloSerieId,
				filtrosCompartilhados,
				bypassCache,
				signal,
			),
		staleTime: 5 * 60 * 1000,
		placeholderData: keepPreviousData,
		refetchOnWindowFocus: false,
	});

	const meta = serieData?.meta;
	const windowStart = meta?.window_start ?? null;
	const semanasEstaveis = useMemo(
		() =>
			windowStart
				? (meta?.available_weeks ?? []).filter((w) => w >= windowStart)
				: (meta?.available_weeks ?? []),
		[meta?.available_weeks, windowStart],
	);

	const seriePontos = useMemo(
		() => serieData?.series ?? [],
		[serieData?.series],
	);
	const seriePontosEstaveis = useMemo(
		() =>
			windowStart
				? seriePontos.filter((p) => p.week_start >= windowStart)
				: seriePontos,
		[seriePontos, windowStart],
	);

	// Período efetivo: default = janela estável inteira; valores salvos são
	// validados contra as semanas disponíveis (e trocados se de > até).
	const rangeEfetivo = useMemo<ProtocolRange>(() => {
		if (semanasEstaveis.length === 0) {
			return { de: null, ate: null };
		}
		let de =
			range.de && semanasEstaveis.includes(range.de)
				? range.de
				: semanasEstaveis[0];
		let ate =
			range.ate && semanasEstaveis.includes(range.ate)
				? range.ate
				: semanasEstaveis[semanasEstaveis.length - 1];
		if (de > ate) {
			[de, ate] = [ate, de];
		}
		return { de, ate };
	}, [semanasEstaveis, range]);

	const snapshotPorSemana = useMemo(
		() =>
			new Map(seriePontosEstaveis.map((p) => [p.week_start, p.snapshot_date])),
		[seriePontosEstaveis],
	);

	const labelAvaliacao = (w: string | null | undefined): string => {
		if (!w) {
			return "—";
		}
		const snap = snapshotPorSemana.get(w);
		return snap ? snapshotLabel(snap) : semanaLabel(w);
	};

	const serieNoRange = useMemo(
		() =>
			seriePontosEstaveis.filter(
				(p) =>
					(!rangeEfetivo.de || p.week_start >= rangeEfetivo.de) &&
					(!rangeEfetivo.ate || p.week_start <= rangeEfetivo.ate),
			),
		[seriePontosEstaveis, rangeEfetivo],
	);

	// Cards: semana final do período × início do período.
	const pontoAtual = serieNoRange[serieNoRange.length - 1];
	const pontoInicio = serieNoRange[0];
	const periodoUnico = serieNoRange.length <= 1;
	const taxaAtual = pontoAtual?.regular_pct ?? null;
	const taxaInicio = pontoInicio?.regular_pct ?? null;
	const deltaReg =
		!periodoUnico && taxaAtual !== null && taxaInicio !== null
			? taxaAtual - taxaInicio
			: null;
	const taxaAtualIrr = pontoAtual?.irregular_pct ?? null;
	const taxaInicioIrr = pontoInicio?.irregular_pct ?? null;
	const deltaIrr =
		!periodoUnico && taxaAtualIrr !== null && taxaInicioIrr !== null
			? taxaAtualIrr - taxaInicioIrr
			: null;
	const gap =
		!periodoUnico && pontoAtual && taxaInicio !== null
			? Math.round(
					pontoAtual.regular_total - (taxaInicio / 100) * pontoAtual.total,
				)
			: null;
	const corTaxa = taxaToHex(taxaAtual);

	const onApplyRange = (de: string, ate: string) => setRange({ de, ate });
	const atalhoRange = (tipo: "12" | "tudo") => {
		if (semanasEstaveis.length === 0) {
			return;
		}
		const de =
			tipo === "12"
				? semanasEstaveis[Math.max(0, semanasEstaveis.length - 12)]
				: semanasEstaveis[0];
		setRange({ de, ate: semanasEstaveis[semanasEstaveis.length - 1] });
	};

	// Export CSV da tabela semanal (mesmas linhas/métricas da tabela).
	const linhasTabela = useMemo(
		() =>
			linhasDoPeriodo(
				seriePontosEstaveis,
				rangeEfetivo.de ?? "",
				rangeEfetivo.ate ?? "",
			),
		[seriePontosEstaveis, rangeEfetivo],
	);

	const handleExportCsv = () => {
		const linhasCsv = linhasTabela.map(({ p, prev }) => {
			const m = metricas(p, prev);
			return [
				p.snapshot_date ? formatDateOnly(p.snapshot_date) : "",
				formatDateOnly(p.week_start),
				p.total,
				m.dTotal,
				m.ar,
				m.dAR,
				num2(m.pctAR),
				num2(m.dPctAR),
				m.ai,
				m.dAI,
				num2(m.pctAI),
				num2(m.dPctAI),
				m.inat,
				m.dInat,
			];
		});
		try {
			downloadCsv(
				`tabela_semanal_${protocoloSerieId}_${rangeEfetivo.de ?? ""}_a_${rangeEfetivo.ate ?? ""}.csv`,
				CABECALHO_CSV,
				linhasCsv,
			);
			toast.success("CSV exportado.");
		} catch (error) {
			console.error("Erro ao exportar CSV:", error);
			toast.error("Erro ao exportar o CSV. Tente novamente.");
		}
	};

	const trocando = serieFetching && serieData?.protocolo?.id !== protocoloSerieId;
	const nomeProtocolo = trocando
		? "Carregando…"
		: `${serieData?.protocolo?.secretaria ? `${serieData.protocolo.secretaria} — ` : ""}${
				serieData?.protocolo?.descricao ?? protocoloId
			}`;
	const nomeExibicao = modo === "geral" ? "Regularidade geral" : nomeProtocolo;

	const excluiInativos = statuses.length > 0 && !statuses.includes("Inativo");

	// Usuário sem acesso ao dashboard: a seção não é renderizada.
	if (serieData?.can_view_monitoring === false) {
		return null;
	}

	return (
		<Card className="mt-6">
			<CardHeader>
				<div className="flex flex-wrap items-center justify-between gap-3">
					<div className="flex items-center gap-2">
						<Users className="h-4 w-4 text-muted-foreground" />
						<CardTitle className="text-base">Evolução semanal</CardTitle>
						<Badge
							variant="outline"
							className="text-xs"
							title={regioes.join(", ")}
						>
							{regioes.length === 0
								? "Cidade inteira"
								: regioes.length <= 2
									? regioes.join(" + ")
									: `${regioes.length} regiões`}
						</Badge>
						{meta?.latest_is_partial ? (
							<Badge variant="secondary" className="text-xs">
								Semana em curso
							</Badge>
						) : null}
					</div>
					<div className="flex flex-wrap items-center justify-end gap-2">
						<CalendarioSemanal
							semanas={semanasEstaveis}
							snapshotPorSemana={snapshotPorSemana}
							de={rangeEfetivo.de ?? ""}
							ate={rangeEfetivo.ate ?? ""}
							onApply={onApplyRange}
							disabled={serieFetching}
						/>
						<Button
							variant="outline"
							size="sm"
							className="h-9 text-xs"
							onClick={() => atalhoRange("12")}
						>
							12 semanas
						</Button>
						<Button
							variant="outline"
							size="sm"
							className="h-9 text-xs"
							onClick={() => atalhoRange("tudo")}
						>
							Todas as semanas
						</Button>
						<Button
							variant="outline"
							size="sm"
							className="h-9 text-xs"
							onClick={handleExportCsv}
							disabled={linhasTabela.length === 0 || serieFetching}
						>
							<Download className="mr-1 h-3.5 w-3.5" />
							Exportar CSV
						</Button>
						<Button
							variant="outline"
							size="sm"
							className="h-9 text-xs"
							onClick={() => refetchSerie()}
							disabled={serieFetching}
						>
							{serieFetching ? (
								<Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
							) : (
								<RefreshCw className="mr-1 h-3.5 w-3.5" />
							)}
							Atualizar
						</Button>
					</div>
				</div>
			</CardHeader>
			<CardContent className="space-y-8">
				{/* Aviso de status sem Inativo (saídas invisíveis) */}
				{excluiInativos ? (
					<div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-700">
						<AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />O filtro de
						status exclui inativos — as saídas do grupo não aparecem na
						evolução.
					</div>
				) : null}

				{serieError ? (
					<div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600">
						Não foi possível carregar a evolução semanal.
						<Button
							variant="outline"
							size="sm"
							className="ml-3 h-7 text-xs"
							onClick={() => refetchSerie()}
						>
							Tentar novamente
						</Button>
					</div>
				) : serieData !== undefined && serieData.meta.has_data === false ? (
					<p className="py-4 text-sm text-muted-foreground">
						Nenhum participante para os filtros atuais.
					</p>
				) : serieFetching && !serieData ? (
					<div className="space-y-4">
						<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
							{Array.from({ length: 4 }).map((_, i) => (
								<Skeleton key={i} className="h-20 rounded-lg" />
							))}
						</div>
						<Skeleton className="h-72 rounded-lg" />
					</div>
				) : (
					<div className="relative">
						{/* Overlay de refetch: keepPreviousData mantém os números
						    antigos na tela — o overlay avisa a troca. */}
						{serieFetching && serieData ? (
							<div className="absolute inset-0 z-10 flex items-start justify-center rounded-lg bg-background/60 pt-6 backdrop-blur-[1px]">
								<div className="flex items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm text-muted-foreground shadow-md">
									<Loader2 className="h-4 w-4 animate-spin" />
									Carregando dados…
								</div>
							</div>
						) : null}
						<div
							aria-busy={serieFetching}
							className={
								serieFetching && serieData
									? "pointer-events-none space-y-8 opacity-60"
									: "space-y-8"
							}
						>
							<div className="flex flex-wrap items-center justify-between gap-4 border-t pt-8">
								<div className="min-w-0">
									<h3 className="text-sm font-semibold text-foreground">
										{nomeExibicao}
									</h3>
								</div>
								{modo === "protocolo" ? (
									<Button
										variant="ghost"
										size="sm"
										className="h-9 text-xs"
										onClick={onClearProtocolo}
									>
										<ArrowLeft className="mr-1 h-3 w-3" />
										Todos os protocolos
									</Button>
								) : null}
							</div>

							{serieNoRange.length === 0 ? (
								<p className="py-4 text-sm text-muted-foreground">
									{modo === "geral"
										? "Sem dados de regularidade geral para o período selecionado."
										: "Sem dados do protocolo para o período selecionado."}
								</p>
							) : (
								<>
									{/* Cards: semana final × início do período */}
									<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
										<MetricaCard
											rotulo="Participantes"
											valor={formatarNumero(pontoAtual?.total)}
											cor={corTaxa}
											detalhe={
												modo === "geral"
													? `total de participantes na avaliação de ${labelAvaliacao(rangeEfetivo.ate)}`
													: `total aplicável na avaliação de ${labelAvaliacao(rangeEfetivo.ate)}`
											}
										/>
										<MetricaCard
											rotulo="% Regulares"
											valor={formatarTaxa(taxaAtual)}
											cor={corTaxa}
											trend={
												deltaReg !== null
													? {
															valor: rotuloDelta(deltaReg),
															positivo: deltaReg >= 0,
															label: "vs início",
															direcao: deltaReg >= 0 ? "up" : "down",
														}
													: undefined
											}
											detalhe={
												pontoAtual
													? `${formatarNumero(pontoAtual.regular_total)} regulares de ${formatarNumero(pontoAtual.total)} participantes`
													: undefined
											}
										/>
										<MetricaCard
											rotulo="% Irregulares"
											valor={formatarTaxa(taxaAtualIrr)}
											cor={corTaxa}
											trend={
												deltaIrr !== null
													? {
															valor: rotuloDelta(deltaIrr),
															positivo: deltaIrr <= 0,
															label: "vs início",
															direcao: deltaIrr >= 0 ? "up" : "down",
														}
													: undefined
											}
											detalhe={
												pontoAtual
													? `${formatarNumero(pontoAtual.irregular)} irregulares de ${formatarNumero(pontoAtual.total)} participantes`
													: undefined
											}
										/>
										<MetricaCard
											rotulo="Início do período"
											valor={formatarTaxa(taxaInicio)}
											cor={corTaxa}
											detalhe={
												pontoInicio
													? `${formatarNumero(pontoInicio.regular_total)} regulares de ${formatarNumero(pontoInicio.total)} participantes na avaliação de ${labelAvaliacao(pontoInicio.week_start)}`
													: undefined
											}
										/>
										<MetricaCard
											rotulo="Acima/Abaixo do início"
											valor={
												gap === null
													? "—"
													: Math.abs(gap).toLocaleString("pt-BR")
											}
											cor={corTaxa}
											trend={
												gap !== null && gap !== 0
													? {
															valor:
																gap > 0
																	? "ACIMA DO INÍCIO"
																	: "ABAIXO DO INÍCIO",
															positivo: gap > 0,
															direcao: gap > 0 ? "up" : "down",
														}
													: undefined
											}
											detalhe={
												gap !== null && taxaInicio !== null
													? `participantes regulares ${gap >= 0 ? "acima" : "abaixo"} do esperado pelo início do período (${formatarTaxa(taxaInicio)})`
													: undefined
											}
										/>
									</div>

									<TaxaSemanalChart serie={serieNoRange} modo={modo} />

									<AtivosClassificacaoChart
										serie={serieNoRange}
										modo={modo}
									/>

									<WeeklyTable
										serieCompleta={seriePontosEstaveis}
										de={rangeEfetivo.de ?? ""}
										ate={rangeEfetivo.ate ?? ""}
										modo={modo}
									/>
								</>
							)}
						</div>
					</div>
				)}

			</CardContent>
		</Card>
	);
});
