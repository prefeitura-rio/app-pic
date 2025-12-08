"use client";

import { useState } from "react";
import { UserAccessRecord, AvailableIds } from "@/app/types";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Edit2, Power, CheckCircle, XCircle, Shield, Crown, ChevronLeft, ChevronRight } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";

interface UserTableProps {
  users: UserAccessRecord[];
  availableIds: AvailableIds;
  currentUserCpf: string; // CPF do usuário logado
  onEdit: (user: UserAccessRecord) => void;
  onToggleActive: (cpf: string, currentActive: boolean) => void;
  isToggling: boolean;
}

export function UserTable({
  users,
  availableIds,
  currentUserCpf,
  onEdit,
  onToggleActive,
  isToggling,
}: UserTableProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 100;

  // Paginação client-side
  const totalPages = Math.ceil(users.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const paginatedUsers = users.slice(startIndex, endIndex);
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
    if (user.id_cap_list?.length) {
      counts.push(`${user.id_cap_list.length} CAPs`);
    }
    if (user.id_cas_list?.length) {
      counts.push(`${user.id_cas_list.length} CAS`);
    }
    if (user.id_clinica_familia_list?.length) {
      counts.push(`${user.id_clinica_familia_list.length} Clínicas`);
    }

    return counts.length > 0 ? counts.join(", ") : "Sem permissões específicas";
  };

  if (users.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-12 text-center">
        <p className="text-muted-foreground">Nenhum usuário encontrado</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Tabela com altura fixa e scroll - mesmo estilo da VirtualizedParticipantTable */}
      <div className="rounded-lg border overflow-hidden h-[600px] bg-card flex flex-col">
        {/* Header Estático */}
        <div className="bg-muted border-b shrink-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[12%]">CPF</TableHead>
                <TableHead className="w-[15%]">Nome</TableHead>
                <TableHead className="w-[12%]">Ocupação</TableHead>
                <TableHead className="w-[12%]">Secretaria</TableHead>
                <TableHead className="w-[10%]">Tipo</TableHead>
                <TableHead className="w-[15%]">Permissões</TableHead>
                <TableHead className="w-[8%]">Status</TableHead>
                <TableHead className="w-[10%]">Criado</TableHead>
                <TableHead className="w-[6%] text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
          </Table>
        </div>

        {/* Área com Scroll */}
        <div className="flex-1 overflow-y-auto" style={{ minHeight: 0 }}>
          <Table>
            <TableBody>
              {paginatedUsers.map((user) => (
                <TableRow key={user.cpf} className="hover:bg-muted/50">
                  {/* CPF */}
                  <TableCell className="w-[12%] font-mono text-sm">
                    {formatCPF(user.cpf)}
                  </TableCell>

                  {/* Nome */}
                  <TableCell className="w-[15%]">
                    <div className="truncate">
                      {user.nome || "—"}
                    </div>
                  </TableCell>

                  {/* Ocupação */}
                  <TableCell className="w-[12%]">
                    <div className="text-sm text-muted-foreground truncate">
                      {user.ocupacao || "—"}
                    </div>
                  </TableCell>

                  {/* Secretaria */}
                  <TableCell className="w-[12%]">
                    <div className="text-sm text-muted-foreground truncate">
                      {user.secretaria || "—"}
                    </div>
                  </TableCell>

                  {/* Type */}
                  <TableCell className="w-[10%]">
                    <div className="flex gap-1">
                      {user.is_super_admin && (
                        <Badge variant="destructive" className="gap-1">
                          <Crown className="h-3 w-3" />
                          Super Admin
                        </Badge>
                      )}
                      {user.is_admin && !user.is_super_admin && (
                        <Badge variant="default" className="gap-1">
                          <Shield className="h-3 w-3" />
                          Admin
                        </Badge>
                      )}
                      {!user.is_admin && !user.is_super_admin && (
                        <Badge variant="secondary">Usuário</Badge>
                      )}
                    </div>
                  </TableCell>

                  {/* Permissions summary */}
                  <TableCell className="w-[15%]">
                    <div className="text-sm text-muted-foreground truncate">
                      {getPermissionsSummary(user)}
                    </div>
                  </TableCell>

                  {/* Status */}
                  <TableCell className="w-[8%]">
                    {user.active ? (
                      <Badge variant="outline" className="gap-1 text-green-600">
                        <CheckCircle className="h-3 w-3" />
                        Ativo
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="gap-1 text-red-600">
                        <XCircle className="h-3 w-3" />
                        Inativo
                      </Badge>
                    )}
                  </TableCell>

                  {/* Created */}
                  <TableCell className="w-[10%] text-sm text-muted-foreground">
                    {formatDistanceToNow(new Date(user.created_at), {
                      addSuffix: true,
                      locale: ptBR,
                    })}
                  </TableCell>

                  {/* Actions */}
                  <TableCell className="w-[6%] text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onEdit(user)}
                        disabled={user.is_super_admin || user.cpf === currentUserCpf}
                        title={
                          user.is_super_admin
                            ? "Super admins não podem ser editados"
                            : user.cpf === currentUserCpf
                            ? "Você não pode editar suas próprias permissões"
                            : "Editar usuário"
                        }
                      >
                        <Edit2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onToggleActive(user.cpf, user.active)}
                        disabled={isToggling || user.is_super_admin || user.cpf === currentUserCpf}
                        title={
                          user.is_super_admin
                            ? "Super admins não podem ser desativados"
                            : user.cpf === currentUserCpf
                            ? "Você não pode alterar seu próprio status"
                            : user.active
                            ? "Desativar usuário"
                            : "Ativar usuário"
                        }
                      >
                        <Power className={`h-4 w-4 ${user.active ? "text-orange-600" : "text-green-600"}`} />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Paginação */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {startIndex + 1} - {Math.min(endIndex, users.length)} de {users.length} usuários
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="h-4 w-4" />
              Anterior
            </Button>

            <span className="text-sm px-2">
              Página {currentPage} de {totalPages}
            </span>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
            >
              Próxima
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
