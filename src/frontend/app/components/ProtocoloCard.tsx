import {
	Card,
	CardContent,
} from "@/app/components/ui/card";
import type { ProtocoloIndicador } from "../types";

export const ProtocoloCard = ({
	protocolo,
	loading,
}: {
	protocolo: ProtocoloIndicador;
	loading?: boolean;
}) => {
	if (protocolo.numerador === 0 && protocolo.denominador === 0) {
		return null;
	}
	return (
		<Card className="relative">
			{loading && <div className="loading-overlay" />}
			<CardContent className="p-4">
				<p className="text-sm font-semibold mb-3 line-clamp-2">
					{protocolo.protocolo_descricao}
				</p>
				<div className="flex items-baseline gap-2">
					<span className="text-2xl font-bold">
						{protocolo.percentual_regular.toFixed(1)}%
					</span>
					<span className="text-xs text-muted-foreground">regular</span>
				</div>
				<p className="text-xs text-muted-foreground mt-1">
					{protocolo.numerador.toLocaleString("pt-BR")} de{" "}
					{protocolo.denominador.toLocaleString("pt-BR")} participantes
				</p>
			</CardContent>
		</Card>
	);
};
