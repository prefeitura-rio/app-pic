"use client";

import { useState, useCallback, useMemo, useTransition, startTransition, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/app/components/ui/tabs";
import { DashboardHeader } from "@/app/components/DashboardHeader";
import { OverviewTab } from "@/app/components/OverviewTab";
import { ProfessionalTab } from "@/app/components/ProfessionalTab";
import { apiService } from "@/app/services/api";
import {
  SmartFilterOptions,
  Dashboard,
  Participante,
  DashboardFilters,
  ParticipantFilters,
  PaginationMeta,
} from "@/app/types";
import { Loader2, BarChart3, Search } from "lucide-react";

interface UserInfo {
  name?: string;
  email?: string;
  preferred_username?: string;
  given_name?: string;
  family_name?: string;
  sub?: string;
  iat?: number;
  exp?: number;
}

/**
 * Main Dashboard Orchestrator Component
 *
 * Arquitetura Híbrida:
 * 1. Inicialização: Carrega dashboard + participants em paralelo
 * 2. Overview tab: Chama /dashboard com filtros para recalcular métricas
 * 3. Professional tab: Chama /participants com filtros + paginação
 * 4. Trocar de aba: NÃO faz chamadas (usa cache)
 * 5. Filtros: Recarrega apenas o endpoint necessário
 */
export function DashboardClient({ userInfo }: { userInfo?: UserInfo | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();

  // State para filtros e paginação
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilters>({});
  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>({});
  const [professionalPage, setProfessionalPage] = useState(1);
  const [activeTab, setActiveTab] = useState<"overview" | "professional">("overview");
  const [isPending, startTransition] = useTransition();
  const [bypassCacheDashboardTimestamp, setBypassCacheDashboardTimestamp] = useState<number | null>(null);
  const [bypassCacheParticipantsTimestamp, setBypassCacheParticipantsTimestamp] = useState<number | null>(null);

  // TanStack Query para Dashboard (Visão Geral)
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
  const {
    data: participantsResponse,
    isLoading: participantsLoading,
    isFetching: participantsFetching,
    error: participantsError,
  } = useQuery({
    queryKey: ['participants', professionalFilters, professionalPage, bypassCacheParticipantsTimestamp],
    queryFn: async ({ queryKey }) => {
      const timestamp = queryKey[queryKey.length - 1] as number | null;
      const shouldBypassCache = timestamp !== null;

      const result = await apiService.getParticipants(
        {
          ...professionalFilters,
          ...(shouldBypassCache && { bypass_cache: true }),
        },
        professionalPage,
        20
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
  const handleOverviewFilterChange = useCallback((newFilters: DashboardFilters) => {
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
   * Handle refresh with cache bypass (for Overview tab)
   */
  const handleOverviewRefresh = useCallback(() => {
    toast.info("Atualizando dados (forçando refresh do cache)...");
    setBypassCacheDashboardTimestamp(Date.now());
  }, []);

  /**
   * Handle refresh with cache bypass (for Professional tab)
   */
  const handleProfessionalRefresh = useCallback(() => {
    toast.info("Atualizando dados (forçando refresh do cache)...");
    setBypassCacheParticipantsTimestamp(Date.now());
  }, []);

  /**
   * Memoizar filter options vazias para evitar re-criação
   */
  const emptyFilterOptions = useMemo(() => ({
    bairros: [],
    grupos: [],
    cohorts: [],
    status_list: [],
    situacoes: [],
    cres: [],
    caps: [],
    cas_list: [],
    cras: [],
    escolas: [],
    clinicas: []
  }), []);

  /**
   * Show loading screen while loading data
   */
  if (dashboardLoading && participantsLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-lg text-muted-foreground">
            Autenticando...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <DashboardHeader userInfo={userInfo} />

      <main className="container mx-auto px-4 py-8 flex-1">
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
          <TabsList className="grid w-full grid-cols-2 mb-8 h-auto p-1 bg-muted">
            <TabsTrigger
              value="overview"
              className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground py-3"
            >
              <BarChart3 className="h-4 w-4 mr-2" />
              Visão Geral
            </TabsTrigger>
            <TabsTrigger
              value="professional"
              className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground py-3"
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
              />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <footer className="bg-muted mt-12 py-6 border-t">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>Prefeitura do Rio de Janeiro • Programa Pequenos Cariocas</p>
          <p className="mt-1">Integração Saúde • Educação • Assistência Social</p>
          {userInfo?.name && (
            <p className="mt-2 text-xs">Logado como: {userInfo.name}</p>
          )}
        </div>
      </footer>
    </div>
  );
}
