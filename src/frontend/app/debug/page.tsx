"use client";

import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiService } from "@/app/services/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Search,
  Bug,
  AlertCircle,
  Shield,
  Database,
  Clock,
  FileCode,
  Table,
  Filter,
  X,
  RefreshCw,
} from "lucide-react";

// Reutilizando funções de badge do ProfessionalTab
const getProtocolBadgeVariant = (status?: string): "default" | "secondary" | "destructive" | "warning" => {
  if (!status) return "secondary";
  const lower = status.toLowerCase();
  if (lower === "irregular" || lower.includes("irregular")) return "destructive";
  if (lower === "regular") return "default";
  if (lower === "atencao" || lower.includes("atenção")) return "warning";
  if (lower === "n/a" || lower === "nao_aplica" || lower === "não aplicável" || lower === "não se aplica") return "secondary";
  return "secondary";
};

const formatProtocolStatus = (status?: string, protocolo_status_label?: string) => {
  const lower = status?.toLowerCase() || "";
  let icon = "";
  if (lower === "regular") icon = "✓ ";
  else if (lower === "atencao" || lower === "atenção") icon = "⚠ ";
  else if (lower === "irregular") icon = "✗ ";

  if (protocolo_status_label) {
    return `${icon}${protocolo_status_label}`;
  }

  if (lower === "regular") return "✓ Regular";
  if (lower === "atencao" || lower === "atenção") return "⚠ Atenção";
  if (lower === "irregular") return "✗ Irregular";
  if (lower === "nao_aplica" || lower === "n/a") return "Não Aplica";
  return status || "Null";
};

