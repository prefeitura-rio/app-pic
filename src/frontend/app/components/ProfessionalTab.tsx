import { useState, useMemo, useCallback, memo } from "react";
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
  Eye,
  RefreshCw,
  X,
  Filter,
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
  pageSize: number;
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
  pageSize,
}: ProfessionalTabProps) => {
  const [searchInput, setSearchInput] = useState("");
  const [selectedParticipant, setSelectedParticipant] = useState<Participante | null>(null);

  // Memoizar callbacks para evitar re-criação
  const handleFilterUpdate = useCallback((key: keyof ParticipantFilters, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  }, [filters, onFilterChange]);

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

  const clearFilters = useCallback(() => {
    setSearchInput("");
    onFilterChange({});
  }, [onFilterChange]);

  const getBadgeVariant = useCallback((situacao?: string): "outline" | "default" | "secondary" | "destructive" | "warning" => {
    if (!situacao) return "outline";
    const lower = situacao.toLowerCase();
    if (lower === "regular") return "default";
    if (lower.includes("atenção") || lower.includes("atencao")) return "warning";
    if (lower.includes("irregular")) return "destructive";
    return "secondary";
  }, []);

  // Memoizar dados filtrados (caso precisemos de filtro client-side no futuro)
  const displayData = useMemo(() => data, [data]);

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
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Busca Individual
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          Busque por CPF ou nome para ver os detalhes de uma pessoa específica
        </p>
      </div>

      {/* Filtros e Busca */}
      <Card className="relative border-2">
        <CardHeader className="pb-4 flex flex-row items-center justify-between">
          <CardTitle className="text-2xl font-bold flex items-center gap-2">
            <Filter className="h-6 w-6" />
            Filtros e Busca
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
          {/* Busca - Full Width com ícone interno */}
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

              {/* Protocolo */}
              <VirtualizedSelect
                value={filters.protocolo_descricao || "todos"}
                onSelect={(v) => handleFilterUpdate("protocolo_descricao", v)}
                disabled={loading}
                placeholder="Protocolo"
                defaultLabel="Todos os Protocolos"
                options={filteredOptions.protocolo_descricoes}
                style={{ gridColumn: "span 2" }}
              />

              {/* Status Protocolo */}
              <VirtualizedSelect
                value={filters.protocolo_status || "todos"}
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
                value={filters.escola || "todas"}
                onSelect={(v) => handleFilterUpdate("escola", v)}
                disabled={loading}
                placeholder="Escola"
                defaultLabel="Todas as Escolas"
                options={filteredOptions.escolas}
                style={{ gridColumn: "span 2" }}
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

              {/* AP (Área Programática) */}
              <VirtualizedSelect
                value={filters.ap || "todas"}
                onSelect={(v) => handleFilterUpdate("ap", v)}
                disabled={loading}
                placeholder="AP"
                defaultLabel="Todas as APs"
                options={filteredOptions.aps}
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
            <div className="pt-4 border-t mt-4 flex items-center gap-2 text-sm text-muted-foreground">
              <span className="font-medium">{meta.total_rows.toLocaleString('pt-BR')}</span> pessoa(s) encontrada(s)
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results Table */}
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
      ) : displayData.length > 0 ? (
        <Card className="border-2 relative">
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Users className="h-5 w-5 text-primary" />
              Lista de Pessoas
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* OTIMIZAÇÃO: Tabela virtualizada para performance com muitos dados */}
            <VirtualizedParticipantTable
              data={displayData}
              onRowClick={setSelectedParticipant}
              getBadgeVariant={getBadgeVariant}
              isLoading={loading}
            />

            {/* Pagination - Footer do Card */}
            {meta && meta.total_pages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t">
                <p className="text-sm text-muted-foreground">
                  Mostrando <span className="font-medium">{((meta.page - 1) * pageSize) + 1}</span> a <span className="font-medium">{((meta.page - 1) * pageSize) + displayData.length}</span> de <span className="font-medium">{meta.total_rows.toLocaleString('pt-BR')}</span> registros
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
                    let endPage = Math.min(totalPages, startPage + 4);

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
                    onClick={() => onPageChange(Math.min(meta.total_pages, meta.page + 1))}
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
      <Dialog open={!!selectedParticipant} onOpenChange={() => setSelectedParticipant(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          {selectedParticipant && (
            <>
              <DialogHeader>
                <DialogTitle className="text-2xl flex items-center gap-2">
                  <Eye className="h-6 w-6 text-primary" />
                  Detalhamento da Pessoa
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
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Idade</p>
                      <p className="font-medium">{selectedParticipant.idade != null ? `${selectedParticipant.idade} anos` : "-"}</p>
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
                          {selectedParticipant.assistencia_protocolos_irregular || 0} irregulares
                        </p>
                      </CardContent>
                    </Card>

                    <Card className="bg-orange-50 dark:bg-orange-950/20">
                      <CardContent className="p-4 text-center">
                        <p className="text-sm text-muted-foreground">Educação</p>
                        <p className="text-2xl font-bold">{selectedParticipant.educacao_fracao || "0/0"}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {selectedParticipant.educacao_protocolos_irregular || 0} irregulares
                        </p>
                      </CardContent>
                    </Card>

                    <Card className="bg-red-50 dark:bg-red-950/20">
                      <CardContent className="p-4 text-center">
                        <p className="text-sm text-muted-foreground">Saúde</p>
                        <p className="text-2xl font-bold">{selectedParticipant.saude_fracao || "0/0"}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {selectedParticipant.saude_protocolos_irregular || 0} irregulares
                        </p>
                      </CardContent>
                    </Card>
                  </div>
                </div>

                <Separator />

                {/* Resumo Protocolos */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Resumo de Protocolos</h3>
                  <div className="bg-muted/50 p-4 rounded-lg">
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Total de Protocolos</p>
                        <p className="text-3xl font-bold text-primary">{selectedParticipant.total_protocolos || 0}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Protocolos Irregulares</p>
                        <p className="text-3xl font-bold text-destructive">{selectedParticipant.total_protocolos_irregular || 0}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Protocolos Regulares</p>
                        <p className="text-3xl font-bold text-green-600">{selectedParticipant.total_protocolos_regular || 0}</p>
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
