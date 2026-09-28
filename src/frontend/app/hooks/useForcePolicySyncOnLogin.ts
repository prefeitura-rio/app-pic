import { useEffect, useState } from "react";

/**
 * Detects a fresh OAuth login via the `policy_force_sync` cookie and returns
 * whether the next `GET /admin/me` call should include `?force_sync=true`.
 *
 * The cookie is created by the OAuth callback (`/api/auth/callback/rmi`) right
 * after token exchange and expires in 60 s — long enough for any page to mount
 * and read it.
 *
 * IMPORTANTE (idempotência com renders concorrentes do React 19): a LEITURA
 * fica no inicializador do useState (para o /me no mount já nascer com
 * force_sync), mas a DELEÇÃO do cookie fica num efeito. Se o React descartar
 * e refazer o render, o inicializador re-lê o cookie intacto — a deleção
 * acontece uma única vez, após o commit.
 *
 * Usage:
 *   const forceSync = useForcePolicySyncOnLogin();
 *   useQuery({
 *     queryKey: ["currentUser"],
 *     queryFn: () => apiService.getCurrentUser(forceSync ? { force_sync: true } : {}),
 *   });
 */
export function useForcePolicySyncOnLogin(): boolean {
  const [forceSync] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;

    try {
      return document.cookie
        .split(";")
        .some((c) => c.trim() === "policy_force_sync=1");
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (!forceSync || typeof window === "undefined") return;

    try {
      // Consume o cookie para que montagens seguintes (ex.: /admin depois do
      // DashboardClient) não re-disparam o sync.
      document.cookie = "policy_force_sync=; path=/; max-age=0";
    } catch {
      // Cookie expira sozinho em 60s — falhar aqui é inofensivo.
    }
  }, [forceSync]);

  return forceSync;
}
