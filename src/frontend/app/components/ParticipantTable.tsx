"use client";

import { memo } from "react";
import { Participante, SortOrder } from "../types";
import { Badge } from "@/app/components/ui/badge";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";

type BadgeVariant = "outline" | "default" | "secondary" | "destructive" | "warning" | "success";

interface ParticipantTableProps {
  data: Participante[];
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => BadgeVariant;
  isLoading?: boolean;
  sortBy?: string | null;
  sortOrder?: SortOrder;
  onSort?: (column: string) => void;
}

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

const SortIcon = ({ column, sortBy, sortOrder }: { column: string; sortBy?: string | null; sortOrder?: SortOrder }) => {
  if (sortBy !== column) {
    return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />;
  }
  return sortOrder === "asc"
    ? <ArrowUp className="h-3 w-3 ml-1" />
    : <ArrowDown className="h-3 w-3 ml-1" />;
};

const capitalizeSituacao = (situacao?: string) => {
  if (!situacao) return "-";
  return situacao.charAt(0).toUpperCase() + situacao.slice(1).toLowerCase();
};

const renderGrupo = (grupo?: string) => {
	if (!grupo) return "-";
	const lower = grupo.toLowerCase();
	if (lower.includes("crian") || lower.includes("criança")) return "👶 Criança";
	if (lower.includes("gestante")) return "🤰 Gestante";
	if (lower.includes("puérpera")) return "🤱 Puérpera";
	return grupo;
};

const getTotalColor = (fracao?: string) => {
  if (!fracao) return "text-muted-foreground";
  const [num, den] = fracao.split('/').map(Number);
  if (isNaN(num) || isNaN(den) || den === 0) return "text-muted-foreground";
  const percent = (num / den) * 100;
  if (percent === 100) return "text-green-600 font-semibold";
  if (percent >= 60) return "text-amber-600 font-semibold";
  return "text-red-600 font-semibold";
};

const MIN_TABLE_WIDTH = 1000;

export const ParticipantTable = memo(({
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

	const visibleColumns = SORTABLE_COLUMNS;

  const handleHeaderClick = (column: string) => {
    if (onSort) {
      onSort(column);
    }
  };

  return (
    <div
      className="relative rounded-lg border bg-card"
      style={{ maxWidth: '100%', overflow: 'hidden' }}
    >
      {isLoading && (
        <div className="absolute inset-0 bg-background/50 z-10 flex items-center justify-center">
          <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      )}

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
									{visibleColumns.map((col) => {
										const key = col.key;

										if (key === "nome")
											return (
												<td
													key={key}
													className="px-3 py-3 font-medium max-w-[200px]"
												>
													<span className="line-clamp-2">
														{participant.nome || "-"}
													</span>
												</td>
											);

										if (key === "cpf")
											return (
												<td
													key={key}
													className="px-3 py-3 font-mono whitespace-nowrap"
												>
													{participant.cpf || "-"}
												</td>
											);

										if (key === "grupo")
											return (
												<td key={key} className="px-3 py-3 whitespace-nowrap">
													{renderGrupo(participant.grupo)}
												</td>
											);

										if (key === "bairro")
											return (
												<td key={key} className="px-3 py-3 max-w-[150px]">
													<span className="line-clamp-2">
														{participant.bairro || "-"}
													</span>
												</td>
											);

										if (key === "idade")
											return (
												<td
													key={key}
													className="px-3 py-3 text-center whitespace-nowrap"
												>
													{participant.idade != null
														? `${participant.idade} anos`
														: "-"}
												</td>
											);

										if (key === "status")
											return (
												<td
													key={key}
													className="px-3 py-3 text-center capitalize whitespace-nowrap"
												>
													{participant.status || "-"}
												</td>
											);

										if (key.includes("_fracao")) {
											const value = (participant as any)[key];
											const hasTotalFracao = visibleColumns.some(
												(c) => c.key === "total_fracao",
											);
											const shouldApplyColor = hasTotalFracao
												? key === "total_fracao"
												: true;
											const colorClass = shouldApplyColor
												? getTotalColor(value)
												: "";
											return (
												<td
													key={key}
													className={`px-3 py-3 text-center font-mono whitespace-nowrap ${colorClass}`}
												>
													{value || "-"}
												</td>
											);
										}

										if (key === "situacao")
											return (
												<td
													key={key}
													className="px-3 py-3 text-center whitespace-nowrap"
												>
													<Badge
														variant={getBadgeVariant(participant.situacao)}
														className="text-xs"
													>
														{capitalizeSituacao(participant.situacao)}
													</Badge>
												</td>
											);

										return (
											<td key={key} className="px-3 py-3">
												-
											</td>
										);
									})}
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
