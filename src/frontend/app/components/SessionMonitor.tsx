"use client";

import { useEffect, useState, useCallback } from "react";

interface SessionMonitorProps {
  /** Token expiration timestamp (seconds since epoch) */
  tokenExpiration?: number;
  /** Callback para abrir a área do usuário */
  onOpenUserArea: () => void;
}

const WARN_BEFORE_SECONDS = 60; // 1 minuto

export function SessionMonitor({ tokenExpiration, onOpenUserArea }: SessionMonitorProps) {
  const [hasWarned, setHasWarned] = useState(false);

  const calculateTimeRemaining = useCallback((): number => {
    if (!tokenExpiration) return 0;
    const now = Math.floor(Date.now() / 1000);
    return Math.max(0, tokenExpiration - now);
  }, [tokenExpiration]);

  const handleLogout = () => {
    window.location.href = "/api/auth/logout";
  };

  // Timer principal
  useEffect(() => {
    if (!tokenExpiration) return;

    const interval = setInterval(() => {
      const remaining = calculateTimeRemaining();

      // Abrir área do usuário automaticamente quando faltar 1 minuto (apenas 1x)
      if (remaining <= WARN_BEFORE_SECONDS && remaining > 0 && !hasWarned) {
        console.warn(`[SessionMonitor] Session expiring in ${remaining}s - opening user area`);
        setHasWarned(true);
        onOpenUserArea();
      }

      // Auto-redirect exatamente quando o token expirar (sem margem)
      if (remaining === 0) {
        console.error("[SessionMonitor] Token expired - redirecting to login");
        handleLogout();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [tokenExpiration, hasWarned, calculateTimeRemaining, onOpenUserArea]);

  // Este componente não renderiza nada - apenas monitora a sessão
  return null;
}
