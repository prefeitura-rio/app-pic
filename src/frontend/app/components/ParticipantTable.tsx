/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { memo } from "react";
import { Badge } from "@/app/components/ui/badge";
import type { Participante, SortOrder } from "../types";

type BadgeVariant =
	| "outline"
	| "default"
	| "secondary"
	| "destructive"
	| "warning"
	| "success";

interface ParticipantTableProps {
	data: Participante[];
	onRowClick: (participant: Participante) => void;
	getBadgeVariant: (situacao?: string) => BadgeVariant;
	isLoading?: boolean;
	sortBy?: string | null;
	sortOrder?: SortOrder;
	onSort?: (column: string) => void;
}

// Configuração base das colunas (key corresponde ao sort_by do backend)
const SORTABLE_COLUMNS = [
	{ key: "nome", label: "Nome", align: "left" as const },
	{ key: "cpf", label: "CPF", align: "left" as const },
	{ key: "grupo", label: "Grupo", align: "left" as const },
	{ key: "bairro", label: "Bairro", align: "left" as const },
	{ key: "idade", label: "Idade", align: "center" as const },
	{ key: "status", label: "Status", align: "center" as const },
	{ key: "total_fracao", label: "Total", align: "center" as const },
	{ key: "assistencia_fracao", label: "Assist.", align: "center" as const },
	{ key: "educacao_fracao", label: "Educ.", align: "center" as const },
	{ key: "saude_fracao", label: "Saúde", align: "center" as const },
	{ key: "situacao", label: "Situação", align: "center" as const },
];

// Componente de ícone de ordenação
const SortIcon = ({
	column,
	sortBy,
	sortOrder,
}: {
	column: string;
	sortBy?: string | null;
	sortOrder?: SortOrder;
}) => {
	if (sortBy !== column) {
		return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />;
	}
	return sortOrder === "asc" ? (
		<ArrowUp className="h-3 w-3 ml-1" />
	) : (
		<ArrowDown className="h-3 w-3 ml-1" />
	);
};

// Função para capitalizar situação
const capitalizeSituacao = (situacao?: string) => {
	if (!situacao) return "-";
	return situacao.charAt(0).toUpperCase() + situacao.slice(1).toLowerCase();
};

// Função para renderizar o grupo com emoji
const renderGrupo = (grupo?: string) => {
	if (!grupo) return "-";
	const lower = grupo.toLowerCase();
	if (lower.includes("crian") || lower.includes("criança")) return "👶 Criança";
	if (lower.includes("gestante")) return "🤰 Gestante";
	return grupo;
};

const getTotalColor = (fracao?: string) => {
	if (!fracao) return "text-muted-foreground";
	const [num, den] = fracao.split("/").map(Number);
	if (isNaN(num) || isNaN(den) || den === 0) return "text-muted-foreground";
	const percent = (num / den) * 100;
	if (percent === 100) return "text-green-600 font-semibold";
	if (percent >= 60) return "text-amber-600 font-semibold";
	return "text-red-600 font-semibold";
};

// Largura mínima total da tabela para garantir scroll horizontal
const MIN_TABLE_WIDTH = 1000;

export const ParticipantTable = memo(
	({
		data,
		onRowClick,
		getBadgeVariant,
		isLoading,
		sortBy,
		sortOrder = "asc",
		onSort,
	}: ParticipantTableProps) => {
		if (!data || !Array.isArray(data) || data.length === 0) {
			return null;
		}

		// Filter columns - mostra apenas colunas que existem nos dados retornados do backend
		// Backend já dropa colunas sensíveis (lat/long) para não-super-admins
		const visibleColumns = SORTABLE_COLUMNS.filter((col) => {
			if (data.length === 0) return true;
			const firstRow = data[0] as any;
			// Mostrar coluna apenas se existir nos dados E não for null/undefined
			return firstRow[col.key] !== undefined && firstRow[col.key] !== null;
		});

		const handleHeaderClick = (column: string) => {
			if (onSort) {
				onSort(column);
			}
		};

		return (
			<div
				className="relative rounded-lg border bg-card"
				style={{ maxWidth: "100%", overflow: "hidden" }}
			>
				{/* Loading overlay */}
				{isLoading && (
					<div className="absolute inset-0 bg-background/50 z-10 flex items-center justify-center">
						<div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
					</div>
				)}

				{/* Wrapper com scroll horizontal */}
				<div
					style={{
						display: "block",
						maxWidth: "100%",
						overflowX: "auto",
						overflowY: "hidden",
					}}
				>
					<table
						style={{ minWidth: MIN_TABLE_WIDTH, width: "100%" }}
						className="text-sm border-collapse"
					>
						<thead className="bg-muted/50">
							<tr className="border-b">
								{visibleColumns.map((col) => (
									<th
										key={col.key}
										className={`px-3 py-3 text-${col.align} font-medium text-muted-foreground whitespace-nowrap cursor-pointer hover:bg-muted/80 transition-colors select-none`}
										onClick={() => handleHeaderClick(col.key)}
									>
										<div
											className={`flex items-center ${col.align === "center" ? "justify-center" : ""}`}
										>
											{col.label}
											<SortIcon
												column={col.key}
												sortBy={sortBy}
												sortOrder={sortOrder}
											/>
										</div>
									</th>
								))}
							</tr>
						</thead>
						<tbody>
							{data.map((participant, index) => (
								<tr
									key={`${participant.cpf}-${index}`}
									className="border-b last:border-b-0 hover:bg-muted/50 cursor-pointer transition-colors"
									onClick={() => onRowClick(participant)}
								>
									<td className="px-3 py-3 font-medium max-w-[200px]">
										<span className="line-clamp-2">
											{participant.nome || "-"}
										</span>
									</td>
									<td className="px-3 py-3 font-mono whitespace-nowrap">
										{participant.cpf || "-"}
									</td>
									<td className="px-3 py-3 whitespace-nowrap">
										{renderGrupo(participant.grupo)}
									</td>
									<td className="px-3 py-3 max-w-[150px]">
										<span className="line-clamp-2">
											{participant.bairro || "-"}
										</span>
									</td>
									<td className="px-3 py-3 text-center whitespace-nowrap">
										{participant.idade != null
											? `${participant.idade} anos`
											: "-"}
									</td>
									<td className="px-3 py-3 text-center capitalize whitespace-nowrap">
										{participant.status || "-"}
									</td>

									{/* Renderizar colunas de protocolos dinamicamente baseado em visibleColumns */}
									{visibleColumns
										.filter((col) => col.key.includes("_fracao"))
										.map((col) => {
											const value = (participant as any)[col.key];
											// Aplicar cores:
											// - Se existe total_fracao: apenas ela tem cores
											// - Se NÃO existe total_fracao (usuário de secretaria): a coluna específica tem cores
											const hasTotalFracao = visibleColumns.some(
												(c) => c.key === "total_fracao",
											);
											const shouldApplyColor = hasTotalFracao
												? col.key === "total_fracao" // Admin: só total tem cor
												: true; // Secretaria específica: qualquer fração tem cor
											const colorClass = shouldApplyColor
												? getTotalColor(value)
												: "";
											return (
												<td
													key={col.key}
													className={`px-3 py-3 text-center font-mono whitespace-nowrap ${colorClass}`}
												>
													{value || "-"}
												</td>
											);
										})}

									<td className="px-3 py-3 text-center whitespace-nowrap">
										<Badge
											variant={getBadgeVariant(participant.situacao)}
											className="text-xs"
										>
											{capitalizeSituacao(participant.situacao)}
										</Badge>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</div>
		);
	},
);

ParticipantTable.displayName = "ParticipantTable";
