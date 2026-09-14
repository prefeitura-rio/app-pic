"use client";

import { memo, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { LazyFilterMultiSelect, LazyFilterSelect } from "@/app/components/LazyFilterSelects";
import { Button } from "@/app/components/ui/button";
import { Filter, X, RefreshCw, Download } from "lucide-react";
import type { DashboardFilterValues } from "@/app/types";

interface DashboardFilterCardProps {
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  onDownload?: () => void;
  loading?: boolean;
}

// Opções de secretaria fixas (dimensão do dashboard, fora do endpoint de filtros)
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
      (newFilters as Record<string, unknown>)[key] = value;
    }
    onFilterChange(newFilters);
  }, [filters, onFilterChange]);

  // Callback para filtros multi-select (arrays)
  const handleMultiFilterUpdate = useCallback((key: keyof DashboardFilterValues, values: string[]) => {
    const newFilters = { ...filters };
    if (values.length > 0) {
      (newFilters as Record<string, unknown>)[key] = values;
    } else {
      delete newFilters[key];
    }
    onFilterChange(newFilters);
  }, [filters, onFilterChange]);

  // Callback para filtros booleanos (converte string "true"/"false" para boolean)
  const handleBooleanFilterUpdate = useCallback((key: keyof DashboardFilterValues, value: string) => {
    const newFilters = { ...filters };
    if (value === "todos" || value === "todas" || value === "") {
      delete newFilters[key];
    } else {
      (newFilters as Record<string, unknown>)[key] = value === "true";
    }
    onFilterChange(newFilters);
  }, [filters, onFilterChange]);

  const clearFilters = useCallback(() => {
    onFilterChange({});
  }, [onFilterChange]);

  const formatGrupo = useMemo(() => formatGrupoLabel, []);

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
              transformLabel={formatGrupo}
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

            {/* Mês de Ingresso - Multi-select */}
            <LazyFilterMultiSelect
              field="cohorts"
              filters={filters}
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
            />

            {/* Secretaria - Single select (dimensão do dashboard, fixa) */}
            <VirtualizedSelect
              value={filters.secretaria || "todas"}
              onSelect={(v) => handleFilterUpdate("secretaria", v)}
              disabled={loading}
              placeholder="Secretaria"
              defaultLabel="Todas as Secretarias"
              options={SECRETARIA_OPTIONS}
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
              onSelect={(v) => handleBooleanFilterUpdate("has_bolsa_familia", v)}
              disabled={loading}
              placeholder="Todos Bolsa Família"
              defaultLabel="Todos Bolsa Família"
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
              onSelect={(values) => handleMultiFilterUpdate("subprefeitura", values)}
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
              onSelect={(values) => handleMultiFilterUpdate("regiao_administrativa", values)}
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

            {/* AP (Saúde) - Multi-select */}
            { (
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
            )}

            {/* CRE (Educação) - Multi-select */}
            { (
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
            )}

            {/* CAS (Assistência Social) - Multi-select */}
            { (
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
            )}

            {/* CRAS (Assistência Social) - Multi-select */}
            { (
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
            )}

            {/* Escolas (Educação) - Multi-select */}
            { (
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
            )}

            {/* Unidades de Saúde - Multi-select */}
            { (
              <LazyFilterMultiSelect
                field="clinicas"
                filters={filters}
                value={
                  Array.isArray(filters.unidade_saude)
                    ? filters.unidade_saude
                    : filters.unidade_saude
                      ? [filters.unidade_saude]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("unidade_saude", values)}
                disabled={loading}
                placeholder="Unidades de Saúde"
                defaultLabel="Todas as Unidades"
              />
            )}

            {/* Equipes de Saúde - Multi-select */}
            { (
              <LazyFilterMultiSelect
                field="equipes_familia"
                filters={filters}
                value={
                  Array.isArray(filters.equipe_saude)
                    ? filters.equipe_saude
                    : filters.equipe_saude
                      ? [filters.equipe_saude]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("equipe_saude", values)}
                disabled={loading}
                placeholder="Equipes de Saúde"
                defaultLabel="Todas as Equipes"
              />
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export const DashboardFilterCard = memo(DashboardFilterCardComponent);
