import { useState, useCallback, memo } from "react";
import {
  Participante,
  SmartFilterOptions,
  ParticipantFilters,
  PaginationMeta,
  SortOrder,
} from "../types";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { ParticipantTable } from "./ParticipantTable";
import { FilterCard } from "./FilterCard";
import { Button } from "@/app/components/ui/button";
import { Badge } from "@/app/components/ui/badge";
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
} from "lucide-react";

// Função para renderizar o grupo com emoji (consistente com VirtualizedParticipantTable)
const renderGrupo = (grupo?: string) => {
  if (!grupo) return "-";
  const lower = grupo.toLowerCase();
  if (lower.includes("crian") || lower.includes("criança")) return "👶 Criança";
  if (lower.includes("gestante")) return "🤰 Gestante";
  return grupo;
};

// Função para renderizar grupo completo (com tipo Bolsa Família se aplicável)
const renderGrupoCompleto = (grupo?: string) => {
  if (!grupo) return "-";
  const grupoBase = renderGrupo(grupo);
  // Adicionar " • Bolsa Família" se o grupo original contiver "bf" ou "bolsa"
  const lower = grupo.toLowerCase();
  if (lower.includes("bf") || lower.includes("bolsa")) {
    return `${grupoBase} • Bolsa Família`;
  }
  return grupoBase;
};


// Função para calcular completude total
const calcularCompletude = (participant: Participante) => {
  const total = participant.total_protocolos || 0;
  const regular = participant.total_protocolos_regular || 0;
  if (total === 0) return 0;
  return Math.round((regular / total) * 100);
};

// Função para obter badge variant baseado no status do protocolo
// Prioriza o status real (regular, atencao, irregular) ao invés de irregular_indicador
// IMPORTANTE: Verificar "irregular" ANTES de "regular" porque "irregular".includes("regular") === true
const getProtocolBadgeVariant = (status?: string): "default" | "secondary" | "destructive" | "warning" => {
  if (!status) return "secondary";
  const lower = status.toLowerCase();
  // Verificar irregular PRIMEIRO (antes de regular)
  if (lower === "irregular" || lower.includes("irregular")) return "destructive";
  if (lower === "regular") return "default";
  if (lower === "atencao" || lower.includes("atenção")) return "warning";
  if (lower === "n/a" || lower === "nao_aplica" || lower === "não aplicável" || lower === "não se aplica") return "secondary";
  return "secondary";
};

