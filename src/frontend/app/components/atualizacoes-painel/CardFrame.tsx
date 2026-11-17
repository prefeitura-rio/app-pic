import type { ReactNode } from "react";

import { cn } from "@/app/utils/utils";

/**
 * Moldura dos cards da linha 2 (decisão B, §3.5 da doc): flex-col em altura
 * total — a LINHA define a altura, não o card; indicadores pinados na base.
 * Mesma aparência do `ui/card`, sem o `py-6`/`gap-6` (o rodapé é exato).
 */
export function CardFrame({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-card text-card-foreground flex h-full flex-col rounded-xl border shadow-sm",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Corpo com altura livre — absorve a sobra da linha (flex-1). */
export function CardCorpo({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("flex-1 px-6 pt-5", className)}>{children}</div>;
}

/**
 * Rodapé padronizado de 101px (decisão B): slot de gráfico (60px) + gap (8px)
 * + eixo/legenda (13px) = 81px de conteúdo + 20px de respiro inferior.
 * Números grandes das linhas alinham na horizontal.
 */
export function CardRodape({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-[101px] flex-col justify-end gap-2 px-6 pb-5",
        className,
      )}
    >
      {children}
    </div>
  );
}
