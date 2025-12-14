import { Card, CardContent } from "@/app/components/ui/card";
import { LucideIcon } from "lucide-react";
import { ReactNode } from "react";

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: LucideIcon | ReactNode;
  trend?: {
    value: string;
    isPositive: boolean;
  };
  variant?: "default" | "success" | "warning" | "accent" | "destructive";
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

export function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  variant = "default",
  isLoading = false
}: StatCardProps) {
  // Check if icon is a LucideIcon component or JSX element
  const isComponent = typeof icon === 'function';
  const Icon = isComponent ? (icon as LucideIcon) : null;
  const variantStyles = {
    default: "bg-card border-border",
    success: "bg-success/10",
    warning: "bg-warning/10",
    accent: "bg-accent/10",
    destructive: "bg-destructive/10",
  };

  // Adjust icon styles to match the bg
  const iconVariantStyles = {
    default: "bg-primary text-primary-foreground",
    success: "bg-success text-success-foreground",
    warning: "bg-warning text-warning-foreground",
    accent: "bg-accent text-accent-foreground",
    destructive: "bg-destructive text-destructive-foreground",
  };

  return (
    <Card className={`${variantStyles[variant]} border-2 transition-all hover:shadow-lg relative`}>
      {isLoading && <div className="loading-overlay"></div>}
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-sm font-medium text-muted-foreground mb-1">{title}</p>
            <h3 className="text-3xl font-bold text-foreground mb-2">{formatNumber(value)}</h3>
            {description && (
              <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
            )}
            {trend && (
              <p className={`text-xs font-medium mt-1 ${trend.isPositive ? 'text-emerald-600' : 'text-amber-600'}`}>
                {trend.value}
              </p>
            )}
          </div>
          <div className={`${iconVariantStyles[variant]} p-3 rounded-lg shadow-md`}>
            {Icon ? <Icon className="h-6 w-6" /> : <>{icon}</>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
