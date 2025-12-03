"use client";

import { useState, useEffect, useCallback } from "react";
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
 * Architecture (CORRIGIDA):
 * - Fetches filter options once on mount
 * - Overview tab: Calls dashboard API with filters
 * - Professional tab: Calls participants API with filters + pagination
 * - Each tab has independent filter state
 * - NO client-side data loading - all via API calls
 */
export function DashboardClient() {
  const { data: session, status } = useSession();

  // Overview tab state
  const [dashboardData, setDashboardData] = useState<Dashboard | null>(null);
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilters>({});
  const [overviewFilterOptions, setOverviewFilterOptions] = useState<SmartFilterOptions | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);

  // Professional tab state
  const [participantsData, setParticipantsData] = useState<Participante[]>([]);
  const [participantsMeta, setParticipantsMeta] = useState<PaginationMeta | null>(null);
  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>({});
  const [professionalFilterOptions, setProfessionalFilterOptions] = useState<SmartFilterOptions | null>(null);
  const [professionalPage, setProfessionalPage] = useState(1);
  const [professionalLoading, setProfessionalLoading] = useState(false);

  // Tab state
  const [activeTab, setActiveTab] = useState<"overview" | "professional">("overview");

  // Loading states
  const [initialLoading, setInitialLoading] = useState(true);

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
   * Fetch dashboard data when overview tab is active or filters change
   */
  const fetchDashboard = useCallback(
    async (filters: DashboardFilters) => {
      if (!session?.accessToken) return;

      setOverviewLoading(true);
      try {
        const response = await apiService.getDashboard(
          filters,
          session.accessToken as string
        );
        setDashboardData(response.data[0]);
        // Dashboard não precisa de filter options (dados pré-agregados)
        // Mas podemos usar os filtros do participants para popular inicialmente
      } catch (err: any) {
        if (err.message !== "Unauthorized") {
          console.error("[DashboardClient] Failed to load dashboard:", err);
        }
      } finally {
        setOverviewLoading(false);
      }
    },
    [session]
  );

  /**
   * Fetch participants when professional tab is active or filters/page change
   */
  const fetchParticipants = useCallback(
    async (filters: ParticipantFilters, page: number) => {
      if (!session?.accessToken) return;

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
        // Atualizar filter options com os filtros dinâmicos da resposta
        if (response.filters) {
          setProfessionalFilterOptions(response.filters);
          // Também usar para overview se não tiver ainda
          if (!overviewFilterOptions) {
            setOverviewFilterOptions(response.filters);
          }
        }
      } catch (err: any) {
        if (err.message !== "Unauthorized") {
          console.error("[DashboardClient] Failed to load participants:", err);
        }
      } finally {
        setProfessionalLoading(false);
      }
    },
    [session, overviewFilterOptions]
  );

  /**
   * Load initial data for active tab
   */
  useEffect(() => {
    if (initialLoading || !session?.accessToken) return;

    if (activeTab === "overview") {
      fetchDashboard(overviewFilters);
    } else {
      fetchParticipants(professionalFilters, professionalPage);
    }
  }, [activeTab, initialLoading, session]);

  /**
   * Handle overview filter changes
   */
  const handleOverviewFilterChange = (newFilters: DashboardFilters) => {
    setOverviewFilters(newFilters);
    fetchDashboard(newFilters);
  };

  /**
   * Handle professional filter changes
   */
  const handleProfessionalFilterChange = (newFilters: ParticipantFilters) => {
    setProfessionalFilters(newFilters);
    setProfessionalPage(1); // Reset to page 1
    fetchParticipants(newFilters, 1);
  };

  /**
   * Handle professional page change
   */
  const handleProfessionalPageChange = (page: number) => {
    setProfessionalPage(page);
    fetchParticipants(professionalFilters, page);
  };

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

  // Filter options serão carregados dinamicamente quando os dados forem buscados

  return (
    <div className="min-h-screen bg-background">
      <DashboardHeader />

      <main className="container mx-auto px-4 py-8">
        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as "overview" | "professional")}
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

          <TabsContent value="overview" className="mt-6">
            <OverviewTab
              data={dashboardData}
              filterOptions={overviewFilterOptions || { bairros: [], grupos: [], cohorts: [], status_list: [], cres: [], cras: [], escolas: [], clinicas: [] }}
              filters={overviewFilters}
              onFilterChange={handleOverviewFilterChange}
              loading={overviewLoading}
            />
          </TabsContent>

          <TabsContent value="professional" className="mt-6">
            <ProfessionalTab
              data={participantsData}
              meta={participantsMeta}
              filterOptions={professionalFilterOptions || { bairros: [], grupos: [], cohorts: [], status_list: [], cres: [], cras: [], escolas: [], clinicas: [] }}
              filters={professionalFilters}
              onFilterChange={handleProfessionalFilterChange}
              onPageChange={handleProfessionalPageChange}
              loading={professionalLoading}
            />
          </TabsContent>
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
