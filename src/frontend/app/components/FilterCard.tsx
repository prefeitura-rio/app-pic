"use client";

import {
	Download,
	Filter,
	Map,
	RefreshCw,
	Search,
	Table,
	X,
} from "lucide-react";
import { memo, useCallback, useState } from "react";
import { Button } from "@/app/components/ui/button";
import {
	Card,
	CardContent,
	CardHeader,
	CardTitle,
} from "@/app/components/ui/card";
import { Input } from "@/app/components/ui/input";
import {
	LazyFilterMultiSelect,
	LazyFilterSelect,
} from "@/app/components/LazyFilterSelects";
import type { ParticipantFilters } from "@/app/types";

interface FilterCardProps {
	filters: ParticipantFilters;
	onFilterChange: (filters: ParticipantFilters) => void;
	onRefresh?: () => void;
	onDownload?: () => void;
	loading?: boolean;
	showSearch?: boolean;
	totalResults?: number;
	onToggleMap?: () => void; // Callback para alternar visualização de mapa
	viewMode?: "table" | "map"; // Modo de visualização atual
	hideSituacao?: boolean; // Esconde o filtro de situação (acesso parcial)
}

const FilterCardComponent = ({
	filters,
	onFilterChange,
	onRefresh,
	onDownload,
	loading = false,
	showSearch = false,
	totalResults,
	onToggleMap,
	viewMode = "table",
	hideSituacao = false,
}: FilterCardProps) => {
	const [searchInput, setSearchInput] = useState("");

	// Sincronizar searchInput com filters.search quando mudar (ex: após refresh).
	// Ajuste feito durante a renderização (não em um efeito), comparando com o
	// valor externo anterior — evita sobrescrever um searchInput que o usuário
	// acabou de digitar/apagar quando outros filtros (protocolo, bairro, etc.) mudam.
	const externalSearch = filters.search;
	const [prevExternalSearch, setPrevExternalSearch] = useState(externalSearch);
	if (externalSearch !== prevExternalSearch) {
		setPrevExternalSearch(externalSearch);
		if (externalSearch && externalSearch !== searchInput) {
			setSearchInput(externalSearch);
		}
	}

	// Memoizar callbacks para evitar re-criação
	const handleFilterUpdate = useCallback(
		(key: string, value: string) => {
			onFilterChange({
				...filters,
				[key]: value,
			});
		},
		[filters, onFilterChange],
	);

	// Callback para filtros multi-select (arrays)
	const handleMultiFilterUpdate = useCallback(
		(key: string, values: string[]) => {
			onFilterChange({
				...filters,
				[key]: values.length > 0 ? values : undefined,
			});
		},
		[filters, onFilterChange],
	);

	// Callback para filtros booleanos (converte string "true"/"false" para boolean)
	const handleBooleanFilterUpdate = useCallback(
		(key: string, value: string) => {
			if (value === "todos" || value === "todas" || value === "") {
				const updated: Record<string, unknown> = { ...filters };
				delete updated[key];
				onFilterChange(updated as ParticipantFilters);
			} else {
				onFilterChange({ ...filters, [key]: value === "true" });
			}
		},
		[filters, onFilterChange],
	);

	const clearFilters = useCallback(() => {
		setSearchInput("");
		onFilterChange({});
	}, [onFilterChange]);

	// Sanitize search input (remove special chars and trim)
	const sanitizeSearchInput = useCallback((input: string): string => {
		return input
			.replace(/[.-]/g, "") // Remove pontos e hífens (útil para CPF)
			.trim(); // Remove espaços em branco no início e fim
	}, []);

	const handleSearch = useCallback(() => {
		const sanitized = sanitizeSearchInput(searchInput);
		onFilterChange({
			...filters,
			search: sanitized,
		});
	}, [filters, searchInput, onFilterChange, sanitizeSearchInput]);

	const capitalizeLabel = useCallback(
		(label: string) => label.charAt(0).toUpperCase() + label.slice(1),
		[],
	);

	return (
		<Card className="relative border-2">
			<CardHeader className="pb-4 flex flex-row items-center justify-between">
				<CardTitle className="text-2xl font-bold flex items-center gap-2">
					<Filter className="h-6 w-6" />
					{showSearch ? "Filtros e Busca" : "Filtros"}
				</CardTitle>
				<div className="flex gap-2">
					{onToggleMap && (
						<Button
							variant={viewMode === "map" ? "default" : "outline"}
							size="sm"
							onClick={onToggleMap}
							className="h-8 text-xs"
							disabled={loading}
						>
							{viewMode === "map" ? (
								<>
									<Table className="h-3 w-3 mr-1" />
									Ver Tabela
								</>
							) : (
								<>
									<Map className="h-3 w-3 mr-1" />
									Ver Mapa
								</>
							)}
						</Button>
					)}
					{onDownload && (
						<Button
							variant="outline"
							size="sm"
							onClick={onDownload}
							className="h-8 text-xs"
							disabled={loading}
						>
							<Download className="h-3 w-3 mr-1" />
							Baixar Dados
						</Button>
					)}
					<Button
						variant="outline"
						size="sm"
						onClick={clearFilters}
						className="h-8 text-xs"
						disabled={loading}
					>
						<X className="h-3 w-3 mr-1" />
						Limpar Filtros
					</Button>
					{onRefresh && (
						<Button
							variant="outline"
							size="sm"
							onClick={onRefresh}
							className="h-8 text-xs"
							disabled={loading}
						>
							<RefreshCw
								className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`}
							/>
							Atualizar
						</Button>
					)}
				</div>
			</CardHeader>
			<CardContent className="pt-0 space-y-4">
				{/* Busca - Full Width com ícone interno (apenas se showSearch) */}
				{showSearch && (
					<div className="relative">
						<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
						<Input
							type="text"
							placeholder="Buscar por CPF, Nome, ID Membro Família ou ID Família (CadÚnico)..."
							value={searchInput}
							onChange={(e) => setSearchInput(e.target.value)}
							onKeyDown={(e) => e.key === "Enter" && handleSearch()}
							className="pl-10 h-11"
							disabled={loading}
						/>
					</div>
				)}

				{/* Primeiro Nível - Filtros Principais */}
				<div className="space-y-1.5">
					<div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
						Filtros Principais
					</div>
					<div className="grid grid-cols-2 md:grid-cols-4 gap-2">
						{/* Grupo - Multi-select */}
						<LazyFilterMultiSelect
							field="grupos"
							filters={filters}
							value={
								Array.isArray(filters.grupo)
									? filters.grupo
									: filters.grupo
										? [filters.grupo]
										: []
							}
							onSelect={(values) => handleMultiFilterUpdate("grupo", values)}
							disabled={loading}
							placeholder="Grupos"
							defaultLabel="Todos os Grupos"
						/>

						{/* Status - Multi-select */}
						<LazyFilterMultiSelect
							field="status_list"
							filters={filters}
							value={
								Array.isArray(filters.status)
									? filters.status
									: filters.status
										? [filters.status]
										: []
							}
							onSelect={(values) => handleMultiFilterUpdate("status", values)}
							disabled={loading}
							placeholder="Status"
							defaultLabel="Todos os Status"
						/>

						{/* Situação - Multi-select (escondido para acesso parcial) */}
						{!hideSituacao && (
							<LazyFilterMultiSelect
								field="situacoes"
								filters={filters}
								value={
									Array.isArray(filters.situacao)
										? filters.situacao
										: filters.situacao
											? [filters.situacao]
											: []
								}
								onSelect={(values) => handleMultiFilterUpdate("situacao", values)}
								disabled={loading}
								placeholder="Situações"
								defaultLabel="Todas as Situações"
							/>
						)}

						{/* Perfil Racial - Multi-select */}
						<LazyFilterMultiSelect
							field="racas"
							filters={filters}
							value={
								Array.isArray(filters.raca)
									? filters.raca
									: filters.raca
										? [filters.raca]
										: []
							}
							onSelect={(values) => handleMultiFilterUpdate("raca", values)}
							disabled={loading}
							placeholder="Perfil Racial"
							defaultLabel="Todos os Perfis Raciais"
							transformLabel={capitalizeLabel}
						/>

						{/* Mês de Ingresso no Programa - Multi-select */}
						<LazyFilterMultiSelect
							field="cohorts"
							filters={filters}
							value={
								Array.isArray(filters.safra)
									? filters.safra
									: filters.safra
										? [filters.safra]
										: []
							}
							onSelect={(values) => handleMultiFilterUpdate("safra", values)}
							disabled={loading}
							placeholder="Meses de Ingresso"
							defaultLabel="Todos os Meses de Ingresso"
						/>

						{/* Bolsa Família */}
						<LazyFilterSelect
							field="bolsa_familia"
							filters={filters}
							value={
								filters.has_bolsa_familia !== undefined
									? String(filters.has_bolsa_familia)
									: "todas"
							}
							onSelect={(v) =>
								handleBooleanFilterUpdate("has_bolsa_familia", v)
							}
							disabled={loading}
							placeholder="Todos Bolsa Família"
							defaultLabel="Todos Bolsa Família"
						/>

						{/* Secretaria de Protocolo */}
						<LazyFilterSelect
							field="protocolo_secretarias"
							filters={filters}
							value={filters.protocolo_secretaria || "todas"}
							onSelect={(v) => handleFilterUpdate("protocolo_secretaria", v)}
							disabled={loading}
							placeholder="Filtrar Protocolos por Secretaria"
							defaultLabel="Todos os Protocolos por Secretaria"
						/>

						{/* Protocolo (Multi-select) */}
						<LazyFilterMultiSelect
							field="protocolo_descricoes"
							filters={filters}
							value={
								Array.isArray(filters.protocolo_descricao)
									? filters.protocolo_descricao
									: filters.protocolo_descricao
										? [filters.protocolo_descricao]
										: []
							}
							onSelect={(values) =>
								handleMultiFilterUpdate("protocolo_descricao", values)
							}
							disabled={loading}
							placeholder="Protocolos"
							defaultLabel="Todos os Protocolos"
						/>

						{/* Status Protocolo - Multi-select */}
						<LazyFilterMultiSelect
							field="protocolo_status_list"
							filters={filters}
							value={
								Array.isArray(filters.protocolo_status)
									? filters.protocolo_status
									: filters.protocolo_status
										? [filters.protocolo_status]
										: []
							}
							onSelect={(values) =>
								handleMultiFilterUpdate("protocolo_status", values)
							}
							disabled={loading}
							placeholder="Status Protocolos"
							defaultLabel="Todos os Status de Protocolos"
						/>
					</div>
				</div>

				{/* Segundo Nível - Filtros Regionais */}
				<div className="space-y-1.5">
					<div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
						Filtros Regionais
					</div>
					<div className="grid grid-cols-2 md:grid-cols-4 gap-2">
						{/* Subprefeitura - Multi-select */}
						<LazyFilterMultiSelect
							field="subprefeituras"
							filters={filters}
							value={
								Array.isArray(filters.subprefeitura)
									? filters.subprefeitura
									: filters.subprefeitura
										? [filters.subprefeitura]
										: []
							}
							onSelect={(values) =>
								handleMultiFilterUpdate("subprefeitura", values)
							}
							disabled={loading}
							placeholder="Subprefeituras"
							defaultLabel="Todas as Subprefeituras"
						/>

						{/* Região Administrativa - Multi-select */}
						<LazyFilterMultiSelect
							field="regioes_administrativas"
							filters={filters}
							value={
								Array.isArray(filters.regiao_administrativa)
									? filters.regiao_administrativa
									: filters.regiao_administrativa
										? [filters.regiao_administrativa]
										: []
							}
							onSelect={(values) =>
								handleMultiFilterUpdate("regiao_administrativa", values)
							}
							disabled={loading}
							placeholder="Regiões Administrativas"
							defaultLabel="Todas as Regiões Adm."
						/>

						{/* Bairro - Multi-select */}
						<LazyFilterMultiSelect
							field="bairros"
							filters={filters}
							value={
								Array.isArray(filters.bairro)
									? filters.bairro
									: filters.bairro
										? [filters.bairro]
										: []
							}
							onSelect={(values) => handleMultiFilterUpdate("bairro", values)}
							disabled={loading}
							placeholder="Bairros"
							defaultLabel="Todos os Bairros"
						/>

						{/* ASSISTÊNCIA SOCIAL */}
						{/* CAS - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="cas_list"
								filters={filters}
								value={
									Array.isArray(filters.cas)
										? filters.cas
										: filters.cas
											? [filters.cas]
											: []
								}
								onSelect={(values) => handleMultiFilterUpdate("cas", values)}
								disabled={loading}
								placeholder="CAS"
								defaultLabel="Todas as CAS"
							/>
						}

						{/* CRAS - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="cras"
								filters={filters}
								value={
									Array.isArray(filters.cras)
										? filters.cras
										: filters.cras
											? [filters.cras]
											: []
								}
								onSelect={(values) => handleMultiFilterUpdate("cras", values)}
								disabled={loading}
								placeholder="CRAS"
								defaultLabel="Todos os CRAS"
							/>
						}

						{/* EDUCAÇÃO */}
						{/* CRE (Coordenadoria Regional de Educação) - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="cres"
								filters={filters}
								value={
									Array.isArray(filters.cre)
										? filters.cre
										: filters.cre
											? [filters.cre]
											: []
								}
								onSelect={(values) => handleMultiFilterUpdate("cre", values)}
								disabled={loading}
								placeholder="CREs"
								defaultLabel="Todas as CREs"
							/>
						}

						{/* Escolas - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="escolas"
								filters={filters}
								value={
									Array.isArray(filters.escola)
										? filters.escola
										: filters.escola
											? [filters.escola]
											: []
								}
								onSelect={(values) => handleMultiFilterUpdate("escola", values)}
								disabled={loading}
								placeholder="Escolas"
								defaultLabel="Todas as Escolas"
							/>
						}

						{/* SAÚDE */}
						{/* AP (Área Programática) - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="aps"
								filters={filters}
								value={
									Array.isArray(filters.ap)
										? filters.ap
										: filters.ap
											? [filters.ap]
											: []
								}
								onSelect={(values) => handleMultiFilterUpdate("ap", values)}
								disabled={loading}
								placeholder="CAPs"
								defaultLabel="Todas as CAPs"
							/>
						}

						{/* Clínicas da Família - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="clinicas"
								filters={filters}
								value={
									Array.isArray(filters.clinica)
										? filters.clinica
										: filters.clinica
											? [filters.clinica]
											: []
								}
								onSelect={(values) =>
									handleMultiFilterUpdate("clinica", values)
								}
								disabled={loading}
								placeholder="Clínicas da Família"
								defaultLabel="Todas as Clínicas"
							/>
						}

						{/* Equipes da Família - Multi-select */}
						{
							<LazyFilterMultiSelect
								field="equipes_familia"
								filters={filters}
								value={
									Array.isArray(filters.equipe_familia)
										? filters.equipe_familia
										: filters.equipe_familia
											? [filters.equipe_familia]
											: []
								}
								onSelect={(values) =>
									handleMultiFilterUpdate("equipe_familia", values)
								}
								disabled={loading}
								placeholder="Equipes da Família"
								defaultLabel="Todas as Equipes"
							/>
						}
					</div>
				</div>

				{totalResults !== undefined && (
					<div className="pt-4 border-t mt-4 flex items-center gap-2 text-sm text-muted-foreground">
						<span className="font-medium">
							{totalResults.toLocaleString("pt-BR")}
						</span>{" "}
						pessoa(s) encontrada(s)
					</div>
				)}
			</CardContent>
		</Card>
	);
};

// Exportar com React.memo para evitar re-renders quando props não mudarem
export const FilterCard = memo(FilterCardComponent);
