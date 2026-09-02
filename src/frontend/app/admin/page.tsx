"use client";

import { useEffect, useState, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiService } from "@/app/services/api";
import { UserAccessRecord, CreateUserRequest, UpdateUserRequest } from "@/app/types";
import { UserTable } from "@/app/components/admin/UserTable";
import { UserForm } from "@/app/components/admin/UserForm";
import { UserTableSkeleton } from "@/app/components/admin/UserTableSkeleton";
import { ImportTab } from "@/app/components/admin/ImportTab";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/app/components/ui/tabs";
import { AlertCircle, Users, UserCog, Search, X, RefreshCw, Filter, Upload, Download, Trash2, Edit, CheckCircle } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"users" | "form" | "import">("users");
  const [editingUser, setEditingUser] = useState<UserAccessRecord | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 100;

  // Filter states
  const [filterOcupacao, setFilterOcupacao] = useState("");
  const [filterSecretaria, setFilterSecretaria] = useState("");
  const [filterPermission, setFilterPermission] = useState<string>(""); // empty = all (super_admin/admin/user)
  const [filterStatus, setFilterStatus] = useState<string>(""); // empty = all
  const [filterSecretariaAcesso, setFilterSecretariaAcesso] = useState<string>(""); // empty = all
  const [searchInput, setSearchInput] = useState(""); // Input do usuário
  const [searchTerm, setSearchTerm] = useState(""); // Termo de busca ativo (enviado ao backend)

  // Selection state for batch actions
  const [selectedCpfs, setSelectedCpfs] = useState<Set<string>>(new Set());

  // Users to pass to ImportTab for batch update
  const [usersForImport, setUsersForImport] = useState<UserAccessRecord[]>([]);

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

  // Ref para controlar bypass de cache (não afeta o query key)
  const bypassCacheRef = useRef(false);

  // Fetch users with backend pagination and filtering
  const {
    data: usersResponse,
    isLoading: usersLoading,
    isFetching: usersFetching,
    error: usersError,
    refetch: refetchUsers,
  } = useQuery({
    queryKey: ["admin", "users", currentPage, filterStatus, filterOcupacao, filterSecretaria, filterPermission, filterSecretariaAcesso, searchTerm],
    queryFn: async () => {
      const shouldBypassCache = bypassCacheRef.current;
      bypassCacheRef.current = false;

      const activeOnly = filterStatus === "active" ? true : filterStatus === "inactive" ? false : undefined;

      return apiService.getUsers({
        page: currentPage,
        pageSize,
        activeOnly,
        search: searchTerm || undefined,
        ocupacao: filterOcupacao && filterOcupacao !== "todas" ? filterOcupacao : undefined,
        secretaria: filterSecretaria && filterSecretaria !== "todas" ? filterSecretaria : undefined,
        permission: filterPermission && filterPermission !== "todas" ? filterPermission : undefined,
        secretariasAcesso: filterSecretariaAcesso && filterSecretariaAcesso !== "todas" ? [filterSecretariaAcesso] : undefined,
        bypassCache: shouldBypassCache || undefined,
      });
    },
    retry: false, // Don't retry on 403
    staleTime: 0, // Sempre considera stale para garantir dados frescos após invalidação
    refetchOnMount: true, // Refetch quando a aba/componente monta
    refetchOnWindowFocus: false, // Não refetch ao focar a janela (evita requests desnecessários)
  });

  // Memoizado para manter referência estável do array vazio quando ainda não há dados,
  // evitando recomputar os useMemo abaixo (activatableSelectedCpfs, editableSelectedCpfs) a cada render.
  const users = useMemo(
    () => (Array.isArray(usersResponse?.data) ? usersResponse.data : []),
    [usersResponse]
  );
  const meta = usersResponse?.meta ?? {
    page: 1,
    page_size: pageSize,
    total_pages: 1,
    total_rows: 0,
    cache_hit: false,
  };
  const filterOptions = usersResponse?.filters ?? null;

  // Compute which users can be ACTIVATED by current user
  // Admin: pode ativar users e admins (não super_admin)
  // Super Admin: pode ativar todos (users, admins, super_admins)
  const activatableSelectedCpfs = useMemo(() => {
    const activatable = new Set<string>();
    const isSuperAdmin = currentUser?.is_super_admin;

    selectedCpfs.forEach((cpf) => {
      const user = users.find((u: UserAccessRecord) => u.cpf === cpf);
      if (!user || user.cpf === currentUser?.cpf) return;

      if (isSuperAdmin) {
        // Super admin pode ativar qualquer um
        activatable.add(cpf);
      } else {
        // Admin pode ativar users e admins (não super_admin)
        if (!user.is_super_admin) {
          activatable.add(cpf);
        }
      }
    });
    return activatable;
  }, [selectedCpfs, users, currentUser?.cpf, currentUser?.is_super_admin]);

  // Compute which users can be UPDATED/DEACTIVATED by current user
  // Admin: pode editar apenas users (não admins, não super_admin)
  // Super Admin: pode editar users e admins (não outros super_admins)
  const editableSelectedCpfs = useMemo(() => {
    const editable = new Set<string>();
    const isSuperAdmin = currentUser?.is_super_admin;

    selectedCpfs.forEach((cpf) => {
      const user = users.find((u: UserAccessRecord) => u.cpf === cpf);
      if (!user || user.cpf === currentUser?.cpf) return;

      if (isSuperAdmin) {
        // Super admin pode editar users e admins (não outros super_admins)
        if (!user.is_super_admin) {
          editable.add(cpf);
        }
      } else {
        // Admin pode editar apenas users (não admins, não super_admin)
        if (!user.is_admin && !user.is_super_admin) {
          editable.add(cpf);
        }
      }
    });
    return editable;
  }, [selectedCpfs, users, currentUser?.cpf, currentUser?.is_super_admin]);

  // Upsert user mutation (create or update)
  const upsertUserMutation = useMutation({
    mutationFn: ({ cpf, data }: { cpf: string; data: Omit<CreateUserRequest, "cpf"> }) =>
      apiService.upsertUser(cpf, data),
    onSuccess: (data) => {
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
      apiService.upsertUser(cpf, { active, is_update: true }),
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
    // Marcar para bypass no próximo fetch e forçar refetch
    bypassCacheRef.current = true;
    refetchUsers();
  };

  // Batch selection handlers
  const handleToggleSelect = (cpf: string) => {
    const newSelection = new Set(selectedCpfs);
    if (newSelection.has(cpf)) {
      newSelection.delete(cpf);
    } else {
      newSelection.add(cpf);
    }
    setSelectedCpfs(newSelection);
  };

  const handleSelectAll = () => {
    if (selectedCpfs.size === users.length) {
      // Deselect all
      setSelectedCpfs(new Set());
    } else {
      // Select all visible users
      setSelectedCpfs(new Set(users.map((u: UserAccessRecord) => u.cpf)));
    }
  };

  const handleClearSelection = () => {
    setSelectedCpfs(new Set());
  };

  // Batch delete mutation
  const batchDeleteMutation = useMutation({
    mutationFn: async (cpfs: string[]) => {
      // Delete users sequentially to avoid rate limiting
      for (const cpf of cpfs) {
        await apiService.deleteUser(cpf);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(`${selectedCpfs.size} usuários desativados`);
      setSelectedCpfs(new Set());
      handleRefreshWithBypass();
    },
    onError: (error: Error) => {
      toast.error("Erro ao desativar usuários", { description: error.message });
    },
  });

  // Handle batch delete (only editable users)
  const handleBatchDelete = () => {
    if (editableSelectedCpfs.size === 0) return;
    if (!confirm(`Desativar ${editableSelectedCpfs.size} usuário(s)?`)) return;
    batchDeleteMutation.mutate(Array.from(editableSelectedCpfs));
  };

  // Handle batch update (go to import tab with editable users only)
  const handleBatchUpdate = () => {
    if (editableSelectedCpfs.size === 0) return;
    // Store only editable users for import tab
    const editableUsers = users.filter((u: UserAccessRecord) => editableSelectedCpfs.has(u.cpf));
    setUsersForImport(editableUsers);
    // Switch to import tab
    setActiveTab("import");
    toast.info(`${editableUsers.length} usuários carregados para atualização`);
  };

  // Batch activate mutation
  const batchActivateMutation = useMutation({
    mutationFn: async (cpfs: string[]) => {
      for (const cpf of cpfs) {
        await apiService.upsertUser(cpf, { active: true, is_update: true });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(`${selectedCpfs.size} usuários ativados`);
      setSelectedCpfs(new Set());
      handleRefreshWithBypass();
    },
    onError: (error: Error) => {
      toast.error("Erro ao ativar usuários", { description: error.message });
    },
  });

  // Handle batch activate (only activatable users)
  const handleBatchActivate = () => {
    if (activatableSelectedCpfs.size === 0) return;
    if (!confirm(`Ativar ${activatableSelectedCpfs.size} usuário(s)?`)) return;
    batchActivateMutation.mutate(Array.from(activatableSelectedCpfs));
  };

  // Handle download users as CSV
  const handleDownloadUsers = () => {
    const dataToDownload = selectedCpfs.size > 0
      ? users.filter((u: UserAccessRecord) => selectedCpfs.has(u.cpf))
      : users;

    // CSV headers
    const headers = ["cpf", "nome", "email", "ocupacao", "secretaria", "is_admin", "is_super_admin", "active"];

    // Convert to CSV rows
    const csvRows = [
      headers.join(","),
      ...dataToDownload.map((u: UserAccessRecord) => {
        const values = [
          u.cpf,
          `"${(u.nome || "").replace(/"/g, '""')}"`,
          `"${(u.email || "").replace(/"/g, '""')}"`,
          `"${(u.ocupacao || "").replace(/"/g, '""')}"`,
          `"${(u.secretaria || "").replace(/"/g, '""')}"`,
          u.is_admin ? "true" : "false",
          u.is_super_admin ? "true" : "false",
          u.active ? "true" : "false",
        ];
        return values.join(",");
      }),
    ];

    const csvContent = csvRows.join("\n");
    const blob = new Blob(["\ufeff" + csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `usuarios_${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success(`${dataToDownload.length} usuários exportados como CSV`);
  };

  // Loading state with skeletons - só mostrar na carga inicial, não em refetch
  // Isso evita desmontar o ImportTab e perder os dados importados
  const isInitialLoading = usersLoading || currentUserLoading;
  if (isInitialLoading && !usersResponse) {
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
  if (!currentUser || !meta) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          setActiveTab(value as "users" | "form" | "import");
          // Limpar estado de edição quando voltar para tab de usuários
          if (value === "users") {
            setEditingUser(null);
          }
        }}
        className="w-full"
      >
        <TabsList className="inline-flex h-11 items-center justify-center rounded-lg bg-muted p-1 mb-8">
          <TabsTrigger
            value="users"
            className="inline-flex items-center justify-center whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm"
          >
            <Users className="h-4 w-4 mr-2" />
            Usuarios
          </TabsTrigger>
          <TabsTrigger
            value="form"
            className="inline-flex items-center justify-center whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm"
          >
            <UserCog className="h-4 w-4 mr-2" />
            {editingUser ? "Editar Usuario" : "Novo Usuario"}
          </TabsTrigger>
          <TabsTrigger
            value="import"
            className="inline-flex items-center justify-center whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm"
          >
            <Upload className="h-4 w-4 mr-2" />
            Importar
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
          <Card className="relative border-2">
            <CardHeader className="pb-4 flex flex-row items-center justify-between">
              <CardTitle className="text-2xl font-bold flex items-center gap-2">
                <Filter className="h-6 w-6" />
                Filtros e Busca
              </CardTitle>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setFilterOcupacao("");
                    setFilterSecretaria("");
                    setFilterPermission("");
                    setFilterStatus("");
                    setFilterSecretariaAcesso("");
                    setSearchInput("");
                    setSearchTerm("");
                    handleFilterChange();
                  }}
                  className="h-8 text-xs"
                  disabled={usersFetching}
                >
                  <X className="h-3 w-3 mr-1" />
                  Limpar Filtros
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRefreshWithBypass}
                  disabled={usersFetching}
                  className="h-8 text-xs"
                >
                  <RefreshCw className={`h-3 w-3 mr-1 ${usersFetching ? "animate-spin" : ""}`} />
                  Atualizar
                </Button>
              </div>
            </CardHeader>
            <CardContent className="pt-0 space-y-4">
              {/* Busca - Full Width com ícone interno */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Buscar por CPF ou nome..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="pl-10 h-11"
                  disabled={usersFetching}
                />
              </div>

              {/* Filtros */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2">
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

                {/* Acesso Protocolos */}
                <VirtualizedSelect
                  value={filterSecretariaAcesso || "todas"}
                  onSelect={(value) => {
                    setFilterSecretariaAcesso(value === "todas" ? "" : value);
                    handleFilterChange();
                  }}
                  disabled={usersFetching}
                  placeholder="Acesso Protocolos"
                  defaultLabel="Todos os Acessos"
                  options={
                    filterOptions?.secretarias_acesso_list?.map((opt) => ({
                      id: opt.id,
                      label: opt.id === "SME"
                        ? "📚 Educação"
                        : opt.id === "SMS"
                        ? "🏥 Saúde"
                        : opt.id === "SMAS"
                        ? "🤝 Assistência"
                        : opt.id,
                    })) || []
                  }
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
                    filterOptions?.status_ativo?.map((opt) => ({
                      id: opt.id === "True" ? "active" : "inactive",
                      label: opt.id === "True" ? "Ativo" : "Inativo",
                    })) || []
                  }
                />
              </div>

              {/* Results count */}
              <div className="pt-4 border-t mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <span className="font-medium">{meta.total_rows?.toLocaleString('pt-BR') || 0}</span> usuário(s) encontrado(s)
              </div>
            </CardContent>
          </Card>

          {/* Action bar */}
          <div className="flex items-center justify-between gap-4 p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center gap-4">
              {/* Select all checkbox */}
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={users.length > 0 && selectedCpfs.size === users.length}
                  onCheckedChange={handleSelectAll}
                  disabled={users.length === 0}
                />
                <span className="text-sm text-muted-foreground">
                  {selectedCpfs.size > 0
                    ? `${selectedCpfs.size} selecionado(s)`
                    : "Selecionar todos"}
                </span>
              </div>

              {/* Clear selection */}
              {selectedCpfs.size > 0 && (
                <Button variant="ghost" size="sm" onClick={handleClearSelection}>
                  <X className="h-4 w-4 mr-1" />
                  Limpar
                </Button>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2">
              {/* Download button */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadUsers}
                disabled={users.length === 0}
              >
                <Download className="h-4 w-4 mr-1" />
                {selectedCpfs.size > 0 ? `Baixar (${selectedCpfs.size})` : "Baixar Todos"}
              </Button>

              {/* Batch actions (only when selection exists) */}
              {selectedCpfs.size > 0 && (
                <>
                  {/* Atualizar - usa editableSelectedCpfs */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleBatchUpdate}
                    disabled={editableSelectedCpfs.size === 0}
                    title={editableSelectedCpfs.size === 0 ? "Nenhum usuário editável selecionado" : ""}
                  >
                    <Edit className="h-4 w-4 mr-1" />
                    Atualizar ({editableSelectedCpfs.size})
                  </Button>

                  {/* Ativar - usa activatableSelectedCpfs */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleBatchActivate}
                    disabled={batchActivateMutation.isPending || activatableSelectedCpfs.size === 0}
                    className="text-green-600 border-green-600 hover:bg-green-50"
                    title={activatableSelectedCpfs.size === 0 ? "Nenhum usuário ativável selecionado" : ""}
                  >
                    <CheckCircle className="h-4 w-4 mr-1" />
                    {batchActivateMutation.isPending ? "Ativando..." : `Ativar (${activatableSelectedCpfs.size})`}
                  </Button>

                  {/* Desativar - usa editableSelectedCpfs */}
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleBatchDelete}
                    disabled={batchDeleteMutation.isPending || editableSelectedCpfs.size === 0}
                    title={editableSelectedCpfs.size === 0 ? "Nenhum usuário desativável selecionado" : ""}
                  >
                    <Trash2 className="h-4 w-4 mr-1" />
                    {batchDeleteMutation.isPending ? "Desativando..." : `Desativar (${editableSelectedCpfs.size})`}
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Users table */}
          <UserTable
            users={users}
            currentUserCpf={currentUser.cpf}
            currentUserIsSuperAdmin={currentUser.is_super_admin}
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
            pageSize={pageSize}
            selectedCpfs={selectedCpfs}
            onToggleSelect={handleToggleSelect}
          />
        </TabsContent>

        {/* Form Tab */}
        <TabsContent value="form" className="space-y-6">
          <UserForm
            currentUser={currentUser}
            user={editingUser ?? undefined}
            onSubmit={handleSubmit}
            onCancel={handleCancel}
            isLoading={upsertUserMutation.isPending}
            error={upsertUserMutation.error?.message}
          />
        </TabsContent>

        {/* Import Tab */}
        <TabsContent value="import" className="space-y-6">
          <ImportTab
            currentUser={currentUser}
            onPermissionsApplied={handleRefreshWithBypass}
            prePopulatedUsers={usersForImport}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
