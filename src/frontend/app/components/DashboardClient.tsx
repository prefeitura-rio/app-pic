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
 * Main Dashboard Orchestrator Component
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

  // State para filtros e paginação
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilterValues>({});
  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>({});
  const [professionalPage, setProfessionalPage] = useState(1);
  const [activeTab, setActiveTab] = useState<"overview" | "professional">("overview");
  const [isPending, startTransition] = useTransition();
  const [bypassCacheDashboardTimestamp, setBypassCacheDashboardTimestamp] = useState<number | null>(null);
  const [bypassCacheParticipantsTimestamp, setBypassCacheParticipantsTimestamp] = useState<number | null>(null);

  // State para ordenação
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");


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
   * Memoizar filter options vazias para evitar re-criação
   */
  const emptyFilterOptions = useMemo<SmartFilterOptions>(() => ({
    // Filtros de participantes
    bairros: [],
    grupos: [],
    cohorts: [],
    status_list: [],
    situacoes: [],
    cres: [],
    aps: [],
    cas_list: [],
    cras: [],
    escolas: [],
    clinicas: [],
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
          <TabsList className="grid w-full grid-cols-2 mb-8 h-auto p-1 bg-muted rounded-md">
            <TabsTrigger
              value="overview"
              className="rounded-sm px-3 py-3 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm font-medium transition-all"
            >
              <BarChart3 className="h-4 w-4 mr-2" />
              Visão Geral
            </TabsTrigger>
            <TabsTrigger
              value="professional"
              className="rounded-sm px-3 py-3 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm font-medium transition-all"
            >
              <Search className="h-4 w-4 mr-2" />
              Busca Individual
            </TabsTrigger>
          </TabsList>

          {activeTab === "overview" && (
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