// Função para formatar status do protocolo para exibição
// Usa protocolo_status_label do backend para exibição, com ícone baseado no status
const formatProtocolStatus = (status?: string, protocolo_status_label?: string) => {
  // Determinar ícone baseado no status
  const lower = status?.toLowerCase() || "";
  let icon = "";
  if (lower === "regular") icon = "✓ ";
  else if (lower === "atencao" || lower === "atenção") icon = "⚠ ";
  else if (lower === "irregular") icon = "✗ ";

  // Usar protocolo_status_label do backend para o texto
  if (protocolo_status_label) {
    return `${icon}${protocolo_status_label}`;
  }

  // Fallback se não tiver label
  if (lower === "regular") return "✓ Regular";
  if (lower === "atencao" || lower === "atenção") return "⚠ Atenção";
  if (lower === "irregular") return "✗ Irregular";
  if (lower === "nao_aplica" || lower === "n/a") return "N/A";
  return status || "N/A";
};

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
  sortBy?: string | null;
  sortOrder?: SortOrder;
  onSortChange?: (sortBy: string, sortOrder: SortOrder) => void;
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
  sortBy,
  sortOrder = "asc",
  onSortChange,
}: ProfessionalTabProps) => {
  const [selectedParticipant, setSelectedParticipant] = useState<Participante | null>(null);

  // Handler para clique no header de ordenação
  const handleSort = useCallback((column: string) => {
    if (!onSortChange) return;

    // Se clicar na mesma coluna, inverte a ordem
    // Se clicar em outra coluna, ordena ASC
    if (sortBy === column) {
      onSortChange(column, sortOrder === "asc" ? "desc" : "asc");
    } else {
      onSortChange(column, "asc");
    }
  }, [sortBy, sortOrder, onSortChange]);

  const getBadgeVariant = useCallback((situacao?: string): "outline" | "default" | "secondary" | "destructive" | "warning" => {
    if (!situacao) return "outline";
    const lower = situacao.toLowerCase();
    if (lower === "regular") return "default";
    if (lower.includes("atenção") || lower.includes("atencao")) return "warning";
    if (lower.includes("irregular")) return "destructive";
    return "secondary";
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Busca Individual
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          Busque por CPF, Nome, ID Membro Família ou ID Família (CadÚnico) para ver os detalhes de uma pessoa específica
        </p>
      </div>

      <FilterCard
        filterOptions={filterOptions}
        filters={filters}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
        loading={loading}
        showSearch
        totalResults={meta?.total_rows}
      />

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
      ) : data.length > 0 ? (
        <Card className="border-2 relative min-w-0">
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Users className="h-5 w-5 text-primary" />
              Lista de Pessoas
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 min-w-0">
            {/* Tabela de participantes */}
            <ParticipantTable
              data={data}
              onRowClick={setSelectedParticipant}
              getBadgeVariant={getBadgeVariant}
              isLoading={loading}
              sortBy={sortBy}
              sortOrder={sortOrder}
              onSort={handleSort}
            />

            {/* Pagination - Footer do Card */}
            {meta && meta.total_pages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t">
                <p className="text-sm text-muted-foreground">
                  Mostrando <span className="font-medium">{((meta.page - 1) * pageSize) + 1}</span> a <span className="font-medium">{((meta.page - 1) * pageSize) + data.length}</span> de <span className="font-medium">{meta.total_rows.toLocaleString('pt-BR')}</span> registros
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
                  Detalhamento Individual
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Informações Básicas */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Informações Básicas</h3>
                  <div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
                    <div>
                      <p className="text-sm text-muted-foreground">Nome</p>
                      <p className="font-medium">{selectedParticipant.nome || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">CPF</p>
                      <p className="font-mono font-medium">{selectedParticipant.cpf || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">ID Família (CadÚnico)</p>
                      <p className="font-mono font-medium">{selectedParticipant.id_familia || "-"}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">ID Membro Família (CadÚnico)</p>
                      <p className="font-mono font-medium">{selectedParticipant.id_membro_familia || "-"}</p>
                    </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Grupo</p>
                        <p className="font-medium">{renderGrupoCompleto(selectedParticipant.grupo)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Idade</p>
                        <p className="font-medium">{selectedParticipant.idade != null ? `${selectedParticipant.idade} anos` : "-"}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Bairro</p>
                        <p className="font-medium">{selectedParticipant.bairro || "-"}</p>
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
                        <p className="text-sm text-muted-foreground">Mês de Ingresso no Programa</p>
                        <p className="font-medium">{selectedParticipant.cohort || "-"}</p>
                      </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Status</p>
                      <Badge variant={selectedParticipant.status?.toLowerCase() === "ativo" ? "success" : "destructive"}>
                        {selectedParticipant.status || "-"}
                      </Badge>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Situação Geral - Simplificada */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Situação Geral</h3>
                  <div className="bg-muted/50 p-4 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground mb-1">Status</p>
                        <Badge variant={getBadgeVariant(selectedParticipant.situacao)} className="text-base">
                          {selectedParticipant.situacao || "-"}
                        </Badge>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground mb-1">Completude Total</p>
                        <p className="text-3xl font-bold text-primary">{calcularCompletude(selectedParticipant)}%</p>
                      </div>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Dimensão Assistência Social */}
                {(() => {
                  const protocolosAssistencia = (selectedParticipant.protocolo_listagem || [])
                    .filter(p => p.secretaria?.toLowerCase() === "smas")
                    .filter(p => {
                      const status = p.status?.toLowerCase() || "";
                      return status !== "nao_aplica" && status !== "não aplica" && status !== "n/a" && status !== "não aplicável" && status !== "nao_priorizado";
                    });
                  if (protocolosAssistencia.length === 0) return null;
                  return (
                    <>
                      <div>
                        <h3 className="text-lg font-semibold mb-3 text-foreground">📋 Dimensão Assistência Social</h3>
                        <div className="space-y-2">
                          {protocolosAssistencia.map((protocolo, idx) => (
                            <div key={idx} className="flex items-center justify-between p-3 bg-muted/30 rounded">
                              <span className="text-sm">{protocolo.descricao || "-"}</span>
                              <Badge variant={getProtocolBadgeVariant(protocolo.status)}>
                                {formatProtocolStatus(protocolo.status, protocolo.protocolo_status_label)}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                      <Separator />
                    </>
                  );
                })()}

                {/* Dimensão Educação */}
                {(() => {
                  const protocolosEducacao = (selectedParticipant.protocolo_listagem || [])
                    .filter(p => p.secretaria?.toLowerCase() === "sme")
                    .filter(p => {
                      const status = p.status?.toLowerCase() || "";
                      return status !== "nao_aplica" && status !== "não aplica" && status !== "n/a" && status !== "não aplicável" && status !== "nao_priorizado";
                    });
                  if (protocolosEducacao.length === 0) return null;
                  return (
                    <>
                      <div>
                        <h3 className="text-lg font-semibold mb-3 text-foreground">📚 Dimensão Educação</h3>
                        <div className="space-y-2">
                          {protocolosEducacao.map((protocolo, idx) => (
                            <div key={idx} className="flex items-center justify-between p-3 bg-muted/30 rounded">
                              <span className="text-sm">{protocolo.descricao || "-"}</span>
                              <Badge variant={getProtocolBadgeVariant(protocolo.status)}>
                                {formatProtocolStatus(protocolo.status, protocolo.protocolo_status_label)}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                      <Separator />
                    </>
                  );
                })()}

                {/* Dimensão Saúde */}
                {(() => {
                  const protocolosSaude = (selectedParticipant.protocolo_listagem || [])
                    .filter(p => p.secretaria?.toLowerCase() === "sms" || p.secretaria?.toLowerCase() === "subpav")
                    .filter(p => {
                      const status = p.status?.toLowerCase() || "";
                      return status !== "nao_aplica" && status !== "não aplica" && status !== "n/a" && status !== "não aplicável" && status !== "nao_priorizado";
                    });
                  if (protocolosSaude.length === 0) return null;
                  return (
                    <>
                      <div>
                        <h3 className="text-lg font-semibold mb-3 text-foreground">🏥 Dimensão Saúde</h3>
                        <div className="space-y-2">
                          {protocolosSaude.map((protocolo, idx) => (
                            <div key={idx} className="flex items-center justify-between p-3 bg-muted/30 rounded">
                              <span className="text-sm">{protocolo.descricao || "-"}</span>
                              <Badge variant={getProtocolBadgeVariant(protocolo.status)}>
                                {formatProtocolStatus(protocolo.status, protocolo.protocolo_status_label)}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                      <Separator />
                    </>
                  );
                })()}

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
