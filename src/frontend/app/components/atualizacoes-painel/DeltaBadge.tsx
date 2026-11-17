import { Badge } from "@/app/components/ui/badge";
import { cn } from "@/app/utils/utils";

import { formatarMagnitude } from "./format";
import type { Tone } from "./types";

interface DeltaBadgeProps {
	/** pct ou p.p. — o SINAL define a seta (o tone é semântico, do backend). */
	valor: number | null;
	/** SEMÂNTICO — nunca derivar do sinal no cliente. */
	tone: Tone;
	unidade: "%" | "p.p.";
	className?: string;
}

/**
 * Chip de variação: seta + valor + unidade (ex.: "↑ 8,6 p.p.",
 * "↓ 7,1%"). Variante soft do `Badge` escolhida pelo `tone`.
 */
export function DeltaBadge({
	valor,
	tone,
	unidade,
	className,
}: DeltaBadgeProps) {
	if (valor === null) {
		return null;
	}
	const subiu = valor >= 0;
	const magnitude = formatarMagnitude(valor);
	return (
		<Badge
			variant={tone === "success" ? "soft-success" : "soft-destructive"}
			className={cn(
				"gap-1 whitespace-nowrap rounded-md px-1.5 py-1.5 font-inter m-1.5",
				className,
			)}
			aria-label={`${subiu ? "alta" : "queda"} de ${magnitude} ${unidade}`}
		>
			<span aria-hidden="true">{subiu ? "↑" : "↓"}</span>
			{magnitude} {unidade}
		</Badge>
	);
}
