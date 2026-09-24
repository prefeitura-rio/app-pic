import { Badge } from "@/app/components/ui/badge";

interface CartaoPicBadgeProps {
	value?: boolean | null;
}

export function CartaoPicBadge({ value }: CartaoPicBadgeProps) {
	const variant =
		value === true ? "success" : value === false ? "warning" : "secondary";
	const label =
		value === true
			? "Cartão retirado"
			: value === false
				? "Não retirado"
				: "Não tem direito";

	return (
		<Badge
			variant={variant}
			className={`w-28 justify-center whitespace-nowrap ${
				value === true ? "bg-green-700 hover:bg-green-700/80" : ""
			}`}
		>
			{label}
		</Badge>
	);
}
