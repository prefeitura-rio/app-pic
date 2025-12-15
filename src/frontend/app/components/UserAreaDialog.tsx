"use client";

import { useRouter } from "next/navigation";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/app/components/ui/dialog";
import { Button } from "@/app/components/ui/button";
import { User, Shield, LogOut, Mail, IdCard, Calendar, Key, Clock } from "lucide-react";

import { IdWithName } from "@/app/types";

interface UserInfo {
  // JWT fields
  name?: string | null;
  email?: string | null;
  preferred_username?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  sub?: string | null;
  iat?: number;
  exp?: number;

  // App fields (from /me or JWT enrichment)
  cpf?: string;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  permission?: string | null;
  is_admin?: boolean;
  is_super_admin?: boolean;
  active?: boolean;
  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;
}

interface UserAreaDialogProps {
  children: React.ReactNode;
  userInfo?: UserInfo | null;
}

export function UserAreaDialog({ children, userInfo }: UserAreaDialogProps) {
  const router = useRouter();

  const handleLogout = () => {
    // Just redirect to logout endpoint - it will handle Keycloak logout and redirect back to /login
    window.location.href = "/api/auth/logout";
  };

  // Formatar datas
  const formatDate = (timestamp?: number) => {
    if (!timestamp) return "Não disponível";
    return new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(timestamp * 1000));
  };

  // Calcular tempo restante
  const getTimeRemaining = (exp?: number) => {
    if (!exp) return "Não disponível";
    const now = Math.floor(Date.now() / 1000);
    const remaining = exp - now;

    if (remaining <= 0) return "Expirado";

    const hours = Math.floor(remaining / 3600);
    const minutes = Math.floor((remaining % 3600) / 60);

    if (hours > 0) {
      return `${hours}h ${minutes}min`;
    }
    return `${minutes}min`;
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[550px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Área do Usuário
          </DialogTitle>
          <DialogDescription>
            Informações da sua conta e detalhes de acesso ao sistema.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="space-y-4">
            {/* Dados Pessoais */}
            <div className="rounded-lg border p-4">
              <h4 className="flex items-center gap-2 font-semibold mb-3">
                <User className="h-4 w-4 text-primary" />
                Dados Pessoais
              </h4>
              <div className="text-sm space-y-2">
                <div className="flex items-start gap-2">
                  <User className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div className="flex-1">
                    <p className="text-xs text-muted-foreground">Nome Completo</p>
                    <p className="font-medium">{userInfo?.name || "Não informado"}</p>
                  </div>
                </div>

                {userInfo?.given_name && (
                  <div className="flex items-start gap-2">
                    <User className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">Primeiro Nome</p>
                      <p className="font-medium">{userInfo.given_name}</p>
                    </div>
                  </div>
                )}

                {userInfo?.family_name && (
                  <div className="flex items-start gap-2">
                    <User className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">Sobrenome</p>
                      <p className="font-medium">{userInfo.family_name}</p>
                    </div>
                  </div>
                )}

                {userInfo?.email && (
                  <div className="flex items-start gap-2">
                    <Mail className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">E-mail</p>
                      <p className="font-medium break-all">{userInfo.email}</p>
                    </div>
                  </div>
                )}

                {userInfo?.preferred_username && (
                  <div className="flex items-start gap-2">
                    <IdCard className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">CPF</p>
                      <p className="font-medium font-mono">{userInfo.preferred_username}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Informações da Sessão */}
            <div className="rounded-lg border p-4 bg-muted/30">
              <h4 className="flex items-center gap-2 font-semibold mb-3">
                <Key className="h-4 w-4 text-primary" />
                Sessão Atual
              </h4>
              <div className="text-sm space-y-2">
                {userInfo?.sub && (
                  <div className="flex items-start gap-2">
                    <Key className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">ID da Sessão</p>
                      <p className="font-medium font-mono text-xs break-all">{userInfo.sub.substring(0, 24)}...</p>
                    </div>
                  </div>
                )}

                {userInfo?.iat && (
                  <div className="flex items-start gap-2">
                    <Calendar className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">Login Realizado em</p>
                      <p className="font-medium">{formatDate(userInfo.iat)}</p>
                    </div>
                  </div>
                )}

                {userInfo?.exp && (
                  <div className="flex items-start gap-2">
                    <Clock className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground">Sessão Expira em</p>
                      <p className="font-medium">{formatDate(userInfo.exp)}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Tempo restante: <span className="text-primary font-semibold">{getTimeRemaining(userInfo.exp)}</span>
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Governança de Dados */}
            <div className="rounded-lg border p-4 bg-muted/50">
              <h4 className="flex items-center gap-2 font-semibold mb-3">
                <Shield className="h-4 w-4 text-primary" />
                Governança de Dados
              </h4>
              <div className="text-sm space-y-2 text-muted-foreground">
                <p>
                  O acesso aos dados é monitorado e auditado conforme a LGPD e as normas da Prefeitura do Rio de Janeiro.
                </p>
                <div className="pt-2 space-y-1">
                  <p className="text-xs">
                    <span className="font-medium text-foreground">Nível de Acesso:</span>{" "}
                    {(() => {
                      // Normalizar permissão (prioriza campo 'permission', fallback para booleans)
                      const perm = userInfo?.permission || 
                                  (userInfo?.is_super_admin ? 'super_admin' : 
                                   userInfo?.is_admin ? 'admin' : 'user');
                      
                      switch (perm) {
                        case 'super_admin':
                          return (
                            <span className="inline-flex items-center rounded-md bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive ring-1 ring-inset ring-destructive/20">
                              Super Admin
                            </span>
                          );
                        case 'admin':
                          return (
                            <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20">
                              Admin
                            </span>
                          );
                        default:
                          return (
                            <span className="inline-flex items-center rounded-md bg-secondary/10 px-2 py-1 text-xs font-medium text-secondary ring-1 ring-inset ring-secondary/20">
                              Usuário Comum
                            </span>
                          );
                      }
                    })()}
                  </p>
                  {/* Seção de Permissões de Acesso */}
                  {((userInfo?.id_cras_list?.length ?? 0) > 0 || (userInfo?.id_escola_list?.length ?? 0) > 0 || (userInfo?.id_cre_list?.length ?? 0) > 0 || (userInfo?.id_ap_list?.length ?? 0) > 0 || (userInfo?.id_cas_list?.length ?? 0) > 0 || (userInfo?.id_clinica_familia_list?.length ?? 0) > 0) ? (
                    <div className="mt-3 pt-3 border-t border-border/50 space-y-3">
                      <p className="text-xs font-semibold text-foreground mb-2">Unidades Permitidas:</p>
                      
                      {/* Assistência Social */}
                      {((userInfo?.id_cras_list?.length ?? 0) > 0 || (userInfo?.id_cas_list?.length ?? 0) > 0) && (
                        <div className="space-y-1">
                          <p className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1">
                            Assistência Social
                          </p>
                          {userInfo?.id_cras_list && userInfo.id_cras_list.length > 0 && (
                             <AccessList label="CRAS" items={userInfo.id_cras_list} />
                          )}
                          {userInfo?.id_cas_list && userInfo.id_cas_list.length > 0 && (
                             <AccessList label="CAS" items={userInfo.id_cas_list} />
                          )}
                        </div>
                      )}

                      {/* Educação */}
                      {((userInfo?.id_escola_list?.length ?? 0) > 0 || (userInfo?.id_cre_list?.length ?? 0) > 0) && (
                        <div className="space-y-1">
                          <p className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1">
                            Educação
                          </p>
                          {userInfo?.id_cre_list && userInfo.id_cre_list.length > 0 && (
                             <AccessList label="CREs" items={userInfo.id_cre_list} />
                          )}
                          {userInfo?.id_escola_list && userInfo.id_escola_list.length > 0 && (
                             <AccessList label="Escolas" items={userInfo.id_escola_list} />
                          )}
                        </div>
                      )}

                      {/* Saúde */}
                      {((userInfo?.id_ap_list?.length ?? 0) > 0 || (userInfo?.id_clinica_familia_list?.length ?? 0) > 0) && (
                        <div className="space-y-1">
                          <p className="text-[10px] uppercase font-bold text-muted-foreground flex items-center gap-1">
                            Saúde
                          </p>
                          {userInfo?.id_ap_list && userInfo.id_ap_list.length > 0 && (
                             <AccessList label="CAPs" items={userInfo.id_ap_list} />
                          )}
                          {userInfo?.id_clinica_familia_list && userInfo.id_clinica_familia_list.length > 0 && (
                             <AccessList label="Clínicas" items={userInfo.id_clinica_familia_list} />
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                     // Se for admin/superadmin sem restrições específicas (acesso total)
                     (userInfo?.is_admin || userInfo?.is_super_admin) && (
                        <div className="mt-3 pt-3 border-t border-border/50">
                          <p className="text-xs text-muted-foreground italic">
                            Acesso irrestrito a todas as unidades.
                          </p>
                        </div>
                     )
                  )}

                  <div className="pt-3 mt-2 border-t border-border/50">
                    <p className="text-xs">
                      <span className="font-medium text-foreground">Provedor de Identidade:</span> GovBR
                    </p>
                    <p className="text-xs">
                      <span className="font-medium text-foreground">Autenticação:</span> Identidade Carioca
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="flex justify-end pt-2 border-t">
          <Button variant="destructive" onClick={handleLogout} className="gap-2">
            <LogOut className="h-4 w-4" />
            Sair
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Componente auxiliar para listar acessos de forma compacta
function AccessList({ label, items }: { label: string, items: { nome: string }[] }) {
  return (
    <div className="text-xs pl-2 border-l-2 border-primary/20">
      <span className="font-medium text-foreground">{label}:</span>{" "}
      <span className="text-muted-foreground">
        {items.length}
      </span>
    </div>
  );
}
