"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode, useState } from "react";

/**
 * Mensagens de erro lançadas por handleResponse() que indicam que um redirect
 * já foi disparado (window.location.href = "/login"). Nesse caso o TanStack
 * Query NÃO deve tentar novamente — a página está navegando e um retry apenas
 * manteria a query em estado "loading" até o unload, causando loading infinito.
 */
const AUTH_ERROR_MESSAGES = new Set([
  "Unauthorized",
  "User Inactive",
  "Not Admin",
]);

function isAuthError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  if (AUTH_ERROR_MESSAGES.has(error.message)) return true;
  // "Access Denied: ..." — prefixo usado para erros 403 genéricos
  if (error.message.startsWith("Access Denied")) return true;
  return false;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  // useState para garantir que o QueryClient seja criado apenas uma vez
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Configurações de cache otimizadas
            staleTime: 5 * 60 * 1000, // 5 minutos - dados são considerados frescos
            gcTime: 10 * 60 * 1000, // 10 minutos - tempo que dados ficam em cache (antes era cacheTime)
            /**
             * Retry condicional: 1 tentativa para erros transitórios de rede/5xx,
             * mas NENHUMA tentativa para erros de autenticação/autorização.
             *
             * Sem isso, quando handleResponse() lança "Unauthorized" e ao mesmo
             * tempo dispara window.location.href = "/login", o TanStack Query
             * agenda um retry (~1s depois). A página ainda não descarregou, a
             * query volta para "loading", e o componente fica num loading infinito
             * enquanto o browser navega.
             */
            retry: (failureCount, error) => {
              if (isAuthError(error)) return false;
              return failureCount < 1;
            },
            refetchOnWindowFocus: false, // Não refetch ao focar a janela
            refetchOnReconnect: false, // Não refetch ao reconectar
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
