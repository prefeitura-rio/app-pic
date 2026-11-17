import { Eye } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { Badge } from "../ui/badge";

interface BarraFechadaProps {
	/** "oculto": painel tem dados, só está fechado; "sem-indicadores": data null. */
	status: "oculto" | "sem-indicadores";
	onAbrir: () => void;
	/** Mostra o badge NOVO (semana de referência mudou — §2.4). */
	badgeNovo: boolean;
}

/**
 * Estado fechado (§3.2 da doc): título "Alertas" + status + botão
 * "Exibir indicadores". Sem dados, o botão some e a barra informa
 * "Sem indicadores para esta região" (§10).
 */
export function BarraFechada({
	status,
	onAbrir,
	badgeNovo,
}: BarraFechadaProps) {
	const semDados = status === "sem-indicadores";

	return (
		<div className="bg-card text-card-foreground flex min-h-20 items-center justify-between gap-3 rounded-xl border px-6 py-4 shadow-sm">
			<div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
				<h2 className="text-lg font-bold">
					Alertas{" "}
					{badgeNovo && (
						<Badge variant="warning" className="animate-pulse">
							NOVO
						</Badge>
					)}
				</h2>
				<span className="text-sm text-muted-foreground">
					{semDados
						? "Sem indicadores para esta região"
						: "Indicadores ocultos - Clique em Exibir indicadores para abrir o painel"}
				</span>
			</div>
			{!semDados && (
				<Button onClick={onAbrir} size="sm" className="gap-1.5">
					<Eye className="h-4 w-4" aria-hidden="true" />
					Exibir indicadores
				</Button>
			)}
		</div>
	);
}
