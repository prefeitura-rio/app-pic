import { Loader2 } from "lucide-react";
import { cn } from "@/app/utils/utils";

/**
 * Loading Spinner Component
 *
 * Spinner reutilizável com diferentes tamanhos
 */
interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

export function LoadingSpinner({ size = "md", className }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-6 w-6",
    lg: "h-8 w-8",
    xl: "h-12 w-12",
  };

  return (
    <Loader2
      className={cn("animate-spin text-primary", sizeClasses[size], className)}
    />
  );
}

/**
 * Full Page Loading
 *
 * Loading state que ocupa a página inteira
 */
interface PageLoadingProps {
  message?: string;
}

export function PageLoading({ message = "Carregando..." }: PageLoadingProps) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4">
      <LoadingSpinner size="xl" />
      <p className="text-muted-foreground animate-pulse">{message}</p>
    </div>
  );
}

/**
 * Card Loading Skeleton
 *
 * Skeleton para cards de conteúdo
 */
export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-lg border bg-card p-6 space-y-3", className)}>
      <div className="h-4 bg-muted rounded animate-pulse w-3/4" />
      <div className="h-4 bg-muted rounded animate-pulse w-1/2" />
      <div className="h-4 bg-muted rounded animate-pulse w-5/6" />
    </div>
  );
}

/**
 * Table Loading Skeleton
 *
 * Skeleton para tabelas
 */
interface TableSkeletonProps {
  rows?: number;
  columns?: number;
  className?: string;
}

export function TableSkeleton({
  rows = 5,
  columns = 4,
  className
}: TableSkeletonProps) {
  return (
    <div className={cn("space-y-3", className)}>
      {/* Header */}
      <div className="flex gap-4">
        {Array.from({ length: columns }).map((_, i) => (
          <div key={i} className="h-4 bg-muted rounded animate-pulse flex-1" />
        ))}
      </div>

      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-4">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <div
              key={colIndex}
              className="h-4 bg-muted/50 rounded animate-pulse flex-1"
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Inline Loading
 *
 * Loading state inline com mensagem
 */
interface InlineLoadingProps {
  message?: string;
  size?: "sm" | "md" | "lg";
}

export function InlineLoading({
  message = "Carregando...",
  size = "sm"
}: InlineLoadingProps) {
  return (
    <div className="flex items-center gap-2">
      <LoadingSpinner size={size} />
      <span className="text-sm text-muted-foreground">{message}</span>
    </div>
  );
}

/**
 * Button Loading State
 *
 * Loading state para uso dentro de botões
 */
export function ButtonLoading() {
  return <Loader2 className="h-4 w-4 animate-spin" />;
}

/**
 * Overlay Loading
 *
 * Loading overlay que cobre um container específico
 */
interface OverlayLoadingProps {
  message?: string;
  show: boolean;
}

export function OverlayLoading({ message, show }: OverlayLoadingProps) {
  if (!show) return null;

  return (
    <div className="absolute inset-0 bg-background/80 backdrop-blur-sm flex flex-col items-center justify-center gap-4 z-50 rounded-lg">
      <LoadingSpinner size="lg" />
      {message && (
        <p className="text-sm text-muted-foreground animate-pulse">{message}</p>
      )}
    </div>
  );
}
