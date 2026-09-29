import { useState } from "react";

/**
 * Detects a fresh OAuth login via the `policy_force_sync` cookie and returns
 * whether the next `GET /admin/me` call should include `?force_sync=true`.
 *
 * The cookie is created by the OAuth callback (`/api/auth/callback/rmi`) right
 * after token exchange and expires in 60 s — long enough for any page to mount
 * and read it. The hook reads and consumes (deletes) the cookie on first render
 * via the useState initializer, so only the very first `getCurrentUser()` call
 * after login carries the flag.
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

    const hasPolicySyncFlag = document.cookie
      .split(";")
      .some((c) => c.trim() === "policy_force_sync=1");

    if (hasPolicySyncFlag) {
      // Consume the cookie immediately so subsequent mounts (e.g. /admin page
      // after DashboardClient already consumed it) don't re-trigger the sync.
      document.cookie = "policy_force_sync=; path=/; max-age=0";
      return true;
    }

    return false;
  });

  return forceSync;
}
