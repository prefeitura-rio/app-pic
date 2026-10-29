import { Check, X } from "lucide-react";

interface BuscaAtivaBadgeProps {
	value?: boolean | null;
}

export function BuscaAtivaBadge({ value }: BuscaAtivaBadgeProps) {
	if (value == null) return <span className="text-muted-foreground">-</span>;

	return (
		<span className="flex justify-center">
			{value ? (
				<Check
					className="h-4 w-4 text-green-600 dark:text-green-400"
					aria-label="Tem registro de busca ativa"
				/>
			) : (
				<X
					className="h-4 w-4 text-muted-foreground"
					aria-label="Sem registro de busca ativa"
				/>
			)}
		</span>
	);
}
