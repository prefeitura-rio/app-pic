import { useState, useMemo, useCallback, memo } from "react";
import { useDebounce } from "../hooks/useDebounce";
import {
  Participante,
  SmartFilterOptions,
  ParticipantFilters,
  PaginationMeta,
} from "../types";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { VirtualizedParticipantTable } from "./VirtualizedParticipantTable";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { Button } from "@/app/components/ui/button";
import { Badge } from "@/app/components/ui/badge";
import { Input } from "@/app/components/ui/input";
import { Skeleton } from "@/app/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/app/components/ui/dialog";
import { Separator } from "@/app/components/ui/separator";
import {
  Users,
  Search,
  ChevronLeft,
  ChevronRight,
  Filter,
  Loader2,
  Eye,
  RefreshCw,
} from "lucide-react";

interface ProfessionalTabProps {
  data: Participante[];
  meta: PaginationMeta | null;
  filterOptions: SmartFilterOptions;
  filters: ParticipantFilters;
  onFilterChange: (filters: ParticipantFilters) => void;
  onPageChange: (page: number) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

// Removido MemoizedSelect - agora usando VirtualizedSelect

const ProfessionalTabComponent = ({
  data,
  meta,
  filterOptions,
  filters,
  onFilterChange,
  onPageChange,
  onRefresh,
  loading = false,
}: ProfessionalTabProps) => {
  const [searchInput, setSearchInput] = useState("");
  const [selectedParticipant, setSelectedParticipant] = useState<Participante | null>(null);

  // Debounce search input para evitar re-renders durante digitação
  const debouncedSearch = useDebounce(searchInput, 300);

  // Memoizar callbacks para evitar re-criação
  const handleFilterUpdate = useCallback((key: keyof ParticipantFilters, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  }, [filters, onFilterChange]);

  const handleSearch = useCallback(() => {
    onFilterChange({
      ...filters,
      search: searchInput,
    });
  }, [filters, searchInput, onFilterChange]);

  const clearFilters = useCallback(() => {
    setSearchInput("");
    onFilterChange({});
  }, [onFilterChange]);

  const getBadgeVariant = useCallback((situacao?: string) => {
    if (!situacao) return "outline";
    if (situacao.toLowerCase().includes("regular")) return "default";
    if (situacao.toLowerCase().includes("atenção")) return "secondary";
    return "destructive";
  }, []);

  // Memoizar dados filtrados (caso precisemos de filtro client-side no futuro)
  const displayData = useMemo(() => data, [data]);

  // OTIMIZAÇÃO CRÍTICA: Pré-filtrar todas as opções de filtro UMA VEZ
  const filteredOptions = useMemo(() => ({
    grupos: filterOptions.grupos.filter((item) => item.id && item.id.trim() !== ""),
    status_list: filterOptions.status_list.filter((item) => item.id && item.id.trim() !== ""),
    situacoes: filterOptions.situacoes.filter((item) => item.id && item.id.trim() !== ""),
    cohorts: filterOptions.cohorts.filter((item) => item.id && item.id.trim() !== ""),
    caps: filterOptions.caps.filter((item) => item.id && item.id.trim() !== ""),
    cres: filterOptions.cres.filter((item) => item.id && item.id.trim() !== ""),
    cas_list: filterOptions.cas_list.filter((item) => item.id && item.id.trim() !== ""),
    bairros: filterOptions.bairros.filter((item) => item.id && item.id.trim() !== ""),
    escolas: filterOptions.escolas.filter((item) => item.id && item.id.trim() !== ""),
    clinicas: filterOptions.clinicas.filter((item) => item.id && item.id.trim() !== ""),
    cras: filterOptions.cras.filter((item) => item.id && item.id.trim() !== ""),
  }), [filterOptions]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Busca Individual
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          Busque por CPF ou nome e aplique filtros para encontrar participantes
        </p>
      </div>

      {/* Filtros */}
      <Card className="relative">
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filtros
          </CardTitle>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="h-8 text-xs"
              disabled={loading}
            >
              Limpar Filtros
            </Button>
            {onRefresh && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onRefresh}
                className="h-8 text-xs"
                disabled={loading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                Atualizar
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {/* Busca */}
          <div className="flex gap-2">
            <Input
              type="text"
              placeholder="Buscar por CPF ou nome..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="flex-1"
              disabled={loading}
            />
            <Button onClick={handleSearch} disabled={loading}>
              <Search className="h-4 w-4 mr-2" />
              Buscar
            </Button>
          </div>

          {/* Primeiro Nível - Filtros Principais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Principais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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

              {/* Situação */}
              <VirtualizedSelect
                value={filters.situacao || "todas"}
                onSelect={(v) => handleFilterUpdate("situacao", v)}
                disabled={loading}
                placeholder="Situação"
                defaultLabel="Todas as Situações"
                options={filteredOptions.situacoes}
              />

              {/* Safra */}
              <VirtualizedSelect
                value={filters.safra || "todas"}
                onSelect={(v) => handleFilterUpdate("safra", v)}
                disabled={loading}
                placeholder="Safra"
                defaultLabel="Todas as Safras"
                options={filteredOptions.cohorts}
              />
            </div>
          </div>

          {/* Segundo Nível - Filtros Regionais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Regionais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* EDUCAÇÃO */}
              {/* Escolas */}
              <VirtualizedSelect
                value={filters.escola || "todas"}
                onSelect={(v) => handleFilterUpdate("escola", v)}
                disabled={loading}
                placeholder="Escola"
                defaultLabel="Todas as Escolas"
                options={filteredOptions.escolas}
              />

              {/* CRE (Coordenadoria Regional de Educação) */}
              <VirtualizedSelect
                value={filters.cre || "todas"}
                onSelect={(v) => handleFilterUpdate("cre", v)}
                disabled={loading}
                placeholder="CRE"
                defaultLabel="Todas as CREs"
                options={filteredOptions.cres}
              />

              {/* ASSISTÊNCIA SOCIAL */}
              {/* CRAS */}
              <VirtualizedSelect
                value={filters.cras || "todas"}
                onSelect={(v) => handleFilterUpdate("cras", v)}
                disabled={loading}
                placeholder="CRAS"
                defaultLabel="Todos os CRAS"
                options={filteredOptions.cras}
              />

              {/* CAS */}
              <VirtualizedSelect
                value={filters.cas || "todas"}
                onSelect={(v) => handleFilterUpdate("cas", v)}
                disabled={loading}
                placeholder="CAS"
                defaultLabel="Todas as CAS"
                options={filteredOptions.cas_list}
              />

              {/* CAP (Centro de Atenção Psicossocial) */}
              <VirtualizedSelect
                value={filters.cap || "todas"}
                onSelect={(v) => handleFilterUpdate("cap", v)}
                disabled={loading}
                placeholder="CAP"
                defaultLabel="Todas as CAPs"
                options={filteredOptions.caps}
              />

              {/* SAÚDE */}
              {/* Clínicas da Família */}
              <VirtualizedSelect
                value={filters.clinica || "todas"}
                onSelect={(v) => handleFilterUpdate("clinica", v)}
                disabled={loading}
                placeholder="Clínica da Família"
                defaultLabel="Todas as Clínicas da Família"
                options={filteredOptions.clinicas}
              />

              {/* LOCALIZAÇÃO */}
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
          </div>

          {meta && (
            <div className="pt-2 text-sm text-muted-foreground border-t mt-4">
              📊 {meta.total_rows.toLocaleString('pt-BR')} resultado(s) encontrado(s)
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results Table */}
      {loading && !data.length ? (
        <Card className="border-2">
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : displayData.length > 0 ? (
        <Card className="border-2 relative">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              Lista de Participantes
            </CardTitle>
          </CardHeader>
          <CardContent>
            {/* OTIMIZAÇÃO: Tabela virtualizada para performance com muitos dados */}
            <VirtualizedParticipantTable
              data={displayData}
              onRowClick={setSelectedParticipant}
              getBadgeVariant={getBadgeVariant}
              isLoading={loading}
            />

            {/* Pagination */}
            {meta && meta.total_pages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-muted-foreground">
                  Página {meta.page} de {meta.total_pages} ({meta.total_rows} itens)
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onPageChange(Math.max(1, meta.page - 1))}
                    disabled={meta.page === 1 || loading}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Anterior
                  </Button>

                  <span className="text-sm px-2">Página {meta.page}</span>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onPageChange(Math.min(meta.total_pages, meta.page + 1))}
                    disabled={meta.page === meta.total_pages || loading}
                  >
                    Próxima
                    <ChevronRight className="h-4 w-4" />
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
              <p className="text-lg font-medium">Nenhum resultado encontrado</p>
              <p className="text-sm mt-2">
                Tente ajustar os filtros ou termo de busca
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Modal de Detalhamento */}
      <Dialog open={!!selectedParticipant} onOpenChange={() => setSelectedParticipant(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          {selectedParticipant && (
            <>
              <DialogHeader>
                <DialogTitle className="text-2xl flex items-center gap-2">
                  <Eye className="h-6 w-6 text-primary" />
                  Detalhamento do Participante
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Informações Básicas */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Informações Básicas</h3>
                  <div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
                    <div>
                      <p className="text-sm text-muted-foreground">Nome</p>
                      <p className="font-medium">{selectedParticipant.nome}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">CPF</p>
                      <p className="font-mono font-medium">{selectedParticipant.cpf}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Grupo</p>
                      <p className="font-medium">
                        {selectedParticipant.grupo?.toLowerCase().includes("crianca") ? "👶 Criança" : "🤰 Gestante"}
                        {selectedParticipant.bolsa_familia_indicador && " • Bolsa Família"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Idade</p>
                      <p className="font-medium">{selectedParticipant.idade || "-"} anos</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Bairro</p>
                      <p className="font-medium">{selectedParticipant.bairro}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Escola</p>
                      <p className="font-medium">{selectedParticipant.nome_escola || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Clínica da Família</p>
                      <p className="font-medium">{selectedParticipant.nome_clinica_familia || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">CRAS</p>
                      <p className="font-medium">{selectedParticipant.nome_cras || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Safra</p>
                      <p className="font-medium">{selectedParticipant.cohort || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Status</p>
                      <Badge variant={selectedParticipant.status === "ativo" ? "default" : "secondary"}>
                        {selectedParticipant.status}
                      </Badge>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Situação Geral */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Situação Geral</h3>
                  <div className="grid grid-cols-4 gap-4">
                    <Card className="bg-muted">
                      <CardContent className="p-4 text-center">
                        <p className="text-sm text-muted-foreground">Total</p>
                        <p className="text-2xl font-bold">{selectedParticipant.total_fracao || "0/0"}</p>
                        <Badge variant={getBadgeVariant(selectedParticipant.situacao)} className="mt-2">
                          {selectedParticipant.situacao}
                        </Badge>
                      </CardContent>
                    </Card>

                    <Card className="bg-green-50 dark:bg-green-950/20">
                      <CardContent className="p-4 text-center">
                        <p className="text-sm text-muted-foreground">Assistência</p>
                        <p className="text-2xl font-bold">{selectedParticipant.assistencia_fracao || "0/0"}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {selectedParticipant.assistencia_protocolos_violados || 0} violados
                        </p>
                      </CardContent>
                    </Card>

                    <Card className="bg-orange-50 dark:bg-orange-950/20">
                      <CardContent className="p-4 text-center">
                        <p className="text-sm text-muted-foreground">Educação</p>
                        <p className="text-2xl font-bold">{selectedParticipant.educacao_fracao || "0/0"}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {selectedParticipant.educacao_protocolos_violados || 0} violados
                        </p>
                      </CardContent>
                    </Card>

                    <Card className="bg-red-50 dark:bg-red-950/20">
                      <CardContent className="p-4 text-center">
                        <p className="text-sm text-muted-foreground">Saúde</p>
                        <p className="text-2xl font-bold">{selectedParticipant.saude_fracao || "0/0"}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {selectedParticipant.saude_protocolos_violados || 0} violados
                        </p>
                      </CardContent>
                    </Card>
                  </div>
                </div>

                <Separator />

                {/* Indicadores Assistência Social */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">📋 Dimensão Assistência Social</h3>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                      <span className="text-sm">💰 Bolsa Família</span>
                      <Badge variant={selectedParticipant.bolsa_familia_indicador ? "default" : "destructive"}>
                        {selectedParticipant.bolsa_familia_indicador ? "✓ Sim" : "✗ Não"}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                      <span className="text-sm">📋 CadÚnico Atualizado</span>
                      <Badge variant={selectedParticipant.cadunico_indicador ? "default" : "destructive"}>
                        {selectedParticipant.cadunico_indicador ? "✓ Sim" : "✗ Não"}
                      </Badge>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Indicadores Educação */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">📚 Dimensão Educação</h3>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                      <span className="text-sm">Frequência Escolar</span>
                      <Badge variant={
                        selectedParticipant.frequencia_escolar_percentual
                          ? (selectedParticipant.frequencia_escolar_percentual >= 75 ? "default" : "destructive")
                          : "secondary"
                      }>
                        {selectedParticipant.frequencia_escolar_percentual
                          ? `${selectedParticipant.frequencia_escolar_percentual.toFixed(1)}%`
                          : "N/A"}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                      <span className="text-sm">Escola</span>
                      <span className="text-sm font-medium">{selectedParticipant.nome_escola || "-"}</span>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Resumo Protocolos */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Resumo de Protocolos</h3>
                  <div className="bg-muted/50 p-4 rounded-lg">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Total de Protocolos</p>
                        <p className="text-3xl font-bold text-primary">{selectedParticipant.total_protocolos || 0}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Protocolos Violados</p>
                        <p className="text-3xl font-bold text-destructive">{selectedParticipant.total_protocolos_violados || 0}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

// Exportar com React.memo para evitar re-renders quando props não mudarem
export const ProfessionalTab = memo(ProfessionalTabComponent);
