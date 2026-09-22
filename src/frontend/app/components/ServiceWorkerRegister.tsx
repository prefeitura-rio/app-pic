"use client";

import { useEffect } from "react";

/**
 * Registra o Service Worker em produção.
 *
 * O SW cacheia `/_next/static/*` (assets imutáveis com hash de conteúdo),
 * tornando a aplicação imune a 503s da camada de borda na volta do fluxo
 * OAuth (gov.br) e em refreshes — após o primeiro load bem-sucedido, os
 * chunks são servidos do cache sem depender da rede.
 *
 * Só registra em produção para não interferir no desenvolvimento.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker
        .register("/sw.js")
        .catch((error) => {
          console.warn("[ServiceWorkerRegister] Falha ao registrar SW:", error);
        });
    };

    // Espera o load completo para não competir com o carregamento inicial
    // dos chunks da página.
    if (document.readyState === "complete") {
      register();
    } else {
      window.addEventListener("load", register, { once: true });
    }
  }, []);

  return null;
}
