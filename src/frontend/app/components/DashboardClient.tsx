"use client";

import { useState, useEffect, useCallback, useMemo, useTransition, startTransition } from "react";
import { useSession, signIn } from "next-auth/react";
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

  // Overview tab state (INDEPENDENTE)
  const [dashboardData, setDashboardData] = useState<Dashboard | null>(null);
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilters>({});
  const [overviewFilterOptions, setOverviewFilterOptions] = useState<SmartFilterOptions | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);

  // Professional tab state (INDEPENDENTE)
  const [participantsData, setParticipantsData] = useState<Participante[]>([]);
  const [participantsMeta, setParticipantsMeta] = useState<PaginationMeta | null>(null);
  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>({});
  const [professionalFilterOptions, setProfessionalFilterOptions] = useState<SmartFilterOptions | null>(null);
  const [professionalPage, setProfessionalPage] = useState(1);
  const [professionalLoading, setProfessionalLoading] = useState(false);

  // Tab state
  const [activeTab, setActiveTab] = useState<"overview" | "professional">("overview");
  const [isPending, startTransition] = useTransition();

  // Loading states
  const [initialLoading, setInitialLoading] = useState(true);
  const [isReauthenticating, setIsReauthenticating] = useState(false);
  const [hasLoadedInitialData, setHasLoadedInitialData] = useState(false);

  /**
   * Check auth status
   */
  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      signIn("authentik");
      return;
    }

    if (session?.accessToken) {
      setInitialLoading(false);
    }
  }, [session, status]);

  /**
   * Fetch dashboard data (métricas agregadas)
   */
  const fetchDashboard = useCallback(
    async (filters: DashboardFilters) => {
      if (!session?.accessToken) return;

      console.log("[DashboardClient] fetchDashboard called with filters:", filters);
      setOverviewLoading(true);
      try {
        const response = await apiService.getDashboard(
          filters,
          session.accessToken as string
        );
        setDashboardData(response.data[0]);

        // Atualizar filter options da aba Overview
        if (response.filters) {
          setOverviewFilterOptions(response.filters);
        }
      } catch (err: any) {
        if (err.message === "Unauthorized") {
          setIsReauthenticating(true);
        } else {
          console.error("[DashboardClient] Failed to load dashboard:", err);
        }
      } finally {
        setOverviewLoading(false);
      }
    },
    [session]
  );

  /**
   * Fetch participants data (lista paginada)
   */
  const fetchParticipants = useCallback(
    async (filters: ParticipantFilters, page: number) => {
      if (!session?.accessToken) return;

      console.log("[DashboardClient] fetchParticipants called with filters:", filters, "page:", page);
      setProfessionalLoading(true);
      try {
        const response = await apiService.getParticipants(
          filters,
          page,
          20, // page_size
          session.accessToken as string
        );
        setParticipantsData(response.data);
        setParticipantsMeta(response.meta);

        // Atualizar filter options da aba Professional
        if (response.filters) {
          setProfessionalFilterOptions(response.filters);
        }
      } catch (err: any) {
        if (err.message === "Unauthorized") {
          setIsReauthenticating(true);
        } else {
          console.error("[DashboardClient] Failed to load participants:", err);
        }
      } finally {
        setProfessionalLoading(false);
      }
    },
    [session]
  );

  /**
   * Load initial data (apenas uma vez)
   */
  useEffect(() => {
    if (initialLoading || !session?.accessToken || hasLoadedInitialData) return;

    let isMounted = true;

    // Carregar dashboard PRIMEIRO (é a aba inicial visível)
    // Dashboard popula cache, participants reutiliza depois
    const loadData = async () => {
      if (!isMounted) return;

      console.log("[DashboardClient] Loading initial data...");

      try {
        await fetchDashboard({}); // Dashboard sem filtros (popula cache + mostra dados)

        if (!isMounted) return;

        await fetchParticipants({}, 1); // Primeira página de participantes (reutiliza cache)

        if (isMounted) {
          setHasLoadedInitialData(true); // Marcar DEPOIS de carregar com sucesso
          console.log("[DashboardClient] Initial data loaded successfully");
        }
      } catch (error) {
        console.error("[DashboardClient] Error loading initial data:", error);
      }
    };

    loadData();

    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialLoading, hasLoadedInitialData]); // hasLoadedInitialData previne múltiplas chamadas

  /**
   * Handle overview filter changes
   */
  const handleOverviewFilterChange = useCallback((newFilters: DashboardFilters) => {
    // Evitar chamada se os filtros não mudaram
    if (JSON.stringify(newFilters) === JSON.stringify(overviewFilters)) {
      return;
    }
    setOverviewFilters(newFilters);
    fetchDashboard(newFilters);
  }, [fetchDashboard, overviewFilters]);

  /**
   * Handle professional filter changes
   */
  const handleProfessionalFilterChange = useCallback((newFilters: ParticipantFilters) => {
    // Evitar chamada se os filtros não mudaram
    if (JSON.stringify(newFilters) === JSON.stringify(professionalFilters)) {
      return;
    }
    setProfessionalFilters(newFilters);
    setProfessionalPage(1); // Reset to page 1
    fetchParticipants(newFilters, 1);
  }, [fetchParticipants, professionalFilters]);

  /**
   * Handle professional page change
   */
  const handleProfessionalPageChange = useCallback((page: number) => {
    setProfessionalPage(page);
    fetchParticipants(professionalFilters, page);
  }, [fetchParticipants, professionalFilters]);

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
   * Show loading screen while initial data loads
   */
  if (status === "loading" || initialLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-lg text-muted-foreground">
            Carregando dados do Painel...
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
                data={dashboardData}
                filterOptions={overviewFilterOptions || emptyFilterOptions}
                filters={overviewFilters}
                onFilterChange={handleOverviewFilterChange}
                loading={overviewLoading}
              />
            </TabsContent>
          )}

          {activeTab === "professional" && (
            <TabsContent value="professional" className="mt-6">
              <ProfessionalTab
                data={participantsData}
                meta={participantsMeta}
                filterOptions={professionalFilterOptions || emptyFilterOptions}
                filters={professionalFilters}
                onFilterChange={handleProfessionalFilterChange}
                onPageChange={handleProfessionalPageChange}
                loading={professionalLoading}
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
