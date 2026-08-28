/** biome-ignore-all lint/suspicious/noArrayIndexKey: to be refatored */
import {
	AlertCircle,
	CheckCircle2,
	ChevronDown,
	ChevronLeft,
	ChevronRight,
	Eye,
	MapPin,
	Search,
	Users,
} from "lucide-react";
import { memo, useCallback, useMemo } from "react";
import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
} from "@/app/components/ui/card";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/app/components/ui/collapsible";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@/app/components/ui/dialog";
import { Separator } from "@/app/components/ui/separator";
import { Skeleton } from "@/app/components/ui/skeleton";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/app/components/ui/tooltip";
import type {
	GeospatialFilterOptions,
	GeospatialFilters,
	GeospatialLayer,
	PaginationMeta,
	Participante,
	ParticipanteListItem,
	ParticipantFilters,
	SmartFilterOptions,
	SortOrder,
} from "../types";
import { FilterCard } from "./FilterCard";
import { GeospatialMapView } from "./GeospatialMapView";
import { ParticipantTable } from "./ParticipantTable";
import { ProtocoloItem } from "./ProtocoloItem";

// Função para renderizar o grupo com emoji (consistente com VirtualizedParticipantTable)
const renderGrupo = (grupo?: string) => {
	if (!grupo) return "-";
	const lower = grupo.toLowerCase();
	if (lower.includes("crian") || lower.includes("criança")) return "👶 Criança";
	if (lower.includes("gestante")) return "🤰 Gestante";
	return grupo;
};

// Função para renderizar grupo completo (com tipo Bolsa Família se aplicável)
const renderGrupoCompleto = (grupo?: string) => {
	if (!grupo) return "-";
	const grupoBase = renderGrupo(grupo);
	// Adicionar " • Bolsa Família" se o grupo original contiver "bf" ou "bolsa"
	const lower = grupo.toLowerCase();
	if (lower.includes("bf") || lower.includes("bolsa")) {
		return `${grupoBase} • Bolsa Família`;
	}
	return grupoBase;
};

// Componente helper para exibir equipamento com badge de origem
const EquipamentoField = ({
	label,
	value,
	source,
	isEquipeSaude = false,
	secretaria, // "SMS" (VitaCare) | "SME" (SGRC) | "SMAS"
}: {
	label: string;
	value?: string | null;
	source?: string | null;
	isEquipeSaude?: boolean; // true para Equipe, Médicos, Enfermeiros
	secretaria?: "SMS" | "SME" | "SMAS";
}) => {
	// Verificar se o valor é válido (não vazio e diferente de "SEM VÍNCULO" ou "0")
	const hasValidValue = value && value !== "SEM VÍNCULO" && value !== "0";

	// Determinar nome do sistema baseado na secretaria
	const getNomeSistema = () => {
		if (secretaria === "SMS") return "VitaCare";
		if (secretaria === "SME") return "SGRC";
		return "RMI";
	};

	return (
		<div>
			<div className="flex items-center gap-1.5 mb-1">
				<p className="text-sm text-muted-foreground">{label}</p>
				{source === "rmi" && (
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<div className="inline-flex items-center justify-center cursor-help">
									<CheckCircle2 className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
								</div>
							</TooltipTrigger>
							<TooltipContent>
								<p className="text-xs font-medium">
									Vínculo oficial confirmado (fonte {getNomeSistema()})
								</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				)}
				{source === "geo" && hasValidValue && (
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<div className="inline-flex items-center justify-center cursor-help">
									<MapPin className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
								</div>
							</TooltipTrigger>
							<TooltipContent>
								<p className="text-xs font-medium max-w-xs">
									Sugestão baseada em geolocalização. Use este equipamento para
									direcionar atendimento quando o protocolo estiver violado.
								</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				)}
				{source === "geo" && !hasValidValue && isEquipeSaude && (
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<div className="inline-flex items-center justify-center cursor-help">
									<AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
								</div>
							</TooltipTrigger>
							<TooltipContent>
								<p className="text-xs font-medium max-w-xs">
									Sem cobertura de equipamento na região
								</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				)}
				{source === null && !hasValidValue && (
					<TooltipProvider>
						<Tooltip>
							<TooltipTrigger asChild>
								<div className="inline-flex items-center justify-center cursor-help">
									<AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
								</div>
							</TooltipTrigger>
							<TooltipContent>
								<p className="text-xs font-medium max-w-xs">
									Sem informação de endereço
								</p>
							</TooltipContent>
						</Tooltip>
					</TooltipProvider>
				)}
			</div>
			<p className="font-medium">{hasValidValue ? value : "-"}</p>
		</div>
	);
};

