"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Skeleton } from "@/app/components/ui/skeleton";
import { apiService } from "@/app/services/api";

import { BarraFechada } from "./BarraFechada";
import { CardsRow } from "./CardsRow";
import { PainelFooter } from "./PainelFooter";
import { PainelHeader } from "./PainelHeader";
import { RegularidadeGeralCard } from "./RegularidadeGeralCard";
import { VariacaoProtocoloCard } from "./VariacaoProtocoloCard";
import type { JanelaComparacao } from "./types";

/** Chave do localStorage da última semana de referência vista (§2.4). */
const CHAVE_SEMANA_VISTA = "atualizacoes-painel:semana-vista";

/**
 * Painel de Atualizações da Busca Individual — raiz (§9 da doc).
 *
 * - Busca o endpoint SEM camada/região: o painel segue os ACESSOS do usuário
 *   (a RLS do data-proxy define o recorte) — sem acoplar aos filtros da busca.
 * - Seletor de janela de comparação (1 | 2 | 4 semanas, default 4): muda a
 *   query key; `keepPreviousData` mantém os números atuais enquanto a nova
 *   janela carrega (sem piscar o esqueleto).
 * - Gate no cliente é só o flag da resposta: `can_view_atualizacoes=false`
 *   → não renderiza nada (§10).
 * - Estado inicial FECHADO; `data=null` → barra "Sem indicadores para esta
 *   região" sem botão de abrir.
 */
export function AtualizacoesPainel() {
	const [aberto, setAberto] = useState(false);
	const [badgeNovo, setBadgeNovo] = useState(false);
	const [janelaComparacao, setJanelaComparacao] = useState<JanelaComparacao>(4);

	const { data, isFetching } = useQuery({
		queryKey: ["atualizacoes-regionais", janelaComparacao],
		queryFn: ({ signal }) =>
			apiService.getAtualizacoesRegionais(janelaComparacao, signal),
		staleTime: 15 * 60 * 1000, // o backend já cacheia por 15 min
		placeholderData: keepPreviousData, // loading não bloqueante na troca de janela
		refetchOnWindowFocus: false,
	});

	// NOVO: aparece quando a semana de referência muda; some no 2º acesso com
	// a mesma semana. Leitura no useEffect (evita mismatch de hidratação —
	// §2.4); o setState é deferido para depois do efeito (sincroniza só o
	// sistema externo — localStorage).
	useEffect(() => {
		const semana = data?.meta.semana_referencia;
		if (!semana) {
			return;
		}
		const vista = localStorage.getItem(CHAVE_SEMANA_VISTA);
		localStorage.setItem(CHAVE_SEMANA_VISTA, semana);
		queueMicrotask(() => setBadgeNovo(vista !== semana));
	}, [data?.meta.semana_referencia]);

	// Gate (b): o backend decide a regra de permissão.
	if (data && !data.can_view_atualizacoes) {
		return null;
	}

	const semDados = Boolean(data && data.data === null);

	if (!aberto) {
		return (
			<BarraFechada
				status={semDados ? "sem-indicadores" : "oculto"}
				onAbrir={() => setAberto(true)}
				badgeNovo={badgeNovo}
			/>
		);
	}

	return (
		<section
			aria-label="Painel de Atualizações"
			aria-busy={isFetching}
			className="animate bg-card font-inter text-card-foreground space-y-5 rounded-xl border p-6 shadow-sm"
		>
			{isFetching && !data ? (
				<Esqueleto />
			) : data?.data ? (
				<>
					<PainelHeader
						data={data.data}
						badgeNovo={badgeNovo}
						janelaComparacao={janelaComparacao}
						onJanelaChange={setJanelaComparacao}
						janelaCarregando={isFetching}
						onFechar={() => setAberto(false)}
					/>
					<div className="grid items-stretch gap-5 lg:grid-cols-[3fr_5fr]">
						<RegularidadeGeralCard
							dados={data.data.regularidade}
							temComparativo={data.meta.tem_comparativo}
						/>
						<VariacaoProtocoloCard
							protocolos={data.data.protocolos}
							temComparativo={data.meta.tem_comparativo}
							janelaComparacao={data.meta.semanas_comparacao}
						/>
					</div>
					<CardsRow
						data={data.data}
						cards={data.meta.cards}
						temComparativo={data.meta.tem_comparativo}
						janelaComparacao={data.meta.semanas_comparacao}
					/>
					<PainelFooter
						semanaComparacao={data.meta.semana_comparacao}
						temComparativo={data.meta.tem_comparativo}
						escopoRestrito={data.meta.escopo_restrito}
					/>
				</>
			) : (
				<p className="text-sm text-muted-foreground">
					Sem indicadores para esta região
				</p>
			)}
		</section>
	);
}

function Esqueleto() {
	return (
		// biome-ignore lint/a11y/useAriaPropsSupportedByRole: <explanation>
		<div className="space-y-5" aria-label="Carregando painel de atualizações">
			<div className="flex items-center justify-between">
				<div className="space-y-2">
					<Skeleton className="h-3 w-28" />
					<Skeleton className="h-6 w-56" />
				</div>
				<Skeleton className="h-9 w-28" />
			</div>
			<div className="grid gap-5 lg:grid-cols-[3fr_5fr]">
				<Skeleton className="h-66 w-full rounded-xl" />
				<Skeleton className="h-66 w-full rounded-xl" />
			</div>
			<div className="grid gap-5 lg:grid-cols-3">
				<Skeleton className="h-66 w-full rounded-xl" />
				<Skeleton className="h-66 w-full rounded-xl" />
				<Skeleton className="h-66 w-full rounded-xl" />
			</div>
		</div>
	);
}
