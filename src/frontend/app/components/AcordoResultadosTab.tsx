import {
	Activity,
	AlertTriangle,
	BookOpen,
	CheckCircle,
	Home,
	Loader2,
	RefreshCw,
	Target,
	Users,
} from "lucide-react";
import { memo, useState } from "react";
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
	ReferenceLine,
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
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/app/components/ui/select";
import type { AcordoDistribuicaoPublico, AcordoResultados } from "../types";
import { ProtocoloCard } from "./ProtocoloCard";
import { StatCard } from "./StatCard";

const PALETA_CATEGORIAS = [
	"#F81B02FF",
	"#FC7715FF",
	"#AFBF41FF",
	"#50C49FFF",
	"#3B95C4FF",
	"#B560D4FF",
];

const CORES_GRUPO: Record<string, string> = {
	Criança: "#50C49FFF",
};

const CORES_CARTAO_PIC: Record<string, string> = {
	Retirado: "#7AD151FF",
	"Não retirado": "#FC7715FF",
};

const CORES_BOLSA_FAMILIA: Record<string, string> = {
	Sim: "#7AD151FF",
	Não: "#F81B02FF",
	"Não informado": "#FC7715FF",
};

const CORES_SITUACAO: Record<string, string> = {
	Ativos: "#7AD151FF",
	Inativos: "#F81B02FF",
};

type SecretariaView = "TODAS" | "SMAS" | "SME" | "SMS";

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

const DistribuicaoPie = ({
	title,
	data,
	nameKey = "categoria",
	height = 440,
	palette = PALETA_CATEGORIAS,
	categoryColors,
}: {
	title: string;
	data: Array<{ categoria?: string; motivo?: string; total?: number }>;
	nameKey?: string;
	height?: number;
	palette?: string[];
	categoryColors?: Record<string, string>;
}) => {
	const cores = paletaPorQuantidade(data.length, palette);

	return (
		<Card>
			<CardHeader>
				<CardTitle>{title}</CardTitle>
			</CardHeader>
			<CardContent>
				<ResponsiveContainer width="100%" height={height}>
					<PieChart>
						<Pie
							data={data}
							dataKey={(entry: { total?: number }) =>
								Math.sqrt(entry.total ?? 0)
							}
							nameKey={nameKey}
							cx="50%"
							cy="50%"
							outerRadius={160}
							innerRadius={80}
						>
							{data.map((entry, index) => {
								const nome = String(
									entry[nameKey as "categoria" | "motivo"] ?? "",
								);
								return (
									<Cell
										key={`cell-${index}`}
										fill={categoryColors?.[nome] ?? cores[index % cores.length]}
									/>
								);
							})}
						</Pie>
						<Tooltip
							formatter={(value, name, item) => [
								item?.payload?.total ?? value,
								name,
							]}
						/>
						<Legend />
					</PieChart>
				</ResponsiveContainer>
			</CardContent>
		</Card>
	);
};

const logTicks = (max: number): number[] => {
	const ticks: number[] = [];
	for (let v = 10; v <= max; v *= 10) {
		ticks.push(v);
	}
	return ticks;
};

const DistribuicaoBarrasHorizontais = ({
	title,
	data,
	color = "#3b82f6",
	height,
	scaleLog = false,
	palette,
}: {
	title: string;
	data: AcordoDistribuicaoPublico[];
	color?: string;
	height?: number;
	scaleLog?: boolean;
	palette?: string[];
}) => (
	<Card>
		<CardHeader>
			<CardTitle>{title}</CardTitle>
		</CardHeader>
		<CardContent>
			<ResponsiveContainer
				width="100%"
				height={height ?? Math.max(300, data.length * 32)}
			>
				<BarChart
					data={data}
					layout="vertical"
					margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
				>
					<CartesianGrid strokeDasharray="3 3" />
					<XAxis
						type="number"
						scale={scaleLog ? "log" : "linear"}
						domain={scaleLog ? [10, "dataMax"] : [0, "auto"]}
						allowDecimals={false}
						ticks={
							scaleLog
								? logTicks(Math.max(...data.map((d) => d.total)))
								: undefined
						}
					/>
					<YAxis type="category" dataKey="categoria" width={140} />
					<Tooltip />
					<Bar dataKey="total" name="Participantes" fill={color}>
						{palette
							? data.map((d, i) => (
									<Cell key={d.categoria} fill={palette[i % palette.length]} />
								))
							: null}
					</Bar>
				</BarChart>
			</ResponsiveContainer>
		</CardContent>
	</Card>
);