// Função para calcular idade detalhada (anos, meses, dias)
const calcularIdadeDetalhada = (
	dataNascimento: string,
	dataReferencia: Date,
) => {
	const nascimento = new Date(dataNascimento);

	let anos = dataReferencia.getFullYear() - nascimento.getFullYear();
	let meses = dataReferencia.getMonth() - nascimento.getMonth();
	let dias = dataReferencia.getDate() - nascimento.getDate();

	// Ajustar se os dias forem negativos
	if (dias < 0) {
		meses--;
		const mesAnterior = new Date(
			dataReferencia.getFullYear(),
			dataReferencia.getMonth(),
			0,
		);
		dias += mesAnterior.getDate();
	}

	// Ajustar se os meses forem negativos
	if (meses < 0) {
		anos--;
		meses += 12;
	}

	return { anos, meses, dias };
};

// Função para formatar idade detalhada
const formatarIdadeDetalhada = (anos: number, meses: number, dias: number) => {
	const partes: string[] = [];

	if (anos > 0) {
		partes.push(`${anos} ${anos === 1 ? "ano" : "anos"}`);
	}
	if (meses > 0) {
		partes.push(`${meses} ${meses === 1 ? "mês" : "meses"}`);
	}
	if (dias > 0) {
		partes.push(`${dias} ${dias === 1 ? "dia" : "dias"}`);
	}

	return partes.length > 0 ? partes.join(", ") : "0 dias";
};

// Função para calcular completude total
// Usa a primeira coluna não-null disponível (total, educacao, saude, ou assistencia)
const calcularCompletude = (participant: Participante) => {
	// Tentar usar total primeiro (se disponível)
	let total = participant.total_protocolos;
	let regular = participant.total_protocolos_regular;

	// Se total é null, usar a secretaria disponível
	if (total == null) {
		if (participant.educacao_protocolos_total != null) {
			total = participant.educacao_protocolos_total;
			regular = participant.educacao_protocolos_regular;
		} else if (participant.saude_protocolos_total != null) {
			total = participant.saude_protocolos_total;
			regular = participant.saude_protocolos_regular;
		} else if (participant.assistencia_protocolos_total != null) {
			total = participant.assistencia_protocolos_total;
			regular = participant.assistencia_protocolos_regular;
		}
	}

	if (!total || total === 0) return 0;
	return Math.round(((regular || 0) / total) * 100);
};

interface ProfessionalTabProps {
	data: ParticipanteListItem[];
	meta: PaginationMeta | null;
	filterOptions: SmartFilterOptions;
	filters: ParticipantFilters;
	onFilterChange: (filters: ParticipantFilters) => void;
	onPageChange: (page: number) => void;
	onRowClick: (idMembroFamilia: string) => void;
	onCloseDetail: () => void;
	selectedParticipant: Participante | null;
	detailLoading: boolean;
	onRefresh?: () => void;
	onDownload?: () => void;
	loading?: boolean;
	pageSize: number;
	sortBy?: string | null;
	sortOrder?: SortOrder;
	onSortChange?: (sortBy: string, sortOrder: SortOrder) => void;
	isSuperAdmin?: boolean;
	secretariasAcesso?: string[];
	geospatialLayers?: GeospatialLayer[];
	geospatialLoading?: boolean;
	geospatialFilters?: GeospatialFilters;
	geospatialAvailableFilters?: GeospatialFilterOptions;
	onGeospatialFilterChange?: (filters: GeospatialFilters) => void;
}

// Removido MemoizedSelect - agora usando VirtualizedSelect

