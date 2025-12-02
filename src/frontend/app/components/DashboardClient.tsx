"use client";

import { useState, useEffect, useCallback } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/app/components/ui/tabs";
import { DashboardHeader } from "@/app/components/DashboardHeader";
import { OverviewTab } from "@/app/components/OverviewTab";
import { ProfessionalTab } from "@/app/components/ProfessionalTab";
import { apiService, DashboardFilters } from "@/app/services/api";
import { Individual, DashboardSummary, FilterOption } from "@/app/types";
import { Loader2, BarChart3, Search } from "lucide-react";
import { useSession, signIn } from "next-auth/react";

export function DashboardClient() {
  const [dashboardData, setDashboardData] = useState<DashboardSummary | null>(null);
  const [participantData, setParticipantData] = useState<Individual[]>([]);
  const [filterOptions, setFilterOptions] = useState<FilterOption[]>([]);
  const [filters, setFilters] = useState<DashboardFilters>({});
  
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");
  const { data: session, status } = useSession();

  const fetchDashboard = useCallback(async (currentFilters: DashboardFilters) => {
    if (session?.accessToken) {
      try {
        const data = await apiService.getDashboardMetrics(currentFilters, session.accessToken as string);
        setDashboardData(data);
      } catch (err) {
        console.error("Failed to load dashboard summary", err);
      }
    }
  }, [session]);

  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      signIn("authentik");
      return;
    }

    if (session?.accessToken) {
      // Fetch initial data
      const loadInitialData = async () => {
        try {
          const [dashboard, participants, options] = await Promise.all([
            apiService.getDashboardMetrics({}, session.accessToken as string),
            apiService.getParticipants(1, 100, session.accessToken as string),
            apiService.getFilterOptions(session.accessToken as string)
          ]);

          setDashboardData(dashboard);
          setParticipantData(participants.data);
          setFilterOptions(options);
        } catch (err) {
          console.error("Failed to load initial data", err);
        } finally {
          setLoading(false);
        }
      };

      loadInitialData();
    }
  }, [session, status]);

  const handleFilterChange = (newFilters: DashboardFilters) => {
    setFilters(newFilters);
    fetchDashboard(newFilters);
  };

  if (loading || status === "loading") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-lg text-muted-foreground">Carregando dados do Painel...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <DashboardHeader />
      
      <main className="container mx-auto px-4 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
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
            {dashboardData ? (
              <OverviewTab 
                data={dashboardData} 
                filterOptions={filterOptions}
                onFilterChange={handleFilterChange}
              />
            ) : (
               <div className="text-center py-10">Não foi possível carregar os dados do painel.</div>
            )}
          </TabsContent>

          <TabsContent value="professional" className="mt-6">
            <ProfessionalTab data={participantData} />
          </TabsContent>
        </Tabs>
      </main>

      <footer className="bg-muted mt-12 py-6 border-t">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>Prefeitura do Rio de Janeiro • Programa Pequenos Cariocas</p>
          <p className="mt-1">Integração Saúde • Educação • Assistência Social</p>
          {session && <p className="mt-2 text-xs">Logado como: {session.user?.email}</p>}
        </div>
      </footer>
    </div>
  );
};
