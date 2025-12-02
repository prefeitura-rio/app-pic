"use client";

import { useSession, signOut } from "next-auth/react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/app/components/ui/dialog";
import { Button } from "@/app/components/ui/button";
import { User, Shield, LogOut } from "lucide-react";

export function UserAreaDialog({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();

  if (!session) return null;

  return (
    <Dialog>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Área do Usuário
          </DialogTitle>
          <DialogDescription>
            Gerencie sua conta e visualize informações de governança.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="space-y-4">
            <div className="rounded-lg border p-4">
              <h4 className="flex items-center gap-2 font-semibold mb-2">
                <User className="h-4 w-4 text-primary" />
                Dados de Autenticação
              </h4>
              <div className="text-sm space-y-1 text-muted-foreground">
                <p><span className="font-medium text-foreground">Nome:</span> {session.user?.name || "Não informado"}</p>
                <p><span className="font-medium text-foreground">Email:</span> {session.user?.email}</p>
                <p><span className="font-medium text-foreground">ID:</span> {session.user?.id || session.sub || "N/A"}</p>
              </div>
            </div>

            <div className="rounded-lg border p-4 bg-muted/50">
              <h4 className="flex items-center gap-2 font-semibold mb-2">
                <Shield className="h-4 w-4 text-primary" />
                Governança de Dados
              </h4>
              <div className="text-sm space-y-2 text-muted-foreground">
                <p>
                  O acesso aos dados é monitorado e auditado conforme a LGPD e as normas da Prefeitura do Rio de Janeiro.
                </p>
                <p className="text-xs">
                  Nível de Acesso: <span className="font-mono bg-background px-1 rounded">Visualização</span>
                </p>
              </div>
            </div>
          </div>
        </div>
        <div className="flex justify-end">
            <Button variant="destructive" onClick={() => signOut()} className="gap-2">
                <LogOut className="h-4 w-4" />
                Sair
            </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
