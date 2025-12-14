"use client";

import { memo, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { Button } from "@/app/components/ui/button";
import { Filter, X, RefreshCw } from "lucide-react";
import { SmartFilterOptions } from "@/app/types";

/**
 * Filtros específicos do Dashboard
 * Mapeados para as colunas da tabela de dashboard pré-agregada
 */
export interface DashboardFilterValues {
  grupo?: string;    // pic_grupo
  cohort?: string;   // pic_cohort (safra)
  status?: string;   // pic_status
  bairro?: string;   // bairro
  cre?: string;      // id_cre
  ap?: string;       // id_ap
  cas?: string;      // id_cas
}

interface DashboardFilterCardProps {
  filterOptions: SmartFilterOptions;
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

const DashboardFilterCardComponent = ({
  filterOptions,
  filters,
  onFilterChange,
  onRefresh,
  loading = false,
}: DashboardFilterCardProps) => {

  const handleFilterUpdate = useCallback((key: keyof DashboardFilterValues, value: string) => {
    const newFilters = { ...filters };
    if (value === "todos" || value === "todas" || value === "") {
      delete newFilters[key];
    } else {
      newFilters[key] = value;
    }
    onFilterChange(newFilters);
  }, [filters, onFilterChange]);

  const clearFilters = useCallback(() => {
    onFilterChange({});
  }, [onFilterChange]);

  // Contar filtros ativos
  const activeFiltersCount = useMemo(() => {
    return Object.keys(filters).filter(k => filters[k as keyof DashboardFilterValues]).length;
  }, [filters]);

  // Pré-filtrar opções (remover vazios)
  const filteredOptions = useMemo(() => ({
    grupos: (filterOptions.grupos || []).filter((item) => item.id && item.id.trim() !== ""),
    cohorts: (filterOptions.cohorts || []).filter((item) => item.id && item.id.trim() !== ""),
    status_list: (filterOptions.status_list || []).filter((item) => item.id && item.id.trim() !== ""),
    bairros: (filterOptions.bairros || []).filter((item) => item.id && item.id.trim() !== ""),
    cres: (filterOptions.cres || []).filter((item) => item.id && item.id.trim() !== ""),
    aps: (filterOptions.aps || []).filter((item) => item.id && item.id.trim() !== ""),
    cas_list: (filterOptions.cas_list || []).filter((item) => item.id && item.id.trim() !== ""),
  }), [filterOptions]);

  return (
    <Card className="relative border-2">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-lg font-semibold flex items-center gap-2">
          <Filter className="h-5 w-5" />
          Filtros
          {activeFiltersCount > 0 && (
            <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-primary text-primary-foreground rounded-full">
              {activeFiltersCount}
            </span>
          )}
        </CardTitle>
        <div className="flex gap-2">
          {activeFiltersCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="h-8 text-xs"
              disabled={loading}
            >
              <X className="h-3 w-3 mr-1" />
              Limpar
            </Button>
          )}
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
      <CardContent className="pt-0">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* Grupo (crianca, gestante) */}
          <VirtualizedSelect
            value={filters.grupo || "todos"}
            onSelect={(v) => handleFilterUpdate("grupo", v)}
            disabled={loading}
            placeholder="Grupo"
            defaultLabel="Todos os Grupos"
            options={filteredOptions.grupos}
          />

          {/* Safra/Cohort */}
          <VirtualizedSelect
            value={filters.cohort || "todas"}
            onSelect={(v) => handleFilterUpdate("cohort", v)}
            disabled={loading}
            placeholder="Safra"
            defaultLabel="Todas as Safras"
            options={filteredOptions.cohorts}
          />

          {/* Status (ativo, inativo) */}
          <VirtualizedSelect
            value={filters.status || "todos"}
            onSelect={(v) => handleFilterUpdate("status", v)}
            disabled={loading}
            placeholder="Status"
            defaultLabel="Todos os Status"
            options={filteredOptions.status_list}
          />

          {/* CAS (Assistência Social) */}
          <VirtualizedSelect
            value={filters.cas || "todas"}
            onSelect={(v) => handleFilterUpdate("cas", v)}
            disabled={loading}
            placeholder="CAS"
            defaultLabel="Todas as CAS"
            options={filteredOptions.cas_list}
          />

          {/* CRE (Educação) */}
          <VirtualizedSelect
            value={filters.cre || "todas"}
            onSelect={(v) => handleFilterUpdate("cre", v)}
            disabled={loading}
            placeholder="CRE"
            defaultLabel="Todas as CREs"
            options={filteredOptions.cres}
          />

          {/* AP (Saúde) */}
          <VirtualizedSelect
            value={filters.ap || "todas"}
            onSelect={(v) => handleFilterUpdate("ap", v)}
            disabled={loading}
            placeholder="AP"
            defaultLabel="Todas as APs"
            options={filteredOptions.aps}
          />

          {/* Bairro */}
          <VirtualizedSelect
            value={filters.bairro || "todos"}
            onSelect={(v) => handleFilterUpdate("bairro", v)}
            disabled={loading}
            placeholder="Bairro"
            defaultLabel="Todos os Bairros"
            options={filteredOptions.bairros}
          />
        </div>
      </CardContent>
    </Card>
  );
};

export const DashboardFilterCard = memo(DashboardFilterCardComponent);
