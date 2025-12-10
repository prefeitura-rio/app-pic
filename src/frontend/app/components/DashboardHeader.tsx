"use client";

import { Heart, User, Shield, Home } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { UserAreaDialog } from "@/app/components/UserAreaDialog";
import { ThemeToggle } from "@/app/components/ThemeToggle";
import { useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";
import { IdWithName } from "@/app/types";

interface UserInfo {
  // JWT standard fields
  name?: string;
  email?: string;
  preferred_username?: string;
  given_name?: string;
  family_name?: string;
  sub?: string;
  iat?: number;
  exp?: number;

  // Application specific fields (merged from /me endpoint)
  permission?: string | null;
  is_admin?: boolean;
  is_super_admin?: boolean;
  id_cras_list?: IdWithName[] | null;
  id_escola_list?: IdWithName[] | null;
  id_cre_list?: IdWithName[] | null;
  id_ap_list?: IdWithName[] | null;
  id_cas_list?: IdWithName[] | null;
  id_clinica_familia_list?: IdWithName[] | null;
}

export function DashboardHeader({ userInfo }: { userInfo?: UserInfo | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const isAdminPage = pathname?.startsWith("/admin");

  // Fetch complete user info (including permissions) from backend
  // IMPORTANTE: Usa mesma queryKey que DashboardClient para compartilhar cache
  const { data: currentUserAccess } = useQuery({
    queryKey: ['currentUser'], // Mesma key que DashboardClient
    queryFn: async () => {
      try {
        return await apiService.getCurrentUser();
      } catch (error) {
        return null;
      }
    },
    retry: false,
    staleTime: 10 * 60 * 1000, // Cache for 10 minutes (mesmo que DashboardClient)
  });

  // Merge basic userInfo (from JWT) with detailed access info (from API)
  const effectiveUserInfo: UserInfo | null = userInfo ? {
    ...userInfo,
    ...(currentUserAccess || {}),
  } : null;

  const isAdmin = currentUserAccess?.is_admin || false;

  return (
    <header className="bg-primary text-primary-foreground shadow-lg">
      <div className="container mx-auto px-6 py-6">
        <div className="flex items-center justify-between">
          {/* Logo - clicável para voltar à página principal */}
          <button
            onClick={() => router.push("/")}
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
          </button>

          <div className="flex items-center gap-2">
            {/* Conditional navigation button based on current page */}
            {isAdminPage ? (
              // Show Home icon when in admin page
              <Button
                variant="ghost"
                size="icon"
                onClick={() => router.push("/")}
                className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground"
              >
                <Home className="h-5 w-5" />
              </Button>
            ) : (
              // Show Admin icon when in main page (only if user is admin)
              isAdmin && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => router.push("/admin")}
                  className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground"
                >
                  <Shield className="h-5 w-5" />
                </Button>
              )
            )}

            <ThemeToggle />
            <UserAreaDialog userInfo={effectiveUserInfo}>
              <Button variant="ghost" size="icon" className="rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground">
                <User className="h-5 w-5" />
              </Button>
            </UserAreaDialog>
          </div>
        </div>
      </div>
    </header>
  );
}
