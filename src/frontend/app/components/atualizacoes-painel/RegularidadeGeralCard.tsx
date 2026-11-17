import { Badge } from "@/app/components/ui/badge";

import { COR_BRAND_MID } from "./cores";
import { DeltaBadge } from "./DeltaBadge";
import { DonutGauge } from "./DonutGauge";
import { formatarNumero, formatarTaxa } from "./format";
import type { Regularidade } from "./types";

interface RegularidadeGeralCardProps {
	dados: Regularidade;
	temComparativo: boolean;
}

/**
 * Card navy da regularidade geral (bloco 2 da §3.1). Fundo `brand` FIXO nos
 * dois temas (§2.5/§8 da doc) — não usa `bg-primary` (no dark o primary é
 * azul claro).
 *
 * A TAXA é a regularidade dos ATIVOS (regulares / ativos) — mesma métrica da
 * Visão Geral com filtro Ativo. O strip de baixo é a COMPOSIÇÃO da base em
 * contagens (regulares + irregulares + inativos = base), para não misturar
 * denominadores.
 */
export function RegularidadeGeralCard({
	dados,
	temComparativo,
}: RegularidadeGeralCardProps) {
	return (
		<section
			className="font-inter bg-brand text-white flex h-full flex-col justify-between gap-4 rounded-xl p-6 shadow-sm"
			aria-label={`Regularidade geral: ${formatarTaxa(dados.taxa)}%`}
		>
			<div className="flex items-start justify-between gap-2 font-bold ">
				Regularidade Geral
				<Badge variant="warning" size="sm">
					NA REGIÃO
				</Badge>
			</div>

			<div className="flex items-center gap-5">
				<DonutGauge
					taxa={dados.taxa}
					tone={dados.tone}
					trilha={COR_BRAND_MID}
					tamanho={112}
				/>
				<div className="space-y-1.5">
					<div className="flex flex-row gap-2 shrink-0 items-center">
						<p className="font-inter text-5xl font-semibold">
							{formatarTaxa(dados.taxa)}%
						</p>
						{temComparativo && (
							<DeltaBadge
								valor={dados.variacao_pp}
								tone={dados.tone}
								unidade="p.p."
							/>
						)}
					</div>
					<p className="font-inter text-sm text-white/90">
						{formatarNumero(dados.regulares)} regulares de{" "}
						{formatarNumero(dados.ativos)} ativos
					</p>
				</div>
			</div>

			<div className="border-t border-white/20 pt-3 text-center flex flex-row items-center justify-around">
				<MetricaMini
					rotulo="REGULARES"
					valor={formatarNumero(dados.regulares)}
				/>
				<MetricaMini
					rotulo="IRREGULARES"
					valor={formatarNumero(dados.irregulares)}
				/>
			</div>
		</section>
	);
}

function MetricaMini({ rotulo, valor }: { rotulo: string; valor: string }) {
	return (
		<div className="font-inter text-center flex flex-row items-center gap-5">
			<p className="font-inter text-[10px] uppercase tracking-wide text-[#E9EAED]">
				{rotulo}
			</p>
			<p className="font-inter text-sm text-white">{valor}</p>
		</div>
	);
}
