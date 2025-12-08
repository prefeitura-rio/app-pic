"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiService } from "@/app/services/api";
import { UserAccessRecord, AvailableIds, CreateUserRequest, UpdateUserRequest } from "@/app/types";
import { UserTable } from "@/app/components/admin/UserTable";
import { UserForm } from "@/app/components/admin/UserForm";
import { UserTableSkeleton } from "@/app/components/admin/UserTableSkeleton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/app/components/ui/tabs";
import { AlertCircle, Users, UserCog, Search, X, RefreshCw, Filter } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"users" | "form">("users");
  const [editingUser, setEditingUser] = useState<UserAccessRecord | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 100;

  // Filter states
  const [filterOcupacao, setFilterOcupacao] = useState("");
  const [filterSecretaria, setFilterSecretaria] = useState("");
  const [filterPermission, setFilterPermission] = useState<string>(""); // empty = all (super_admin/admin/user)
  const [filterStatus, setFilterStatus] = useState<string>(""); // empty = all
  const [searchInput, setSearchInput] = useState(""); // Input do usuário
  const [searchTerm, setSearchTerm] = useState(""); // Termo de busca ativo (enviado ao backend)

  // Fetch current user (compartilha cache com DashboardHeader via queryKey)
  const {
    data: currentUser,
    isLoading: currentUserLoading,
  } = useQuery({
    queryKey: ['currentUser'], // Mesma key que DashboardHeader/DashboardClient
    queryFn: () => apiService.getCurrentUser(),
    retry: false,
    staleTime: 10 * 60 * 1000, // 10 minutos (mesmo que DashboardHeader)
  });

  // State para controlar bypass de cache (timestamp para forçar refetch)
  const [bypassCacheTimestamp, setBypassCacheTimestamp] = useState<number | null>(null);

  // Fetch users with backend pagination and filtering
  const {
    data: usersResponse,
    isLoading: usersLoading,
    isFetching: usersFetching,
    error: usersError,
    refetch: refetchUsers,
  } = useQuery({
    queryKey: ["admin", "users", currentPage, filterStatus, filterOcupacao, filterSecretaria, filterPermission, searchTerm, bypassCacheTimestamp],
    queryFn: async ({ queryKey }) => {
      // Extrair timestamp da queryKey para saber se deve fazer bypass
      const timestamp = queryKey[queryKey.length - 1] as number | null;
      const shouldBypassCache = timestamp !== null;

      // Construir query params (seguindo padrão de participants)
      const params = new URLSearchParams();
      params.append("page", currentPage.toString());
      params.append("page_size", pageSize.toString());

      // Filtro de status ativo/inativo
      if (filterStatus && filterStatus !== "todos") {
        params.append("active", filterStatus === "active" ? "true" : "false");
      }

      // Filtro de ocupação (valor direto do backend)
      if (filterOcupacao && filterOcupacao !== "todas") {
        params.append("ocupacao", filterOcupacao);
      }

      // Filtro de secretaria (valor direto do backend)
      if (filterSecretaria && filterSecretaria !== "todas") {
        params.append("secretaria", filterSecretaria);
      }

      // Filtro de permissão (valor direto: super_admin/admin/user)
      if (filterPermission && filterPermission !== "todas") {
        params.append("permission", filterPermission);
      }

      // Busca por CPF ou nome
      if (searchTerm) {
        params.append("search", searchTerm);
      }

      // Bypass cache se solicitado
      if (shouldBypassCache) {
        params.append("bypass_cache", "true");
      }

      const url = `/api/proxy/api/v1/admin/users?${params.toString()}`;
      const response = await fetch(url, { cache: "no-store" });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API Error ${response.status}: ${errorText}`);
      }

      // Reset bypass cache após uso
      if (shouldBypassCache) {
        setBypassCacheTimestamp(null);
      }

      return response.json();
    },
    retry: false, // Don't retry on 403
    staleTime: 5 * 60 * 1000, // 5 minutos (igual ao padrão da página principal)
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos (evita piscar)
  });

  const users = Array.isArray(usersResponse?.data) ? usersResponse.data : [];
  const meta = usersResponse?.meta ?? {
    page: 1,
    page_size: pageSize,
    total_pages: 1,
    total_rows: 0,
    cache_hit: false,
  };
  const filterOptions = usersResponse?.filters ?? null;

  // Fetch available IDs
  const {
    data: availableIds,
    isLoading: idsLoading,
  } = useQuery({
    queryKey: ["admin", "available-ids"],
    queryFn: () => apiService.getAvailableIds(),
    retry: false,
  });

  // Upsert user mutation (create or update)
  const upsertUserMutation = useMutation({
    mutationFn: ({ cpf, data }: { cpf: string; data: Omit<CreateUserRequest, "cpf"> }) =>
      apiService.upsertUser(cpf, data),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

      const isUpdate = editingUser !== null;
      toast.success(isUpdate ? "Usuário atualizado com sucesso!" : "Usuário criado com sucesso!", {
        description: `CPF ${data.cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")} ${isUpdate ? "foi atualizado" : "adicionado ao sistema"}`,
      });

      // Voltar para tab de usuários
      setActiveTab("users");
      setEditingUser(null);
    },
    onError: (error: Error) => {
      toast.error("Erro ao salvar usuário", {
        description: error.message,
      });
    },
  });

  // Toggle user active status mutation
  const toggleActiveMutation = useMutation({
    mutationFn: ({ cpf, active }: { cpf: string; active: boolean }) =>
      apiService.upsertUser(cpf, { active, is_update: true } as any),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      const action = variables.active ? "ativado" : "desativado";
      toast.success(`Usuário ${action}`, {
        description: `CPF ${variables.cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")} foi ${action} com sucesso`,
      });
    },
    onError: (error: Error) => {
      toast.error("Erro ao alterar status do usuário", {
        description: error.message,
      });
    },
  });

  // Handle page change
  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
  };

  // Reset page when filters change
  const handleFilterChange = () => {
    setCurrentPage(1); // Resetar para primeira página
  };

  // Sanitize search input (remove special chars and trim)
  const sanitizeSearchInput = (input: string): string => {
    return input
      .replace(/[.\-]/g, "") // Remove pontos e hífens (útil para CPF)
      .trim(); // Remove espaços em branco no início e fim
  };

  // Handle search button click
  const handleSearch = () => {
    const sanitized = sanitizeSearchInput(searchInput);
    setSearchTerm(sanitized);
    setCurrentPage(1); // Reset to page 1
  };

  // Handle search input keypress (Enter to search)
  const handleSearchKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  // Redirect if not admin (403 error)
  useEffect(() => {
    if (usersError && usersError.message.includes("403")) {
      router.push("/");
    }
  }, [usersError, router]);

  // Handle edit - switch to form tab
  const handleEdit = (user: UserAccessRecord) => {
    setEditingUser(user);
    setActiveTab("form");
  };

  // Handle create - switch to form tab
  const handleCreate = () => {
    setEditingUser(null);
    setActiveTab("form");
  };

  // Handle cancel - go back to users tab
  const handleCancel = () => {
    setEditingUser(null);
    setActiveTab("users");
  };

  // Handle submit
  const handleSubmit = (data: CreateUserRequest | UpdateUserRequest) => {
    const isUpdate = editingUser !== null;
    const cpf = isUpdate ? editingUser.cpf : (data as CreateUserRequest).cpf;
    const userData = {
      ...(isUpdate ? data : { ...data, cpf: undefined }),
      is_update: isUpdate, // Indica ao backend se é atualização intencional
    };
    upsertUserMutation.mutate({ cpf, data: userData as Omit<CreateUserRequest, "cpf"> });
  };

  // Handle refresh with cache bypass
  const handleRefreshWithBypass = () => {
    toast.info("Atualizando lista (forçando refresh do cache)...");
    setBypassCacheTimestamp(Date.now());
  };

  // Loading state with skeletons
  if (usersLoading || idsLoading || currentUserLoading) {
    return (
      <div className="space-y-6">
        {/* Header skeleton */}
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-10 w-80 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="flex gap-2">
            <Skeleton className="h-9 w-24" />
            <Skeleton className="h-9 w-32" />
          </div>
        </div>

        {/* Stats skeleton */}
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-lg border bg-card p-4">
              <Skeleton className="h-4 w-32 mb-2" />
              <Skeleton className="h-8 w-16" />
            </div>
          ))}
        </div>

        {/* Filter skeleton */}
        <Skeleton className="h-9 w-48" />

        {/* Table skeleton */}
        <UserTableSkeleton rows={10} />
      </div>
    );
  }

  // Error state (other than 403)
  if (usersError && !usersError.message.includes("403")) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Erro ao carregar dados: {usersError.message}
        </AlertDescription>
      </Alert>
    );
  }

  // No data state
  if (!availableIds || !currentUser || !meta) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          setActiveTab(value as "users" | "form");
          // Limpar estado de edição quando voltar para tab de usuários
          if (value === "users") {
            setEditingUser(null);
          }
        }}
        className="w-full"
      >
        <TabsList className="grid w-full grid-cols-2 mb-8 h-auto p-1 bg-muted">
          <TabsTrigger
            value="users"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground py-3"
          >
            <Users className="h-4 w-4 mr-2" />
            Usuários
          </TabsTrigger>
          <TabsTrigger
            value="form"
            className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground py-3"
          >
            <UserCog className="h-4 w-4 mr-2" />
            {editingUser ? "Editar Usuário" : "Novo Usuário"}
          </TabsTrigger>
        </TabsList>

        {/* Users Tab */}
        <TabsContent value="users" className="space-y-6">
          {/* Stats */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Total de Usuários
              </div>
              <div className="text-2xl font-bold mt-2">{meta.total_rows || 0}</div>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Admins
              </div>
              <div className="text-2xl font-bold mt-2">
                {users.filter((u: UserAccessRecord) => u.is_admin).length || 0}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                (nesta página)
              </div>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Super Admins
              </div>
              <div className="text-2xl font-bold mt-2">
                {users.filter((u: UserAccessRecord) => u.is_super_admin).length || 0}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                (nesta página)
              </div>
            </div>
          </div>

          {/* Filters */}
          <Card className="relative">
            <CardHeader className="pb-3 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Filter className="h-4 w-4" />
                Filtros
              </CardTitle>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setFilterOcupacao("");
                    setFilterSecretaria("");
                    setFilterPermission("");
                    setFilterStatus("");
                    setSearchInput("");
                    setSearchTerm("");
                    handleFilterChange();
                  }}
                  className="h-8 text-xs"
                  disabled={usersFetching}
                >
                  Limpar Filtros
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleRefreshWithBypass}
                  disabled={usersFetching}
                  className="h-8 text-xs"
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${usersFetching ? "animate-spin" : ""}`} />
                  Atualizar
                </Button>
              </div>
            </CardHeader>
            <CardContent className="pt-0 space-y-4">
              {/* Busca */}
              <div className="flex gap-2">
                <Input
                  placeholder="Buscar por CPF ou nome..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyPress={handleSearchKeyPress}
                  disabled={usersFetching}
                  className="flex-1"
                />
                <Button
                  onClick={handleSearch}
                  disabled={usersFetching}
                  size="default"
                >
                  <Search className="h-4 w-4 mr-2" />
                  Buscar
                </Button>
              </div>

              {/* Filtros */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                {/* Ocupação */}
                <VirtualizedSelect
                  value={filterOcupacao || "todas"}
                  onSelect={(value) => {
                    setFilterOcupacao(value === "todas" ? "" : value);
                    handleFilterChange();
                  }}
                  disabled={usersFetching}
                  placeholder="Ocupação"
                  defaultLabel="Todas as Ocupações"
                  options={filterOptions?.ocupacoes || []}
                />

                {/* Secretaria */}
                <VirtualizedSelect
                  value={filterSecretaria || "todas"}
                  onSelect={(value) => {
                    setFilterSecretaria(value === "todas" ? "" : value);
                    handleFilterChange();
                  }}
                  disabled={usersFetching}
                  placeholder="Secretaria"
                  defaultLabel="Todas as Secretarias"
                  options={filterOptions?.secretarias || []}
                />

                {/* Permissão */}
                <VirtualizedSelect
                  value={filterPermission || "todas"}
                  onSelect={(value) => {
                    setFilterPermission(value === "todas" ? "" : value);
                    handleFilterChange();
                  }}
                  disabled={usersFetching}
                  placeholder="Permissão"
                  defaultLabel="Todas as Permissões"
                  options={filterOptions?.permissions || []}
                />

                {/* Status */}
                <VirtualizedSelect
                  value={filterStatus || "todos"}
                  onSelect={(value) => {
                    setFilterStatus(value === "todos" ? "" : value);
                    handleFilterChange();
                  }}
                  disabled={usersFetching}
                  placeholder="Status"
                  defaultLabel="Todos os Status"
                  options={
                    filterOptions?.status_ativo?.map((opt: any) => ({
                      id: opt.id === "True" ? "active" : "inactive",
                      label: opt.id === "True" ? "Ativo" : "Inativo",
                    })) || []
                  }
                />
              </div>

              {/* Results count */}
              <div className="text-sm text-muted-foreground">
                Mostrando {users.length} de {meta.total_rows || 0} usuários
              </div>
            </CardContent>
          </Card>

          {/* Users table */}
          <UserTable
            users={users}
            availableIds={availableIds}
            currentUserCpf={currentUser.cpf}
            meta={meta}
            onEdit={handleEdit}
            onToggleActive={(cpf, currentActive) => {
              const action = currentActive ? "desativar" : "ativar";
              if (confirm(`Tem certeza que deseja ${action} este usuário?\n\nEsta ação pode ser revertida posteriormente.`)) {
                toggleActiveMutation.mutate({ cpf, active: !currentActive });
              }
            }}
            onPageChange={handlePageChange}
            isToggling={toggleActiveMutation.isPending}
            isLoading={usersFetching}
          />
        </TabsContent>

        {/* Form Tab */}
        <TabsContent value="form" className="space-y-6">
          <UserForm
            availableIds={availableIds}
            currentUser={currentUser}
            user={editingUser ?? undefined}
            onSubmit={handleSubmit}
            onCancel={handleCancel}
            isLoading={upsertUserMutation.isPending}
            error={upsertUserMutation.error?.message}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
