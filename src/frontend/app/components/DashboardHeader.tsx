"use client";

import { useState } from "react";
import { Heart, User, Shield, Home, Bug } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { UserAreaDialog } from "@/app/components/UserAreaDialog";
import { SessionMonitor } from "@/app/components/SessionMonitor";
import { ThemeToggle } from "@/app/components/ThemeToggle";
import { AnonymizeToggle } from "@/app/components/AnonymizeToggle";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useCurrentUserCache } from "@/app/hooks/useCurrentUserCache";
import { IdWithName } from "@/app/types";
import { DEBUG_PAGE_ENABLED } from "@/app/debug/config";

interface UserInfo {
  // JWT standard fields
  name?: string | null;
  email?: string | null;
  preferred_username?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  sub?: string | null;
  iat?: number;
  exp?: number;

  // Application specific fields (merged from /me endpoint)
  cpf?: string;
  nome?: string | null;
  ocupacao?: string | null;
  secretaria?: string | null;
  secretarias_acesso?: string[] | null;
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

interface DashboardHeaderProps {
  userInfo?: UserInfo | null;
  showUserControls?: boolean;
}

export function DashboardHeader({ userInfo, showUserControls = true }: DashboardHeaderProps) {
  const pathname = usePathname();
  const isAdminPage = pathname?.startsWith("/admin");
  const isDebugPage = pathname?.startsWith("/debug");
  const [userAreaOpen, setUserAreaOpen] = useState(false);

  // Consome o /me do cache da query ["currentUser"] — o único observer é o
  // do DashboardClient (ou da página /admin), que aplica force_sync e trata
  // erros de auth corretamente. Aqui não há queryFn próprio: evita a corrida
  // de queryFns diferentes na mesma chave e o loop 401 -> /login -> 401.
  const currentUserAccess = useCurrentUserCache();

  // Merge basic userInfo (from JWT) with detailed access info (from API)
  const effectiveUserInfo: UserInfo | null = userInfo ? {
    ...userInfo,
    ...(currentUserAccess || {}),
  } : null;

  const isAdmin = currentUserAccess?.is_admin || false;
  const isSuperAdmin = currentUserAccess?.is_super_admin || false;

  // Callback para SessionMonitor abrir a área do usuário
  const handleOpenUserArea = () => {
    setUserAreaOpen(true);
  };

  return (
    <>
      <header className="bg-primary text-primary-foreground shadow-lg">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            {/* Logo - clicável para voltar à página principal */}
            <Link
              href="/"
              className="flex items-center gap-4 hover:opacity-80 transition-opacity"
            >
              <div className="bg-primary-foreground/10 p-3 rounded-lg">
                <Heart className="h-8 w-8" fill="currentColor" />
              </div>
              <div className="text-left">
                <h1 className="text-3xl font-bold">Pequenos Cariocas</h1>
                <p className="text-primary-foreground/80 text-sm">
                  Primeira Infância Integrada • Prefeitura do Rio de Janeiro
                </p>
              </div>
            </Link>

            <div className="flex items-center gap-2">
              {showUserControls && (
                <>
                  {/* Debug icon for super admin (always visible except on debug page) */}
                  {!isDebugPage && isSuperAdmin && DEBUG_PAGE_ENABLED && (
                    <Button
                      variant="ghost"
                      size="icon"
                      asChild
                      className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground"
                      title="Debug"
                    >
                      <Link href="/debug">
                        <Bug className="h-5 w-5" />
                      </Link>
                    </Button>
                  )}

                  {/* Conditional navigation button based on current page */}
                  {isAdminPage || isDebugPage ? (
                    // Show Home icon when in admin or debug page
                    <Button
                      variant="ghost"
                      size="icon"
                      asChild
                      className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground"
                    >
                      <Link href="/"><Home className="h-5 w-5" /></Link>
                    </Button>
                  ) : (
                    // Show Admin icon when in main page (only if user is admin)
                    isAdmin && (
                      <Button
                        variant="ghost"
                        size="icon"
                        asChild
                        className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground"
                      >
                        <Link href="/admin"><Shield className="h-5 w-5" /></Link>
                      </Button>
                    )
                  )}
                </>
              )}

              <AnonymizeToggle />
              <ThemeToggle />

              {showUserControls && (
                <UserAreaDialog
                  userInfo={effectiveUserInfo}
                  open={userAreaOpen}
                  onOpenChange={setUserAreaOpen}
                >
                  <Button variant="ghost" size="icon" className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground">
                    <User className="h-5 w-5" />
                  </Button>
                </UserAreaDialog>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Session Monitor - only show when user is authenticated */}
      {showUserControls && effectiveUserInfo?.exp && (
        <SessionMonitor
          tokenExpiration={effectiveUserInfo.exp}
          onOpenUserArea={handleOpenUserArea}
        />
      )}
    </>
  );
}
