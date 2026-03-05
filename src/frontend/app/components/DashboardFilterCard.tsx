"use client";

import { memo, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { VirtualizedMultiSelect } from "@/app/components/ui/virtualized-multi-select";
import { Button } from "@/app/components/ui/button";
import { Filter, X, RefreshCw, Download } from "lucide-react";
import { SmartFilterOptions } from "@/app/types";

/**
 * Filtros específicos do Dashboard
 * Mapeados para as colunas da tabela de dashboard pré-agregada
 * Todos os filtros suportam multi-select
 */
export interface DashboardFilterValues {
  grupo?: string | string[];               // pic_grupo (multi-select)
  cohort?: string | string[];              // pic_cohort (safra) (multi-select)
  status?: string | string[];              // pic_status (multi-select)
  secretaria?: string | string[];          // secretaria (SMAS, SME, SMS) (multi-select)
  subprefeitura?: string | string[];       // subprefeitura (multi-select)
  regiao_administrativa?: string | string[]; // regiao_administrativa (multi-select)
  bairro?: string | string[];              // bairro (multi-select)
  cre?: string | string[];                 // id_cre (multi-select)
  ap?: string | string[];                  // id_ap (multi-select)
  cas?: string | string[];                 // id_cas (multi-select)
}

interface DashboardFilterCardProps {
  filterOptions: SmartFilterOptions;
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  onDownload?: () => void;
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
  onDownload,
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

  // Callback para filtros multi-select (arrays)
  const handleMultiFilterUpdate = useCallback((key: keyof DashboardFilterValues, values: string[]) => {
    const newFilters = { ...filters };
    if (values.length > 0) {
      newFilters[key] = values as any;
    } else {
      delete newFilters[key];
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
    subprefeituras: (filterOptions.subprefeituras || []).filter((item) => item.id && item.id.trim() !== ""),
    regioes_administrativas: (filterOptions.regioes_administrativas || []).filter((item) => item.id && item.id.trim() !== ""),
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
          {onDownload && (
            <Button
              variant="outline"
              size="sm"
              onClick={onDownload}
              className="h-8 text-xs"
              disabled={loading}
            >
              <Download className="h-3 w-3 mr-1" />
              Baixar JSON
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
            {/* Grupo - Multi-select */}
            <VirtualizedMultiSelect
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
              options={filteredOptions.grupos}
            />

            {/* Status - Multi-select */}
            <VirtualizedMultiSelect
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
              options={filteredOptions.status_list}
            />

            {/* Mês de Ingresso - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray(filters.cohort)
                  ? filters.cohort
                  : filters.cohort
                    ? [filters.cohort]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("cohort", values)}
              disabled={loading}
              placeholder="Meses de Ingresso"
              defaultLabel="Todos os Meses de Ingresso"
              options={filteredOptions.cohorts}
            />

            {/* Secretaria - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray(filters.secretaria)
                  ? filters.secretaria
                  : filters.secretaria
                    ? [filters.secretaria]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("secretaria", values)}
              disabled={loading}
              placeholder="Secretarias"
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
            {/* Subprefeitura - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray(filters.subprefeitura)
                  ? filters.subprefeitura
                  : filters.subprefeitura
                    ? [filters.subprefeitura]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("subprefeitura", values)}
              disabled={loading}
              placeholder="Subprefeituras"
              defaultLabel="Todas as Subprefeituras"
              options={filteredOptions.subprefeituras}
            />

            {/* Região Administrativa - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray(filters.regiao_administrativa)
                  ? filters.regiao_administrativa
                  : filters.regiao_administrativa
                    ? [filters.regiao_administrativa]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("regiao_administrativa", values)}
              disabled={loading}
              placeholder="Regiões Administrativas"
              defaultLabel="Todas as Regiões Adm."
              options={filteredOptions.regioes_administrativas}
            />

            {/* Bairro - Multi-select */}
            <VirtualizedMultiSelect
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
              options={filteredOptions.bairros}
            />

            {/* AP (Saúde) - Multi-select */}
            <VirtualizedMultiSelect
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
              options={filteredOptions.aps}
            />

            {/* CRE (Educação) - Multi-select */}
            <VirtualizedMultiSelect
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
              options={filteredOptions.cres}
            />

            {/* CAS (Assistência Social) - Multi-select */}
            <VirtualizedMultiSelect
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
              options={filteredOptions.cas_list}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export const DashboardFilterCard = memo(DashboardFilterCardComponent);
