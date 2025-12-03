import { useState, useMemo, useCallback, memo } from "react";
import { useDebounce } from "../hooks/useDebounce";
import {
  Participante,
  SmartFilterOptions,
  ParticipantFilters,
  PaginationMeta,
} from "../types";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/app/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/app/components/ui/table";
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
} from "lucide-react";

interface ProfessionalTabProps {
  data: Participante[];
  meta: PaginationMeta | null;
  filterOptions: SmartFilterOptions;
  filters: ParticipantFilters;
  onFilterChange: (filters: ParticipantFilters) => void;
  onPageChange: (page: number) => void;
  loading?: boolean;
}

const ProfessionalTabComponent = ({
  data,
  meta,
  filterOptions,
  filters,
  onFilterChange,
  onPageChange,
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

      {/* Search and Filters */}
      <Card className="border-2 relative">
        {/* Indicador de loading nos filtros */}
        {loading && (
          <div className="absolute top-3 right-3 z-10">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
          </div>
        )}
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-primary" />
            Busca e Filtros
            {loading && <span className="text-xs text-muted-foreground">(carregando...)</span>}
          </CardTitle>
          <Button variant="outline" size="sm" onClick={clearFilters} disabled={loading}>
            Limpar Tudo
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Search Input */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Buscar por CPF ou Nome..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="pl-10"
                disabled={loading}
              />
            </div>
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
              <Select
                value={filters.grupo || "todos"}
                onValueChange={(v) => handleFilterUpdate("grupo", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Grupo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os Grupos</SelectItem>
                  {filterOptions.grupos
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Status */}
              <Select
                value={filters.status || "todos"}
                onValueChange={(v) => handleFilterUpdate("status", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os Status</SelectItem>
                  {filterOptions.status_list
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Situação */}
              <Select
                value={filters.situacao || "todas"}
                onValueChange={(v) => handleFilterUpdate("situacao", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Situação" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Situações</SelectItem>
                  {filterOptions.situacoes
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Safra */}
              <Select
                value={filters.safra || "todas"}
                onValueChange={(v) => handleFilterUpdate("safra", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Safra" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Safras</SelectItem>
                  {filterOptions.cohorts
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Segundo Nível - Filtros Regionais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Regionais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* CAP */}
              <Select
                value={filters.cap || "todas"}
                onValueChange={(v) => handleFilterUpdate("cap", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="CAP" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as CAPs</SelectItem>
                  {filterOptions.caps
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* CRE */}
              <Select
                value={filters.cre || "todas"}
                onValueChange={(v) => handleFilterUpdate("cre", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="CRE" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as CREs</SelectItem>
                  {filterOptions.cres
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* CAS */}
              <Select
                value={filters.cas || "todas"}
                onValueChange={(v) => handleFilterUpdate("cas", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="CAS" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as CAS</SelectItem>
                  {filterOptions.cas_list
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Bairro */}
              <Select
                value={filters.bairro || "todos"}
                onValueChange={(v) => handleFilterUpdate("bairro", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Bairro" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os Bairros</SelectItem>
                  {filterOptions.bairros
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Escolas */}
              <Select
                value={filters.escola || "todas"}
                onValueChange={(v) => handleFilterUpdate("escola", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Escola" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Escolas</SelectItem>
                  {filterOptions.escolas
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Clínicas da Família */}
              <Select
                value={filters.clinica || "todas"}
                onValueChange={(v) => handleFilterUpdate("clinica", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Clínica da Família" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Clínicas da Família</SelectItem>
                  {filterOptions.clinicas
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* CRAS */}
              <Select
                value={filters.cras || "todas"}
                onValueChange={(v) => handleFilterUpdate("cras", v)}
                disabled={loading}
              >
                <SelectTrigger>
                  <SelectValue placeholder="CRAS" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todos os CRAS</SelectItem>
                  {filterOptions.cras
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {meta && (
            <div className="pt-2 text-sm text-muted-foreground">
              {meta.total_rows} resultado(s) encontrado(s)
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
          {/* Loading overlay durante refetch */}
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/70 z-20 rounded-lg">
              <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">Atualizando dados...</p>
              </div>
            </div>
          )}
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              Lista de Participantes
            </CardTitle>
          </CardHeader>
          <CardContent className={loading ? 'opacity-50 pointer-events-none' : ''}>
            <div className="rounded-lg border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted">
                    <TableHead>Nome</TableHead>
                    <TableHead>CPF</TableHead>
                    <TableHead>Grupo</TableHead>
                    <TableHead>Bairro</TableHead>
                    <TableHead>Idade</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center">Situação</TableHead>
                    <TableHead className="text-center">Total</TableHead>
                    <TableHead className="text-center">Assistência</TableHead>
                    <TableHead className="text-center">Educação</TableHead>
                    <TableHead className="text-center">Saúde</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayData.map((participant, idx) => {
                    // Extrair numerador e denominador das frações para colorir
                    const getTotalColor = (fracao?: string) => {
                      if (!fracao) return "text-muted-foreground";
                      const [num, den] = fracao.split('/').map(Number);
                      if (isNaN(num) || isNaN(den) || den === 0) return "text-muted-foreground";
                      const percent = (num / den) * 100;
                      if (percent === 100) return "text-green-600 font-semibold";
                      if (percent >= 60) return "text-yellow-600 font-semibold";
                      return "text-red-600 font-semibold";
                    };

                    return (
                    <TableRow
                      key={`${participant.cpf}-${idx}`}
                      className="hover:bg-muted/50 cursor-pointer"
                      onClick={() => setSelectedParticipant(participant)}
                    >
                      <TableCell className="font-medium">
                        {participant.nome || "-"}
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {participant.cpf || "-"}
                      </TableCell>
                      <TableCell>
                        {participant.grupo?.toLowerCase().includes("crianca")
                          ? "👶 Criança"
                          : participant.grupo?.toLowerCase().includes("gestante")
                          ? "🤰 Gestante"
                          : participant.grupo || "-"}
                      </TableCell>
                      <TableCell>{participant.bairro || "-"}</TableCell>
                      <TableCell>{participant.idade ? `${participant.idade} anos` : "0 anos"}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            participant.status === "ativo"
                              ? "default"
                              : "secondary"
                          }
                        >
                          {participant.status || "-"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant={getBadgeVariant(participant.situacao)}>
                          {participant.situacao || "-"}
                        </Badge>
                      </TableCell>
                      <TableCell className={`text-center font-mono text-sm ${getTotalColor(participant.total_fracao)}`}>
                        {participant.total_fracao || "-"}
                      </TableCell>
                      <TableCell className="text-center font-mono text-sm">
                        {participant.assistencia_fracao || "-"}
                      </TableCell>
                      <TableCell className="text-center font-mono text-sm">
                        {participant.educacao_fracao || "-"}
                      </TableCell>
                      <TableCell className="text-center font-mono text-sm">
                        {participant.saude_fracao || "-"}
                      </TableCell>
                    </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

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