const ProfessionalTabComponent = ({
	data,
	meta,
	filterOptions,
	filters,
	onFilterChange,
	onPageChange,
	onRowClick,
	onCloseDetail,
	selectedParticipant,
	detailLoading,
	onRefresh,
	onDownload,
	loading = false,
	pageSize,
	sortBy,
	sortOrder = "asc",
	onSortChange,
	isSuperAdmin = false,
	secretariasAcesso = [],
	geospatialLayers = [],
	geospatialLoading = false,
	geospatialFilters = {},
	geospatialAvailableFilters,
	onGeospatialFilterChange,
}: ProfessionalTabProps) => {
	// Acesso completo a protocolos: super admin ou as 3 secretarias.
	const fullAccess =
		isSuperAdmin || (secretariasAcesso || []).length === 3;

	// Colunas visíveis na tabela conforme o acesso do usuário.
	const visibleColumns = useMemo(() => {
		if (fullAccess) return undefined;
		const columns = [
			"nome",
			"cpf",
			"grupo",
			"bairro",
			"idade",
			"status",
			"total_fracao",
			"total_irregular",
		];
		if (secretariasAcesso?.includes("SMAS")) columns.push("assistencia_fracao");
		if (secretariasAcesso?.includes("SME")) columns.push("educacao_fracao");
		if (secretariasAcesso?.includes("SMS")) columns.push("saude_fracao");
		return columns;
	}, [fullAccess, secretariasAcesso]);

	// Handler para clique no header de ordenação
	const handleSort = useCallback(
		(column: string) => {
			if (!onSortChange) return;

			// Se clicar na mesma coluna, inverte a ordem
			// Se clicar em outra coluna, ordena ASC
			if (sortBy === column) {
				onSortChange(column, sortOrder === "asc" ? "desc" : "asc");
			} else {
				onSortChange(column, "asc");
			}
		},
		[sortBy, sortOrder, onSortChange],
	);

	const getBadgeVariant = useCallback(
		(
			situacao?: string,
		): "outline" | "default" | "secondary" | "destructive" | "warning" => {
			if (!situacao) return "outline";
			const lower = situacao.toLowerCase();
			if (lower === "regular") return "default";
			if (lower.includes("atenção") || lower.includes("atencao"))
				return "warning";
			if (lower.includes("irregular")) return "destructive";
			return "secondary";
		},
		[],
	);

	return (
		<div className="space-y-6">
			<div>
				<h2 className="text-2xl font-bold text-foreground mb-2">
					Busca Individual
				</h2>
				<p className="text-sm text-muted-foreground mb-6">
					Busque por CPF, Nome, ID Membro Família ou ID Família (CadÚnico) para
					ver os detalhes de uma pessoa específica
				</p>
			</div>

			<FilterCard
				filterOptions={filterOptions}
				filters={filters}
				onFilterChange={onFilterChange}
				onRefresh={onRefresh}
				onDownload={onDownload}
				loading={loading}
				showSearch
				totalResults={meta?.total_rows}
				hideSituacao={!fullAccess}
			/>

			{/* Results - Table */}
			{loading && !data.length ? (
				<Card className="border-2">
					<CardHeader className="pb-4">
						<Skeleton className="h-6 w-48" />
					</CardHeader>
					<CardContent className="space-y-3">
						<Skeleton className="h-11 w-full" />
						{Array.from({ length: 8 }).map((_, i) => (
							<Skeleton key={i} className="h-12 w-full" />
						))}
					</CardContent>
				</Card>
			) : data.length > 0 ? (
				<Card className="border-2 relative min-w-0">
					<CardHeader className="pb-4">
						<CardTitle className="flex items-center gap-2 text-lg">
							<Users className="h-5 w-5 text-primary" />
							Lista de Pessoas
						</CardTitle>
					</CardHeader>
					<CardContent className="space-y-4 min-w-0">
						{/* Tabela de participantes */}
						<ParticipantTable
							data={data}
							onRowClick={onRowClick}
							getBadgeVariant={getBadgeVariant}
							isLoading={loading}
							sortBy={sortBy}
							sortOrder={sortOrder}
							onSort={handleSort}
							visibleColumns={visibleColumns}
						/>

						{/* Pagination - Footer do Card */}
						{meta && meta.total_pages > 1 && (
							<div className="flex items-center justify-between pt-4 border-t">
								<p className="text-sm text-muted-foreground">
									Mostrando{" "}
									<span className="font-medium">
										{(meta.page - 1) * pageSize + 1}
									</span>{" "}
									a{" "}
									<span className="font-medium">
										{(meta.page - 1) * pageSize + data.length}
									</span>{" "}
									de{" "}
									<span className="font-medium">
										{meta.total_rows.toLocaleString("pt-BR")}
									</span>{" "}
									registros
								</p>
								<div className="flex items-center gap-1">
									<Button
										variant="outline"
										size="sm"
										onClick={() => onPageChange(Math.max(1, meta.page - 1))}
										disabled={meta.page === 1 || loading}
									>
										<ChevronLeft className="h-4 w-4 mr-1" />
										Anterior
									</Button>

									{/* Page Numbers */}
									{(() => {
										const pages: number[] = [];
										const totalPages = meta.total_pages;
										const currentPage = meta.page;

										// Mostrar até 5 páginas
										let startPage = Math.max(1, currentPage - 2);
										const endPage = Math.min(totalPages, startPage + 4);

										// Ajustar se estiver no final
										if (endPage - startPage < 4) {
											startPage = Math.max(1, endPage - 4);
										}
										for (let i = startPage; i <= endPage; i++) {
											pages.push(i);
										}

										return pages.map((page) => (
											<Button
												key={page}
												variant={page === currentPage ? "default" : "outline"}
												size="sm"
												className="w-9"
												onClick={() => onPageChange(page)}
												disabled={loading}
											>
												{page}
											</Button>
										));
									})()}

									<Button
										variant="outline"
										size="sm"
										onClick={() =>
											onPageChange(Math.min(meta.total_pages, meta.page + 1))
										}
										disabled={meta.page === meta.total_pages || loading}
									>
										Próxima
										<ChevronRight className="h-4 w-4 ml-1" />
									</Button>
								</div>
							</div>
						)}
					</CardContent>
				</Card>
			) : (
				<Card className="border-2 border-dashed">
					<CardContent className="py-12">
						<div className="text-center text-muted-foreground">
							<Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
							<p className="text-lg font-medium">Nenhuma pessoa encontrada</p>
							<p className="text-sm mt-2">
								Tente ajustar os filtros ou termo de busca
							</p>
						</div>
					</CardContent>
				</Card>
			)}

			{/* Modal de Detalhamento */}
			<Dialog
				open={!!selectedParticipant || detailLoading}
				onOpenChange={(open) => {
					if (!open) onCloseDetail();
				}}
			>
				<DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
					<DialogHeader>
						<DialogTitle className="text-2xl flex items-center gap-2">
							<Eye className="h-6 w-6 text-primary" />
							Detalhamento Individual
						</DialogTitle>
						<DialogDescription>
							Visualize informações completas, protocolos e histórico do
							participante
						</DialogDescription>
					</DialogHeader>

					{detailLoading ? (
						<div className="space-y-6 mt-4">
							<Skeleton className="h-8 w-64" />
							<Skeleton className="h-4 w-48" />
							<div className="grid grid-cols-2 gap-4">
								<Skeleton className="h-20" />
								<Skeleton className="h-20" />
								<Skeleton className="h-20" />
								<Skeleton className="h-20" />
							</div>
							<Skeleton className="h-40" />
						</div>
					) : selectedParticipant ? (
						<div className="space-y-6 mt-4">
							{/* Informações Básicas */}
							<div>
								<h3 className="text-lg font-semibold mb-3 text-foreground">
									Informações Básicas
								</h3>
								<div className="space-y-4">
									{/* ── Seção 1: Identificação ── */}
									<div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
										<div>
											<p className="text-sm text-muted-foreground">Nome</p>
											<p className="font-medium">
												{selectedParticipant.nome || "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">CPF</p>
											<p className="font-mono font-medium">
												{selectedParticipant.cpf || "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">
												ID Família (CadÚnico)
											</p>
											<p className="font-mono font-medium">
												{selectedParticipant.id_familia || "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">
												ID Membro Família (CadÚnico)
											</p>
											<p className="font-mono font-medium">
												{selectedParticipant.id_membro_familia || "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">Grupo</p>
											<p className="font-medium">
												{renderGrupoCompleto(selectedParticipant.grupo)}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">Idade</p>
											<p className="font-medium">
												{selectedParticipant.idade != null &&
												selectedParticipant.nascimento_data
													? `${selectedParticipant.idade} anos (${new Date(selectedParticipant.nascimento_data).toLocaleDateString("pt-BR")})`
													: selectedParticipant.idade != null
														? `${selectedParticipant.idade} anos`
														: "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">
												Idade em 31/03/{new Date().getFullYear()}
											</p>
											<p className="font-medium">
												{selectedParticipant.nascimento_data
													? (() => {
															const dataReferencia = new Date(
																new Date().getFullYear(),
																2,
																31,
															);
															const { anos, meses, dias } =
																calcularIdadeDetalhada(
																	selectedParticipant.nascimento_data,
																	dataReferencia,
																);
															return formatarIdadeDetalhada(anos, meses, dias);
														})()
													: "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">
												Perfil Racial Declarado
											</p>
											<p className="font-medium">
												{selectedParticipant.raca
													? selectedParticipant.raca.charAt(0).toUpperCase() +
														selectedParticipant.raca.slice(1).toLowerCase()
													: "NÃO DECLARADO"}
											</p>
										</div>
									</div>

									{/* ── Seção 2: Localização & Contato ── */}
									<div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
										{/* Endereço SMAS */}
										<div className="space-y-1">
											<p className="text-sm text-muted-foreground">
												Endereço SMAS
											</p>
											<div>
												<span className="text-xs text-muted-foreground">
													Endereço:{" "}
												</span>
												<span className="font-medium">
													{[
														selectedParticipant.endereco,
														selectedParticipant.complemento,
													]
														.filter(Boolean)
														.join(", ") || "-"}
												</span>
											</div>
											<div>
												<span className="text-xs text-muted-foreground">
													Bairro:{" "}
												</span>
												<span className="font-medium uppercase">
													{selectedParticipant.bairro || "-"}
												</span>
											</div>
										</div>

										{/* Endereço SMS */}
										<div className="space-y-1">
											<p className="text-sm text-muted-foreground">
												Endereço SMS
											</p>
											<div>
												<span className="text-xs text-muted-foreground">
													Endereço:{" "}
												</span>
												<span className="font-medium">
													{[
														selectedParticipant.endereco_sms?.endereco,
														selectedParticipant.endereco_sms?.complemento,
													]
														.filter(Boolean)
														.join(", ") || "-"}
												</span>
											</div>
											<div>
												<span className="text-xs text-muted-foreground">
													Bairro:{" "}
												</span>
												<span className="font-medium uppercase">
													{selectedParticipant.endereco_sms?.bairro || "-"}
												</span>
											</div>
										</div>

										{/* Contato */}
										<div className="space-y-1">
											<p className="text-sm text-muted-foreground">Contato</p>
											{selectedParticipant.telefone_1_ddd &&
											selectedParticipant.telefone_1_numero ? (
												<div>
													<span className="text-xs text-muted-foreground">
														Principal:{" "}
													</span>
													<span className="font-medium">
														({selectedParticipant.telefone_1_ddd}){" "}
														{selectedParticipant.telefone_1_numero.replace(
															/\D/g,
															"",
														).length === 9
															? selectedParticipant.telefone_1_numero
																	.replace(/\D/g, "")
																	.replace(/(\d{5})(\d{4})/, "$1-$2")
															: selectedParticipant.telefone_1_numero
																	.replace(/\D/g, "")
																	.replace(/(\d{4})(\d{4})/, "$1-$2")}
													</span>
												</div>
											) : (
												<p className="font-medium">-</p>
											)}
											{selectedParticipant.telefone_2_ddd &&
												selectedParticipant.telefone_2_numero && (
													<div>
														<span className="text-xs text-muted-foreground">
															Alternativo:{" "}
														</span>
														<span className="font-medium">
															({selectedParticipant.telefone_2_ddd}){" "}
															{selectedParticipant.telefone_2_numero.replace(
																/\D/g,
																"",
															).length === 9
																? selectedParticipant.telefone_2_numero
																		.replace(/\D/g, "")
																		.replace(/(\d{5})(\d{4})/, "$1-$2")
																: selectedParticipant.telefone_2_numero
																		.replace(/\D/g, "")
																		.replace(/(\d{4})(\d{4})/, "$1-$2")}
														</span>
													</div>
												)}
										</div>
									</div>

									{/* ── Seção 3: Equipamentos ── */}
									<div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
										{/* Equipamentos Públicos - Educação (SME) */}
										<EquipamentoField
											label="CRE"
											value={selectedParticipant.nome_cre}
											source={selectedParticipant.source_escola}
											secretaria="SME"
										/>

										{/* Escola mostra "-" se for inferida (source == "geo") */}
										<EquipamentoField
											label="Escola"
											value={
												selectedParticipant.source_escola === "geo"
													? null
													: selectedParticipant.nome_escola
											}
											source={
												selectedParticipant.source_escola === "geo"
													? undefined
													: selectedParticipant.source_escola
											}
											secretaria="SME"
										/>

										{/* Equipamentos Públicos - Assistência Social (SMAS) */}
										<EquipamentoField
											label="CAS"
											value={selectedParticipant.nome_cas}
											source={selectedParticipant.source_cras}
											secretaria="SMAS"
										/>

										<EquipamentoField
											label="CRAS"
											value={selectedParticipant.nome_cras}
											source={selectedParticipant.source_cras}
											secretaria="SMAS"
										/>

										{/* Equipamentos Públicos - Saúde (SMS) */}
										<EquipamentoField
											label="Clínica da Família"
											value={selectedParticipant.nome_clinica_familia}
											source={selectedParticipant.source_clinica_familia}
											secretaria="SMS"
										/>

										<EquipamentoField
											label="Equipe da Família"
											value={selectedParticipant.nome_equipe_familia}
											source={selectedParticipant.source_equipe_familia}
											isEquipeSaude={true}
											secretaria="SMS"
										/>
										{(() => {
											const equipeMedicos = selectedParticipant.equipe_familia;
											const sourceEquipe =
												selectedParticipant.source_equipe_familia;

											const hasValidEquipe =
												equipeMedicos &&
												equipeMedicos !== "SEM VÍNCULO" &&
												equipeMedicos !== "0";

											if (!hasValidEquipe) {
												// Componente para exibir badge mesmo sem equipe válida
												const EmptyEquipeBadge = () => {
													// source === "geo" + SEM VÍNCULO = sem cobertura na região
													if (sourceEquipe === "geo") {
														return (
															<TooltipProvider>
																<Tooltip>
																	<TooltipTrigger asChild>
																		<div className="inline-flex items-center justify-center cursor-help">
																			<AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
																		</div>
																	</TooltipTrigger>
																	<TooltipContent>
																		<p className="text-xs font-medium max-w-xs">
																			Sem cobertura de equipamento na região
																		</p>
																	</TooltipContent>
																</Tooltip>
															</TooltipProvider>
														);
													}
													// source === null = sem informação de endereço
													if (sourceEquipe === null) {
														return (
															<TooltipProvider>
																<Tooltip>
																	<TooltipTrigger asChild>
																		<div className="inline-flex items-center justify-center cursor-help">
																			<AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
																		</div>
																	</TooltipTrigger>
																	<TooltipContent>
																		<p className="text-xs font-medium max-w-xs">
																			Sem informação de endereço
																		</p>
																	</TooltipContent>
																</Tooltip>
															</TooltipProvider>
														);
													}
													return null;
												};

												return (
													<>
														<div>
															<div className="flex items-center gap-1.5 mb-1">
																<p className="text-sm text-muted-foreground">
																	Médicos
																</p>
																<EmptyEquipeBadge />
															</div>
															<p className="font-medium">-</p>
														</div>
														<div>
															<div className="flex items-center gap-1.5 mb-1">
																<p className="text-sm text-muted-foreground">
																	Enfermeiros
																</p>
																<EmptyEquipeBadge />
															</div>
															<p className="font-medium">-</p>
														</div>
													</>
												);
											}

											// Parse da string: "MEDICOS:\nNome1\nNome2\n\nENFERMEIROS:\nNome3\nNome4"
											const lines = equipeMedicos
												.split("\n")
												.map((l) => l.trim())
												.filter((l) => l);
											const medicos: string[] = [];
											const enfermeiros: string[] = [];
											let currentSection = "";

											for (const line of lines) {
												if (line.startsWith("MEDICOS:") || line === "MEDICOS") {
													currentSection = "medicos";
												} else if (
													line.startsWith("ENFERMEIROS:") ||
													line === "ENFERMEIROS"
												) {
													currentSection = "enfermeiros";
												} else if (
													line !== "SEM MÉDICOS" &&
													line !== "SEM ENFERMEIROS"
												) {
													if (currentSection === "medicos") {
														medicos.push(line);
													} else if (currentSection === "enfermeiros") {
														enfermeiros.push(line);
													}
												}
											}

											// Componente Badge para equipe (usado em médicos e enfermeiros)
											const EquipeBadge = () => {
												if (sourceEquipe === "rmi") {
													return (
														<TooltipProvider>
															<Tooltip>
																<TooltipTrigger asChild>
																	<div className="inline-flex items-center justify-center cursor-help">
																		<CheckCircle2 className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
																	</div>
																</TooltipTrigger>
																<TooltipContent>
																	<p className="text-xs font-medium">
																		Vínculo oficial confirmado (fonte VitaCare)
																	</p>
																</TooltipContent>
															</Tooltip>
														</TooltipProvider>
													);
												}
												if (sourceEquipe === "geo") {
													return (
														<TooltipProvider>
															<Tooltip>
																<TooltipTrigger asChild>
																	<div className="inline-flex items-center justify-center cursor-help">
																		<MapPin className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
																	</div>
																</TooltipTrigger>
																<TooltipContent>
																	<p className="text-xs font-medium max-w-xs">
																		Sugestão baseada em geolocalização. Use esta
																		equipe para direcionar atendimento quando o
																		protocolo estiver violado.
																	</p>
																</TooltipContent>
															</Tooltip>
														</TooltipProvider>
													);
												}
												if (sourceEquipe === null && equipeMedicos) {
													return (
														<TooltipProvider>
															<Tooltip>
																<TooltipTrigger asChild>
																	<div className="inline-flex items-center justify-center cursor-help">
																		<AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
																	</div>
																</TooltipTrigger>
																<TooltipContent>
																	<p className="text-xs font-medium max-w-xs">
																		Sem informação de endereço ou sem cobertura
																		de equipamento na região
																	</p>
																</TooltipContent>
															</Tooltip>
														</TooltipProvider>
													);
												}
												return null;
											};

											return (
												<>
													<div>
														<div className="flex items-center gap-1.5 mb-1">
															<p className="text-sm text-muted-foreground">
																Médicos
															</p>
															<EquipeBadge />
														</div>
														{medicos.length > 0 ? (
															<div className="space-y-0.5">
																{medicos.map((medico, idx) => (
																	<p key={idx} className="font-medium">
																		{medico}
																	</p>
																))}
															</div>
														) : (
															<p className="font-medium">-</p>
														)}
													</div>
													<div>
														<div className="flex items-center gap-1.5 mb-1">
															<p className="text-sm text-muted-foreground">
																Enfermeiros
															</p>
															<EquipeBadge />
														</div>
														{enfermeiros.length > 0 ? (
															<div className="space-y-0.5">
																{enfermeiros.map((enfermeiro, idx) => (
																	<p key={idx} className="font-medium">
																		{enfermeiro}
																	</p>
																))}
															</div>
														) : (
															<p className="font-medium">-</p>
														)}
													</div>
												</>
											);
										})()}
									</div>
									{/* fim Seção 3 */}

									{/* ── Seção 4: Programa ── */}
									<div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
										<div>
											<p className="text-sm text-muted-foreground">
												Bolsa Família
											</p>
											<Badge
												variant={
													selectedParticipant.has_bolsa_familia === true
														? "success"
														: selectedParticipant.has_bolsa_familia === false
															? "secondary"
															: "outline"
												}
											>
												{selectedParticipant.has_bolsa_familia === true
													? "Beneficiário"
													: selectedParticipant.has_bolsa_familia === false
														? "Não beneficiário"
														: "-"}
											</Badge>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">
												Cartão PIC
											</p>
											<Badge
												variant={
													selectedParticipant.has_cartao_pic === true
														? "success"
														: selectedParticipant.has_cartao_pic === false
															? "warning"
															: "secondary"
												}
											>
												{selectedParticipant.has_cartao_pic === true
													? "Possui cartão"
													: selectedParticipant.has_cartao_pic === false
														? "Tem direito, mas não retirou"
														: "Não tem direito"}
											</Badge>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">
												Mês de Ingresso no Programa
											</p>
											<p className="font-medium">
												{selectedParticipant.cohort || "-"}
											</p>
										</div>
										<div>
											<p className="text-sm text-muted-foreground">Status</p>
											<Badge
												variant={
													selectedParticipant.status?.toLowerCase() === "ativo"
														? "success"
														: "destructive"
												}
											>
												{selectedParticipant.status || "-"}
											</Badge>
										</div>
									</div>
									{/* fim Seção 4 */}
								</div>
								{/* fim space-y-4 */}
							</div>

							{/* Visualização Geoespacial - Apenas Super Admin */}
							{isSuperAdmin &&
								selectedParticipant.latitude &&
								selectedParticipant.longitude && (
									<>
										<Separator />
										<Collapsible defaultOpen={false} className="w-full">
											<CollapsibleTrigger asChild>
												<Button
													variant="ghost"
													className="w-full justify-start p-0 hover:bg-transparent"
												>
													<div className="flex items-center gap-2 py-2">
														<h3 className="text-lg font-semibold text-foreground">
															Visualização Geoespacial
														</h3>
														<ChevronDown className="h-4 w-4 text-muted-foreground ml-auto transition-transform duration-200 ui-expanded:rotate-180" />
													</div>
												</Button>
											</CollapsibleTrigger>
											<CollapsibleContent>
												<div className="pt-4">
													<GeospatialMapView
														loading={geospatialLoading}
														layers={geospatialLayers}
														filters={geospatialFilters}
														availableFilters={geospatialAvailableFilters}
														onFilterChange={onGeospatialFilterChange}
														hideHeader={true}
														participantLocation={{
															latitude: selectedParticipant.latitude,
															longitude: selectedParticipant.longitude,
															nome: selectedParticipant.nome || "Participante",
															idade: selectedParticipant.idade,
															grupo: selectedParticipant.grupo,
															bairro: selectedParticipant.bairro,
															situacao: selectedParticipant.situacao,
															status: selectedParticipant.status,
															nome_escola: selectedParticipant.nome_escola,
															nome_cras: selectedParticipant.nome_cras,
															nome_clinica_familia:
																selectedParticipant.nome_clinica_familia,
															nome_equipe_familia:
																selectedParticipant.nome_equipe_familia,
															equipe_familia:
																selectedParticipant.equipe_familia,
														}}
													/>
												</div>
											</CollapsibleContent>
										</Collapsible>
									</>
								)}

							<Separator />

							{/* Situação Geral - Simplificada */}
							<div>
								<h3 className="text-lg font-semibold mb-3 text-foreground">
									Situação Geral
								</h3>
								<div className="bg-muted/50 p-4 rounded-lg">
									<div className="flex items-center justify-between">
										<div>
											<p className="text-sm text-muted-foreground mb-1">
												Status
											</p>
											<Badge
												variant={getBadgeVariant(selectedParticipant.situacao)}
												className="text-base"
											>
												{selectedParticipant.situacao || "-"}
											</Badge>
										</div>
										<div className="text-right">
											<p className="text-sm text-muted-foreground mb-1">
												Completude Total
											</p>
											<p className="text-3xl font-bold text-primary">
												{calcularCompletude(selectedParticipant)}%
											</p>
										</div>
									</div>
								</div>
							</div>

							<Separator />

							{/* Dimensão Assistência Social */}
							{(() => {
								const protocolosAssistencia = (
									selectedParticipant.protocolo_listagem || []
								)
									.filter((p) => p.secretaria?.toLowerCase() === "smas")
									.filter((p) => {
										const status = p.status?.toLowerCase() || "";
										return (
											status !== "nao_aplica" &&
											status !== "não aplica" &&
											status !== "n/a" &&
											status !== "não aplicável" &&
											status !== "nao_priorizado"
										);
									});
								if (protocolosAssistencia.length === 0) return null;
								return (
									<>
										<div>
											<h3 className="text-lg font-semibold mb-3 text-foreground">
												📋 Dimensão Assistência Social
											</h3>
											<div className="space-y-2">
												{protocolosAssistencia.map((protocolo, idx) => (
													<ProtocoloItem key={idx} protocolo={protocolo} />
												))}
											</div>
										</div>
										<Separator />
									</>
								);
							})()}

							{/* Dimensão Educação */}
							{(() => {
								const protocolosEducacao = (
									selectedParticipant.protocolo_listagem || []
								)
									.filter((p) => p.secretaria?.toLowerCase() === "sme")
									.filter((p) => {
										const status = p.status?.toLowerCase() || "";
										return (
											status !== "nao_aplica" &&
											status !== "não aplica" &&
											status !== "n/a" &&
											status !== "não aplicável" &&
											status !== "nao_priorizado"
										);
									});
								if (protocolosEducacao.length === 0) return null;
								return (
									<>
										<div>
											<h3 className="text-lg font-semibold mb-3 text-foreground">
												📚 Dimensão Educação
											</h3>
											<div className="space-y-2">
												{protocolosEducacao.map((protocolo, idx) => (
													<ProtocoloItem key={idx} protocolo={protocolo} />
												))}
											</div>
										</div>
										<Separator />
									</>
								);
							})()}

							{/* Dimensão Saúde */}
							{(() => {
								const protocolosSaude = (
									selectedParticipant.protocolo_listagem || []
								)
									.filter(
										(p) =>
											p.secretaria?.toLowerCase() === "sms" ||
											p.secretaria?.toLowerCase() === "subpav",
									)
									.filter((p) => {
										const status = p.status?.toLowerCase() || "";
										return (
											status !== "nao_aplica" &&
											status !== "não aplica" &&
											status !== "n/a" &&
											status !== "não aplicável" &&
											status !== "nao_priorizado"
										);
									});
								if (protocolosSaude.length === 0) return null;
								return (
									<>
										<div>
											<h3 className="text-lg font-semibold mb-3 text-foreground">
												🏥 Dimensão Saúde
											</h3>
											<div className="space-y-2">
												{protocolosSaude.map((protocolo, idx) => (
													<ProtocoloItem key={idx} protocolo={protocolo} />
												))}
											</div>
										</div>
										<Separator />
									</>
								);
							})()}
						</div>
					) : null}
				</DialogContent>
			</Dialog>
		</div>
	);
};

// Exportar com React.memo para evitar re-renders quando props não mudarem
export const ProfessionalTab = memo(ProfessionalTabComponent);
