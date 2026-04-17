import { useState, useCallback, memo } from "react";
import {
  Participante,
  SmartFilterOptions,
  ParticipantFilters,
  PaginationMeta,
  SortOrder,
} from "../types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/app/components/ui/card";
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
  DialogDescription,
} from "@/app/components/ui/dialog";
import { Separator } from "@/app/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/app/components/ui/tooltip";
import {
  Users,
  Search,
  ChevronLeft,
  ChevronRight,
  Eye,
  MapPin,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

// Função para renderizar o grupo com emoji (consistente com VirtualizedParticipantTable)
const renderGrupo = (grupo?: string) => {
  if (!grupo) return "-";
  const lower = grupo.toLowerCase();
  if (lower.includes("crian") || lower.includes("criança"))
    return "👶 Criança";
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

// Componente helper para exibir equipamento com badge de origem
const EquipamentoField = ({
  label,
  value,
  source,
  isEquipeSaude = false,
}: {
  label: string;
  value?: string | null;
  source?: string | null;
  isEquipeSaude?: boolean; // true para Equipe, Médicos, Enfermeiros
}) => {
  // Verificar se o valor é válido (não vazio e diferente de "SEM VÍNCULO" ou "0")
  const hasValidValue = value && value !== "SEM VÍNCULO" && value !== "0";

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1">
        <p className="text-sm text-muted-foreground">{label}</p>
        {source === "rmi" && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="inline-flex items-center justify-center cursor-help">
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs font-medium">
                  Vínculo oficial confirmado (fonte RMI)
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {source === "geo" && hasValidValue && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="inline-flex items-center justify-center cursor-help">
                  <MapPin className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs font-medium max-w-xs">
                  Sugestão baseada em geolocalização. Use este equipamento
                  para direcionar atendimento quando o protocolo estiver
                  violado.
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {source === "geo" && !hasValidValue && isEquipeSaude && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="inline-flex items-center justify-center cursor-help">
                  <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs font-medium max-w-xs">
                  Sem cobertura de equipamento na região
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {source === null && !hasValidValue && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="inline-flex items-center justify-center cursor-help">
                  <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs font-medium max-w-xs">
                  Sem informação de endereço
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
      <p className="font-medium">{hasValidValue ? value : "-"}</p>
    </div>
  );
};

// Função para calcular idade detalhada (anos, meses, dias)
const calcularIdadeDetalhada = (
  dataNascimento: string,
  dataReferencia: Date,
) => {
  const nascimento = new Date(dataNascimento);

  let anos = dataReferencia.getFullYear() - nascimento.getFullYear();
  let meses = dataReferencia.getMonth() - nascimento.getMonth();
  let dias = dataReferencia.getDate() - nascimento.getDate();

  // Ajustar se os dias forem negativos
  if (dias < 0) {
    meses--;
    const mesAnterior = new Date(
      dataReferencia.getFullYear(),
      dataReferencia.getMonth(),
      0,
    );
    dias += mesAnterior.getDate();
  }

  // Ajustar se os meses forem negativos
  if (meses < 0) {
    anos--;
    meses += 12;
  }

  return { anos, meses, dias };
};

// Função para formatar idade detalhada
const formatarIdadeDetalhada = (
  anos: number,
  meses: number,
  dias: number,
) => {
  const partes: string[] = [];

  if (anos > 0) {
    partes.push(`${anos} ${anos === 1 ? "ano" : "anos"}`);
  }
  if (meses > 0) {
    partes.push(`${meses} ${meses === 1 ? "mês" : "meses"}`);
  }
  if (dias > 0) {
    partes.push(`${dias} ${dias === 1 ? "dia" : "dias"}`);
  }

  return partes.length > 0 ? partes.join(", ") : "0 dias";
};

// Função para calcular completude total
// Usa a primeira coluna não-null disponível (total, educacao, saude, ou assistencia)
const calcularCompletude = (participant: Participante) => {
  // Tentar usar total primeiro (se disponível)
  let total = participant.total_protocolos;
  let regular = participant.total_protocolos_regular;

  // Se total é null, usar a secretaria disponível
  if (total == null) {
    if (participant.educacao_protocolos_total != null) {
      total = participant.educacao_protocolos_total;
      regular = participant.educacao_protocolos_regular;
    } else if (participant.saude_protocolos_total != null) {
      total = participant.saude_protocolos_total;
      regular = participant.saude_protocolos_regular;
    } else if (participant.assistencia_protocolos_total != null) {
      total = participant.assistencia_protocolos_total;
      regular = participant.assistencia_protocolos_regular;
    }
  }

  if (!total || total === 0) return 0;
  return Math.round(((regular || 0) / total) * 100);
};

// Função para obter badge variant baseado no status do protocolo
// Prioriza o status real (regular, atencao, irregular) ao invés de irregular_indicador
// IMPORTANTE: Verificar "irregular" ANTES de "regular" porque "irregular".includes("regular") === true
const getProtocolBadgeVariant = (
  status?: string,
): "default" | "secondary" | "destructive" | "warning" => {
  if (!status) return "secondary";
  const lower = status.toLowerCase();
  // Verificar irregular PRIMEIRO (antes de regular)
  if (lower === "irregular" || lower.includes("irregular"))
    return "destructive";
  if (lower === "regular") return "default";
  if (lower === "atencao" || lower.includes("atenção")) return "warning";
  if (
    lower === "n/a" ||
    lower === "nao_aplica" ||
    lower === "não aplicável" ||
    lower === "não se aplica"
  )
    return "secondary";
  return "secondary";
};

// Função para formatar status do protocolo para exibição
// Usa protocolo_status_label do backend para exibição, com ícone baseado no status
const formatProtocolStatus = (
  status?: string,
  protocolo_status_label?: string,
) => {
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
  onDownload?: () => void;
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
  onDownload,
  loading = false,
  pageSize,
  sortBy,
  sortOrder = "asc",
  onSortChange,
}: ProfessionalTabProps) => {
  const [selectedParticipant, setSelectedParticipant] =
    useState<Participante | null>(null);

  // Handler para clique no header de ordenação
  const handleSort = useCallback(
    (column: string) => {
      if (!onSortChange) return;

      // Se clicar na mesma coluna, inverte a ordem
      // Se clicar em outra coluna, ordena ASC
      if (sortBy === column) {
        onSortChange(column, sortOrder === "asc" ? "desc" : "asc");
      } else {
        onSortChange(column, "asc");
      }
    },
    [sortBy, sortOrder, onSortChange],
  );

  const getBadgeVariant = useCallback(
    (
      situacao?: string,
    ): "outline" | "default" | "secondary" | "destructive" | "warning" => {
      if (!situacao) return "outline";
      const lower = situacao.toLowerCase();
      if (lower === "regular") return "default";
      if (lower.includes("atenção") || lower.includes("atencao"))
        return "warning";
      if (lower.includes("irregular")) return "destructive";
      return "secondary";
    },
    [],
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Busca Individual
        </h2>
        <p className="text-sm text-muted-foreground mb-6">
          Busque por CPF, Nome, ID Membro Família ou ID Família (CadÚnico)
          para ver os detalhes de uma pessoa específica
        </p>
      </div>

      <FilterCard
        filterOptions={filterOptions}
        filters={filters}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
        onDownload={onDownload}
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
                  Mostrando{" "}
                  <span className="font-medium">
                    {(meta.page - 1) * pageSize + 1}
                  </span>{" "}
                  a{" "}
                  <span className="font-medium">
                    {(meta.page - 1) * pageSize + data.length}
                  </span>{" "}
                  de{" "}
                  <span className="font-medium">
                    {meta.total_rows.toLocaleString("pt-BR")}
                  </span>{" "}
                  registros
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
                    onClick={() =>
                      onPageChange(Math.min(meta.total_pages, meta.page + 1))
                    }
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
      <Dialog
        open={!!selectedParticipant}
        onOpenChange={() => setSelectedParticipant(null)}
      >
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          {selectedParticipant && (
            <>
              <DialogHeader>
                <DialogTitle className="text-2xl flex items-center gap-2">
                  <Eye className="h-6 w-6 text-primary" />
                  Detalhamento Individual
                </DialogTitle>
                <DialogDescription>
                  Visualize informações completas, protocolos e histórico do
                  participante
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Informações Básicas */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">
                    Informações Básicas
                  </h3>
                  <div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
                    <div>
                      <p className="text-sm text-muted-foreground">Nome</p>
                      <p className="font-medium">
                        {selectedParticipant.nome || "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">CPF</p>
                      <p className="font-mono font-medium">
                        {selectedParticipant.cpf || "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">
                        ID Família (CadÚnico)
                      </p>
                      <p className="font-mono font-medium">
                        {selectedParticipant.id_familia || "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">
                        ID Membro Família (CadÚnico)
                      </p>
                      <p className="font-mono font-medium">
                        {selectedParticipant.id_membro_familia || "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Grupo</p>
                      <p className="font-medium">
                        {renderGrupoCompleto(selectedParticipant.grupo)}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Idade</p>
                      <p className="font-medium">
                        {selectedParticipant.idade != null &&
                        selectedParticipant.nascimento_data
                          ? `${selectedParticipant.idade} anos (${new Date(selectedParticipant.nascimento_data).toLocaleDateString("pt-BR")})`
                          : selectedParticipant.idade != null
                            ? `${selectedParticipant.idade} anos`
                            : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">
                        Idade em 31/03/{new Date().getFullYear()}
                      </p>
                      <p className="font-medium">
                        {selectedParticipant.nascimento_data
                          ? (() => {
                              const dataReferencia = new Date(
                                new Date().getFullYear(),
                                2,
                                31,
                              ); // Março = 2 (0-indexed)
                              const { anos, meses, dias } =
                                calcularIdadeDetalhada(
                                  selectedParticipant.nascimento_data,
                                  dataReferencia,
                                );
                              return formatarIdadeDetalhada(
                                anos,
                                meses,
                                dias,
                              );
                            })()
                          : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Bairro</p>
                      <p className="font-medium">
                        {selectedParticipant.bairro || "-"}
                      </p>
                    </div>

                    {/* Equipamentos Públicos - Educação (SME) */}
                    <EquipamentoField
                      label="Escola"
                      value={selectedParticipant.nome_escola}
                      source={selectedParticipant.source_escola}
                    />

                    {/* Equipamentos Públicos - Assistência Social (SMAS) */}
                    <EquipamentoField
                      label="CRAS"
                      value={selectedParticipant.nome_cras}
                      source={selectedParticipant.source_cras}
                    />

                    {/* Equipamentos Públicos - Saúde (SMS) */}
                    <EquipamentoField
                      label="Clínica da Família"
                      value={selectedParticipant.nome_clinica_familia}
                      source={selectedParticipant.source_clinica_familia}
                    />

                    <EquipamentoField
                      label="Equipe da Família"
                      value={selectedParticipant.nome_equipe_familia}
                      source={selectedParticipant.source_equipe_familia}
                      isEquipeSaude={true}
                    />
                    {(() => {
                      const equipeMedicos =
                        selectedParticipant.equipe_familia;
                      const sourceEquipe =
                        selectedParticipant.source_equipe_familia;

                      const hasValidEquipe = equipeMedicos && equipeMedicos !== "SEM VÍNCULO" && equipeMedicos !== "0";

                      if (!hasValidEquipe) {
                        // Componente para exibir badge mesmo sem equipe válida
                        const EmptyEquipeBadge = () => {
                          // source === "geo" + SEM VÍNCULO = sem cobertura na região
                          if (sourceEquipe === "geo") {
                            return (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div className="inline-flex items-center justify-center cursor-help">
                                      <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                                    </div>
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    <p className="text-xs font-medium max-w-xs">
                                      Sem cobertura de equipamento na região
                                    </p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            );
                          }
                          // source === null = sem informação de endereço
                          if (sourceEquipe === null) {
                            return (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div className="inline-flex items-center justify-center cursor-help">
                                      <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                                    </div>
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    <p className="text-xs font-medium max-w-xs">
                                      Sem informação de endereço
                                    </p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            );
                          }
                          return null;
                        };

                        return (
                          <>
                            <div>
                              <div className="flex items-center gap-1.5 mb-1">
                                <p className="text-sm text-muted-foreground">
                                  Médicos
                                </p>
                                <EmptyEquipeBadge />
                              </div>
                              <p className="font-medium">-</p>
                            </div>
                            <div>
                              <div className="flex items-center gap-1.5 mb-1">
                                <p className="text-sm text-muted-foreground">
                                  Enfermeiros
                                </p>
                                <EmptyEquipeBadge />
                              </div>
                              <p className="font-medium">-</p>
                            </div>
                          </>
                        );
                      }

                      // Parse da string: "MEDICOS:\nNome1\nNome2\n\nENFERMEIROS:\nNome3\nNome4"
                      const lines = equipeMedicos
                        .split("\n")
                        .map((l) => l.trim())
                        .filter((l) => l);
                      const medicos: string[] = [];
                      const enfermeiros: string[] = [];
                      let currentSection = "";

                      for (const line of lines) {
                        if (
                          line.startsWith("MEDICOS:") ||
                          line === "MEDICOS"
                        ) {
                          currentSection = "medicos";
                        } else if (
                          line.startsWith("ENFERMEIROS:") ||
                          line === "ENFERMEIROS"
                        ) {
                          currentSection = "enfermeiros";
                        } else if (
                          line !== "SEM MÉDICOS" &&
                          line !== "SEM ENFERMEIROS"
                        ) {
                          if (currentSection === "medicos") {
                            medicos.push(line);
                          } else if (currentSection === "enfermeiros") {
                            enfermeiros.push(line);
                          }
                        }
                      }

                      // Componente Badge para equipe (usado em médicos e enfermeiros)
                      const EquipeBadge = () => {
                        if (sourceEquipe === "rmi") {
                          return (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div className="inline-flex items-center justify-center cursor-help">
                                    <CheckCircle2 className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className="text-xs font-medium">
                                    Vínculo oficial confirmado (fonte RMI)
                                  </p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          );
                        }
                        if (sourceEquipe === "geo") {
                          return (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div className="inline-flex items-center justify-center cursor-help">
                                    <MapPin className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className="text-xs font-medium max-w-xs">
                                    Sugestão baseada em geolocalização. Use
                                    esta equipe para direcionar atendimento
                                    quando o protocolo estiver violado.
                                  </p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          );
                        }
                        if (sourceEquipe === null && equipeMedicos) {
                          return (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div className="inline-flex items-center justify-center cursor-help">
                                    <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className="text-xs font-medium max-w-xs">
                                    Sem informação de endereço ou sem cobertura de equipamento na região
                                  </p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          );
                        }
                        return null;
                      };

                      return (
                        <>
                          <div>
                            <div className="flex items-center gap-1.5 mb-1">
                              <p className="text-sm text-muted-foreground">
                                Médicos
                              </p>
                              <EquipeBadge />
                            </div>
                            {medicos.length > 0 ? (
                              <div className="space-y-0.5">
                                {medicos.map((medico, idx) => (
                                  <p key={idx} className="font-medium">
                                    {medico}
                                  </p>
                                ))}
                              </div>
                            ) : (
                              <p className="font-medium">-</p>
                            )}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5 mb-1">
                              <p className="text-sm text-muted-foreground">
                                Enfermeiros
                              </p>
                              <EquipeBadge />
                            </div>
                            {enfermeiros.length > 0 ? (
                              <div className="space-y-0.5">
                                {enfermeiros.map((enfermeiro, idx) => (
                                  <p key={idx} className="font-medium">
                                    {enfermeiro}
                                  </p>
                                ))}
                              </div>
                            ) : (
                              <p className="font-medium">-</p>
                            )}
                          </div>
                        </>
                      );
                    })()}
                    <div>
                      <p className="text-sm text-muted-foreground">
                        Mês de Ingresso no Programa
                      </p>
                      <p className="font-medium">
                        {selectedParticipant.cohort || "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Status</p>
                      <Badge
                        variant={
                          selectedParticipant.status?.toLowerCase() ===
                          "ativo"
                            ? "success"
                            : "destructive"
                        }
                      >
                        {selectedParticipant.status || "-"}
                      </Badge>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Situação Geral - Simplificada */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">
                    Situação Geral
                  </h3>
                  <div className="bg-muted/50 p-4 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground mb-1">
                          Status
                        </p>
                        <Badge
                          variant={getBadgeVariant(
                            selectedParticipant.situacao,
                          )}
                          className="text-base"
                        >
                          {selectedParticipant.situacao || "-"}
                        </Badge>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground mb-1">
                          Completude Total
                        </p>
                        <p className="text-3xl font-bold text-primary">
                          {calcularCompletude(selectedParticipant)}%
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Dimensão Assistência Social */}
                {(() => {
                  const protocolosAssistencia = (
                    selectedParticipant.protocolo_listagem || []
                  )
                    .filter((p) => p.secretaria?.toLowerCase() === "smas")
                    .filter((p) => {
                      const status = p.status?.toLowerCase() || "";
                      return (
                        status !== "nao_aplica" &&
                        status !== "não aplica" &&
                        status !== "n/a" &&
                        status !== "não aplicável" &&
                        status !== "nao_priorizado"
                      );
                    });
                  if (protocolosAssistencia.length === 0) return null;
                  return (
                    <>
                      <div>
                        <h3 className="text-lg font-semibold mb-3 text-foreground">
                          📋 Dimensão Assistência Social
                        </h3>
                        <div className="space-y-2">
                          {protocolosAssistencia.map((protocolo, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between gap-3 p-3 bg-muted/30 rounded"
                            >
                              <span className="text-sm flex-1 min-w-0">
                                {protocolo.descricao || "-"}
                              </span>
                              <Badge
                                variant={getProtocolBadgeVariant(
                                  protocolo.status,
                                )}
                                className="flex-shrink-0 whitespace-nowrap"
                              >
                                {formatProtocolStatus(
                                  protocolo.status,
                                  protocolo.protocolo_status_label,
                                )}
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
                  const protocolosEducacao = (
                    selectedParticipant.protocolo_listagem || []
                  )
                    .filter((p) => p.secretaria?.toLowerCase() === "sme")
                    .filter((p) => {
                      const status = p.status?.toLowerCase() || "";
                      return (
                        status !== "nao_aplica" &&
                        status !== "não aplica" &&
                        status !== "n/a" &&
                        status !== "não aplicável" &&
                        status !== "nao_priorizado"
                      );
                    });
                  if (protocolosEducacao.length === 0) return null;
                  return (
                    <>
                      <div>
                        <h3 className="text-lg font-semibold mb-3 text-foreground">
                          📚 Dimensão Educação
                        </h3>
                        <div className="space-y-2">
                          {protocolosEducacao.map((protocolo, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between gap-3 p-3 bg-muted/30 rounded"
                            >
                              <span className="text-sm flex-1 min-w-0">
                                {protocolo.descricao || "-"}
                              </span>
                              <Badge
                                variant={getProtocolBadgeVariant(
                                  protocolo.status,
                                )}
                                className="flex-shrink-0 whitespace-nowrap"
                              >
                                {formatProtocolStatus(
                                  protocolo.status,
                                  protocolo.protocolo_status_label,
                                )}
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
                  const protocolosSaude = (
                    selectedParticipant.protocolo_listagem || []
                  )
                    .filter(
                      (p) =>
                        p.secretaria?.toLowerCase() === "sms" ||
                        p.secretaria?.toLowerCase() === "subpav",
                    )
                    .filter((p) => {
                      const status = p.status?.toLowerCase() || "";
                      return (
                        status !== "nao_aplica" &&
                        status !== "não aplica" &&
                        status !== "n/a" &&
                        status !== "não aplicável" &&
                        status !== "nao_priorizado"
                      );
                    });
                  if (protocolosSaude.length === 0) return null;
                  return (
                    <>
                      <div>
                        <h3 className="text-lg font-semibold mb-3 text-foreground">
                          🏥 Dimensão Saúde
                        </h3>
                        <div className="space-y-2">
                          {protocolosSaude.map((protocolo, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between gap-3 p-3 bg-muted/30 rounded"
                            >
                              <span className="text-sm flex-1 min-w-0">
                                {protocolo.descricao || "-"}
                              </span>
                              <Badge
                                variant={getProtocolBadgeVariant(
                                  protocolo.status,
                                )}
                                className="flex-shrink-0 whitespace-nowrap"
                              >
                                {formatProtocolStatus(
                                  protocolo.status,
                                  protocolo.protocolo_status_label,
                                )}
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
