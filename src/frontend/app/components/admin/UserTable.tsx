"use client";

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
import { Edit2, Power, CheckCircle, XCircle, Shield, Crown } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";

interface UserTableProps {
  users: UserAccessRecord[];
  availableIds: AvailableIds;
  onEdit: (user: UserAccessRecord) => void;
  onToggleActive: (cpf: string, currentActive: boolean) => void;
  isToggling: boolean;
}

export function UserTable({
  users,
  availableIds,
  onEdit,
  onToggleActive,
  isToggling,
}: UserTableProps) {
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
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>CPF</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead>Permissões</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Criado</TableHead>
            <TableHead>Notas</TableHead>
            <TableHead className="text-right">Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => (
            <TableRow key={user.cpf}>
              {/* CPF */}
              <TableCell className="font-mono text-sm">
                {formatCPF(user.cpf)}
              </TableCell>

              {/* Type */}
              <TableCell>
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
              <TableCell>
                <div className="text-sm text-muted-foreground max-w-xs truncate">
                  {getPermissionsSummary(user)}
                </div>
              </TableCell>

              {/* Status */}
              <TableCell>
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
              <TableCell className="text-sm text-muted-foreground">
                {formatDistanceToNow(new Date(user.created_at), {
                  addSuffix: true,
                  locale: ptBR,
                })}
              </TableCell>

              {/* Notes */}
              <TableCell>
                <div className="text-sm text-muted-foreground max-w-xs truncate">
                  {user.notes || "—"}
                </div>
              </TableCell>

              {/* Actions */}
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(user)}
                  >
                    <Edit2 className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onToggleActive(user.cpf, user.active)}
                    disabled={isToggling || user.is_super_admin} // Can't deactivate super admin
                    title={user.active ? "Desativar usuário" : "Ativar usuário"}
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
  );
}
