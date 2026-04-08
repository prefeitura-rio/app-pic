"use client";

import { useState, useCallback, useMemo, useTransition, startTransition, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/app/components/ui/tabs";
import { DashboardHeader } from "@/app/components/DashboardHeader";
import { Footer } from "@/app/components/Footer";
import { OverviewTab } from "@/app/components/OverviewTab";
import { ProfessionalTab } from "@/app/components/ProfessionalTab";
import { apiService } from "@/app/services/api";
import {
  SmartFilterOptions,
  Dashboard,
  Participante,
  ParticipantFilters,
  PaginationMeta,
  SortOrder,
} from "@/app/types";
import { DashboardFilterValues } from "@/app/components/DashboardFilterCard";
import { Loader2, BarChart3, Search } from "lucide-react";

interface UserInfo {
  name?: string | null;
  email?: string | null;
  preferred_username?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  sub?: string | null;
  iat?: number;
  exp?: number;
}

const PAGE_SIZE = 50;

/**
 * Main Dashboard Orchestrator Component.
 *
 * Arquitetura Híbrida (OTIMIZADA):
 * 1. Inicialização: Carrega currentUser + dashboard + participants em PARALELO
 *    (elimina waterfall de auth, reduz tempo de ~11s para ~7s)
 * 2. Overview tab: Chama /dashboard com filtros para recalcular métricas
 * 3. Professional tab: Chama /participants com filtros + paginação
 * 4. Trocar de aba: NÃO faz chamadas (usa cache do TanStack Query)
 * 5. Filtros: Recarrega apenas o endpoint necessário
 * 6. Errors: Backend retorna 401/403, frontend redireciona para /login
 */
export function DashboardClient({ userInfo }: { userInfo?: UserInfo | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Chave para sessionStorage
  const STORAGE_KEY = "dashboard-state";

  // State para filtros e paginação (com restauração do sessionStorage)
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilterValues>(() => {
    if (typeof window === "undefined") return {};
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.overviewFilters || {};
      }
    } catch (e) {
      console.error("Error restoring overview filters:", e);
    }
    return {};
  });

  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>(() => {
    if (typeof window === "undefined") return {};
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.professionalFilters || {};
      }
    } catch (e) {
      console.error("Error restoring professional filters:", e);
    }
    return {};
  });

  const [professionalPage, setProfessionalPage] = useState(() => {
    if (typeof window === "undefined") return 1;
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.professionalPage || 1;
      }
    } catch (e) {
      console.error("Error restoring professional page:", e);
    }
    return 1;
  });

  const [activeTab, setActiveTab] = useState<"overview" | "professional">(() => {
    if (typeof window === "undefined") return "professional";
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.activeTab || "professional";
      }
    } catch (e) {
      console.error("Error restoring active tab:", e);
    }
    return "professional";
  });


  const [isPending, startTransition] = useTransition();
  const [bypassCacheDashboardTimestamp, setBypassCacheDashboardTimestamp] = useState<number | null>(null);
  const [bypassCacheParticipantsTimestamp, setBypassCacheParticipantsTimestamp] = useState<number | null>(null);

  // State para ordenação (com restauração do sessionStorage)
  const [sortBy, setSortBy] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.sortBy || null;
      }
    } catch (e) {
      console.error("Error restoring sortBy:", e);
    }
    return null;
  });

  const [sortOrder, setSortOrder] = useState<SortOrder>(() => {
    if (typeof window === "undefined") return "asc";
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.sortOrder || "asc";
      }
    } catch (e) {
      console.error("Error restoring sortOrder:", e);
    }
    return "asc";
  });

  // Persistir estado no sessionStorage sempre que mudar
  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      const state = {
        overviewFilters,
        professionalFilters,
        professionalPage,
        activeTab,
        sortBy,
        sortOrder,
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.error("Error saving state to sessionStorage:", e);
    }
  }, [overviewFilters, professionalFilters, professionalPage, activeTab, sortBy, sortOrder]);


  // Verificação prévia de permissões (evita chamadas desnecessárias)
  const {
    data: currentUser,
    isLoading: currentUserLoading,
    error: currentUserError,
  } = useQuery({
    queryKey: ['currentUser'],
    queryFn: () => apiService.getCurrentUser(),
    staleTime: 10 * 60 * 1000, // 10 minutos
    retry: false, // Não retry em caso de 403/401
  });

  // Redirect se usuário não autorizado
  useEffect(() => {
    if (currentUserError) {
      // Erro já foi tratado por handleResponse() que faz redirect
      return;
    }

    // Se usuário carregou mas está inativo, o backend vai retornar 403
    // e handleResponse() vai redirecionar para /login?error=InactiveUser
    if (currentUser && !currentUser.active) {
      router.push("/login?error=InactiveUser");
    }
  }, [currentUser, currentUserError, router]);

  // TanStack Query para Dashboard (Visão Geral)
  // OTIMIZAÇÃO: Roda em paralelo com currentUser (não espera auth terminar)
  // O backend já valida auth e retorna 401/403 se não autorizado
  const {
    data: dashboardResponse,
    isLoading: dashboardLoading,
    isFetching: dashboardFetching,
    error: dashboardError,
  } = useQuery({
    queryKey: ['dashboard', overviewFilters, bypassCacheDashboardTimestamp],
    queryFn: async ({ queryKey }) => {
      const timestamp = queryKey[queryKey.length - 1] as number | null;
      const shouldBypassCache = timestamp !== null;

      const result = await apiService.getDashboard({
        ...overviewFilters,
        ...(shouldBypassCache && { bypass_cache: true }),
      });

      if (shouldBypassCache) {
        setBypassCacheDashboardTimestamp(null);
      }

      return result;
    },
    staleTime: 5 * 60 * 1000, // 5 minutos
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos (sem piscar)
  });

  // TanStack Query para Participants (Busca Individual)
  // OTIMIZAÇÃO: Roda em paralelo com currentUser (não espera auth terminar)
  // O backend já valida auth e retorna 401/403 se não autorizado
  const {
    data: participantsResponse,
    isLoading: participantsLoading,
    isFetching: participantsFetching,
    error: participantsError,
  } = useQuery({
    queryKey: ['participants', professionalFilters, professionalPage, sortBy, sortOrder, bypassCacheParticipantsTimestamp],
    queryFn: async ({ queryKey }) => {
      const timestamp = queryKey[queryKey.length - 1] as number | null;
      const shouldBypassCache = timestamp !== null;

      const result = await apiService.getParticipants(
        {
          ...professionalFilters,
          ...(sortBy && { sort_by: sortBy, sort_order: sortOrder }),
          ...(shouldBypassCache && { bypass_cache: true }),
        },
        professionalPage,
        PAGE_SIZE
      );

      if (shouldBypassCache) {
        setBypassCacheParticipantsTimestamp(null);
      }

      return result;
    },
    staleTime: 5 * 60 * 1000, // 5 minutos
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos
  });

  // Backend controla se usuário pode ver dashboard via meta.can_view_dashboard
  // Se false, esconder a aba "Visão Geral" e forçar "Busca Individual"
  const canViewDashboard = dashboardResponse?.meta?.can_view_dashboard !== false;

  // Force professional tab if user cannot view dashboard
  useEffect(() => {
    if (dashboardResponse && !canViewDashboard && activeTab === "overview") {
      setActiveTab("professional");
    }
  }, [dashboardResponse, canViewDashboard, activeTab]);

  /**
   * Handle authentication errors
   */
  useEffect(() => {
    // Handle errors from queries
    if (dashboardError && (dashboardError as any).message === "Unauthorized") {
      router.push("/login");
      return;
    }
    if (participantsError && (participantsError as any).message === "Unauthorized") {
      router.push("/login");
      return;
    }
  }, [dashboardError, participantsError, router]);

  /**
   * Handle overview filter changes
   * TanStack Query refetch automaticamente quando overviewFilters muda
   */
  const handleOverviewFilterChange = useCallback((newFilters: DashboardFilterValues) => {
    setOverviewFilters(newFilters);
  }, []);

  /**
   * Handle professional filter changes
   * TanStack Query refetch automaticamente quando professionalFilters muda
   */
  const handleProfessionalFilterChange = useCallback((newFilters: ParticipantFilters) => {
    setProfessionalFilters(newFilters);
    setProfessionalPage(1); // Reset to page 1
  }, []);

  /**
   * Handle professional page change
   * TanStack Query refetch automaticamente quando professionalPage muda
   */
  const handleProfessionalPageChange = useCallback((page: number) => {
    setProfessionalPage(page);
  }, []);

  /**
   * Handle sort change
   * Atualiza sortBy e sortOrder, reseta para página 1
   */
  const handleSortChange = useCallback((newSortBy: string, newSortOrder: SortOrder) => {
    setSortBy(newSortBy);
    setSortOrder(newSortOrder);
    setProfessionalPage(1); // Reset to page 1 when sorting changes
  }, []);

  /**
   * Handle refresh with cache bypass (for Overview tab)
   */
  const handleOverviewRefresh = useCallback(() => {
    // Invalidate TanStack Query cache to force refetch
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    setBypassCacheDashboardTimestamp(Date.now());
  }, [queryClient]);

  /**
   * Handle refresh with cache bypass (for Professional tab)
   */
  const handleProfessionalRefresh = useCallback(() => {
    // Invalidate TanStack Query cache to force refetch
    queryClient.invalidateQueries({ queryKey: ['participants'] });
    setBypassCacheParticipantsTimestamp(Date.now());
  }, [queryClient]);

  /**
   * Convert JSON array to CSV string with protocol expansion
   * Each participant with N protocols becomes N rows
   * Optimized for protocol-level analysis in Excel
   */
  const jsonToCSVBlob = useCallback((data: any[]): Blob => {
    // Gera CSV em chunks para evitar "Invalid string length" com datasets grandes
    // Retorna Blob diretamente ao invés de string gigante

    if (data.length === 0) return new Blob([''], { type: 'text/csv;charset=utf-8;' });

    // Define headers for expanded format
    const participantFields = [
      'cpf',
      'id_membro_familia',
      'id_familia',
      'nome',
      'sexo',
      'nascimento_data',
      'idade',
      'subprefeitura',
      'regiao_administrativa',
      'bairro',
      'grupo',
      'cohort',
      'status',
      'status_inativo_motivo',
      'situacao',
      'total_protocolos',
      'total_protocolos_regular',
      'total_protocolos_irregular',
      'total_protocolos_atencao',
      'total_fracao',
      'assistencia_protocolos_total',
      'assistencia_protocolos_regular',
      'assistencia_protocolos_irregular',
      'assistencia_fracao',
      'educacao_protocolos_total',
      'educacao_protocolos_regular',
      'educacao_protocolos_irregular',
      'educacao_fracao',
      'saude_protocolos_total',
      'saude_protocolos_regular',
      'saude_protocolos_irregular',
      'saude_fracao',
      'id_cras',
      'nome_cras',
      'id_cas',
      'nome_cas',
      'id_escola',
      'nome_escola',
      'id_cre',
      'nome_cre',
      'id_ap',
      'nome_ap',
      'id_clinica_familia',
      'nome_clinica_familia',
      'id_equipe_familia',
      'nome_equipe_familia',
      'equipe_medicos',
    ];

    const protocolFields = [
      'protocolo_id',
      'protocolo_secretaria',
      'protocolo_descricao',
      'protocolo_status',
      'protocolo_irregular_indicador',
      'protocolo_status_label',
    ];

    const headers = [...participantFields, ...protocolFields];

    const escapeCSV = (value: any): string => {
      if (value === null || value === undefined) return '';
      const str = String(value);
      if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return `"${str.replace(/"/g, '""')}"`;
      }
      return str;
    };

    // Array de chunks de string (cada chunk ~1000 linhas)
    const chunks: string[] = [];
    const CHUNK_SIZE = 1000; // linhas por chunk

    // Header
    chunks.push(headers.join(',') + '\n');

    let buffer: string[] = [];
    let linesInBuffer = 0;

    // Processar participantes
    data.forEach(participant => {
      const protocolos = participant.protocolo_listagem || [];

      if (protocolos.length > 0) {
        protocolos.forEach((protocolo: any) => {
          const row = headers.map(header => {
            if (header === 'protocolo_id') return escapeCSV(protocolo.id);
            if (header === 'protocolo_secretaria') return escapeCSV(protocolo.secretaria);
            if (header === 'protocolo_descricao') return escapeCSV(protocolo.descricao);
            if (header === 'protocolo_status') return escapeCSV(protocolo.status);
            if (header === 'protocolo_irregular_indicador') return escapeCSV(protocolo.irregular_indicador);
            if (header === 'protocolo_status_label') return escapeCSV(protocolo.protocolo_status_label);
            return escapeCSV(participant[header]);
          });

          buffer.push(row.join(','));
          linesInBuffer++;

          // Flush buffer quando atingir chunk size
          if (linesInBuffer >= CHUNK_SIZE) {
            chunks.push(buffer.join('\n') + '\n');
            buffer = [];
            linesInBuffer = 0;
          }
        });
      } else {
        const row = headers.map(header => {
          if (header.startsWith('protocolo_')) return '';
          return escapeCSV(participant[header]);
        });

        buffer.push(row.join(','));
        linesInBuffer++;

        if (linesInBuffer >= CHUNK_SIZE) {
          chunks.push(buffer.join('\n') + '\n');
          buffer = [];
          linesInBuffer = 0;
        }
      }
    });

    // Flush remaining buffer
    if (buffer.length > 0) {
      chunks.push(buffer.join('\n'));
    }

    // Criar Blob a partir dos chunks (evita string gigante)
    const BOM = '\uFEFF';
    return new Blob([BOM, ...chunks], { type: 'text/csv;charset=utf-8;' });
  }, []);

  /**
   * Handle download all filtered participants (no pagination)
   * Uses page_size=-1 to bypass pagination limit and get all data
   * Downloads as CSV for better Excel compatibility
   */
  const handleDownloadParticipants = useCallback(async () => {
    const startTime = performance.now();

    try {
      toast.info("📥 Buscando dados...", { duration: 30000 });

      // Fetch ALL data without pagination using page_size=-1
      // -1 is a special value that bypasses pagination and returns all filtered data
      const result = await apiService.getParticipants(
        {
          ...professionalFilters,
          ...(sortBy && { sort_by: sortBy, sort_order: sortOrder }),
        },
        1,
        -1 // Special value: -1 = return all data (bypass pagination)
      );

      const fetchTime = ((performance.now() - startTime) / 1000).toFixed(1);
      toast.info(`⚙️ Processando ${result.meta.total_rows.toLocaleString('pt-BR')} participantes...`);

      // Convert to CSV Blob (com BOM, em chunks para evitar limite de string)
      const blob = jsonToCSVBlob(result.data);

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      // Generate filename with timestamp and filter count
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0];
      const filterCount = Object.keys(professionalFilters).filter(k => k !== 'bypass_cache').length;
      const filename = `participantes_${timestamp}_${result.meta.total_rows}rows${filterCount > 0 ? `_${filterCount}filters` : ''}.csv`;
      link.download = filename;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      const totalTime = ((performance.now() - startTime) / 1000).toFixed(1);
      const fileSize = (blob.size / 1024 / 1024).toFixed(1); // MB

      toast.success(
        `✅ ${result.meta.total_rows.toLocaleString('pt-BR')} participantes baixados (${fileSize} MB em ${totalTime}s)`,
        { duration: 5000 }
      );
    } catch (error) {
      console.error("Download error:", error);
      toast.error("❌ Erro ao baixar dados. Tente novamente.");
    }
  }, [professionalFilters, sortBy, sortOrder, jsonToCSVBlob]);

  /**
   * Memoizar filter options vazias para evitar re-criação
   */
  const emptyFilterOptions = useMemo<SmartFilterOptions>(() => ({
    // Filtros de participantes
    bairros: [],
    grupos: [],
    cohorts: [],
    status_list: [],
    situacoes: [],
    subprefeituras: [],
    regioes_administrativas: [],
    cres: [],
    aps: [],
    cas_list: [],
    cras: [],
    escolas: [],
    clinicas: [],
    equipes_familia: [],
    unidades_saude: [],
    equipes_saude: [],
    protocolo_descricoes: [],
    protocolo_status_list: [],
    // Filtros de usuários (admin)
    ocupacoes: [],
    secretarias: [],
    status_ativo: [],
    permissions: []
  }), []);

  /**
   * Show loading screen while all data is loading
   * OTIMIZAÇÃO: Todas as queries rodam em paralelo, mostra loading até a primeira completar
   */
  const isInitialLoading = currentUserLoading && dashboardLoading && participantsLoading;

  if (isInitialLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-lg text-muted-foreground">
            Carregando dados...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <DashboardHeader userInfo={userInfo} />

      <main className="container mx-auto px-6 py-8 flex-1">
        <Tabs
          value={activeTab}
          onValueChange={(value) => {
            // OTIMIZAÇÃO: Usar startTransition para tornar a troca de abas não-bloqueante
            startTransition(() => {
              setActiveTab(value as "overview" | "professional");
            });
          }}
          className="w-full"
        >
          <TabsList className={`grid w-full ${canViewDashboard ? "grid-cols-2" : "grid-cols-1"} mb-8 h-auto p-1 bg-muted rounded-md`}>
            {canViewDashboard && (
              <TabsTrigger
                value="overview"
                className="rounded-sm px-3 py-3 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm font-medium transition-all"
              >
                <BarChart3 className="h-4 w-4 mr-2" />
                Visão Geral
              </TabsTrigger>
            )}
            <TabsTrigger
              value="professional"
              className="rounded-sm px-3 py-3 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm font-medium transition-all"
            >
              <Search className="h-4 w-4 mr-2" />
              Busca Individual
            </TabsTrigger>
          </TabsList>

          {canViewDashboard && activeTab === "overview" && (
            <TabsContent value="overview" className="mt-6">
              <OverviewTab
                data={dashboardResponse?.data?.[0] || null}
                filterOptions={dashboardResponse?.filters || emptyFilterOptions}
                filters={overviewFilters}
                onFilterChange={handleOverviewFilterChange}
                onRefresh={handleOverviewRefresh}
                loading={dashboardFetching}
              />
            </TabsContent>
          )}

          {activeTab === "professional" && (
            <TabsContent value="professional" className="mt-6">
              <ProfessionalTab
                data={participantsResponse?.data || []}
                meta={participantsResponse?.meta || null}
                filterOptions={participantsResponse?.filters || emptyFilterOptions}
                filters={professionalFilters}
                onFilterChange={handleProfessionalFilterChange}
                onPageChange={handleProfessionalPageChange}
                onRefresh={handleProfessionalRefresh}
                onDownload={handleDownloadParticipants}
                loading={participantsFetching}
                pageSize={PAGE_SIZE}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortChange={handleSortChange}
              />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <Footer />
    </div>
  );
}