interface AcordoResultadosTabProps {
	data: AcordoResultados | null;
	loading?: boolean;
	onRefresh?: () => void;
}

const AcordoResultadosTabComponent = ({
	data,
	loading = false,
	onRefresh,
}: AcordoResultadosTabProps) => {
	const [secretariaView, setSecretariaView] = useState<SecretariaView>("TODAS");

	const showSMAS = secretariaView === "TODAS" || secretariaView === "SMAS";
	const showSME = secretariaView === "TODAS" || secretariaView === "SME";
	const showSMS = secretariaView === "TODAS" || secretariaView === "SMS";

	if (loading && !data) {
		return (
			<div className="flex flex-col items-center justify-center py-16 text-center">
				<Loader2 className="h-10 w-10 animate-spin text-primary mb-4" />
				<p className="text-base font-semibold">
					Carregando indicadores do acordo...
				</p>
				<p className="text-sm text-muted-foreground mt-2 max-w-sm">
					Agregando métricas dosparticipantes até 31-03-2026 por status, safra,
					protocolo e dimensão.
				</p>
			</div>
		);
	}

	if (!data) {
		return (
			<div className="text-center py-12">
				<p className="text-muted-foreground">Nenhum dado disponível</p>
			</div>
		);
	}

	const protocolosPorSecretaria = {
		SMAS:
			data.protocolos?.filter((p) => p.protocolo_secretaria === "SMAS") || [],
		SME: data.protocolos?.filter((p) => p.protocolo_secretaria === "SME") || [],
		SMS: data.protocolos?.filter((p) => p.protocolo_secretaria === "SMS") || [],
	};

	return (
		<div className="space-y-8">
			{/* ===================================================================== */}
			{/* CABEÇALHO + SELETOR DE SECRETARIA */}
			{/* ===================================================================== */}
			<div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
				<div className="space-y-1">
					<h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
						<Target className="h-6 w-6 text-primary" />
						Monitoramento
					</h2>
					<p className="text-sm text-muted-foreground">
						Dados do programa considerando desde o início até 31 de março de
						2026.
					</p>
				</div>
				<div className="flex items-center gap-2">
					<Select
						value={secretariaView}
						onValueChange={(value) =>
							setSecretariaView(value as SecretariaView)
						}
					>
						<SelectTrigger className="w-50">
							<SelectValue placeholder="Visão por secretaria" />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="TODAS">Todas as secretarias</SelectItem>
							<SelectItem value="SMAS">Assistência Social</SelectItem>
							<SelectItem value="SME">Educação</SelectItem>
							<SelectItem value="SMS">Saúde</SelectItem>
						</SelectContent>
					</Select>
					{onRefresh && (
						<button
							type="button"
							onClick={onRefresh}
							className="inline-flex items-center justify-center h-9 px-3 rounded-md border border-input bg-background text-sm hover:bg-accent hover:text-accent-foreground"
						>
							<RefreshCw className="h-4 w-4 mr-1.5" />
							Atualizar
						</button>
					)}
				</div>
			</div>

			{/* ===================================================================== */}
			{/* SEÇÃO 1: REGULARIDADE POR STATUS */}
			{/* ===================================================================== */}
			<div className="space-y-6">
				<div className="space-y-3">
					<h2 className="text-xl font-bold text-foreground flex items-center gap-2">
						<Users className="h-5 w-5 text-primary" />
						Quem ainda está no programa
					</h2>
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
						<StatCard
							title="Total de Ativos"
							value={(data.ativos.total || 0).toLocaleString("pt-BR")}
							description="Participantes ativos nos cohorts do acordo"
							icon={<Users className="h-6 w-6" />}
							variant="default"
							isLoading={loading}
						/>
						<StatCard
							title="Ativos Regulares"
							value={`${(data.ativos.percentual_regular || 0).toFixed(1)}%`}
							description={`${(data.ativos.regulares || 0).toLocaleString("pt-BR")} de ${(data.ativos.total || 0).toLocaleString("pt-BR")} ativos`}
							icon={<CheckCircle className="h-6 w-6" />}
							variant="success"
							isLoading={loading}
						/>
						<StatCard
							title="Ativos Irregulares"
							value={`${(data.ativos.percentual_irregular || 0).toFixed(1)}%`}
							description={`${(data.ativos.irregulares || 0).toLocaleString("pt-BR")} de ${(data.ativos.total || 0).toLocaleString("pt-BR")} ativos`}
							icon={<AlertTriangle className="h-6 w-6" />}
							variant="destructive"
							isLoading={loading}
						/>
					</div>
				</div>

				<div className="space-y-3">
					<h2 className="text-xl font-bold text-foreground flex items-center gap-2">
						<AlertTriangle className="h-5 w-5 text-muted-foreground" />
						Quem entrou e já saiu do programa
					</h2>
					<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
						<StatCard
							title="Total de Inativos"
							value={(data.inativos.total || 0).toLocaleString("pt-BR")}
							description="Participantes que saíram do programa"
							icon={<Users className="h-6 w-6" />}
							variant="default"
							isLoading={loading}
						/>
						<StatCard
							title="Inativos Regulares"
							value={`${(data.inativos.percentual_regular || 0).toFixed(1)}%`}
							description={`${(data.inativos.regulares || 0).toLocaleString("pt-BR")} de ${(data.inativos.total || 0).toLocaleString("pt-BR")} inativos`}
							icon={<CheckCircle className="h-6 w-6" />}
							variant="success"
							isLoading={loading}
						/>
						<StatCard
							title="Inativos Irregulares"
							value={`${(data.inativos.percentual_irregular || 0).toFixed(1)}%`}
							description={`${(data.inativos.irregulares || 0).toLocaleString("pt-BR")} de ${(data.inativos.total || 0).toLocaleString("pt-BR")} inativos`}
							icon={<AlertTriangle className="h-6 w-6" />}
							variant="destructive"
							isLoading={loading}
						/>
					</div>
				</div>
			</div>

			{/* ===================================================================== */}
			{/* SEÇÃO 2: CARDS DE PROTOCOLO POR DIMENSÃO */}
			{/* ===================================================================== */}
			{data.protocolos && data.protocolos.length > 0 && (
				<div className="space-y-6">
					<div className="space-y-2">
						<h2 className="text-2xl font-bold text-foreground">
							Protocolos por Dimensão
						</h2>
						<p className="text-sm text-muted-foreground">
							Taxa de regularidade por protocolo nos grupos do acordo
						</p>
					</div>

					{showSMAS && protocolosPorSecretaria.SMAS.length > 0 && (
						<div className="space-y-3">
							<h3 className="text-xl font-bold flex items-center gap-2">
								<Home className="h-5 w-5 text-green-600" />
								Dimensão Assistência Social
							</h3>
							<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
								{protocolosPorSecretaria.SMAS.map((protocolo) => (
									<ProtocoloCard
										key={protocolo.protocolo_id}
										protocolo={protocolo}
										loading={loading}
									/>
								))}
							</div>
						</div>
					)}

					{showSME && protocolosPorSecretaria.SME.length > 0 && (
						<div className="space-y-3">
							<h3 className="text-xl font-bold flex items-center gap-2">
								<BookOpen className="h-5 w-5 text-amber-600" />
								Dimensão Educação
							</h3>
							<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
								{protocolosPorSecretaria.SME.map((protocolo) => (
									<ProtocoloCard
										key={protocolo.protocolo_id}
										protocolo={protocolo}
										loading={loading}
									/>
								))}
							</div>
						</div>
					)}

					{showSMS && protocolosPorSecretaria.SMS.length > 0 && (
						<div className="space-y-3">
							<h3 className="text-xl font-bold flex items-center gap-2">
								<Activity className="h-5 w-5 text-red-600" />
								Dimensão Saúde
							</h3>
							<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
								{protocolosPorSecretaria.SMS.map((protocolo) => (
									<ProtocoloCard
										key={protocolo.protocolo_id}
										protocolo={protocolo}
										loading={loading}
									/>
								))}
							</div>
						</div>
					)}
				</div>
			)}

			{/* ===================================================================== */}
			{/* SEÇÃO 3: EVOLUÇÃO MENSAL (com meta) */}
			{/* ===================================================================== */}
			{data.evolucao_mensal && data.evolucao_mensal.length > 0 && (
				<Card>
					<CardHeader>
						<CardTitle>Evolução Mensal da Regularidade</CardTitle>
						<CardDescription>
							Evolução mensal da completude de protocolos por dimensão nos
							grupos do acordo
						</CardDescription>
					</CardHeader>
					<CardContent>
						<ResponsiveContainer width="100%" height={400}>
							<LineChart
								data={data.evolucao_mensal}
								margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
							>
								<CartesianGrid strokeDasharray="3 3" />
								<XAxis dataKey="mes_label" />
								<YAxis
									domain={[0, 100]}
									label={{
										value: "% Regular",
										angle: -90,
										position: "insideLeft",
										style: { textAnchor: "middle" },
									}}
								/>
								<Tooltip formatter={(value) => `${value}%`} />
								<Legend />
								<ReferenceLine
									y={data.meta_regularidade}
									stroke="#26dc5d"
									strokeDasharray="6 3"
									label={{
										value: `Meta ${data.meta_regularidade}%`,
										position: "insideTopRight",
										fill: "#26dc5d",
										fontSize: 12,
									}}
								/>
								{showSMAS && (
									<Line
										type="monotone"
										dataKey="assistencia"
										name="Protocolos da Assistência"
										stroke="#10b981"
										strokeWidth={2}
										dot={false}
									/>
								)}
								{showSME && (
									<Line
										type="monotone"
										dataKey="educacao"
										name="Protocolos da Educação"
										stroke="#f59e0b"
										strokeWidth={2}
										dot={false}
									/>
								)}
								{showSMS && (
									<Line
										type="monotone"
										dataKey="saude"
										name="Protocolos da Saúde"
										stroke="#ef4444"
										strokeWidth={2}
										dot={false}
									/>
								)}
								<Line
									type="monotone"
									dataKey="todos"
									name="Todos os Protocolos"
									stroke="#8b5cf6"
									strokeWidth={2}
									dot={false}
								/>
							</LineChart>
						</ResponsiveContainer>
					</CardContent>
				</Card>
			)}

			{/* ===================================================================== */}
			{/* SEÇÃO 4: DISTRIBUIÇÕES DE PÚBLICO (PIZZAS) */}
			{/* ===================================================================== */}
			<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
				{data.distribuicao_grupo && data.distribuicao_grupo.length > 0 && (
					<DistribuicaoPie
						title="Distribuição por Grupo"
						data={data.distribuicao_grupo}
						categoryColors={CORES_GRUPO}
					/>
				)}

				{data.distribuicao_cartao_pic &&
					data.distribuicao_cartao_pic.length > 0 && (
						<DistribuicaoPie
							title="Distribuição por Cartão PIC"
							data={data.distribuicao_cartao_pic}
							categoryColors={CORES_CARTAO_PIC}
						/>
					)}

				{data.distribuicao_bolsa_familia &&
					data.distribuicao_bolsa_familia.length > 0 && (
						<DistribuicaoPie
							title="Distribuição por Bolsa Família"
							data={data.distribuicao_bolsa_familia}
							categoryColors={CORES_BOLSA_FAMILIA}
						/>
					)}
			</div>

			{/* ===================================================================== */}
			{/* SEÇÃO 5: DISTRIBUIÇÕES POR RAÇA E REGIÃO ADMINISTRATIVA (BARRAS HORIZONTAIS, LINHAS SEPARADAS) */}
			{/* ===================================================================== */}
			{data.distribuicao_raca && data.distribuicao_raca.length > 0 && (
				<DistribuicaoBarrasHorizontais
					title="Distribuição por Raça"
					data={data.distribuicao_raca}
					palette={PALETA_CATEGORIAS}
					scaleLog
				/>
			)}

			{data.distribuicao_ra && data.distribuicao_ra.length > 0 && (
				<DistribuicaoBarrasHorizontais
					title="Distribuição por Região Administrativa"
					data={data.distribuicao_ra}
					color="#3B95C4FF"
				/>
			)}

			{/* ===================================================================== */}
			{/* SEÇÃO 6: MOTIVOS DE SAÍDA + SITUAÇÃO (2 colunas) */}
			{/* ===================================================================== */}
			<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
				{data.motivos_saida && data.motivos_saida.length > 0 && (
					<DistribuicaoPie
						title="Motivos de Saída"
						data={data.motivos_saida}
						nameKey="motivo"
					/>
				)}

				{((data.ativos?.total ?? 0) > 0 || (data.inativos?.total ?? 0) > 0) && (
					<DistribuicaoPie
						title="Participantes por Situação"
						data={[
							{
								categoria: "Ativos",
								total: data.ativos?.total ?? 0,
							},
							{
								categoria: "Inativos",
								total: data.inativos?.total ?? 0,
							},
						]}
						categoryColors={CORES_SITUACAO}
					/>
				)}
			</div>
		</div>
	);
};

export const AcordoResultadosTab = memo(AcordoResultadosTabComponent);
