"use client";

import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/app/components/ui/tooltip";
import { useAnonymizeData } from "@/app/hooks/useAnonymizeData";

export function AnonymizeToggle() {
	const { isAnonymized, setIsAnonymized } = useAnonymizeData();

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button
					variant="ghost"
					size="icon"
					className={`rounded-full text-primary-foreground hover:bg-primary-foreground/20 hover:text-primary-foreground ${
						isAnonymized ? "bg-primary-foreground/20" : ""
					}`}
					onClick={() => setIsAnonymized(!isAnonymized)}
					aria-label={
						isAnonymized
							? "Desativar anonimização de dados"
							: "Ativar anonimização de dados"
					}
					aria-pressed={isAnonymized}
				>
					{isAnonymized ? (
						<EyeOff className="h-5 w-5" />
					) : (
						<Eye className="h-5 w-5" />
					)}
					<span className="sr-only">Anonimizar dados</span>
				</Button>
			</TooltipTrigger>
			<TooltipContent>
				{isAnonymized
					? "Exibir dados completos"
					: "Ocultar dados sensíveis"}
			</TooltipContent>
		</Tooltip>
	);
}
