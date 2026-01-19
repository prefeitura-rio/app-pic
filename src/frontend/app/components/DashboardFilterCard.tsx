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
  grupo?: string;       // pic_grupo
  cohort?: string;      // pic_cohort (safra)
  status?: string;      // pic_status
  secretaria?: string;  // secretaria (SMAS, SME, SMS)
  bairro?: string;      // bairro
  cre?: string;         // id_cre
  ap?: string;          // id_ap
  cas?: string;         // id_cas
}

interface DashboardFilterCardProps {
  filterOptions: SmartFilterOptions;
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

// Opções de secretaria fixas
const SECRETARIA_OPTIONS = [
  { id: "SMAS", label: "Assistência Social (SMAS)" },
  { id: "SME", label: "Educação (SME)" },
  { id: "SMS", label: "Saúde (SMS)" },
];

// Função para formatar labels de grupo
const formatGrupoLabel = (id: string): string => {
  const mapping: Record<string, string> = {
    "criancas_com_bolsa_familia": "Crianças com Bolsa Família",
    "criancas_sem_bolsa_familia": "Crianças sem Bolsa Família",
    "gravidas_com_bolsa_familia": "Grávidas com Bolsa Família",
    "gravidas_sem_bolsa_familia": "Grávidas sem Bolsa Família",
  };
  return mapping[id] || id;
};

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

  // Pré-filtrar opções (remover vazios) e formatar labels
  const filteredOptions = useMemo(() => ({
    grupos: (filterOptions.grupos || [])
      .filter((item) => item.id && item.id.trim() !== "")
      .map((item) => ({ ...item, label: formatGrupoLabel(item.id) })),
    cohorts: (filterOptions.cohorts || []).filter((item) => item.id && item.id.trim() !== ""),
    status_list: (filterOptions.status_list || []).filter((item) => item.id && item.id.trim() !== ""),
    bairros: (filterOptions.bairros || []).filter((item) => item.id && item.id.trim() !== ""),
    cres: (filterOptions.cres || []).filter((item) => item.id && item.id.trim() !== ""),
    aps: (filterOptions.aps || []).filter((item) => item.id && item.id.trim() !== ""),
    cas_list: (filterOptions.cas_list || []).filter((item) => item.id && item.id.trim() !== ""),
  }), [filterOptions]);

  return (
    <Card className="relative border-2">
      <CardHeader className="pb-4 flex flex-row items-center justify-between">
        <CardTitle className="text-2xl font-bold flex items-center gap-2">
          <Filter className="h-6 w-6" />
          Filtros
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
        {/* Primeiro Nível - Filtros Principais */}
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Filtros Principais
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {/* Grupo */}
            <VirtualizedSelect
              value={filters.grupo || "todos"}
              onSelect={(v) => handleFilterUpdate("grupo", v)}
              disabled={loading}
              placeholder="Grupo"
              defaultLabel="Todos os Grupos"
              options={filteredOptions.grupos}
            />

            {/* Status */}
            <VirtualizedSelect
              value={filters.status || "todos"}
              onSelect={(v) => handleFilterUpdate("status", v)}
              disabled={loading}
              placeholder="Status"
              defaultLabel="Todos os Status"
              options={filteredOptions.status_list}
            />

            {/* Mês de Ingresso */}
            <VirtualizedSelect
              value={filters.cohort || "todas"}
              onSelect={(v) => handleFilterUpdate("cohort", v)}
              disabled={loading}
              placeholder="Mês de Ingresso"
              defaultLabel="Todos os Meses de Ingresso"
              options={filteredOptions.cohorts}
            />

            {/* Secretaria */}
            <VirtualizedSelect
              value={filters.secretaria || "todas"}
              onSelect={(v) => handleFilterUpdate("secretaria", v)}
              disabled={loading}
              placeholder="Secretaria"
              defaultLabel="Todas as Secretarias"
              options={SECRETARIA_OPTIONS}
            />
          </div>
        </div>

        {/* Segundo Nível - Filtros Regionais */}
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Filtros Regionais
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {/* Bairro - oculto por padrão */}
            <VirtualizedSelect
              show={true}
              value={filters.bairro || "todos"}
              onSelect={(v) => handleFilterUpdate("bairro", v)}
              disabled={loading}
              placeholder="Bairro"
              defaultLabel="Todos os Bairros"
              options={filteredOptions.bairros}
            />

            {/* AP (Saúde) */}
            <VirtualizedSelect
              value={filters.ap || "todas"}
              onSelect={(v) => handleFilterUpdate("ap", v)}
              disabled={loading}
              placeholder="AP"
              defaultLabel="Todas as CAPs"
              options={filteredOptions.aps}
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

            {/* CAS (Assistência Social) */}
            <VirtualizedSelect
              value={filters.cas || "todas"}
              onSelect={(v) => handleFilterUpdate("cas", v)}
              disabled={loading}
              placeholder="CAS"
              defaultLabel="Todos as CAS"
              options={filteredOptions.cas_list}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export const DashboardFilterCard = memo(DashboardFilterCardComponent);
