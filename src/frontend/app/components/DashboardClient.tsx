"use client";

import {
  useState,
  useCallback,
  useTransition,
  useEffect,
} from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useForcePolicySyncOnLogin } from "@/app/hooks/useForcePolicySyncOnLogin";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/app/components/ui/tabs";
import { DashboardHeader } from "@/app/components/DashboardHeader";
import { Footer } from "@/app/components/Footer";
import { TermsDialog } from "@/app/components/TermsDialog";
import { OverviewTab } from "@/app/components/OverviewTab";
import { ProfessionalTab } from "@/app/components/ProfessionalTab";
import { apiService } from "@/app/services/api";
import {
  ParticipantFilters,
  GeospatialFilters,
  SortOrder,
  Participante,
  DashboardFilterValues,
} from "@/app/types";
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
export function DashboardClient({
  userInfo,
}: {
  userInfo?: UserInfo | null;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();

  // Chave do sessionStorage com o estado da página (filtros, aba, paginação,
  // ordenação). Declarada antes do bloco de fresh login, que pode limpar.
  const STORAGE_KEY = "dashboard-state";

  // Termo de responsabilidade
  // Novo login → callback seta cookie fresh_login=1 → sessionStorage vai pra "0"
  // Aceite → sessionStorage vai pra "1" e fica assim até novo login
  const TERMS_KEY = "terms-accepted";
  const [isFreshLogin] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return document.cookie
      .split(";")
      .some((c) => c.trim() === "fresh_login=1");
  });
  const [termsAccepted, setTermsAccepted] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    if (isFreshLogin) {
      // Consome o cookie de fresh login e zera o estado da página: filtros,
      // aba, paginação e ordenação voltam aos defaults (ordenação por nome).
      document.cookie = "fresh_login=; path=/; max-age=0";
      sessionStorage.setItem(TERMS_KEY, "0");
      sessionStorage.removeItem(STORAGE_KEY);
    }
    return sessionStorage.getItem(TERMS_KEY) === "1";
  });

  // Fresh login: descarta TODO o cache do TanStack Query do usuário anterior
  // (lista, dashboard, opções de filtro, detalhe) para a página nascer limpa.
  useEffect(() => {
    if (isFreshLogin) {
      queryClient.clear();
    }
  }, [isFreshLogin, queryClient]);

  const handleTermsAccept = () => {
    sessionStorage.setItem(TERMS_KEY, "1");
    setTermsAccepted(true);
  };

  // State para filtros e paginação (com restauração do sessionStorage)
  const [overviewFilters, setOverviewFilters] =
    useState<DashboardFilterValues>(() => {
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

  const [professionalFilters, setProfessionalFilters] =
    useState<ParticipantFilters>(() => {
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

  // O tipo de camada padrão ao abrir a visualização geoespacial é "BAIRRO":
  // a primeira query de camadas já nasce filtrada, evitando baixar as 4470+
  // camadas inteiras no primeiro fetch do mapa.
  const [geospatialFilters, setGeospatialFilters] =
    useState<GeospatialFilters>(() => {
      const DEFAULT: GeospatialFilters = { tipo_camada: "BAIRRO" };
      if (typeof window === "undefined") return DEFAULT;
      try {
        const saved = sessionStorage.getItem(STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved);
          const restored = parsed.geospatialFilters;
          if (restored && Object.keys(restored).length > 0) return restored;
        }
      } catch (e) {
        console.error("Error restoring geospatial filters:", e);
      }
      return DEFAULT;
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

  const [activeTab, setActiveTab] = useState<"overview" | "professional">(
    () => {
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
    },
  );

  const [, startTransition] = useTransition();
  const [bypassCacheDashboardTimestamp, setBypassCacheDashboardTimestamp] =
    useState<number | null>(null);
  const [
    bypassCacheParticipantsTimestamp,
    setBypassCacheParticipantsTimestamp,
  ] = useState<number | null>(null);
  const [
    bypassCacheGeospatialTimestamp,
    setBypassCacheGeospatialTimestamp,
  ] = useState<number | null>(null);

  // Lazy load: mapa geoespacial só carrega quando o usuário abre o collapsible
  const [geospatialMapOpen, setGeospatialMapOpen] = useState(false);

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

  // V2 detail — clicked participant
  const [selectedParticipantId, setSelectedParticipantId] = useState<
    string | null
  >(null);

  // V2 detail fetch
  const {
    data: participantDetailResponse,
    isLoading: detailLoading,
  } = useQuery({
    queryKey: ["participantDetailV2", selectedParticipantId],
    queryFn: () =>
      apiService.getParticipantDetailV2(selectedParticipantId!),
    enabled: !!selectedParticipantId,
    staleTime: 5 * 60 * 1000,
  });

  const selectedParticipant: Participante | null =
    participantDetailResponse?.data ?? null;

  // Persistir estado no sessionStorage sempre que mudar
  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      const state = {
        overviewFilters,
        professionalFilters,
        geospatialFilters,
        professionalPage,
        activeTab,
        sortBy,
        sortOrder,
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.error("Error saving state to sessionStorage:", e);
    }
  }, [
    overviewFilters,
    professionalFilters,
    geospatialFilters,
    professionalPage,
    activeTab,
    sortBy,
    sortOrder,
  ]);

  // Força sincronização completa de policies no primeiro acesso pós-login OAuth.
  const forceSync = useForcePolicySyncOnLogin();

  // Verificação prévia de permissões (evita chamadas desnecessárias)
  const {
    data: currentUser,
    isLoading: currentUserLoading,
    error: currentUserError,
  } = useQuery({
    queryKey: ["currentUser"],
    queryFn: () => apiService.getCurrentUser(forceSync ? { force_sync: true } : {}),
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
    isFetching: dashboardFetching,
    error: dashboardError,
  } = useQuery({
    queryKey: ["dashboardV2", overviewFilters, bypassCacheDashboardTimestamp],
    queryFn: async ({ queryKey }) => {
      const timestamp = queryKey[queryKey.length - 1] as number | null;
      const shouldBypassCache = timestamp !== null;

      const result = await apiService.getDashboardV2({
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
    enabled: activeTab === "overview", // Lazy load: só busca quando a aba é acessada
  });

  // V2 — Participants (Busca Individual)
  // Substitui getParticipants V1 pelo endpoint enxuto (13 campos)
  const {
    data: participantsResponse,
    isLoading: participantsLoading,
    isFetching: participantsFetching,
    error: participantsError,
  } = useQuery({
    queryKey: [
      "participantsV2",
      professionalFilters,
      professionalPage,
      sortBy,
      sortOrder,
      bypassCacheParticipantsTimestamp,
    ],
    queryFn: async ({ queryKey }) => {
      const timestamp = queryKey[queryKey.length - 1] as number | null;
      const shouldBypassCache = timestamp !== null;

      const result = await apiService.getParticipantsV2(
        {
          ...professionalFilters,
          ...(sortBy && { sort_by: sortBy, sort_order: sortOrder }),
          ...(shouldBypassCache && { bypass_cache: true }),
        },
        professionalPage,
        PAGE_SIZE,
      );

      if (shouldBypassCache) {
        setBypassCacheParticipantsTimestamp(null);
      }

      return result;
    },
    staleTime: 5 * 60 * 1000, // 5 minutos
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos
  });

  // TanStack Query para Geospatial Layers (Mapa) — LAZY
  // Só carrega quando a aba "professional" está ativa E o mapa foi aberto.
  // Filtros e bypassCacheTimestamp incluídos no queryKey para refetch automático.
  const geospatialEnabled =
    activeTab === "professional" && geospatialMapOpen;

  const {
    data: geospatialLayersResponse,
    isFetching: geospatialFetching,
  } = useQuery({
    queryKey: ["geospatialLayers", geospatialFilters, bypassCacheGeospatialTimestamp],
    queryFn: async ({ queryKey }) => {
      const filters = queryKey[1] as GeospatialFilters;
      const timestamp = queryKey[2] as number | null;
      const shouldBypassCache = timestamp !== null;

      const result = await apiService.getGeospatialLayers(filters, shouldBypassCache);

      if (shouldBypassCache) {
        setBypassCacheGeospatialTimestamp(null);
      }

      return result;
    },
    enabled: geospatialEnabled,
    staleTime: 30 * 60 * 1000, // 30 minutos (dados geográficos mudam raramente)
    placeholderData: (prev) => prev,
  });

  const geospatialLayers = geospatialLayersResponse?.data || [];

  // Determina se usuário pode ver dashboard baseado em currentUser (já carregado
  // em paralelo com participants). A regra espelha o backend: secretarias_acesso
  // com as 3 secretarias ou is_super_admin equivale a "TODOS".
  // Isso elimina a dependência de dashboardResponse para mostrar/esconder a aba,
  // permitindo que o dashboard carregue lazily apenas quando a aba é acessada.
  const _ALL_SECRETARIAS = new Set(["SMAS", "SME", "SMS"]);
  const canViewDashboard =
    !currentUser ||
    currentUser.is_super_admin ||
    (currentUser.secretarias_acesso?.length === 3 &&
      currentUser.secretarias_acesso.every((s) => _ALL_SECRETARIAS.has(s)));

  // Force professional tab if user cannot view dashboard.
  // Ajuste feito durante a renderização (não em um efeito): a própria condição
  // (`activeTab === "overview"`) deixa de ser verdadeira após o ajuste, então
  // não há loop, e evita o "flash" da aba Visão Geral antes do commit.
  if (!canViewDashboard && activeTab === "overview") {
    setActiveTab("professional");
  }

  /**
   * Handle authentication errors
   */
  useEffect(() => {
    // Handle errors from queries
    if (dashboardError && dashboardError.message === "Unauthorized") {
      router.push("/login");
      return;
    }
    if (participantsError && participantsError.message === "Unauthorized") {
      router.push("/login");
      return;
    }
  }, [dashboardError, participantsError, router]);

  /**
   * Handle overview filter changes
   * TanStack Query refetch automaticamente quando overviewFilters muda
   */
  const handleOverviewFilterChange = useCallback(
    (newFilters: DashboardFilterValues) => {
      setOverviewFilters(newFilters);
    },
    [],
  );

  /**
   * Handle professional filter changes
   * TanStack Query refetch automaticamente quando professionalFilters muda
   */
  const handleProfessionalFilterChange = useCallback(
    (newFilters: ParticipantFilters) => {
      setProfessionalFilters(newFilters);
      setProfessionalPage(1); // Reset to page 1
    },
    [],
  );

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
  const handleSortChange = useCallback(
    (newSortBy: string, newSortOrder: SortOrder) => {
      setSortBy(newSortBy);
      setSortOrder(newSortOrder);
      setProfessionalPage(1); // Reset to page 1 when sorting changes
    },
    [],
  );

  /**
   * Handle refresh with cache bypass (for Overview tab)
   */
  const handleOverviewRefresh = useCallback(() => {
    // Invalidate TanStack Query cache to force refetch
    queryClient.invalidateQueries({ queryKey: ["dashboardV2"] });
    queryClient.invalidateQueries({ queryKey: ["filterFieldOptions"] });
    setBypassCacheDashboardTimestamp(Date.now());
  }, [queryClient]);

  /**
   * Handle refresh with cache bypass (for Professional tab)
   */
  const handleProfessionalRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["participantsV2"] });
    queryClient.invalidateQueries({ queryKey: ["geospatialLayers"] });
    queryClient.invalidateQueries({ queryKey: ["filterFieldOptions"] });
    setBypassCacheParticipantsTimestamp(Date.now());
    setBypassCacheGeospatialTimestamp(Date.now());
  }, [queryClient]);

  const handleRowClick = useCallback((idMembroFamilia: string) => {
    setSelectedParticipantId(idMembroFamilia);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedParticipantId(null);
  }, []);

  /**
   * Handle download all filtered participants as CSV via server-side streaming,
   * com feedback de progresso contínuo ao usuário.
   *
   * Fluxo:
   * 1. Mostra "Aguardando servidor..." enquanto o backend processa (fase silenciosa)
   * 2. Assim que o primeiro byte chega, calibra bytes/linha com dados reais do chunk
   * 3. Lê o stream chunk a chunk via ReadableStream, acumulando em um Uint8Array
   * 4. Ao final, cria o Blob e dispara o download
   *
   * O progresso é calculado com base em bytes_por_linha medido no primeiro chunk real,
   * eliminando a dependência de constantes empíricas fixas.
   */
  const handleDownloadParticipants = useCallback(async () => {
    const startTime = performance.now();
    const TOAST_ID = "csv-download";

    try {
      toast.loading("⏳ Aguardando servidor...", {
        id: TOAST_ID,
        duration: Infinity,
      });

      const response = await apiService.exportParticipants({
        ...professionalFilters,
        ...(sortBy && { sort_by: sortBy, sort_order: sortOrder }),
      });

      if (!response.body) {
        throw new Error("Stream não disponível no response");
      }

      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let receivedBytes = 0;

      // Leitura do stream chunk a chunk — mostra MB recebidos sem estimativas
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        chunks.push(value);
        receivedBytes += value.byteLength;

        const receivedMB = (receivedBytes / 1024 / 1024).toFixed(1);
        toast.loading(`📥 Baixando... ${receivedMB} MB`, {
          id: TOAST_ID,
          duration: Infinity,
        });
      }

      // Montar o Blob a partir dos chunks acumulados
      const totalLength = chunks.reduce((sum, c) => sum + c.byteLength, 0);
      const merged = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.byteLength;
      }
      const blob = new Blob([merged], { type: "text/csv;charset=utf-8;" });

      // Disparar o download
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;

      const timestamp = new Date().toISOString().split("T")[0];
      const filterCount = Object.keys(professionalFilters).filter(
        (k) => k !== "bypass_cache",
      ).length;
      const filename = `participantes_${timestamp}_${filterCount}filters.csv`;
      link.download = filename;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      const totalTime = ((performance.now() - startTime) / 1000).toFixed(1);
      const fileSize = (blob.size / 1024 / 1024).toFixed(1);

      toast.success(
        `✅ Download concluído (${fileSize} MB em ${totalTime}s)`,
        { id: TOAST_ID, duration: 6000 },
      );
    } catch (error) {
      console.error("Download error:", error);
      toast.error("❌ Erro ao baixar dados. Tente novamente.", {
        id: TOAST_ID,
        duration: 5000,
      });
    }
  }, [professionalFilters, sortBy, sortOrder]);

  /**
   * Show loading screen while critical data is loading.
   * Dashboard é lazy (carrega apenas quando a aba é acessada), então não
   * bloqueia o load inicial.
   */
  const isInitialLoading = currentUserLoading || participantsLoading;

  if (isInitialLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center max-w-md px-6">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
          <p className="text-lg font-semibold">
            {participantsLoading
              ? "Carregando participantes..."
              : "Verificando suas permissões..."}
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            {participantsLoading
              ? "Buscando a listagem de participantes na base de dados."
              : "Confirmando seu acesso às secretarias antes de abrir o painel."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {!termsAccepted && <TermsDialog onAccept={handleTermsAccept} />}
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
          <TabsList
            className={`grid w-full ${canViewDashboard ? "grid-cols-2" : "grid-cols-1"} mb-8 h-auto p-1 bg-muted rounded-md`}
          >
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
                data={dashboardResponse?.data || null}
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
                filters={professionalFilters}
                onFilterChange={handleProfessionalFilterChange}
                onPageChange={handleProfessionalPageChange}
                onRowClick={handleRowClick}
                onCloseDetail={handleCloseDetail}
                selectedParticipant={selectedParticipant}
                detailLoading={detailLoading}
                onRefresh={handleProfessionalRefresh}
                onDownload={handleDownloadParticipants}
                loading={participantsFetching}
                pageSize={PAGE_SIZE}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortChange={handleSortChange}
                isSuperAdmin={currentUser?.is_super_admin || false}
                secretariasAcesso={currentUser?.secretarias_acesso || []}
                geospatialLayers={geospatialLayers}
                geospatialLoading={geospatialFetching}
                geospatialFilters={geospatialFilters}
                onGeospatialMapOpen={setGeospatialMapOpen}
                onGeospatialFilterChange={setGeospatialFilters}
              />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <Footer />
    </div>
  );
}
