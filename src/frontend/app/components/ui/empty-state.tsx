import { LucideIcon, Search, FileX, Database, Filter, AlertCircle } from "lucide-react";
import { Button } from "@/app/components/ui/button";
import { cn } from "@/app/utils/utils";

/**
 * Empty State Component
 *
 * Componente reutilizável para estados vazios com ilustração e ações
 */
interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({
  icon: Icon = FileX,
  title,
  description,
  action,
  secondaryAction,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center p-8 text-center",
        className
      )}
    >
      {/* Icon */}
      <div className="mb-6 rounded-full bg-muted/50 p-6">
        <Icon className="h-12 w-12 text-muted-foreground" />
      </div>

      {/* Title */}
      <h3 className="text-lg font-semibold mb-2">{title}</h3>

      {/* Description */}
      {description && (
        <p className="text-sm text-muted-foreground max-w-md mb-6">
          {description}
        </p>
      )}

      {/* Actions */}
      {(action || secondaryAction) && (
        <div className="flex gap-3">
          {action && (
            <Button onClick={action.onClick}>{action.label}</Button>
          )}
          {secondaryAction && (
            <Button onClick={secondaryAction.onClick} variant="outline">
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * No Search Results
 *
 * Empty state específico para quando não há resultados de busca
 */
interface NoSearchResultsProps {
  searchTerm?: string;
  onClearSearch?: () => void;
}

export function NoSearchResults({
  searchTerm,
  onClearSearch,
}: NoSearchResultsProps) {
  return (
    <EmptyState
      icon={Search}
      title="Nenhum resultado encontrado"
      description={
        searchTerm
          ? `Não encontramos resultados para "${searchTerm}". Tente ajustar sua busca.`
          : "Tente usar termos diferentes ou remova alguns filtros."
      }
      action={
        onClearSearch
          ? {
              label: "Limpar Busca",
              onClick: onClearSearch,
            }
          : undefined
      }
    />
  );
}

/**
 * No Data Available
 *
 * Empty state para quando não há dados disponíveis
 */
interface NoDataProps {
  title?: string;
  description?: string;
  onRefresh?: () => void;
}

export function NoData({
  title = "Nenhum dado disponível",
  description = "Ainda não há dados para exibir aqui.",
  onRefresh,
}: NoDataProps) {
  return (
    <EmptyState
      icon={Database}
      title={title}
      description={description}
      action={
        onRefresh
          ? {
              label: "Atualizar",
              onClick: onRefresh,
            }
          : undefined
      }
    />
  );
}

/**
 * No Filters Match
 *
 * Empty state para quando filtros não retornam resultados
 */
interface NoFiltersMatchProps {
  onClearFilters: () => void;
}

export function NoFiltersMatch({ onClearFilters }: NoFiltersMatchProps) {
  return (
    <EmptyState
      icon={Filter}
      title="Nenhum item corresponde aos filtros"
      description="Tente ajustar ou remover alguns filtros para ver mais resultados."
      action={{
        label: "Limpar Filtros",
        onClick: onClearFilters,
      }}
    />
  );
}

/**
 * Error State
 *
 * Empty state para quando ocorre um erro ao carregar dados
 */
interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Erro ao carregar dados",
  description = "Ocorreu um erro ao tentar carregar as informações. Por favor, tente novamente.",
  onRetry,
}: ErrorStateProps) {
  return (
    <EmptyState
      icon={AlertCircle}
      title={title}
      description={description}
      action={
        onRetry
          ? {
              label: "Tentar Novamente",
              onClick: onRetry,
            }
          : undefined
      }
      className="text-destructive"
    />
  );
}

/**
 * Table Empty State
 *
 * Empty state específico para tabelas
 */
interface TableEmptyStateProps {
  message?: string;
  hasFilters?: boolean;
  onClearFilters?: () => void;
}

export function TableEmptyState({
  message = "Nenhum registro encontrado",
  hasFilters = false,
  onClearFilters,
}: TableEmptyStateProps) {
  if (hasFilters && onClearFilters) {
    return <NoFiltersMatch onClearFilters={onClearFilters} />;
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-4 rounded-full bg-muted/50 p-4">
        <FileX className="h-8 w-8 text-muted-foreground" />
      </div>
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
