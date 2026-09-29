"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { UserAccessRecord } from "@/app/types";

/**
 * Consumidor puro da query `["currentUser"]`: lê os dados do cache do
 * TanStack Query e re-renderiza quando eles mudam, SEM criar observer próprio
 * (sem queryFn, sem fetch).
 *
 * Motivação: a query `["currentUser"]` é "dona" do DashboardClient (único
 * lugar que monta a query com `force_sync` correto e trata erros de
 * auth). Observers adicionais com queryFns diferentes na MESMA chave
 * sobrescreviam o queryFn vencedor (o último `setOptions` ganha) — o
 * `force_sync=true` do pós-login nunca era aplicado e erros do /me eram
 * engolidos como `null`. Com este hook, só existe um observer.
 */
export function useCurrentUserCache(): UserAccessRecord | undefined {
	const queryClient = useQueryClient();

	const subscribe = useCallback(
		(onStoreChange: () => void) => {
			const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
				if (event.query.queryKey[0] === "currentUser") {
					onStoreChange();
				}
			});
			return unsubscribe;
		},
		[queryClient],
	);

	const getSnapshot = useCallback(
		() => queryClient.getQueryData<UserAccessRecord>(["currentUser"]),
		[queryClient],
	);

	return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
