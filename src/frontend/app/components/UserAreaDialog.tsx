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

interface UserInfo {
  name?: string;
  email?: string;
  preferred_username?: string;
  given_name?: string;
  family_name?: string;
  sub?: string;
  iat?: number;
  exp?: number;
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
                    <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20">
                      Visualização
                    </span>
                  </p>
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
