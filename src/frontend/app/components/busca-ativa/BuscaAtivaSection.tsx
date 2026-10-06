"use client";

import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { apiService } from "@/app/services/api";
import type { BuscaAtivaEvento } from "@/app/types";
import { BuscaAtivaTimeline } from "./BuscaAtivaTimeline";

const DETAIL_PAGE_SIZE = 20;

/**
 * Seção "Busca Ativa" do detalhamento individual: eventos de
 * `endpoint_busca_ativa` (SMS/SMAS) em linha do tempo (mais recente no topo).
 * A primeira página vem embutida no detalhe (`participant.busca_ativa`,
 * limit 20); "Carregar mais" pagina pela rota dedicada. Renderiza `null`
 * apenas quando o campo é nulo (falha graciosa do backend); lista vazia
 * mostra o empty state "Sem registros de busca ativa".
 */
export function BuscaAtivaSection({
	idMembroFamilia,
	buscaAtiva,
}: {
	idMembroFamilia?: string | null;
	buscaAtiva?: BuscaAtivaEvento[] | null;
}) {
	const [items, setItems] = useState<BuscaAtivaEvento[]>(buscaAtiva ?? []);
	const [offset, setOffset] = useState<number>(buscaAtiva?.length ?? 0);
	const [hasMore, setHasMore] = useState<boolean>(
		(buscaAtiva?.length ?? 0) >= DETAIL_PAGE_SIZE,
	);
	const [loadingMore, setLoadingMore] = useState(false);

	const loadMore = useCallback(async () => {
		if (!idMembroFamilia || loadingMore) return;
		setLoadingMore(true);
		try {
			const page = await apiService.getBuscaAtivaV2(
				idMembroFamilia,
				offset,
				DETAIL_PAGE_SIZE,
			);
			setItems((prev) => [...prev, ...page.data]);
			setOffset(offset + page.data.length);
			setHasMore(page.meta.has_more && page.data.length > 0);
		} catch {
			// Best-effort: mantém os eventos já carregados; o botão continua
			// disponível para uma nova tentativa.
		} finally {
			setLoadingMore(false);
		}
	}, [idMembroFamilia, loadingMore, offset]);

	if (buscaAtiva === null || buscaAtiva === undefined) return null;

	return (
		<div>
			<h3 className="text-lg font-semibold text-foreground flex items-center gap-2 mb-3">
				<Search className="h-5 w-5 text-primary" />
				Busca Ativa
			</h3>

			{items.length === 0 ? (
				<p className="py-6 text-sm text-muted-foreground text-center">
					Sem registros de busca ativa
				</p>
			) : (
				<BuscaAtivaTimeline eventos={items} />
			)}

			{items.length > 0 && hasMore && (
				<div className="flex justify-center pt-3">
					<Button
						variant="outline"
						size="sm"
						onClick={loadMore}
						disabled={loadingMore}
					>
						{loadingMore ? "Carregando..." : "Carregar mais"}
					</Button>
				</div>
			)}
		</div>
	);
}
