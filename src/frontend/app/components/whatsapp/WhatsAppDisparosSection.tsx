"use client";

import { MessageCircle } from "lucide-react";
import { Separator } from "@/app/components/ui/separator";
import type { Disparo } from "@/app/types";
import { WhatsAppDisparosCard } from "./WhatsAppDisparosCard";

/**
 * Seção "Disparos WhatsApp" do detalhamento individual: um card por campanha
 * (dados vindos de `endpoint_whatsapp_disparo` via data-proxy). Renderiza
 * `null` quando não há disparos (campo nulo — falha graciosa do backend — ou
 * lista vazia), mantendo o modal inalterado nesses casos.
 */
export function WhatsAppDisparosSection({
	disparos,
}: {
	disparos?: Disparo[] | null;
}) {
	if (!disparos || disparos.length === 0) return null;

	return (
		<>
			<div>
				<h3 className="text-lg font-semibold mb-3 text-foreground flex items-center gap-2">
					<MessageCircle className="h-5 w-5 text-primary" />
					Disparos WhatsApp
				</h3>
				<div className="space-y-2">
					{disparos.map((disparo, idx) => (
						<WhatsAppDisparosCard
							key={`${disparo.campanha ?? "campanha"}-${idx}`}
							disparo={disparo}
						/>
					))}
				</div>
			</div>
			<Separator />
		</>
	);
}
