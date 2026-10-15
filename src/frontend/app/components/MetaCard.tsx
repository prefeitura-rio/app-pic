import { Card, CardContent } from "@/app/components/ui/card";
import { LucideIcon, TrendingDown, TrendingUp } from "lucide-react";
import { ReactNode } from "react";

interface MetaCardProps {
	title: string;
	value: string | number;
	description?: string;
	icon: LucideIcon | ReactNode;
	trend?: {
		value: string;
		isPositive: boolean;
		label?: string;
	};
	reference?: {
		label: string;
		value: string;
	};
	isLoading?: boolean;
}

// Formata número com separador de milhar (pt-BR)
const formatNumber = (value: string | number): string => {
	if (typeof value === "number") {
		return value.toLocaleString("pt-BR");
	}
	// Se for string que parece número, tenta formatar
	const num = parseFloat(value.replace(/[^\d.-]/g, ""));
	if (!isNaN(num) && /^\d+$/.test(value)) {
		return num.toLocaleString("pt-BR");
	}
	return value;
};

/**
 * Card de meta (padrão da seção "Meta de Regularidade"): título, ícone em
 * bolha circular, valor grande e rodapés opcionais: linha de referência
 * (valor + rótulo) e variação (seta + delta + rótulo).
 */
export function MetaCard({
	title,
	value,
	description,
	icon,
	trend,
	reference,
	isLoading = false,
}: MetaCardProps) {
	// Check if icon is a LucideIcon component or JSX element
	const isComponent = typeof icon === "function";
	const Icon = isComponent ? (icon as LucideIcon) : null;

	return (
		<Card className="border-2 transition-all hover:shadow-lg relative">
			{isLoading && <div className="loading-overlay"></div>}
			<CardContent className="p-6 flex-1 flex flex-col justify-center">
				<div className="flex items-start justify-between gap-3">
					<div className="flex-1 min-w-0">
						<p className="text-sm font-medium text-muted-foreground mb-1">
							{title}
						</p>
						<h3 className="text-3xl font-bold text-foreground mb-2">
							{formatNumber(value)}
						</h3>
					</div>
					<div className="rounded-full bg-primary/10 text-primary p-3 shrink-0">
						{Icon ? <Icon className="h-6 w-6" /> : <>{icon}</>}
					</div>
				</div>
				{reference && (
					<div className="flex items-center gap-1.5 flex-wrap">
						<span className="text-sm font-semibold text-blue-600 dark:text-blue-400">
							{reference.value}
						</span>
						<span className="text-xs uppercase tracking-wide text-muted-foreground">
							{reference.label}
						</span>
					</div>
				)}
				{trend && (
					<div className="flex items-center gap-1.5 flex-wrap">
						{trend.isPositive ? (
							<TrendingUp className="h-4 w-4 text-emerald-600 shrink-0" />
						) : (
							<TrendingDown className="h-4 w-4 text-red-600 shrink-0" />
						)}
						<span
							className={`text-sm font-semibold ${
								trend.isPositive ? "text-emerald-600" : "text-red-600"
							}`}
						>
							{trend.value}
						</span>
						{trend.label && (
							<span className="text-xs uppercase tracking-wide text-muted-foreground">
								{trend.label}
							</span>
						)}
					</div>
				)}
				{description && (
					<p className="text-sm text-muted-foreground leading-relaxed mt-2">
						{description}
					</p>
				)}
			</CardContent>
		</Card>
	);
}
