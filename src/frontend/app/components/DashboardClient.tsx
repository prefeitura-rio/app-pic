"use client";

import { useState, useEffect } from "react";
import { useSession, signIn } from "next-auth/react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/app/components/ui/tabs";
import { DashboardHeader } from "@/app/components/DashboardHeader";
import { OverviewTab } from "@/app/components/OverviewTab";
import { ProfessionalTab } from "@/app/components/ProfessionalTab";
import { apiService } from "@/app/services/api";
import {
  SmartFilterOptions,
  Participante,
  DashboardFilters,
  ParticipantFilters,
  LoadingState,
} from "@/app/types";
import { Loader2, BarChart3, Search } from "lucide-react";

/**
 * Main Dashboard Orchestrator Component
 *
 * Architecture:
 * - Fetches filter options once on mount (shared between tabs)
 * - Fetches participants once on mount (shared between tabs)
 * - Each tab has independent filter state
 * - Overview tab: Filters participants in-memory for calculations
 * - Professional tab: Uses search and client-side pagination
 */
export function DashboardClient() {
  const { data: session, status } = useSession();

  // Shared data (fetched once, used by both tabs)
  const [filterOptions, setFilterOptions] = useState<SmartFilterOptions | null>(null);
  const [allParticipants, setAllParticipants] = useState<Participante[]>([]);

  // Loading states
  const [filterOptionsState, setFilterOptionsState] = useState<LoadingState>("idle");
  const [participantsState, setParticipantsState] = useState<LoadingState>("idle");

  // Tab state
  const [activeTab, setActiveTab] = useState<"overview" | "professional">("overview");

  // Independent filter states (each tab manages its own)
  const [overviewFilters, setOverviewFilters] = useState<DashboardFilters>({});
  const [professionalFilters, setProfessionalFilters] = useState<ParticipantFilters>({});

  /**
   * Fetch filter options on mount
   */
  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      signIn("authentik");
      return;
    }

    if (session?.accessToken && filterOptionsState === "idle") {
      setFilterOptionsState("loading");

      apiService
        .getFilterOptions(session.accessToken as string)
        .then((options) => {
          setFilterOptions(options);
          setFilterOptionsState("success");
        })
        .catch((err) => {
          if (err.message !== "Unauthorized") {
            console.error("[DashboardClient] Failed to load filter options:", err);
          }
          setFilterOptionsState("error");
        });
    }
  }, [session, status, filterOptionsState]);

  /**
   * Fetch ALL participants on mount (for in-memory filtering)
   * We request a large page size to get everything in one call
   */
  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      signIn("authentik");
      return;
    }

    if (session?.accessToken && participantsState === "idle") {
      setParticipantsState("loading");

      // Request all participants (adjust page_size based on your dataset)
      // For datasets > 100k, consider implementing proper pagination
      apiService
        .getParticipants({}, 1, 100000, session.accessToken as string)
        .then((response) => {
          setAllParticipants(response.data);
          setParticipantsState("success");
          console.log(
            `[DashboardClient] Loaded ${response.data.length} participants (${response.meta.total_rows} total)`
          );
        })
        .catch((err) => {
          if (err.message !== "Unauthorized") {
            console.error("[DashboardClient] Failed to load participants:", err);
          }
          setParticipantsState("error");
        });
    }
  }, [session, status, participantsState]);

  /**
   * Show loading screen while initial data loads
   */
  const isLoading =
    status === "loading" ||
    filterOptionsState === "loading" ||
    participantsState === "loading";

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-lg text-muted-foreground">
            Carregando dados do Painel...
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            {filterOptionsState === "loading" && "Carregando opções de filtros..."}
            {participantsState === "loading" && "Carregando participantes..."}
          </p>
        </div>
      </div>
    );
  }

  /**
   * Show error state if data failed to load
   */
  if (filterOptionsState === "error" || participantsState === "error") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg text-destructive mb-4">
            Erro ao carregar dados do painel
          </p>
          <p className="text-sm text-muted-foreground">
            Verifique sua conexão e tente novamente.
          </p>
        </div>
      </div>
    );
  }

  /**
   * Show empty state if no data loaded
   */
  if (!filterOptions || allParticipants.length === 0) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg text-muted-foreground">
            Nenhum dado disponível no momento
          </p>
        </div>
      </div>
    );
  }

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
              allParticipants={allParticipants}
              filterOptions={filterOptions}
              filters={overviewFilters}
              onFilterChange={setOverviewFilters}
            />
          </TabsContent>

          <TabsContent value="professional" className="mt-6">
            <ProfessionalTab
              allParticipants={allParticipants}
              filterOptions={filterOptions}
              filters={professionalFilters}
              onFilterChange={setProfessionalFilters}
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
