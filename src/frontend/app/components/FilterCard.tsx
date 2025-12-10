"use client";

import { memo, useMemo, useCallback, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Filter, X, RefreshCw, Search } from "lucide-react";
import { SmartFilterOptions, DashboardFilters, ParticipantFilters } from "@/app/types";

type FilterType = DashboardFilters | ParticipantFilters;

interface FilterCardProps {
  filterOptions: SmartFilterOptions;
  filters: FilterType;
  onFilterChange: (filters: FilterType) => void;
  onRefresh?: () => void;
  loading?: boolean;
  showSearch?: boolean;
  totalResults?: number;
}

const FilterCardComponent = ({
  filterOptions,
  filters,
  onFilterChange,
  onRefresh,
  loading = false,
  showSearch = false,
  totalResults,
}: FilterCardProps) => {
  const [searchInput, setSearchInput] = useState("");

  // Memoizar callbacks para evitar re-criação
  const handleFilterUpdate = useCallback((key: string, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  }, [filters, onFilterChange]);

  const clearFilters = useCallback(() => {
    setSearchInput("");
    onFilterChange({});
  }, [onFilterChange]);

  // Sanitize search input (remove special chars and trim)
  const sanitizeSearchInput = useCallback((input: string): string => {
    return input
      .replace(/[.\-]/g, "") // Remove pontos e hífens (útil para CPF)
      .trim(); // Remove espaços em branco no início e fim
  }, []);

  const handleSearch = useCallback(() => {
    const sanitized = sanitizeSearchInput(searchInput);
    onFilterChange({
      ...filters,
      search: sanitized,
    });
  }, [filters, searchInput, onFilterChange, sanitizeSearchInput]);

  // OTIMIZAÇÃO CRÍTICA: Pré-filtrar todas as opções de filtro UMA VEZ
  const filteredOptions = useMemo(() => ({
    grupos: filterOptions.grupos.filter((item) => item.id && item.id.trim() !== ""),
    status_list: filterOptions.status_list.filter((item) => item.id && item.id.trim() !== ""),
    situacoes: filterOptions.situacoes.filter((item) => item.id && item.id.trim() !== ""),
    cohorts: filterOptions.cohorts.filter((item) => item.id && item.id.trim() !== ""),
    aps: filterOptions.aps.filter((item) => item.id && item.id.trim() !== ""),
    cres: filterOptions.cres.filter((item) => item.id && item.id.trim() !== ""),
    cas_list: filterOptions.cas_list.filter((item) => item.id && item.id.trim() !== ""),
    bairros: filterOptions.bairros.filter((item) => item.id && item.id.trim() !== ""),
    escolas: filterOptions.escolas.filter((item) => item.id && item.id.trim() !== ""),
    clinicas: filterOptions.clinicas.filter((item) => item.id && item.id.trim() !== ""),
    cras: filterOptions.cras.filter((item) => item.id && item.id.trim() !== ""),
    protocolo_descricoes: (filterOptions.protocolo_descricoes || []).filter((item) => item.id && item.id.trim() !== ""),
    protocolo_status_list: (filterOptions.protocolo_status_list || []).filter((item) => item.id && item.id.trim() !== ""),
  }), [filterOptions]);

  return (
    <Card className="relative border-2">
      <CardHeader className="pb-4 flex flex-row items-center justify-between">
        <CardTitle className="text-2xl font-bold flex items-center gap-2">
          <Filter className="h-6 w-6" />
          {showSearch ? "Filtros e Busca" : "Filtros"}
        </CardTitle>
        <div className="flex gap-2">
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
              <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
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
              placeholder="Buscar por CPF ou nome..."
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
            {/* Grupo */}
            <VirtualizedSelect
              value={(filters as any).grupo || "todos"}
              onSelect={(v) => handleFilterUpdate("grupo", v)}
              disabled={loading}
              placeholder="Grupo"
              defaultLabel="Todos os Grupos"
              options={filteredOptions.grupos}
            />

            {/* Status */}
            <VirtualizedSelect
              value={(filters as any).status || "todos"}
              onSelect={(v) => handleFilterUpdate("status", v)}
              disabled={loading}
              placeholder="Status"
              defaultLabel="Todos os Status"
              options={filteredOptions.status_list}
            />

            {/* Situação */}
            <VirtualizedSelect
              value={(filters as any).situacao || "todas"}
              onSelect={(v) => handleFilterUpdate("situacao", v)}
              disabled={loading}
              placeholder="Situação"
              defaultLabel="Todas as Situações"
              options={filteredOptions.situacoes}
            />

            {/* Safra */}
            <VirtualizedSelect
              value={(filters as any).safra || "todas"}
              onSelect={(v) => handleFilterUpdate("safra", v)}
              disabled={loading}
              placeholder="Safra"
              defaultLabel="Todas as Safras"
              options={filteredOptions.cohorts}
            />

            {/* Protocolo */}
            <VirtualizedSelect
              value={(filters as any).protocolo_descricao || "todos"}
              onSelect={(v) => handleFilterUpdate("protocolo_descricao", v)}
              disabled={loading}
              placeholder="Protocolo"
              defaultLabel="Todos os Protocolos"
              options={filteredOptions.protocolo_descricoes}
              style={{ gridColumn: "span 2" }}
            />

            {/* Status Protocolo */}
            <VirtualizedSelect
              value={(filters as any).protocolo_status || "todos"}
              onSelect={(v) => handleFilterUpdate("protocolo_status", v)}
              disabled={loading}
              placeholder="Status Protocolo"
              defaultLabel="Todos os Status de Protocolos"
              options={filteredOptions.protocolo_status_list}
              style={{ gridColumn: "span 2" }}
            />
          </div>
        </div>

        {/* Segundo Nível - Filtros Regionais */}
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Filtros Regionais
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {/* EDUCAÇÃO */}
            {/* Escolas */}
            <VirtualizedSelect
              value={(filters as any).escola || "todas"}
              onSelect={(v) => handleFilterUpdate("escola", v)}
              disabled={loading}
              placeholder="Escola"
              defaultLabel="Todas as Escolas"
              options={filteredOptions.escolas}
              style={{ gridColumn: "span 2" }}
            />

            {/* CRE (Coordenadoria Regional de Educação) */}
            <VirtualizedSelect
              value={(filters as any).cre || "todas"}
              onSelect={(v) => handleFilterUpdate("cre", v)}
              disabled={loading}
              placeholder="CRE"
              defaultLabel="Todas as CREs"
              options={filteredOptions.cres}
            />

            {/* ASSISTÊNCIA SOCIAL */}
            {/* CRAS */}
            <VirtualizedSelect
              value={(filters as any).cras || "todas"}
              onSelect={(v) => handleFilterUpdate("cras", v)}
              disabled={loading}
              placeholder="CRAS"
              defaultLabel="Todos os CRAS"
              options={filteredOptions.cras}
            />

            {/* CAS */}
            <VirtualizedSelect
              value={(filters as any).cas || "todas"}
              onSelect={(v) => handleFilterUpdate("cas", v)}
              disabled={loading}
              placeholder="CAS"
              defaultLabel="Todas as CAS"
              options={filteredOptions.cas_list}
            />

            {/* AP (Área Programática) */}
            <VirtualizedSelect
              value={(filters as any).ap || "todas"}
              onSelect={(v) => handleFilterUpdate("ap", v)}
              disabled={loading}
              placeholder="AP"
              defaultLabel="Todas as APs"
              options={filteredOptions.aps}
            />

            {/* SAÚDE */}
            {/* Clínicas da Família */}
            <VirtualizedSelect
              value={(filters as any).clinica || "todas"}
              onSelect={(v) => handleFilterUpdate("clinica", v)}
              disabled={loading}
              placeholder="Clínica da Família"
              defaultLabel="Todas as Clínicas da Família"
              options={filteredOptions.clinicas}
            />

            {/* LOCALIZAÇÃO */}
            {/* Bairro */}
            <VirtualizedSelect
              value={(filters as any).bairro || "todos"}
              onSelect={(v) => handleFilterUpdate("bairro", v)}
              disabled={loading}
              placeholder="Bairro"
              defaultLabel="Todos os Bairros"
              options={filteredOptions.bairros}
            />
          </div>
        </div>

        {totalResults !== undefined && (
          <div className="pt-4 border-t mt-4 flex items-center gap-2 text-sm text-muted-foreground">
            <span className="font-medium">{totalResults.toLocaleString('pt-BR')}</span> pessoa(s) encontrada(s)
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Exportar com React.memo para evitar re-renders quando props não mudarem
export const FilterCard = memo(FilterCardComponent);
