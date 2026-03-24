"use client";

import { memo, useMemo, useCallback, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { VirtualizedMultiSelect } from "@/app/components/ui/virtualized-multi-select";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Filter, X, RefreshCw, Search, Download } from "lucide-react";
import { SmartFilterOptions, DashboardFilters, ParticipantFilters } from "@/app/types";

type FilterType = DashboardFilters | ParticipantFilters;

interface FilterCardProps {
  filterOptions: SmartFilterOptions;
  filters: FilterType;
  onFilterChange: (filters: FilterType) => void;
  onRefresh?: () => void;
  onDownload?: () => void;
  loading?: boolean;
  showSearch?: boolean;
  totalResults?: number;
}

const FilterCardComponent = ({
  filterOptions,
  filters,
  onFilterChange,
  onRefresh,
  onDownload,
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

  // Callback para filtros multi-select (arrays)
  const handleMultiFilterUpdate = useCallback((key: string, values: string[]) => {
    onFilterChange({
      ...filters,
      [key]: values.length > 0 ? values : undefined,
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
    grupos: (filterOptions.grupos || []).filter((item) => item.id && item.id.trim() !== ""),
    status_list: (filterOptions.status_list || []).filter((item) => item.id && item.id.trim() !== ""),
    situacoes: (filterOptions.situacoes || []).filter((item) => item.id && item.id.trim() !== ""),
    cohorts: (filterOptions.cohorts || []).filter((item) => item.id && item.id.trim() !== ""),
    aps: (filterOptions.aps || []).filter((item) => item.id && item.id.trim() !== ""),
    cres: (filterOptions.cres || []).filter((item) => item.id && item.id.trim() !== ""),
    cas_list: (filterOptions.cas_list || []).filter((item) => item.id && item.id.trim() !== ""),
    subprefeituras: (filterOptions.subprefeituras || []).filter((item) => item.id && item.id.trim() !== ""),
    regioes_administrativas: (filterOptions.regioes_administrativas || []).filter((item) => item.id && item.id.trim() !== ""),
    bairros: (filterOptions.bairros || []).filter((item) => item.id && item.id.trim() !== ""),
    escolas: (filterOptions.escolas || []).filter((item) => item.id && item.id.trim() !== ""),
    clinicas: (filterOptions.clinicas || []).filter((item) => item.id && item.id.trim() !== ""),
    cras: (filterOptions.cras || []).filter((item) => item.id && item.id.trim() !== ""),
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
            <VirtualizedMultiSelect
              value={
                Array.isArray((filters as any).grupo)
                  ? (filters as any).grupo
                  : (filters as any).grupo
                    ? [(filters as any).grupo]
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
                Array.isArray((filters as any).status)
                  ? (filters as any).status
                  : (filters as any).status
                    ? [(filters as any).status]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("status", values)}
              disabled={loading}
              placeholder="Status"
              defaultLabel="Todos os Status"
              options={filteredOptions.status_list}
            />

            {/* Situação - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray((filters as any).situacao)
                  ? (filters as any).situacao
                  : (filters as any).situacao
                    ? [(filters as any).situacao]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("situacao", values)}
              disabled={loading}
              placeholder="Situações"
              defaultLabel="Todas as Situações"
              options={filteredOptions.situacoes}
            />

            {/* Mês de Ingresso no Programa - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray((filters as any).safra)
                  ? (filters as any).safra
                  : (filters as any).safra
                    ? [(filters as any).safra]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("safra", values)}
              disabled={loading}
              placeholder="Meses de Ingresso"
              defaultLabel="Todos os Meses de Ingresso"
              options={filteredOptions.cohorts}
            />

            {/* Secretaria de Protocolo */}
            <VirtualizedSelect
              value={(filters as any).protocolo_secretaria || "todas"}
              onSelect={(v) => handleFilterUpdate("protocolo_secretaria", v)}
              disabled={loading}
              placeholder="Filtrar Protocolos por Secretaria"
              defaultLabel="Todos os Protocolos por Secretaria"
              options={[
                { id: "SME", label: "Educação (SME)" },
                { id: "SMAS", label: "Assistência (SMAS)" },
                { id: "SMS", label: "Saúde (SMS)" },
              ]}
            />

            {/* Protocolo (Multi-select) */}
            <VirtualizedMultiSelect
              value={
                Array.isArray((filters as any).protocolo_descricao)
                  ? (filters as any).protocolo_descricao
                  : (filters as any).protocolo_descricao
                    ? [(filters as any).protocolo_descricao]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("protocolo_descricao", values)}
              disabled={loading}
              placeholder="Protocolos"
              defaultLabel="Todos os Protocolos"
              options={filteredOptions.protocolo_descricoes}
            />

            {/* Status Protocolo - Multi-select */}
            <VirtualizedMultiSelect
              value={
                Array.isArray((filters as any).protocolo_status)
                  ? (filters as any).protocolo_status
                  : (filters as any).protocolo_status
                    ? [(filters as any).protocolo_status]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("protocolo_status", values)}
              disabled={loading}
              placeholder="Status Protocolos"
              defaultLabel="Todos os Status de Protocolos"
              options={filteredOptions.protocolo_status_list}
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
                Array.isArray((filters as any).subprefeitura)
                  ? (filters as any).subprefeitura
                  : (filters as any).subprefeitura
                    ? [(filters as any).subprefeitura]
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
                Array.isArray((filters as any).regiao_administrativa)
                  ? (filters as any).regiao_administrativa
                  : (filters as any).regiao_administrativa
                    ? [(filters as any).regiao_administrativa]
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
                Array.isArray((filters as any).bairro)
                  ? (filters as any).bairro
                  : (filters as any).bairro
                    ? [(filters as any).bairro]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("bairro", values)}
              disabled={loading}
              placeholder="Bairros"
              defaultLabel="Todos os Bairros"
              options={filteredOptions.bairros}
            />

            {/* ASSISTÊNCIA SOCIAL */}
            {/* CAS - Multi-select */}
            { (
              <VirtualizedMultiSelect
                value={
                  Array.isArray((filters as any).cas)
                    ? (filters as any).cas
                    : (filters as any).cas
                      ? [(filters as any).cas]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("cas", values)}
                disabled={loading}
                placeholder="CAS"
                defaultLabel="Todas as CAS"
                options={filteredOptions.cas_list}
              />
            )}

            {/* CRAS - Multi-select */}
            { (
              <VirtualizedMultiSelect
                value={
                  Array.isArray((filters as any).cras)
                    ? (filters as any).cras
                    : (filters as any).cras
                      ? [(filters as any).cras]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("cras", values)}
                disabled={loading}
                placeholder="CRAS"
                defaultLabel="Todos os CRAS"
                options={filteredOptions.cras}
              />
            )}

            {/* EDUCAÇÃO */}
            {/* CRE (Coordenadoria Regional de Educação) - Multi-select */}
            { (
              <VirtualizedMultiSelect
                value={
                  Array.isArray((filters as any).cre)
                    ? (filters as any).cre
                    : (filters as any).cre
                      ? [(filters as any).cre]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("cre", values)}
                disabled={loading}
                placeholder="CREs"
                defaultLabel="Todas as CREs"
                options={filteredOptions.cres}
              />
            )}

            {/* Escolas - Multi-select */}
            { (
              <VirtualizedMultiSelect
                value={
                  Array.isArray((filters as any).escola)
                    ? (filters as any).escola
                    : (filters as any).escola
                      ? [(filters as any).escola]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("escola", values)}
                disabled={loading}
                placeholder="Escolas"
                defaultLabel="Todas as Escolas"
                options={filteredOptions.escolas}
              />
            )}

            {/* SAÚDE */}
            {/* AP (Área Programática) - Multi-select */}
            { (
              <VirtualizedMultiSelect
                value={
                  Array.isArray((filters as any).ap)
                    ? (filters as any).ap
                    : (filters as any).ap
                      ? [(filters as any).ap]
                      : []
                }
                onSelect={(values) => handleMultiFilterUpdate("ap", values)}
                disabled={loading}
                placeholder="CAPs"
                defaultLabel="Todas as CAPs"
                options={filteredOptions.aps}
              />
            )}

            {/* Clínicas da Família - Multi-select */}
            { (
              <VirtualizedMultiSelect
                value={
                  Array.isArray((filters as any).clinica)
                    ? (filters as any).clinica
                    : (filters as any).clinica
                      ? [(filters as any).clinica]
                    : []
              }
              onSelect={(values) => handleMultiFilterUpdate("clinica", values)}
              disabled={loading}
              placeholder="Clínicas da Família"
              defaultLabel="Todas as Clínicas"
              options={filteredOptions.clinicas}
            />
            )}
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
