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
import { Plus, RefreshCw, AlertCircle, Users, UserCog } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function AdminPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"users" | "form">("users");
  const [editingUser, setEditingUser] = useState<UserAccessRecord | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  // Fetch current user
  const {
    data: currentUser,
    isLoading: currentUserLoading,
  } = useQuery({
    queryKey: ["admin", "me"],
    queryFn: () => apiService.getCurrentUser(),
    retry: false,
  });

  // Fetch users
  const {
    data: users,
    isLoading: usersLoading,
    error: usersError,
    refetch: refetchUsers,
  } = useQuery({
    queryKey: ["admin", "users", showInactive],
    queryFn: () => apiService.getUsers(showInactive ? false : true), // active_only parameter
    retry: false, // Don't retry on 403
  });

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
    const cpf = editingUser ? editingUser.cpf : (data as CreateUserRequest).cpf;
    const userData = editingUser ? data : { ...data, cpf: undefined };
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
          {/* Action buttons */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button
                variant={showInactive ? "default" : "outline"}
                size="sm"
                onClick={() => setShowInactive(!showInactive)}
              >
                {showInactive ? "Exibir apenas ativos" : "Exibir inativos também"}
              </Button>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  refetchUsers();
                  toast.info("Atualizando lista de usuários...");
                }}
                disabled={usersLoading}
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${usersLoading ? "animate-spin" : ""}`} />
                Atualizar
              </Button>
              <Button
                onClick={handleCreate}
                size="sm"
              >
                <Plus className="h-4 w-4 mr-2" />
                Novo Usuário
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Total de Usuários
              </div>
              <div className="text-2xl font-bold mt-2">{users.length}</div>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Admins
              </div>
              <div className="text-2xl font-bold mt-2">
                {users.filter((u) => u.is_admin).length}
              </div>
            </div>
            <div className="rounded-lg border bg-card p-4">
              <div className="text-sm font-medium text-muted-foreground">
                Super Admins
              </div>
              <div className="text-2xl font-bold mt-2">
                {users.filter((u) => u.is_super_admin).length}
              </div>
            </div>
          </div>

          {/* Users table */}
          <UserTable
            users={users}
            availableIds={availableIds}
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
