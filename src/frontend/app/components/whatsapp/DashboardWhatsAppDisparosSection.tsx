/** biome-ignore-all lint/suspicious/noArrayIndexKey: necessary in that context */
"use client";

import { AlertTriangle, CheckCircle2, Send, Target, Users } from "lucide-react";
import {
	Bar,
	BarChart,
	CartesianGrid,
	Cell,
	Legend,
	Pie,
	PieChart,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { StatCard } from "@/app/components/StatCard";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/app/components/ui/card";
import type { DisparosDashboard } from "@/app/types";

/**
 * Seção "Disparos WhatsApp" do dashboard (visão geral): KPIs, distribuição de
 * status e ranking de campanhas com segmentos por status, a partir de
 * `endpoint_whatsapp_disparo` (agregados no backend, snapshot dos últimos 30
 * dias).
 *
 * A "Taxa de Entrega" é efetiva: conta ENTREGUE + RESPONDIDO + LIDO sobre o
 * total de disparos com status (ler/responder implica entrega). Renderiza
 * `null` quando o backend degrada (campo nulo) ou quando não há nenhum
 * disparo no escopo.
 */

const STATUS_COLORS: Record<string, string> = {
	ENTREGUE: "#FD7C45FF",
	RESPONDIDO: "#626063FF",
	LIDO: "#AD5E59FF",
	ENVIADO: "#FABA62FF",
	SEM_RETORNO: "#FFFFBBFF",
	FALHOU: "#BBDADCFF",
};

const STATUS_LABELS: Record<string, string> = {
	ENTREGUE: "Entregue",
	RESPONDIDO: "Respondido",
	LIDO: "Lido",
	ENVIADO: "Enviado",
	SEM_RETORNO: "Sem retorno",
	FALHOU: "Falhou",
};

const STATUS_ORDER = [
	"RESPONDIDO",
	"LIDO",
	"ENTREGUE",
	"ENVIADO",
	"SEM_RETORNO",
	"FALHOU",
];

function statusOrderIndex(status?: string | null): number {
	const idx = STATUS_ORDER.indexOf(status ?? "");
	return idx === -1 ? STATUS_ORDER.length : idx;
}

function statusLabel(status?: string | null): string {
	if (!status) return "Sem status";
	return STATUS_LABELS[status] ?? status;
}

function EmptyState({ message }: { message: string }) {
	return (
		<div className="flex items-center justify-center h-64 text-muted-foreground">
			<div className="text-center">
				<Send className="h-12 w-12 mx-auto mb-4 opacity-50" />
				<p className="text-lg font-medium">Sem dados</p>
				<p className="text-sm mt-2">{message}</p>
			</div>
		</div>
	);
}

export function DashboardWhatsAppDisparosSection({
	disparos,
	loading = false,
}: {
	disparos?: DisparosDashboard | null;
	loading?: boolean;
}) {
	if (!disparos) return null;
	if ((disparos.alcancados ?? 0) === 0 && (disparos.total_30d ?? 0) === 0) {
		return null;
	}

	const statusData = (disparos.status_distribuicao ?? [])
		.filter((s) => (s.total ?? 0) > 0)
		.sort((a, b) => statusOrderIndex(a.status) - statusOrderIndex(b.status))
		.map((s) => ({
			name: statusLabel(s.status),
			value: s.total ?? 0,
			color: STATUS_COLORS[s.status ?? ""] ?? "#8b5cf6",
		}));

	const jornadas = (disparos.por_jornada ?? []).slice(0, 10).map((j, idx) => {
		const fullName = j.jornada ?? "Campanha não identificada";
		const entry: Record<string, string | number | null> = {
			label: String(idx + 1),
			jornada_full: fullName,
			taxa_falha: j.taxa_falha ?? 0,
		};
		for (const s of j.status_distribuicao ?? []) {
			if (s.status) entry[s.status] = s.total ?? 0;
		}
		return entry;
	});

	return (
		<div className="space-y-6">
			<div className="space-y-2">
				<h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
					<Send className="h-6 w-6 text-primary" />
					Disparos WhatsApp
				</h2>
				<p className="text-sm text-muted-foreground">
					Comunicação com participantes nos últimos 30 dias
				</p>
			</div>

			<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
				<StatCard
					title="Participantes Alcançados"
					value={disparos.alcancados ?? 0}
					description="participantes com disparo em 30d"
					icon={<Users className="h-6 w-6" />}
					variant="default"
					isLoading={loading}
				/>
				<StatCard
					title="Cobertura"
					value={`${(disparos.cobertura_percentual ?? 0).toFixed(1)}%`}
					description="dos participantes do escopo"
					icon={<Target className="h-6 w-6" />}
					variant="success"
					isLoading={loading}
				/>
				<StatCard
					title="Taxa de Entrega"
					value={`${(disparos.taxa_entrega ?? 0).toFixed(1)}%`}
					description={`${(disparos.entregues_30d ?? 0).toLocaleString("pt-BR")} entregas confirmadas (30d)`}
					icon={<CheckCircle2 className="h-6 w-6" />}
					variant="success"
					isLoading={loading}
				/>
				<StatCard
					title="Taxa de Falha"
					value={`${(disparos.taxa_falha ?? 0).toFixed(1)}%`}
					description={`${(disparos.falhas_30d ?? 0).toLocaleString("pt-BR")} disparos falharam (30d)`}
					icon={<AlertTriangle className="h-6 w-6" />}
					variant="destructive"
					isLoading={loading}
				/>
			</div>

			<div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
				<Card className="relative">
					{loading && <div className="loading-overlay" />}
					<CardHeader>
						<CardTitle className="text-xl">Status dos Disparos</CardTitle>
						<CardDescription>
							{(disparos.engajados ?? 0).toLocaleString("pt-BR")} participantes
							responderam ou leram a mensagem
						</CardDescription>
					</CardHeader>
					<CardContent>
						{statusData.length > 0 ? (
							<div className="space-y-4">
								<ResponsiveContainer width="100%" height={320}>
									<PieChart margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
										<Pie
											data={statusData}
											cx="50%"
											cy="50%"
											innerRadius={70}
											outerRadius={150}
											dataKey="value"
											nameKey="name"
											startAngle={90}
											endAngle={450}
											stroke="#424847FF"
										>
											{statusData.map((entry, index) => (
												<Cell key={`cell-${index}`} fill={entry.color} />
											))}
										</Pie>
										<Tooltip
											content={({ active, payload }) => {
												if (active && payload && payload.length) {
													const d = payload[0];
													return (
														<div className="bg-background border rounded-lg p-3 shadow-lg">
															<p className="font-semibold mb-1">{d.name}</p>
															<p className="text-sm">
																{(d.value as number).toLocaleString("pt-BR")}{" "}
																disparos
															</p>
														</div>
													);
												}
												return null;
											}}
										/>
									</PieChart>
								</ResponsiveContainer>
								<div className="space-y-2 px-4">
									{statusData.map((item, index) => {
										const total = statusData.reduce(
											(acc, i) => acc + i.value,
											0,
										);
										const percent =
											total > 0
												? ((item.value / total) * 100).toFixed(1)
												: "0.0";
										return (
											<div
												key={index}
												className="flex items-center justify-between text-sm"
											>
												<div className="flex items-center gap-2">
													<div
														className="w-3 h-3 rounded-full flex-shrink-0"
														style={{ backgroundColor: item.color }}
													/>
													<span>{item.name}</span>
												</div>
												<span className="font-medium">
													{item.value.toLocaleString("pt-BR")} ({percent}%)
												</span>
											</div>
										);
									})}
								</div>
							</div>
						) : (
							<EmptyState message="Nenhum status de disparo no período" />
						)}
					</CardContent>
				</Card>

				<Card className="relative flex flex-col h-full">
					{loading && <div className="loading-overlay" />}
					<CardHeader>
						<CardTitle className="text-xl">Disparos por Campanha</CardTitle>
						<CardDescription>
							Participantes alcançados por campanha, segmentados por status (top
							10)
						</CardDescription>
					</CardHeader>
					<CardContent className="flex-1 flex flex-col">
						{jornadas.length > 0 ? (
							<>
								<div className="flex-1 min-h-[380px]">
									<ResponsiveContainer width="100%" height="100%">
										<BarChart
											data={jornadas}
											margin={{ top: 5, right: 24, left: 10, bottom: 5 }}
										>
											<CartesianGrid strokeDasharray="3 3" vertical={false} />
											<XAxis
												type="category"
												dataKey="label"
												interval={0}
												tick={{ fontSize: 12 }}
											/>
											<YAxis type="number" />
											<Tooltip
												cursor={{ fill: "transparent" }}
												content={({ active, payload }) => {
													if (active && payload && payload.length) {
														const d = payload[0].payload;
														const segments = STATUS_ORDER.filter(
															(s) => (d[s] ?? 0) > 0,
														).map((s) => ({
															label: STATUS_LABELS[s] ?? s,
															value: d[s] as number,
														}));
														return (
															<div className="bg-background border rounded-lg p-3 shadow-lg">
																<p className="font-semibold mb-2">
																	{d.jornada_full ?? d.label}
																</p>
																{segments.map((seg) => (
																	<p key={seg.label} className="text-sm">
																		{seg.label}:{" "}
																		{seg.value.toLocaleString("pt-BR")}
																	</p>
																))}
																<p className="text-sm text-muted-foreground mt-1">
																	Taxa de falha:{" "}
																	{(d.taxa_falha ?? 0).toFixed(1)}%
																</p>
															</div>
														);
													}
													return null;
												}}
											/>
											<Legend
												labelStyle={{ color: "var(--foreground)" }}
												itemSorter={(item) =>
													statusOrderIndex(
														typeof item.dataKey === "string"
															? item.dataKey
															: undefined,
													)
												}
											/>
											{STATUS_ORDER.map((status) => (
												<Bar
													key={status}
													dataKey={status}
													stackId="a"
													name={STATUS_LABELS[status] ?? status}
													fill={STATUS_COLORS[status] ?? "#8b5cf6"}
												/>
											))}
										</BarChart>
									</ResponsiveContainer>
								</div>
								<div className="space-y-1.5 mt-4 px-2 shrink-0">
									{jornadas.map((entry, idx) => (
										<div key={idx} className="flex items-center gap-2 text-sm">
											<span className="w-5 h-5 rounded bg-muted flex items-center justify-center text-xs font-medium shrink-0">
												{idx + 1}
											</span>
											<span>{entry.jornada_full}</span>
										</div>
									))}
								</div>
							</>
						) : (
							<EmptyState message="Nenhuma campanha de disparo no período" />
						)}
					</CardContent>
				</Card>
			</div>
		</div>
	);
}
