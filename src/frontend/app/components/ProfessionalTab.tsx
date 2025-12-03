import { useState } from "react";
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
import {
  Users,
  Search,
  ChevronLeft,
  ChevronRight,
  Filter,
  Loader2,
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

export function ProfessionalTab({
  data,
  meta,
  filterOptions,
  filters,
  onFilterChange,
  onPageChange,
  loading = false,
}: ProfessionalTabProps) {
  const [searchInput, setSearchInput] = useState("");

  const handleFilterUpdate = (key: keyof ParticipantFilters, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  };

  const handleSearch = () => {
    onFilterChange({
      ...filters,
      search: searchInput,
    });
  };

  const clearFilters = () => {
    setSearchInput("");
    onFilterChange({});
  };

  const getBadgeVariant = (situacao?: string) => {
    if (!situacao) return "outline";
    if (situacao.toLowerCase().includes("regular")) return "default";
    if (situacao.toLowerCase().includes("atenção")) return "secondary";
    return "destructive";
  };

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
      <Card className="border-2">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-primary" />
            Busca e Filtros
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

          {/* Primary Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                <SelectItem value="crianca">Crianças</SelectItem>
                <SelectItem value="gestante">Gestantes</SelectItem>
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
                <SelectItem value="todos">Todos</SelectItem>
                {filterOptions.status_list
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

          {/* Regional Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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

            {/* CRE */}
            <Select
              value={filters.cre || "todas"}
              onValueChange={(v) => handleFilterUpdate("cre", v)}
              disabled={loading}
            >
              <SelectTrigger>
                <SelectValue placeholder="CRE (Educação)" />
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

            {/* CRAS */}
            <Select
              value={filters.cras || "todas"}
              onValueChange={(v) => handleFilterUpdate("cras", v)}
              disabled={loading}
            >
              <SelectTrigger>
                <SelectValue placeholder="CRAS (Assistência)" />
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

          {meta && (
            <div className="pt-2 text-sm text-muted-foreground">
              {meta.total_rows} resultado(s) encontrado(s)
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results Table */}
      {loading && !data.length ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : data.length > 0 ? (
        <Card className="border-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              Lista de Participantes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted">
                    <TableHead>Nome</TableHead>
                    <TableHead>CPF</TableHead>
                    <TableHead>Grupo</TableHead>
                    <TableHead>Bairro</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center">Situação</TableHead>
                    <TableHead className="text-right">Protocolos</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.map((participant, idx) => (
                    <TableRow
                      key={`${participant.cpf}-${idx}`}
                      className="hover:bg-muted/50"
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
                      <TableCell className="text-right font-mono text-sm">
                        {participant.total_fracao || "-"}
                      </TableCell>
                    </TableRow>
                  ))}
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
    </div>
  );
}
