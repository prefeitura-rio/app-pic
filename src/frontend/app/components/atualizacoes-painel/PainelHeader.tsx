import { X } from "lucide-react";

import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";

import { formatarNumero, semanaFaixaLabel } from "./format";
import { SeletorComparacao } from "./SeletorComparacao";
import type { AtualizacoesPainelData, JanelaComparacao } from "./types";

interface PainelHeaderProps {
	data: AtualizacoesPainelData;
	badgeNovo: boolean;
	janelaComparacao: JanelaComparacao;
	onJanelaChange: (valor: JanelaComparacao) => void;
	janelaCarregando: boolean;
	onFechar: () => void;
}

/**
 * Bloco 1 (cabeçalho, §3.1 da doc): eyebrow, título, pill da região (rótulo
 * da tabela — Q6), badge NOVO (localStorage, §2.4), semana de referência com
 * a comparação explícita (W−1 × W−(N+1)), seletor de janela e pill de
 * participantes. Título aberto: "Atualizações do Painel".
 */
export function PainelHeader({
	data,
	badgeNovo,
	janelaComparacao,
	onJanelaChange,
	janelaCarregando,
	onFechar,
}: PainelHeaderProps) {
	const referencia = semanaFaixaLabel(data.contexto.semana_referencia);
	const comparacao = semanaFaixaLabel(data.contexto.semana_comparacao);

	return (
		<header className="flex flex-wrap items-start justify-between gap-3">
			<div className="min-w-0">
				<p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
					Visão regional
				</p>
				<div className="mt-1 flex flex-wrap items-center gap-2">
					<h2 className="text-xl font-bold">Atualizações do Painel</h2>
					<Badge variant="outline">{data.contexto.regiao_label}</Badge>
					{badgeNovo && <Badge variant="warning">NOVO</Badge>}
				</div>
				{referencia && (
					<p className="mt-1 text-sm text-foreground animate-[pulse_3s_ease-in-out_2]">
						Semana de {referencia}
						{comparacao ? ` · comparada com ${comparacao}` : ""}
					</p>
				)}
			</div>

			<div className="flex flex-wrap items-center gap-3">
				<SeletorComparacao
					valor={janelaComparacao}
					onChange={onJanelaChange}
					disabled={janelaCarregando}
				/>
				<Badge variant="outline" size="md">
					{formatarNumero(data.contexto.participantes)} participantes
				</Badge>
				<Button
					variant="ghost"
					size="sm"
					onClick={onFechar}
					className="gap-1.5"
				>
					Fechar
					<X className="h-4 w-4" aria-hidden="true" />
				</Button>
			</div>
		</header>
	);
}
