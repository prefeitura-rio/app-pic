"use client";

/**
 * Gráficos de linha da série de UM protocolo (Acompanhamento semanal).
 *
 * Eixo X = data de avaliação (``snapshot_date``); a semana de referência
 * aparece no tooltip. Linha suavizada (``monotone`` — passa pelos pontos,
 * sem overshoot) com pontos visíveis em todas as semanas; cada ponto é a
 * apuração semanal (a suavização é só leitura de tendência).
 *
 * - ``TaxaSemanalChart`` — toggle **Regularidade | Irregularidade**: uma
 *   série por vez com eixo Y FIXO de 0 a 100%. Rótulo com o valor em TODOS
 *   os pontos; o tooltip mostra sempre os dois valores. Precisão dinâmica
 *   (2 casas quando a amplitude/valor é < 1).
 * - ``AtivosClassificacaoChart`` — toggle **Ativos | Inativos**: na vista
 *   "Ativos", os ativos regulares (inclui atenção) e irregulares; na vista
 *   "Inativos", os inativos do snapshot semanal (contagens).
 */

import { memo, useMemo, useState, type ReactNode } from "react";
import {
	Legend,
	Line,
	LineChart,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { Button } from "@/app/components/ui/button";
import type { MonitoringProtocolPoint } from "@/app/types";
import {
	COR_ATIVO,
	COR_ATIVO_IRREGULAR,
	COR_INATIVO_ALERTA,
	COR_IRREGULAR,
	COR_REGULAR,
} from "./cores";
import {
	formatarNumero,
	formatarTaxa,
	formatarTaxaCom,
	semanaLabel,
	snapshotLabel,
} from "./format";
import { ativoIrr, ativoReg, inativos } from "./semana";

const dataCurta = new Intl.DateTimeFormat("pt-BR", {
	day: "2-digit",
	month: "2-digit",
});

/** "2026-07-25" → "25/07" (rótulo curto do eixo X). */
function snapshotCurta(snapshot: string): string {
	return dataCurta.format(new Date(`${snapshot}T12:00:00`));
}

/** 1234 → "1,2 mil"; 1234567 → "1,2 mi" (eixos de contagem). */
function compacto(valor: number): string {
	if (valor >= 1_000_000) {
		return `${(valor / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`;
	}
	if (valor >= 1_000) {
		return `${(valor / 1_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
	}
	return String(valor);
}

// ---------------------------------------------------------------------------
// Dados derivados por semana
// ---------------------------------------------------------------------------

interface DadoSemana {
	label: string;
	avaliacao: string | null;
	semana: string;
	total: number;
	regPct: number | null;
	irrPct: number | null;
	ativoReg: number;
	ativoIrr: number;
	inativos: number;
	ativos: number;
}

function dadosSemana(serie: MonitoringProtocolPoint[]): DadoSemana[] {
	return serie.map((p) => ({
		label: p.snapshot_date
			? snapshotCurta(p.snapshot_date)
			: semanaLabel(p.week_start),
		avaliacao: p.snapshot_date ? snapshotLabel(p.snapshot_date) : null,
		semana: semanaLabel(p.week_start),
		total: p.total,
		regPct: p.regular_pct,
		irrPct: p.irregular_pct,
		ativoReg: ativoReg(p),
		ativoIrr: ativoIrr(p),
		inativos: inativos(p),
		ativos: p.by_status["Ativo"]?.total ?? 0,
	}));
}

// ---------------------------------------------------------------------------
// Tooltips e rótulo do último ponto
// ---------------------------------------------------------------------------

interface ItemTooltip {
	dataKey?: string | number | ((obj: unknown) => unknown);
	name?: string | number;
	value?: unknown;
	color?: string;
	payload?: Record<string, number | string | null>;
}

function TooltipLinhas({
	active,
	payload,
	label,
	eixoPct,
	comPartes,
}: {
	active?: boolean;
	payload?: readonly ItemTooltip[];
	label?: string | number;
	eixoPct?: boolean;
	comPartes?: boolean;
}) {
	if (!active || !payload || payload.length === 0) {
		return null;
	}
	const registro = payload[0]?.payload;
	const total =
		typeof registro?.total === "number" ? registro.total : null;
	return (
		<div className="rounded-md border bg-background p-3 text-sm shadow-md">
			<p className="font-semibold">
				{registro?.avaliacao
					? `Avaliação de ${String(registro.avaliacao)}`
					: `Semana de ${String(label)}`}
			</p>
			{registro?.avaliacao ? (
				<p className="text-muted-foreground">
					Semana de início {String(registro.semana)}
				</p>
			) : null}
			<div className="mt-1 space-y-0.5">
				{payload.map((item) => {
					const bruto = item.value;
					const valor = typeof bruto === "number" ? bruto : null;
					return (
						<div
							key={String(item.dataKey)}
							className="flex items-center justify-between gap-4"
						>
							<span className="flex items-center gap-1.5">
								<span
									className="inline-block h-2 w-2 rounded-sm"
									style={{ backgroundColor: item.color }}
								/>
								{String(item.name)}
							</span>
							<span className="tabular-nums">
								{eixoPct
									? formatarTaxa(valor)
									: formatarNumero(valor)}
								{comPartes &&
								total !== null &&
								total > 0 &&
								valor !== null ? (
									<span className="ml-1 text-muted-foreground">
										({formatarTaxa((valor / total) * 100)})
									</span>
								) : null}
							</span>
						</div>
					);
				})}
			</div>
		</div>
	);
}

/** Tooltip do gráfico de regularidade: mostra SEMPRE os dois valores. */
function TooltipTaxa({
	active,
	payload,
	modo,
}: {
	active?: boolean;
	payload?: readonly ItemTooltip[];
	modo: "protocolo" | "geral";
}) {
	if (!active || !payload || payload.length === 0) {
		return null;
	}
	const registro = payload[0]?.payload;
	const reg = typeof registro?.regPct === "number" ? registro.regPct : null;
	const irr = typeof registro?.irrPct === "number" ? registro.irrPct : null;
	const sufixo = modo === "geral" ? "(geral)" : "(grupo)";
	return (
		<div className="rounded-md border bg-background p-3 text-sm shadow-md">
			<p className="font-semibold">
				{registro?.avaliacao
					? `Avaliação de ${String(registro.avaliacao)}`
					: "—"}
			</p>
			<p className="text-muted-foreground">
				Semana de início {String(registro?.semana ?? "—")}
			</p>
			<div className="mt-1 space-y-0.5">
				<p className="flex items-center justify-between gap-4">
					<span className="flex items-center gap-1.5">
						<span
							className="inline-block h-2 w-2 rounded-sm"
							style={{ backgroundColor: COR_REGULAR }}
						/>
						% Regular {sufixo}
					</span>
					<span className="tabular-nums">{formatarTaxa(reg)}</span>
				</p>
				<p className="flex items-center justify-between gap-4">
					<span className="flex items-center gap-1.5">
						<span
							className="inline-block h-2 w-2 rounded-sm"
							style={{ backgroundColor: COR_IRREGULAR }}
						/>
						% Irregular {sufixo}
					</span>
					<span className="tabular-nums">{formatarTaxa(irr)}</span>
				</p>
			</div>
		</div>
	);
}

interface DotComProps {
	cx?: number;
	cy?: number;
	index?: number;
	payload?: Record<string, number | string | null>;
}

/** Ponto visível em todas as semanas, com valor rotulado acima.
 *  ``rotuloEmTodos`` rotula todos os pontos (série única); senão só o último. */
function DotComRotulo(
	props: DotComProps & {
		ultimoIndex: number;
		dataKey: string;
		cor: string;
		formato: (v: number | null) => string;
		rotuloEmTodos?: boolean;
	},
) {
	const {
		cx,
		cy,
		index,
		payload,
		ultimoIndex,
		dataKey,
		cor,
		formato,
		rotuloEmTodos,
	} = props;
	if (cx === undefined || cy === undefined) {
		return <g />;
	}
	const ehUltimo = index === ultimoIndex;
	const bruto = payload?.[dataKey];
	const valor = typeof bruto === "number" ? bruto : null;
	const mostrarRotulo =
		valor !== null && (rotuloEmTodos ? true : ehUltimo);
	// Âncoras nas pontas para o rótulo não invadir o eixo Y (esquerda) nem
	// a margem direita: primeiro ponto à direita do centro, último à
	// esquerda, demais centralizados.
	const ehPrimeiro = index === 0;
	const anchor = ehPrimeiro ? "start" : ehUltimo ? "end" : "middle";
	const xRotulo = ehPrimeiro ? cx + 6 : ehUltimo ? cx - 6 : cx;
	return (
		<g>
			<circle
				cx={cx}
				cy={cy}
				r={ehUltimo ? 3.5 : 2.5}
				fill={cor}
				stroke="var(--background)"
				strokeWidth={1.5}
			/>
			{mostrarRotulo ? (
				<text
					x={xRotulo}
					y={cy - 10}
					textAnchor={anchor}
					fontSize={11}
					fontWeight={600}
					fill="currentColor"
				>
					{formato(valor)}
				</text>
			) : null}
		</g>
	);
}

// ---------------------------------------------------------------------------
// Gráfico genérico (contagens)
// ---------------------------------------------------------------------------

interface ConfigLinha {
	dataKey: string;
	nome: string;
	cor: string;
}

/** Dimensão inicial do ResponsiveContainer: evita o aviso de -1×-1 do
 *  Recharts no 1º render (antes da primeira medição do ResizeObserver).
 *  640×320 é o tamanho aproximado dos gráficos (h-80 = 320px). */
const DIMENSAO_INICIAL = { width: 640, height: 320 };

interface GraficoLinhasProps {
	serie: MonitoringProtocolPoint[];
	linhas: ConfigLinha[];
	/** true = eixo Y em % (0–100); false = contagens. */
	eixoPct?: boolean;
	/** Tooltip mostra % do total em cada item (gráficos de contagem). */
	comPartes?: boolean;
	titulo: string;
	nota: string;
	ariaLabel: string;
	altura?: string;
	/** Controles opcionais exibidos ao lado do título (ex.: toggle de vista). */
	acoes?: ReactNode;
}

function GraficoLinhas({
	serie,
	linhas,
	eixoPct = false,
	comPartes = false,
	titulo,
	nota,
	ariaLabel,
	altura = "h-80",
	acoes,
}: GraficoLinhasProps) {
	const dados = useMemo(() => dadosSemana(serie), [serie]);
	const ultimoIndex = dados.length - 1;
	const formato = eixoPct ? formatarTaxa : formatarNumero;

	return (
		<div className="space-y-2">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<h3 className="text-sm font-semibold text-foreground">{titulo}</h3>
				{acoes}
			</div>
			<div
				className={`${altura} text-muted-foreground`}
				role="img"
				aria-label={ariaLabel}
			>
				<ResponsiveContainer
					width="100%"
					height="100%"
					initialDimension={DIMENSAO_INICIAL}
				>
					<LineChart
						data={dados}
						margin={{ top: 28, right: 16, left: 0, bottom: 0 }}
					>
						<XAxis
							dataKey="label"
							tick={{ fontSize: 12 }}
							interval="preserveStartEnd"
						/>
						<YAxis
							domain={eixoPct ? [0, 100] : [0, "auto" as const]}
							tick={{ fontSize: 12 }}
							width={58}
							tickFormatter={(v: number) =>
								eixoPct
									? `${v.toLocaleString("pt-BR")}%`
									: compacto(v)
							}
						/>
						<Tooltip
							content={(props) => (
								<TooltipLinhas
									active={props.active}
									payload={props.payload}
									label={props.label}
									eixoPct={eixoPct}
									comPartes={comPartes}
								/>
							)}
						/>
						<Legend wrapperStyle={{ fontSize: 13 }} />
						{linhas.map((l) => (
							<Line
								key={l.dataKey}
								type="monotone"
								dataKey={l.dataKey}
								name={l.nome}
								stroke={l.cor}
								strokeWidth={2}
								strokeLinecap="round"
								strokeLinejoin="round"
								connectNulls={false}
								isAnimationActive={false}
								activeDot={{ r: 4 }}
								dot={(props: DotComProps) => (
									<DotComRotulo
										{...props}
										ultimoIndex={ultimoIndex}
										dataKey={l.dataKey}
										cor={l.cor}
										formato={formato}
										rotuloEmTodos
									/>
								)}
							/>
						))}
					</LineChart>
				</ResponsiveContainer>
			</div>
			<p className="text-xs leading-relaxed text-muted-foreground">
				{nota}
			</p>
		</div>
	);
}

// ---------------------------------------------------------------------------
// Regularidade | Irregularidade (toggle, eixo ampliado)
// ---------------------------------------------------------------------------

type VistaTaxa = "regular" | "irregular";

const VISTAS_TAXA: { id: VistaTaxa; rotulo: string }[] = [
	{ id: "regular", rotulo: "Regularidade" },
	{ id: "irregular", rotulo: "Irregularidade" },
];

export const TaxaSemanalChart = memo(function TaxaSemanalChart({
	serie,
	modo = "protocolo",
}: {
	serie: MonitoringProtocolPoint[];
	/** "geral" ajusta rótulos/notas para a regularidade geral. */
	modo?: "protocolo" | "geral";
}) {
	const [vista, setVista] = useState<VistaTaxa>("regular");
	const dados = useMemo(() => dadosSemana(serie), [serie]);

	const ehRegular = vista === "regular";
	const dataKey = ehRegular ? "regPct" : "irrPct";
	const cor = ehRegular ? COR_REGULAR : COR_IRREGULAR;
	const sufixo = modo === "geral" ? "(geral)" : "(grupo)";

	const valores = dados
		.map((d) => (ehRegular ? d.regPct : d.irrPct))
		.filter((v): v is number => v !== null);
	const span =
		valores.length > 0
			? Math.max(...valores) - Math.min(...valores)
			: 100;
	// 2 casas quando a amplitude é pequena (< 1 p.p.), senão 1.
	const casas = span < 1 ? 2 : 1;
	const formato = (v: number | null) => formatarTaxaCom(v, casas);
	const ultimoIndex = dados.length - 1;

	return (
		<div className="space-y-2">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<h3 className="text-sm font-semibold text-foreground">
					{ehRegular
						? "Regularidade por semana"
						: "Irregularidade por semana"}
				</h3>
				<div
					className="flex rounded-lg border p-0.5"
					role="group"
					aria-label="Série exibida no gráfico"
				>
					{VISTAS_TAXA.map((op) => (
						<Button
							key={op.id}
							variant={vista === op.id ? "secondary" : "ghost"}
							size="sm"
							className="h-7 px-2 text-xs"
							onClick={() => setVista(op.id)}
						>
							{op.rotulo}
						</Button>
					))}
				</div>
			</div>
			<div
				className="h-80 text-muted-foreground"
				role="img"
				aria-label={
					ehRegular
						? "Gráfico de linha da regularidade por semana"
						: "Gráfico de linha da irregularidade por semana"
				}
			>
				<ResponsiveContainer
					width="100%"
					height="100%"
					initialDimension={DIMENSAO_INICIAL}
				>
					<LineChart
						data={dados}
						margin={{ top: 36, right: 16, left: 0, bottom: 0 }}
					>
						<XAxis
							dataKey="label"
							tick={{ fontSize: 12 }}
							interval="preserveStartEnd"
						/>
						<YAxis
							domain={[0, 100]}
							tick={{ fontSize: 12 }}
							width={68}
							tickFormatter={(v: number) =>
								`${v.toLocaleString("pt-BR", {
									minimumFractionDigits: casas,
									maximumFractionDigits: casas,
								})}%`
							}
						/>
						<Tooltip
							content={(props) => (
								<TooltipTaxa
									active={props.active}
									payload={props.payload}
									modo={modo}
								/>
							)}
						/>
						<Line
							type="monotone"
							dataKey={dataKey}
							name={
								ehRegular
									? `% Regular ${sufixo}`
									: `% Irregular ${sufixo}`
							}
							stroke={cor}
							strokeWidth={2}
							strokeLinecap="round"
							strokeLinejoin="round"
							connectNulls={false}
							isAnimationActive={false}
							activeDot={{ r: 4 }}
							dot={(props: DotComProps) => (
								<DotComRotulo
									{...props}
									ultimoIndex={ultimoIndex}
									dataKey={dataKey}
									cor={cor}
									formato={formato}
									rotuloEmTodos
								/>
							)}
						/>
					</LineChart>
				</ResponsiveContainer>
			</div>
			<p className="text-xs leading-relaxed text-muted-foreground">
				{ehRegular
					? modo === "geral"
						? "Regular = participante regular em todos os protocolos aplicáveis (regular estrito + atenção). Inclui participantes inativos com regularidade geral. Denominador: total de participantes."
						: "Regular = regular estrito + atenção. Inclui participantes inativos com status regular no protocolo. Denominador: total aplicável."
					: modo === "geral"
						? "Irregular = participante com pelo menos um protocolo irregular / total de participantes."
						: "Irregular / total aplicável. Complemento do % regular na janela atual."}{" "}
				Eixo fixo de 0 a 100%. Linha suavizada para leitura de
				tendência; cada ponto é a apuração semanal.
			</p>
		</div>
	);
});

// ---------------------------------------------------------------------------
// Gráficos de contagem
// ---------------------------------------------------------------------------

type VistaAtivos = "ativos" | "inativos";

const VISTAS_ATIVOS: { id: VistaAtivos; rotulo: string }[] = [
	{ id: "ativos", rotulo: "Ativos" },
	{ id: "inativos", rotulo: "Inativos" },
];

export const AtivosClassificacaoChart = memo(function AtivosClassificacaoChart({
	serie,
	modo = "protocolo",
}: {
	serie: MonitoringProtocolPoint[];
	/** "geral" ajusta as notas para a regularidade geral. */
	modo?: "protocolo" | "geral";
}) {
	const [vista, setVista] = useState<VistaAtivos>("ativos");
	const ehAtivos = vista === "ativos";
	return (
		<GraficoLinhas
			serie={serie}
			linhas={
				ehAtivos
					? [
							{
								dataKey: "ativoReg",
								nome: "Ativo regular (inclui atenção)",
								cor: COR_ATIVO,
							},
							{
								dataKey: "ativoIrr",
								nome: "Ativo irregular",
								cor: COR_ATIVO_IRREGULAR,
							},
						]
					: [
							{
								dataKey: "inativos",
								nome: "Inativo",
								cor: COR_INATIVO_ALERTA,
							},
						]
			}
			comPartes
			titulo={ehAtivos ? "Ativos por semana" : "Inativos por semana"}
			nota={
				ehAtivos
					? modo === "geral"
						? "Contagens de participantes ativos, regulares (regularidade geral — inclui atenção) e irregulares. Linha suavizada para leitura de tendência; cada ponto é a apuração semanal."
						: "Contagens de participantes ativos, regulares (inclui atenção) e irregulares. Linha suavizada para leitura de tendência; cada ponto é a apuração semanal."
					: "Contagens de participantes inativos — o status do snapshot semanal. Linha suavizada para leitura de tendência; cada ponto é a apuração semanal."
			}
			ariaLabel={
				ehAtivos
					? "Gráfico de linhas de ativos regulares e ativos irregulares por semana"
					: "Gráfico de linhas de inativos por semana"
			}
			acoes={
				<div
					className="flex rounded-lg border p-0.5"
					role="group"
					aria-label="Série exibida no gráfico"
				>
					{VISTAS_ATIVOS.map((op) => (
						<Button
							key={op.id}
							variant={vista === op.id ? "secondary" : "ghost"}
							size="sm"
							className="h-7 px-2 text-xs"
							onClick={() => setVista(op.id)}
						>
							{op.rotulo}
						</Button>
					))}
				</div>
			}
		/>
	);
});
