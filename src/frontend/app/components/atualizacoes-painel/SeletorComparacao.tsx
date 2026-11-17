import { Button } from "@/app/components/ui/button";

import type { JanelaComparacao } from "./types";

export const OPCOES_JANELA: { valor: JanelaComparacao; rotulo: string; completo: string }[] = [
	{ valor: 1, rotulo: "1 sem.", completo: "1 semana" },
	{ valor: 2, rotulo: "2 sem.", completo: "2 semanas" },
	{ valor: 4, rotulo: "4 sem.", completo: "4 semanas" },
];

interface SeletorComparacaoProps {
	valor: JanelaComparacao;
	onChange: (valor: JanelaComparacao) => void;
	disabled?: boolean;
}

/**
 * Seletor da janela de comparação do painel (1 | 2 | 4 semanas — decisão E).
 * Grupo de botões com `aria-pressed`; ativo usa o variant default, os demais
 * outline. Enquanto o fetch da nova janela roda, fica desabilitado.
 */
export function SeletorComparacao({
	valor,
	onChange,
	disabled = false,
}: SeletorComparacaoProps) {
	return (
		<div
			role="group"
			aria-label="Janela de comparação"
			className="flex items-center gap-1.5"
		>
			<span className="text-xs text-muted-foreground">Comparar com:</span>
			{OPCOES_JANELA.map((opcao) => {
				const ativa = opcao.valor === valor;
				return (
					<Button
						key={opcao.valor}
						type="button"
						size="sm"
						variant={ativa ? "default" : "outline"}
						aria-pressed={ativa}
						aria-label={`Comparar com ${opcao.completo}`}
						title={`Comparar com ${opcao.completo}`}
						disabled={disabled}
						onClick={() => onChange(opcao.valor)}
						className="h-8 px-2.5 text-xs"
					>
						{opcao.rotulo}
					</Button>
				);
			})}
		</div>
	);
}