const formatValue = (value: any): string => {
  if (value === null || value === undefined) return "null";
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const renderValue = (value: any) => {
  // null/undefined → texto azul
  if (value === null || value === undefined) {
    return <span className="font-medium text-blue-600">null</span>;
  }

  // true → texto verde
  if (value === true) {
    return <span className="font-medium text-green-600">true</span>;
  }

  // false → texto vermelho
  if (value === false) {
    return <span className="font-medium text-red-600">false</span>;
  }

  // object → JSON string
  if (typeof value === 'object') {
    return <span className="font-medium break-all">{JSON.stringify(value)}</span>;
  }

  // outros valores → normal
  return <span className="font-medium break-all">{String(value)}</span>;
};

export default function DebugPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [searchTerm, setSearchTerm] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Filtros de protocolo
  const [protocoloFilter, setProtocoloFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [secretariaFilter, setSecretariaFilter] = useState<string>("");

  // Fetch current user to verify super admin
  const {
    data: currentUser,
    isLoading: isLoadingUser,
  } = useQuery({
    queryKey: ["currentUser"],
    queryFn: apiService.getCurrentUser,
    retry: false,
  });

  // Fetch debug data (only when searchTerm is set)
  const {
    data: debugData,
    isLoading: isLoadingDebug,
    error: debugError,
  } = useQuery({
    queryKey: ["debug", searchTerm],
    queryFn: () => apiService.getDebugParticipants(searchTerm!, false),
    enabled: !!searchTerm && searchTerm.length > 0,
    retry: false,
  });

  // Show toast and redirect if not super admin
  useEffect(() => {
    if (!isLoadingUser && currentUser && !currentUser.is_super_admin) {
      toast.error('Acesso Negado', {
        description: 'Você não possui permissões de super administrador. Apenas super admins podem acessar dados de debug.',
        duration: 6000,
      });

      const timer = setTimeout(() => {
        router.push("/");
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [isLoadingUser, currentUser, router]);

  const handleSearch = () => {
    const term = searchInput.trim();
    if (term.length === 0) {
      toast.error("Digite um CPF, nome ou ID para buscar");
      return;
    }
    setSearchTerm(term);
  };

  const handleClear = () => {
    setSearchInput("");
    setSearchTerm(null);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);

    try {
      // Atualizar cache no backend (força refresh de ambas tabelas)
      const term = searchTerm || "bypass_cache_refresh";
      toast.info("Atualizando cache do BigQuery...");
      await apiService.getDebugParticipants(term, true);

      if (searchTerm) {
        // Com busca ativa: invalidar query força refetch automático com dados frescos
        queryClient.invalidateQueries({ queryKey: ["debug", searchTerm] });
        toast.success("Cache atualizado!");
      } else {
        // Sem busca: apenas atualiza cache
        toast.success("Cache atualizado! Faça uma busca para ver dados frescos.");
      }
    } catch (error) {
      toast.error("Erro ao atualizar cache");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleClearFilters = () => {
    setProtocoloFilter("");
    setStatusFilter("");
    setSecretariaFilter("");
  };

  // Extrair valores únicos dos dados para popular dropdowns
  const { uniqueProtocolos, uniqueStatus, uniqueSecretarias } = useMemo(() => {
    if (!debugData?.data) return { uniqueProtocolos: [], uniqueStatus: [], uniqueSecretarias: [] };

    const protocolos = new Map<string, string>(); // id -> descricao
    const status = new Set<string>();
    const secretarias = new Set<string>();

    debugData.data.forEach((participant: any) => {
      participant.protocolos?.forEach((p: any) => {
        if (p.protocolo_id && p.protocolo_descricao) {
          protocolos.set(p.protocolo_id, p.protocolo_descricao);
        }
        if (p.protocolo_status) {
          status.add(p.protocolo_status);
        }
        if (p.protocolo_secretaria) {
          secretarias.add(p.protocolo_secretaria);
        }
      });
    });

    return {
      uniqueProtocolos: Array.from(protocolos.entries())
        .sort((a, b) => a[1].localeCompare(b[1])) // Sort by descricao
        .map(([id, descricao]) => ({ id, descricao })),
      uniqueStatus: Array.from(status).sort(),
      uniqueSecretarias: Array.from(secretarias).sort(),
    };
  }, [debugData]);

  // Show loading or nothing while checking/redirecting
  if (isLoadingUser || !currentUser?.is_super_admin) {
    return null;
  }

  return (
    <div className="container mx-auto p-6 max-w-6xl" suppressHydrationWarning>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Debug de Participantes</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Rastreamento completo de protocolos e metadados do BigQuery
            </p>
          </div>
          <Badge variant="destructive">
            <Shield className="h-3 w-3 mr-1" />
            SUPER ADMIN
          </Badge>
        </div>
      </div>

      {/* Search and Filters */}
      <Card className="mb-6 border-2">
        <CardHeader className="pb-4 flex flex-row items-center justify-between">
          <CardTitle className="text-2xl font-bold flex items-center gap-2">
            <Filter className="h-6 w-6" />
            Filtros e Busca
          </CardTitle>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleClearFilters}
              className="h-8 text-xs"
              disabled={isLoadingDebug || isRefreshing}
            >
              <X className="h-3 w-3 mr-1" />
              Limpar Filtros
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              className="h-8 text-xs"
              disabled={isLoadingDebug || isRefreshing}
            >
              <RefreshCw className={`h-3 w-3 mr-1 ${isRefreshing ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {/* Search Input - com ícone interno */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Buscar por CPF, Nome, ID Membro Família (CadÚnico)..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="pl-10 h-11"
              disabled={isLoadingDebug || isRefreshing}
            />
          </div>

          {/* Filters - always visible, populated after search */}
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Filtros de Protocolos
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <select
                  value={protocoloFilter}
                  onChange={(e) => setProtocoloFilter(e.target.value)}
                  className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                  disabled={!debugData || debugData.data.length === 0 || isLoadingDebug || isRefreshing}
                >
                  <option value="">Todos os Protocolos</option>
                  {uniqueProtocolos.map(({ id, descricao }) => (
                    <option key={id} value={id}>
                      {descricao}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                  disabled={!debugData || debugData.data.length === 0 || isLoadingDebug || isRefreshing}
                >
                  <option value="">Todos os Status</option>
                  {uniqueStatus.map((status) => (
                    <option key={status} value={status.toLowerCase()}>
                      {status}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <select
                  value={secretariaFilter}
                  onChange={(e) => setSecretariaFilter(e.target.value)}
                  className="w-full h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
                  disabled={!debugData || debugData.data.length === 0 || isLoadingDebug || isRefreshing}
                >
                  <option value="">Todos os Protocolos por Secretaria</option>
                  {uniqueSecretarias.map((secretaria) => (
                    <option key={secretaria} value={secretaria}>
                      {secretaria}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Result Count - discreto, igual FilterCard */}
          {debugData && debugData.data.length > 0 && (
            <div className="pt-4 border-t flex items-center gap-2 text-sm text-muted-foreground">
              <span className="font-medium">{debugData.total_found}</span> pessoa(s) encontrada(s)
              <span>|</span>
              <span>Retornado {debugData.total_returned}</span>
              {debugData.total_found > 1 && (
                <span className="text-xs ml-2">(Use CPF ou nome completo para resultado específico)</span>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error Display */}
      {debugError && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Erro ao buscar dados: {(debugError as any)?.message || "Erro desconhecido"}
          </AlertDescription>
        </Alert>
      )}

      {/* Results Display */}
      {searchTerm && !isLoadingDebug && debugData && (
        <>
          {debugData.data.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="py-12">
                <div className="text-center text-muted-foreground">
                  <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium">Nenhum resultado encontrado</p>
                  <p className="text-sm mt-2">Tente buscar por outro termo</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-8">
              {debugData.data.map((participant, pIdx) => (
                <div key={pIdx} className="space-y-6">
                  {/* Participant Info */}
                  <Card>
                    <CardContent className="pt-6">
                      <h2 className="text-2xl font-bold mb-4">{participant.nome ?? "null"}</h2>

                      <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">cpf:</span>
                          <span className="font-mono font-medium">{participant.cpf ?? "null"}</span>
                        </div>
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">id_membro_familia:</span>
                          <span className="font-mono font-medium">{participant.id_membro_familia ?? "null"}</span>
                        </div>
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">nascimento_data:</span>
                          <span className="font-medium">
                            {participant.nascimento_data ? new Date(participant.nascimento_data).toLocaleDateString('pt-BR') : "null"}
                          </span>
                        </div>
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">pic_grupo:</span>
                          <span className="font-medium">{participant.pic_grupo ?? "null"}</span>
                        </div>
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">pic_cohort:</span>
                          <span className="font-medium">{participant.pic_cohort ?? "null"}</span>
                        </div>
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">pic_status:</span>
                          <Badge variant={participant.pic_status === "ativo" ? "default" : "secondary"}>
                            {participant.pic_status ?? "null"}
                          </Badge>
                        </div>
                        <div className="flex gap-2">
                          <span className="text-muted-foreground font-mono text-xs inline-block w-[160px]">pic_fase_atual:</span>
                          <span className="font-medium">{participant.pic_fase_atual ?? "null"}</span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Protocolos */}
                  {participant.protocolos && participant.protocolos.length > 0 && (() => {
                    // Aplicar filtros e ordenação
                    const filteredProtocolos = participant.protocolos
                      .filter((p: any) => {
                        // Filtro de protocolo ID
                        if (protocoloFilter && !p.protocolo_id?.toLowerCase().includes(protocoloFilter.toLowerCase())) {
                          return false;
                        }

                        // Filtro de status
                        if (statusFilter) {
                          const status = p.protocolo_status?.toLowerCase() || "";
                          const label = p.protocolo_status_label?.toLowerCase() || "";
                          if (statusFilter === "regular" && status !== "regular") return false;
                          if (statusFilter === "irregular" && status !== "irregular") return false;
                          if (statusFilter === "atencao" && label !== "atenção") return false;
                        }

                        // Filtro de secretaria
                        if (secretariaFilter && p.protocolo_secretaria !== secretariaFilter) {
                          return false;
                        }

                        return true;
                      })
                      .sort((a: any, b: any) => {
                        const idA = a.protocolo_id || "";
                        const idB = b.protocolo_id || "";
                        return idA.localeCompare(idB);
                      });

                    if (filteredProtocolos.length === 0) return null;

                    return (
                    <div className="space-y-4">
                      <h3 className="text-xl font-bold">Protocolos ({filteredProtocolos.length})</h3>

                      {filteredProtocolos.map((protocolo: any, prtIdx: number) => {
                        // Associate data with their sources
                        const dataBySource: Array<{
                          data: Record<string, any>,
                          source: {table: string | null, model: string | null, githubUrl: string | null, updated: string | null}
                        }> = [];

                        if (protocolo.metadata) {
                          protocolo.metadata.forEach((meta: any) => {
                            const parsed = meta.dados ? JSON.parse(meta.dados) : {};

                            // Clean BQ table name (remove backticks)
                            const cleanTable = meta.tabela_bq ? meta.tabela_bq.replace(/`/g, "") : null;

                            // Build GitHub link for DBT model
                            const modelPath = meta.dbt_model_path || null;
                            const githubUrl = modelPath
                              ? `https://github.com/prefeitura-rio/queries-rj-crm-registry/blob/master/${modelPath}`
                              : null;

                            dataBySource.push({
                              data: parsed,
                              source: {
                                table: cleanTable,
                                model: modelPath,
                                githubUrl: githubUrl,
                                updated: meta.updated_at ? new Date(meta.updated_at).toLocaleString('pt-BR') : null
                              }
                            });
                          });
                        }

                        return (
                          <Card key={prtIdx}>
                            <CardContent className="pt-6">
                              {/* Protocol Header */}
                              <div className="flex items-start justify-between mb-4">
                                <div>
                                  <h4 className="text-lg font-bold mb-2">
                                    {protocolo.protocolo_descricao || "Sem descrição"}
                                  </h4>
                                  <div className="flex gap-2 flex-wrap">
                                    <Badge variant="outline" className="font-mono text-xs">
                                      {protocolo.protocolo_id}
                                    </Badge>
                                    {protocolo.protocolo_secretaria && (
                                      <Badge variant="secondary" className="text-xs">
                                        {protocolo.protocolo_secretaria}
                                      </Badge>
                                    )}
                                    {protocolo.protocolo_level && (
                                      <Badge variant="secondary" className="text-xs">
                                        Level: {protocolo.protocolo_level}
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                                <Badge variant={getProtocolBadgeVariant(protocolo.protocolo_status)}>
                                  {formatProtocolStatus(protocolo.protocolo_status, protocolo.protocolo_status_label)}
                                </Badge>
                              </div>

                              <Separator className="my-4" />

                              {/* Headers */}
                              <div className="grid grid-cols-2 gap-6 mb-4">
                                <h5 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                                  Dados Extraídos
                                </h5>
                                <h5 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                                  Origem dos Dados ({dataBySource.length} {dataBySource.length === 1 ? 'tabela' : 'tabelas'})
                                </h5>
                              </div>

                              {/* Data paired with sources - separator crosses both columns */}
                              {dataBySource.map((item, idx) => (
                                <div key={idx}>
                                  {idx > 0 && <div className="mb-6" />}
                                  <div className="grid grid-cols-2 gap-6 mb-6">
                                    {/* Coluna Esquerda: Dados desta fonte */}
                                    <div>
                                      {Object.keys(item.data).length > 0 ? (
                                        <div className="space-y-1">
                                          {Object.entries(item.data).map(([key, value]) => (
                                            <div key={key} className="text-sm flex items-center gap-2">
                                              <span className="text-muted-foreground font-mono text-xs">{key}: </span>
                                              {renderValue(value)}
                                            </div>
                                          ))}
                                        </div>
                                      ) : (
                                        <p className="text-sm text-muted-foreground italic">Sem dados</p>
                                      )}
                                    </div>

                                    {/* Coluna Direita: Fonte correspondente */}
                                    <div>
                                      <div className="space-y-1 text-sm">
                                        {item.source.table && (
                                          <div className="flex items-center gap-2 text-muted-foreground">
                                            <Database className="h-4 w-4 shrink-0" />
                                            <span className="font-mono text-xs break-all">{item.source.table}</span>
                                          </div>
                                        )}
                                        {item.source.githubUrl ? (
                                          <div className="flex items-center gap-2">
                                            <FileCode className="h-4 w-4 shrink-0 text-muted-foreground" />
                                            <a
                                              href={item.source.githubUrl}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              className="font-mono text-xs text-blue-600 hover:text-blue-800 hover:underline break-all"
                                            >
                                              {item.source.model?.split('/').pop()}
                                            </a>
                                          </div>
                                        ) : (
                                          item.source.model && (
                                            <div className="flex items-center gap-2 text-muted-foreground">
                                              <FileCode className="h-4 w-4 shrink-0" />
                                              <span className="font-mono text-xs break-all">{item.source.model.split('/').pop()}</span>
                                            </div>
                                          )
                                        )}
                                        {item.source.updated && (
                                          <div className="flex items-center gap-2 text-muted-foreground">
                                            <Clock className="h-4 w-4 shrink-0" />
                                            <span className="text-xs">{item.source.updated}</span>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>

                                  {/* Separator crossing both columns with spacing */}
                                  {idx < dataBySource.length - 1 && (
                                    <div className="my-6">
                                      <Separator />
                                    </div>
                                  )}
                                </div>
                              ))}
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                    );
                  })()}
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {/* Empty State */}
      {!searchTerm && (
        <Card className="border-dashed">
          <CardContent className="py-16">
            <div className="text-center text-muted-foreground">
              <Bug className="h-16 w-16 mx-auto mb-4 opacity-30" />
              <p className="text-xl font-medium text-foreground mb-2">Digite um termo para começar</p>
              <p className="text-sm">
                Busque por CPF, nome ou ID de membro família para ver o rastreamento completo dos dados
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
