"use client";

import { useEffect, useState } from "react";
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
import { AlertCircle, Users, UserCog, Search, X, RefreshCw } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function AdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"users" | "form">("users");
  const [editingUser, setEditingUser] = useState<UserAccessRecord | null>(null);

  // Filter states
  const [filterCpf, setFilterCpf] = useState("");
  const [filterNome, setFilterNome] = useState("");
  const [filterOcupacao, setFilterOcupacao] = useState("");
  const [filterSecretaria, setFilterSecretaria] = useState("");
  const [filterPermission, setFilterPermission] = useState<string>("all"); // all, admin, super_admin, user
  const [filterStatus, setFilterStatus] = useState<string>("all"); // all, active, inactive

  // Fetch current user
  const {
    data: currentUser,
    isLoading: currentUserLoading,
  } = useQuery({
    queryKey: ["admin", "me"],
    queryFn: () => apiService.getCurrentUser(),
    retry: false,
  });

  // Fetch users (always fetch all users, filter client-side)
  const {
    data: allUsers,
    isLoading: usersLoading,
    error: usersError,
    refetch: refetchUsers,
  } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => apiService.getUsers(false, false), // active_only = false, forceRefresh = false
    retry: false, // Don't retry on 403
  });

  // Client-side filtering
  const filteredUsers = allUsers?.filter((user) => {
    // CPF filter
    if (filterCpf && !user.cpf.includes(filterCpf.replace(/\D/g, ""))) {
      return false;
    }

    // Nome filter
    if (filterNome && !user.nome?.toLowerCase().includes(filterNome.toLowerCase())) {
      return false;
    }

    // Ocupação filter
    if (filterOcupacao && !user.ocupacao?.toLowerCase().includes(filterOcupacao.toLowerCase())) {
      return false;
    }

    // Secretaria filter
    if (filterSecretaria && !user.secretaria?.toLowerCase().includes(filterSecretaria.toLowerCase())) {
      return false;
    }

    // Permission filter
    if (filterPermission !== "all") {
      if (filterPermission === "super_admin" && !user.is_super_admin) return false;
      if (filterPermission === "admin" && (!user.is_admin || user.is_super_admin)) return false;
      if (filterPermission === "user" && (user.is_admin || user.is_super_admin)) return false;
    }

    // Status filter
    if (filterStatus !== "all") {
      if (filterStatus === "active" && !user.active) return false;
      if (filterStatus === "inactive" && user.active) return false;
    }

    return true;
  }) || [];

  const users = filteredUsers;

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
      apiService.upsertUser(cpf, { active }),
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

  // Force refresh mutation
  const forceRefreshMutation = useMutation({
    mutationFn: () => apiService.getUsers(false, true), // force_refresh = true
    onSuccess: (data) => {
      queryClient.setQueryData(["admin", "users"], data);
      toast.success("Cache atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar cache", {
        description: error.message,
      });
    },
  });

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
  if (!users || !availableIds || !currentUser) {
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
              <div className="text-2xl font-bold mt-2">{allUsers?.length || 0}</div>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Admins
              </div>
              <div className="text-2xl font-bold mt-2">
                {allUsers?.filter((u) => u.is_admin).length || 0}
              </div>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Super Admins
              </div>
              <div className="text-2xl font-bold mt-2">
                {allUsers?.filter((u) => u.is_super_admin).length || 0}
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Search className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-medium">Filtros</h3>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    toast.info("Forçando atualização do cache...");
                    forceRefreshMutation.mutate();
                  }}
                  disabled={forceRefreshMutation.isPending}
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${forceRefreshMutation.isPending ? "animate-spin" : ""}`} />
                  Atualizar
                </Button>
                {(filterCpf || filterNome || filterOcupacao || filterSecretaria || filterPermission !== "all" || filterStatus !== "all") && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setFilterCpf("");
                      setFilterNome("");
                      setFilterOcupacao("");
                      setFilterSecretaria("");
                      setFilterPermission("all");
                      setFilterStatus("all");
                    }}
                  >
                    <X className="h-4 w-4 mr-2" />
                    Limpar filtros
                  </Button>
                )}
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              {/* CPF Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-cpf" className="text-xs">CPF</Label>
                <Input
                  id="filter-cpf"
                  placeholder="000.000.000-00"
                  value={filterCpf}
                  onChange={(e) => setFilterCpf(e.target.value)}
                  className="h-9"
                />
              </div>

              {/* Nome Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-nome" className="text-xs">Nome</Label>
                <Input
                  id="filter-nome"
                  placeholder="Buscar por nome..."
                  value={filterNome}
                  onChange={(e) => setFilterNome(e.target.value)}
                  className="h-9"
                />
              </div>

              {/* Ocupação Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-ocupacao" className="text-xs">Ocupação</Label>
                <Input
                  id="filter-ocupacao"
                  placeholder="Buscar por ocupação..."
                  value={filterOcupacao}
                  onChange={(e) => setFilterOcupacao(e.target.value)}
                  className="h-9"
                />
              </div>

              {/* Secretaria Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-secretaria" className="text-xs">Secretaria</Label>
                <Input
                  id="filter-secretaria"
                  placeholder="Buscar por secretaria..."
                  value={filterSecretaria}
                  onChange={(e) => setFilterSecretaria(e.target.value)}
                  className="h-9"
                />
              </div>

              {/* Permission Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-permission" className="text-xs">Permissão</Label>
                <Select value={filterPermission} onValueChange={setFilterPermission}>
                  <SelectTrigger id="filter-permission" className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="super_admin">Super Admin</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="user">Usuário</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Status Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-status" className="text-xs">Status</Label>
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger id="filter-status" className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="active">Ativo</SelectItem>
                    <SelectItem value="inactive">Inativo</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Results count */}
            <div className="mt-4 text-sm text-muted-foreground">
              Mostrando {users.length} de {allUsers?.length || 0} usuários
            </div>
          </div>

          {/* Users table */}
          <UserTable
            users={users}
            availableIds={availableIds}
            currentUserCpf={currentUser.cpf}
            onEdit={handleEdit}
            onToggleActive={(cpf, currentActive) => {
              const action = currentActive ? "desativar" : "ativar";
              if (confirm(`Tem certeza que deseja ${action} este usuário?\n\nEsta ação pode ser revertida posteriormente.`)) {
                toggleActiveMutation.mutate({ cpf, active: !currentActive });
              }
            }}
            isToggling={toggleActiveMutation.isPending}
          />
        </TabsContent>

        {/* Form Tab */}
        <TabsContent value="form" className="space-y-6">
          <UserForm
            availableIds={availableIds}
            currentUser={currentUser}
            user={editingUser}
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
