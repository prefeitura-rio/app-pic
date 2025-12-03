"use client";

import { useState, useCallback, useMemo, useTransition, startTransition, useEffect } from "react";
import { useSession, signIn } from "next-auth/react";
import { useQuery } from "@tanstack/react-query";
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
export function DashboardClient() {
  const { data: session, status } = useSession();

  // State para filtros e paginação
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilters>({});
  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>({});
  const [professionalPage, setProfessionalPage] = useState(1);
  const [activeTab, setActiveTab] = useState<"overview" | "professional">("overview");
  const [isPending, startTransition] = useTransition();
  const [isReauthenticating, setIsReauthenticating] = useState(false);

  // TanStack Query para Dashboard (Visão Geral)
  const {
    data: dashboardResponse,
    isLoading: dashboardLoading,
    error: dashboardError,
  } = useQuery({
    queryKey: ['dashboard', overviewFilters],
    queryFn: () => apiService.getDashboard(overviewFilters, session?.accessToken as string),
    enabled: !!session?.accessToken && status === "authenticated",
    staleTime: 5 * 60 * 1000, // 5 minutos
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos (sem piscar)
  });

  // TanStack Query para Participants (Busca Individual)
  const {
    data: participantsResponse,
    isLoading: participantsLoading,
    error: participantsError,
  } = useQuery({
    queryKey: ['participants', professionalFilters, professionalPage],
    queryFn: () => apiService.getParticipants(professionalFilters, professionalPage, 20, session?.accessToken as string),
    enabled: !!session?.accessToken && status === "authenticated",
    staleTime: 5 * 60 * 1000, // 5 minutos
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos
  });

  /**
   * Check auth status and handle errors
   */
  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      signIn("authentik");
      return;
    }

    // Handle errors from queries
    if (dashboardError && (dashboardError as any).message === "Unauthorized") {
      setIsReauthenticating(true);
    }
    if (participantsError && (participantsError as any).message === "Unauthorized") {
      setIsReauthenticating(true);
    }
  }, [status, dashboardError, participantsError]);

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
   * Show reauthentication message if token expired
   */
  if (isReauthenticating) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center max-w-md mx-auto p-8">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-foreground mb-2">
            Sessão Expirada
          </h2>
          <p className="text-muted-foreground">
            Sua sessão expirou. Redirecionando para login...
          </p>
        </div>
      </div>
    );
  }

  /**
   * Show loading screen while authenticating
   */
  if (status === "loading") {
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
      <DashboardHeader />

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
                loading={dashboardLoading}
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
                loading={participantsLoading}
              />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <footer className="bg-muted mt-12 py-6 border-t">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>Prefeitura do Rio de Janeiro • Programa Pequenos Cariocas</p>
          <p className="mt-1">Integração Saúde • Educação • Assistência Social</p>
          {session && (
            <p className="mt-2 text-xs">Logado como: {session.user?.email}</p>
          )}
        </div>
      </footer>
    </div>
  );
}
