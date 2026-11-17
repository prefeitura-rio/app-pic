import { COR_TRILHA, TONE_CORES } from "./cores";
import { DeltaBadge } from "./DeltaBadge";
import { formatarTaxa } from "./format";
import type { JanelaComparacao, ProtocoloVariacao } from "./types";

interface VariacaoProtocoloCardProps {
	protocolos: ProtocoloVariacao[];
	temComparativo: boolean;
	janelaComparacao: JanelaComparacao;
}

/**
 * Card "Extremos por protocolo" (bloco 3 da §3.1 — coluna larga 848).
 * Extremos escolhidos pelo backend por **Δpp** (pontos percentuais), entre
 * W−(N+1) e W−1 — mesma unidade do chip e da trilha; piso de 100
 * participantes na referência. `delta_abs` (participantes) é informativo.
 */
export function VariacaoProtocoloCard({
	protocolos,
	temComparativo,
	janelaComparacao,
}: VariacaoProtocoloCardProps) {
	const semDados = !temComparativo || protocolos.length === 0;
	const subtitulo =
		janelaComparacao === 1
			? "Maiores variações em pontos percentuais na semana anterior"
			: `Maiores variações em pontos percentuais nas últimas ${janelaComparacao} semanas`;

	return (
		<section className="font-inter bg-card text-card-foreground flex h-full flex-col gap-4 rounded-xl border p-6 shadow-sm">
			<div>
				<h3 className="text-[15px] font-bold text-shadow-white">
					Extremos por protocolo
				</h3>
				<p className="text-xs text-muted-foreground">{subtitulo}</p>
			</div>

			{semDados ? (
				<p className="flex-1 text-sm text-muted-foreground">
					Sem dados comparáveis nesta semana
				</p>
			) : (
				<ul className="flex flex-1 flex-col justify-center gap-6">
					{protocolos.map((protocolo) => (
						<ProtocoloDeltaRow
							key={protocolo.protocolo_id}
							protocolo={protocolo}
						/>
					))}
				</ul>
			)}
		</section>
	);
}

function ProtocoloDeltaRow({ protocolo }: { protocolo: ProtocoloVariacao }) {
	const delta = protocolo.delta_pp ?? 0;
	const cor = TONE_CORES[protocolo.tone];
	// Trilha ±10 p.p. com zero central — a largura do segmento é |delta|/10.
	const magnitude = Math.min(Math.abs(delta), 10) / 10;
	const largura = magnitude * 50; // % da trilha total
	const esquerda = delta >= 0 ? 50 : 50 - largura;
	const faixa =
		protocolo.de !== null && protocolo.para !== null
			? `${formatarTaxa(protocolo.de)}% → ${formatarTaxa(protocolo.para)}%`
			: null;

	return (
		<li className="space-y-2">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<p className="text-sm font-semibold leading-snug">{protocolo.nome}</p>
					<p className="text-xs text-muted-foreground">
						Taxa de regularidade dos participantes
					</p>
				</div>
				{protocolo.delta_pp !== null && (
					<DeltaBadge
						valor={protocolo.delta_pp}
						tone={protocolo.tone}
						unidade="p.p."
					/>
				)}
			</div>

			<div
				className="relative h-2 w-full rounded-full bg-muted"
				role="img"
				aria-label={`Variação de ${faixa ?? "—"}`}
				style={{ backgroundColor: COR_TRILHA }}
			>
				<div className="absolute bottom-0 top-0 left-1/2 w-px bg-foreground/30" />
				{delta !== 0 && (
					<div
						className="absolute bottom-0 top-0 rounded-full"
						style={{
							left: `${esquerda}%`,
							width: `${largura}%`,
							backgroundColor: cor,
						}}
					/>
				)}
			</div>

			<div className="flex items-center justify-between text-[11px] text-muted-foreground">
				<span>Anterior · {formatarTaxa(protocolo.de)}%</span>
				<span>Atual · {formatarTaxa(protocolo.para)}%</span>
			</div>
		</li>
	);
}
