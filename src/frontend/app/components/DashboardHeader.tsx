"use client";

import { Heart, User, Shield } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { UserAreaDialog } from "@/app/components/UserAreaDialog";
import { ThemeToggle } from "@/app/components/ThemeToggle";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";

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

export function DashboardHeader({ userInfo }: { userInfo?: UserInfo | null }) {
  const router = useRouter();

  // Check if user is admin by trying to fetch users
  // If 403, user is not admin, so we hide the button
  const { data: isAdmin } = useQuery({
    queryKey: ["admin", "check"],
    queryFn: async () => {
      try {
        await apiService.getUsers(true);
        return true;
      } catch (error) {
        return false;
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  return (
    <header className="bg-primary text-primary-foreground shadow-lg">
      <div className="container mx-auto px-6 py-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="bg-primary-foreground/10 p-3 rounded-lg">
              <Heart className="h-8 w-8" fill="currentColor" />
            </div>
            <div>
              <h1 className="text-3xl font-bold">Pequenos Cariocas</h1>
              <p className="text-primary-foreground/80 text-sm">
                Primeira Infância Integrada • Prefeitura do Rio de Janeiro
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Admin button - only show if user is admin */}
            {isAdmin && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => router.push("/admin")}
                className="gap-2"
              >
                <Shield className="h-4 w-4" />
                Admin
              </Button>
            )}

            <ThemeToggle />
            <UserAreaDialog userInfo={userInfo}>
              <Button variant="secondary" size="icon" className="rounded-full">
                <User className="h-5 w-5" />
              </Button>
            </UserAreaDialog>
          </div>
        </div>
      </div>
    </header>
  );
}
