"use client";

import { memo, useRef, useCallback } from "react";
import { UserAccessRecord, AvailableIds, PaginationMeta } from "@/app/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Edit2, Power, CheckCircle, XCircle, Shield, Crown, ChevronLeft, ChevronRight, Users } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";

interface UserTableProps {
  users: UserAccessRecord[];
  availableIds: AvailableIds;
  currentUserCpf: string; // CPF do usuário logado
  currentUserIsSuperAdmin: boolean; // Se o usuário logado é super admin
  meta: PaginationMeta; // Metadados de paginação do backend
  onEdit: (user: UserAccessRecord) => void;
  onToggleActive: (cpf: string, currentActive: boolean) => void;
  onPageChange: (page: number) => void; // Callback para mudança de página
  isToggling: boolean;
  isLoading?: boolean;
  pageSize?: number;
  selectedCpfs?: Set<string>; // CPFs selecionados para ações em batch
  onToggleSelect?: (cpf: string) => void; // Callback para toggle de seleção
}

const UserTableComponent = ({
  users,
  availableIds,
  currentUserCpf,
  currentUserIsSuperAdmin,
  meta,
  onEdit,
  onToggleActive,
  onPageChange,
  isToggling,
  isLoading = false,
  pageSize = 100,
  selectedCpfs = new Set(),
  onToggleSelect,
}: UserTableProps) => {
  const headerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Sincroniza o scroll horizontal do header com a lista
  const handleListScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    if (headerRef.current) {
      headerRef.current.scrollLeft = e.currentTarget.scrollLeft;
    }
  }, []);
  const formatCPF = (cpf: string) => {
    return cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  };

  const getPermissionsSummary = (user: UserAccessRecord) => {
    const counts = [];

    if (user.id_cras_list?.length) {
      counts.push(`${user.id_cras_list.length} CRAS`);
    }
    if (user.id_escola_list?.length) {
      counts.push(`${user.id_escola_list.length} Escolas`);
    }
    if (user.id_cre_list?.length) {
      counts.push(`${user.id_cre_list.length} CREs`);
    }
    if (user.id_ap_list?.length) {
      counts.push(`${user.id_ap_list.length} APs`);
    }
    if (user.id_cas_list?.length) {
      counts.push(`${user.id_cas_list.length} CAS`);
    }
    if (user.id_clinica_familia_list?.length) {
      counts.push(`${user.id_clinica_familia_list.length} Clínicas`);
    }

    return counts.length > 0 ? counts.join(", ") : "Sem permissões específicas";
  };

  // Largura mínima total da tabela
  const minTableWidth = 1195;

  if (users.length === 0) {
    return (
      <Card className="border-2 border-dashed">
        <CardContent className="py-12">
          <div className="text-center text-muted-foreground">
            <Users className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-medium">Nenhum usuário encontrado</p>
            <p className="text-sm mt-2">
              Tente ajustar os filtros ou termo de busca
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-2 relative">
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Users className="h-5 w-5 text-primary" />
          Lista de Usuários
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Tabela com altura fixa e scroll - mesmo estilo da VirtualizedParticipantTable */}
        <div className="rounded-lg border overflow-hidden h-[700px] bg-card flex flex-col relative">
          {/* Loading overlay */}
          {isLoading && <div className="loading-overlay" />}

          {/* Header - scrollável horizontalmente, sincronizado com a lista */}
          <div
            ref={headerRef}
            className="overflow-x-hidden shrink-0"
          >
            <div
              className="flex items-center bg-muted/50 border-b font-medium text-sm text-muted-foreground h-11"
              style={{ minWidth: minTableWidth }}
            >
              {onToggleSelect && (
                <div style={{ width: 40, minWidth: 40 }} className="px-2 text-center" />
              )}
              <div style={{ width: 45, minWidth: 45 }} className="px-2 text-center text-muted-foreground/70">#</div>
              <div style={{ flex: '1 1 0%', minWidth: 110 }} className="px-2">CPF</div>
              <div style={{ flex: '1.5 1 0%', minWidth: 140 }} className="px-2">Nome</div>
              <div style={{ flex: '1.3 1 0%', minWidth: 150 }} className="px-2">Email</div>
              <div style={{ flex: '1 1 0%', minWidth: 100 }} className="px-2">Ocupação</div>
              <div style={{ flex: '1 1 0%', minWidth: 100 }} className="px-2">Secretaria</div>
              <div style={{ flex: '0.8 1 0%', minWidth: 90 }} className="px-2">Tipo</div>
              <div style={{ flex: '1.3 1 0%', minWidth: 140 }} className="px-2">Permissões</div>
              <div style={{ flex: '0.6 1 0%', minWidth: 70 }} className="px-2 text-center">Status</div>
              <div style={{ flex: '0.8 1 0%', minWidth: 80 }} className="px-2">Criado</div>
              <div style={{ flex: '0.5 1 0%', minWidth: 70 }} className="px-2 text-center">Ações</div>
            </div>
          </div>

          {/* Área com Scroll sincronizado */}
          <div
            ref={listRef}
            className="flex-1 overflow-auto"
            onScroll={handleListScroll}
          >
            <div style={{ minWidth: minTableWidth }}>
              {users.map((user, index) => (
                <div
                  key={user.cpf}
                  className={`flex items-center border-b hover:bg-muted/50 transition-colors text-sm ${
                    selectedCpfs.has(user.cpf) ? "bg-primary/5" : ""
                  }`}
                  style={{ minHeight: 56 }}
                >
                  {/* Checkbox */}
                  {onToggleSelect && (
                    <div style={{ width: 40, minWidth: 40 }} className="px-2 text-center">
                      <Checkbox
                        checked={selectedCpfs.has(user.cpf)}
                        onCheckedChange={() => onToggleSelect(user.cpf)}
                        disabled={user.cpf === currentUserCpf}
                      />
                    </div>
                  )}

                  {/* Index */}
                  <div style={{ width: 45, minWidth: 45 }} className="px-2 text-center text-xs text-muted-foreground/50">
                    {index + 1}
                  </div>

                  {/* CPF */}
                  <div style={{ flex: '1 1 0%', minWidth: 110 }} className="px-2 font-mono">
                    {formatCPF(user.cpf)}
                  </div>

                  {/* Nome */}
                  <div style={{ flex: '1.5 1 0%', minWidth: 140 }} className="px-2 font-medium">
                    <span className="line-clamp-2">{user.nome || "—"}</span>
                  </div>

                  {/* Email */}
                  <div style={{ flex: '1.3 1 0%', minWidth: 150 }} className="px-2 text-muted-foreground">
                    <span className="line-clamp-1 text-xs">{user.email || "—"}</span>
                  </div>

                  {/* Ocupação */}
                  <div style={{ flex: '1 1 0%', minWidth: 100 }} className="px-2 text-muted-foreground">
                    <span className="line-clamp-2">{user.ocupacao || "—"}</span>
                  </div>

                  {/* Secretaria */}
                  <div style={{ flex: '1 1 0%', minWidth: 100 }} className="px-2 text-muted-foreground">
                    <span className="line-clamp-2">{user.secretaria || "—"}</span>
                  </div>

                  {/* Type */}
                  <div style={{ flex: '0.8 1 0%', minWidth: 90 }} className="px-2">
                    <div className="flex gap-1 flex-wrap">
                      {user.is_super_admin && (
                        <Badge variant="destructive" className="gap-1 text-xs h-5 px-1.5">
                          <Crown className="h-3 w-3" />
                          Super
                        </Badge>
                      )}
                      {user.is_admin && !user.is_super_admin && (
                        <Badge variant="default" className="gap-1 text-xs h-5 px-1.5">
                          <Shield className="h-3 w-3" />
                          Admin
                        </Badge>
                      )}
                      {!user.is_admin && !user.is_super_admin && (
                        <Badge variant="secondary" className="text-xs h-5 px-1.5">Usuário</Badge>
                      )}
                    </div>
                  </div>

                  {/* Permissions summary */}
                  <div style={{ flex: '1.3 1 0%', minWidth: 140 }} className="px-2 text-muted-foreground">
                    <span className="line-clamp-2">{getPermissionsSummary(user)}</span>
                  </div>

                  {/* Status */}
                  <div style={{ flex: '0.6 1 0%', minWidth: 70 }} className="px-2 text-center">
                    {user.active ? (
                      <Badge variant="outline" className="gap-1 text-green-600 text-xs h-5 px-1.5">
                        <CheckCircle className="h-3 w-3" />
                        Ativo
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="gap-1 text-red-600 text-xs h-5 px-1.5">
                        <XCircle className="h-3 w-3" />
                        Inativo
                      </Badge>
                    )}
                  </div>

                  {/* Created */}
                  <div style={{ flex: '0.8 1 0%', minWidth: 80 }} className="px-2 text-muted-foreground text-xs">
                    {formatDistanceToNow(new Date(user.created_at), {
                      addSuffix: true,
                      locale: ptBR,
                    })}
                  </div>

                  {/* Actions */}
                  <div style={{ flex: '0.5 1 0%', minWidth: 70 }} className="px-2 text-center">
                    {(() => {
                      // Determinar se pode editar este usuário
                      // Super admins não podem ser editados por ninguém
                      // Admins só podem ser editados por super admins
                      // Usuários podem ser editados por admins e super admins
                      const canEdit = (() => {
                        if (user.cpf === currentUserCpf) return false; // Não pode editar a si mesmo
                        if (user.is_super_admin) return false; // Super admins não editáveis
                        if (user.is_admin && !currentUserIsSuperAdmin) return false; // Admins só editáveis por super admin
                        return true;
                      })();

                      const editTitle = (() => {
                        if (user.cpf === currentUserCpf) return "Você não pode editar suas próprias permissões";
                        if (user.is_super_admin) return "Super admins não podem ser editados";
                        if (user.is_admin && !currentUserIsSuperAdmin) return "Admins só podem ser editados por super admins";
                        return "Editar usuário";
                      })();

                      // Para toggle active (desativar):
                      // Mesma regra de edição
                      const canToggle = canEdit && !isToggling;

                      const toggleTitle = (() => {
                        if (user.cpf === currentUserCpf) return "Você não pode alterar seu próprio status";
                        if (user.is_super_admin) return "Super admins não podem ser desativados";
                        if (user.is_admin && !currentUserIsSuperAdmin) return "Admins só podem ser desativados por super admins";
                        return user.active ? "Desativar usuário" : "Ativar usuário";
                      })();

                      return (
                        <div className="flex justify-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onEdit(user)}
                            disabled={!canEdit}
                            title={editTitle}
                          >
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onToggleActive(user.cpf, user.active)}
                            disabled={!canToggle}
                            title={toggleTitle}
                          >
                            <Power className={`h-4 w-4 ${user.active ? "text-orange-600" : "text-green-600"}`} />
                          </Button>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Pagination - Footer do Card */}
        {meta.total_pages > 1 && (
          <div className="flex items-center justify-between pt-4 border-t">
            <p className="text-sm text-muted-foreground">
              Mostrando <span className="font-medium">{((meta.page - 1) * pageSize) + 1}</span> a <span className="font-medium">{((meta.page - 1) * pageSize) + users.length}</span> de <span className="font-medium">{meta.total_rows.toLocaleString('pt-BR')}</span> registros
            </p>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(Math.max(1, meta.page - 1))}
                disabled={meta.page === 1 || isLoading}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Anterior
              </Button>

              {/* Page Numbers */}
              {(() => {
                const pages: number[] = [];
                const totalPages = meta.total_pages;
                const currentPage = meta.page;

                // Mostrar até 5 páginas
                let startPage = Math.max(1, currentPage - 2);
                let endPage = Math.min(totalPages, startPage + 4);

                // Ajustar se estiver no final
                if (endPage - startPage < 4) {
                  startPage = Math.max(1, endPage - 4);
                }

                for (let i = startPage; i <= endPage; i++) {
                  pages.push(i);
                }

                return pages.map((page) => (
                  <Button
                    key={page}
                    variant={page === currentPage ? "default" : "outline"}
                    size="sm"
                    className="w-9"
                    onClick={() => onPageChange(page)}
                    disabled={isLoading}
                  >
                    {page}
                  </Button>
                ));
              })()}

              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(Math.min(meta.total_pages, meta.page + 1))}
                disabled={meta.page === meta.total_pages || isLoading}
              >
                Próxima
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Exportar com React.memo para evitar re-renders quando props não mudarem
export const UserTable = memo(UserTableComponent);

UserTable.displayName = "UserTable";
