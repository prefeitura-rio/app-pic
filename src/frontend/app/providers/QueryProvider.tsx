"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactNode, useState } from "react";

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
            retry: 1, // Tentar apenas 1 vez em caso de erro
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
