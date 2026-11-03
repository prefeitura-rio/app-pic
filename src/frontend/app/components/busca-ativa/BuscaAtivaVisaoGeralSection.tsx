"use client";

import { useMemo } from "react";
import { Search, UserCheck } from "lucide-react";
import {
	Bar,
	BarChart,
	CartesianGrid,
	Cell,
	Legend,
	Line,
	LineChart,
	Pie,
	PieChart,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/app/components/ui/card";
import { StatCard } from "@/app/components/StatCard";
import type {
	BuscaAtivaCategoria,
	BuscaAtivaDashboard,
	BuscaAtivaDesfechoMensal,
} from "@/app/types";

// Paleta de categorias (tons do WhatsApp disparos).
const PALETA_CATEGORIAS = [
	"#1BB6AFFF",
	"#172869FF",
	"#088BBEFF",
	"#F8CD9CFF",
	"#F6A1A5FF",
	"#EA7580FF",
];

const COR_SMAS = "#3b82f6";

// A busca ativa da SMAS começa a ser acompanhada em mar/2026.
const SMAS_MES_INICIAL = "2026-03";

const paletaPorQuantidade = (total: number, paleta: string[]): string[] => {
	if (total === 2) {
		return [paleta[0], paleta[paleta.length - 1]];
	}
	if (total === 3) {
		return [
			paleta[0],
			paleta[Math.floor(paleta.length / 2)],
			paleta[paleta.length - 1],
		];
	}
	return paleta;
};

// Cor do desfecho no gráfico "Resultado SMAS por Mês": "não localizada"
// (qualquer grafia) em vermelho; os demais seguem a paleta por índice.
function corDesfecho(desfecho: string, index: number): string {
	const norm = desfecho
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.toLowerCase();
	if (norm.includes("nao") && norm.includes("localizad")) {
		return "#EA7580";
	}
	return PALETA_CATEGORIAS[index % PALETA_CATEGORIAS.length];
}

interface BuscaAtivaVisaoGeralSectionProps {
	data?: BuscaAtivaDashboard | null;
	showSMAS?: boolean;
	loading?: boolean;
}

/** Pivota a série de desfecho (mes × desfecho) para o gráfico empilhado. */
function pivotDesfecho(
	rows: BuscaAtivaDesfechoMensal[],
): { data: Record<string, string | number>[]; desfechos: string[] } {
	const labelPorMes = new Map<string, string>();
	const porMes = new Map<string, Map<string, number>>();
	for (const row of rows) {
		labelPorMes.set(row.mes, row.mes_label);
		if (!porMes.has(row.mes)) {
			porMes.set(row.mes, new Map());
		}
		porMes.get(row.mes)!.set(row.desfecho, row.total);
	}

	const desfechos = Array.from(
		new Set(rows.map((r) => r.desfecho)),
	).sort();

	// Ordena por mês (YYYY-MM) para manter a ordem cronológica no eixo X.
	const data = Array.from(porMes.entries())
		.sort((a, b) => a[0].localeCompare(b[0]))
		.map(([mes, porDesfecho]) => {
			const ponto: Record<string, string | number> = {
				mes_label: labelPorMes.get(mes) ?? mes,
			};
			for (const desfecho of desfechos) {
				ponto[desfecho] = porDesfecho.get(desfecho) ?? 0;
			}
			return ponto;
		});

	return { data, desfechos };
}

function EmptyChart({ height = 260 }: { height?: number }) {
	return (
		<div
			className="flex items-center justify-center text-muted-foreground"
			style={{ height }}
		>
			<p className="text-sm">Sem dados no período selecionado</p>
		</div>
	);
}

/** Donut de distribuição por categoria (tática da aba de acordo de resultados:
 * `sqrt(total)` amplia as fatias pequenas, com legenda customizada abaixo). */
function CategoriaDonut({
	title,
	description,
	data,
	height = 400,
}: {
	title: string;
	description?: string;
	data: BuscaAtivaCategoria[];
	height?: number;
}) {
	const cores = paletaPorQuantidade(data.length, PALETA_CATEGORIAS);
	const total = data.reduce((acc, i) => acc + (i.total ?? 0), 0);

	return (
		<Card className="relative">
			<CardHeader>
				<CardTitle className="text-lg">{title}</CardTitle>
				{description && <CardDescription>{description}</CardDescription>}
			</CardHeader>
			<CardContent>
				{data.length === 0 ? (
					<EmptyChart height={height} />
				) : (
					<>
						<ResponsiveContainer width="100%" height={height}>
					<PieChart>
						<Pie
							data={data}
							dataKey={(entry: { total?: number }) =>
								Math.sqrt(entry.total ?? 0)
							}
							nameKey="categoria"
							cx="50%"
							cy="50%"
							outerRadius={160}
							innerRadius={80}
						>
							{data.map((entry, index) => (
								<Cell
									key={`cell-${index}`}
									fill={cores[index % cores.length]}
								/>
							))}
						</Pie>
						<Tooltip
							formatter={(value, name, item) => [
								item?.payload?.total ?? value,
								name,
							]}
						/>
					</PieChart>
				</ResponsiveContainer>
				<div className="space-y-2 px-4">
					{data.map((entry, index) => {
						const color = cores[index % cores.length];
						const percent =
							total > 0
								? (((entry.total ?? 0) / total) * 100).toFixed(1)
								: 0;
						return (
							<div
								key={index}
								className="flex items-center justify-between text-sm"
							>
								<div className="flex items-center gap-2">
									<div
										className="w-3 h-3 rounded-full flex-shrink-0"
										style={{ backgroundColor: color }}
									/>
									<span style={{ color }}>{entry.categoria}</span>
								</div>
								<span className="font-medium" style={{ color }}>
									{(entry.total ?? 0).toLocaleString("pt-BR")} ({percent}%)
								</span>
							</div>
						);
					})}
					</div>
				</>
				)}
			</CardContent>
		</Card>
	);
}

export function BuscaAtivaVisaoGeralSection({
	data,
	showSMAS = true,
	loading = false,
}: BuscaAtivaVisaoGeralSectionProps) {
	const desfecho = useMemo(
		() =>
			pivotDesfecho(
				(data?.smas_desfecho_mensal ?? []).filter(
					(r) => r.mes >= SMAS_MES_INICIAL,
				),
			),
		[data?.smas_desfecho_mensal],
	);

	const evolucaoSMAS = useMemo(
		() =>
			(data?.evolucao_mensal ?? []).filter((p) => p.mes >= SMAS_MES_INICIAL),
		[data?.evolucao_mensal],
	);

	if (!data) return null;

	const { totais } = data;
	const temEvolucaoSMAS = evolucaoSMAS.some((p) => p.smas > 0);
	const temDesfecho = desfecho.data.length > 0;

	return (
		<div className="space-y-4">
			<div className="space-y-2">
				<h2 className="text-2xl font-bold text-foreground">Busca Ativa</h2>
				<p className="text-sm text-muted-foreground">
					Visão consolidada dos eventos de busca ativa (Saúde e Assistência
					Social) no recorte filtrado
				</p>
			</div>

			{/* Cards de totais */}
			<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
				<StatCard
					title="Buscas ativas"
					value={totais.buscas}
					description="Total de buscas ativas realizadas"
					icon={<Search className="h-6 w-6" />}
					variant="default"
					isLoading={loading}
				/>
				<StatCard
					title="Participantes com busca ativa"
					value={totais.participantes}
					description="Membros distintos com busca ativa no mês mais recente da tabela"
					icon={<UserCheck className="h-6 w-6" />}
					variant="success"
					isLoading={loading}
				/>
			</div>

			{/* Evolução mensal — SMAS */}
			{showSMAS && (
				<Card className="relative">
					<CardHeader>
						<CardTitle className="text-lg">
							Evolução Mensal — SMAS
						</CardTitle>
						<CardDescription>
							Buscas ativas da Assistência Social (desde Mar/26)
						</CardDescription>
					</CardHeader>
					<CardContent>
						{temEvolucaoSMAS ? (
							<ResponsiveContainer width="100%" height={300}>
								<LineChart data={evolucaoSMAS}>
									<CartesianGrid strokeDasharray="3 3" />
									<XAxis dataKey="mes_label" interval={1} />
									<YAxis allowDecimals={false} />
									<Tooltip />
									<Line
										type="monotone"
										dataKey="smas"
										name="SMAS"
										stroke={COR_SMAS}
										strokeWidth={2}
										dot={false}
									/>
								</LineChart>
							</ResponsiveContainer>
						) : (
							<EmptyChart height={300} />
						)}
					</CardContent>
				</Card>
			)}

			{/* Resultado SMAS por mês */}
			{showSMAS && (
				<Card className="relative">
					<CardHeader>
						<CardTitle className="text-xl">Resultado SMAS por Mês</CardTitle>
						<CardDescription>
							Buscas ativas da Assistência Social por desfecho (desde Mar/26)
						</CardDescription>
					</CardHeader>
					<CardContent>
						{temDesfecho ? (
							<ResponsiveContainer width="100%" height={320}>
								<BarChart data={desfecho.data}>
									<CartesianGrid strokeDasharray="3 3" />
									<XAxis dataKey="mes_label" />
									<YAxis allowDecimals={false} />
									<Tooltip />
									<Legend />
									{desfecho.desfechos.map((d, index) => (
										<Bar
											key={d}
											dataKey={d}
											stackId="a"
											fill={corDesfecho(d, index)}
										/>
									))}
								</BarChart>
							</ResponsiveContainer>
						) : (
							<EmptyChart height={320} />
						)}
					</CardContent>
				</Card>
			)}

			{/* Tipos de busca */}
			{showSMAS && (
				<CategoriaDonut
					title="Tipos de Busca — SMAS"
					description="Buscas da Assistência por tipo"
					data={data.smas_tipos}
				/>
			)}
		</div>
	);
}
