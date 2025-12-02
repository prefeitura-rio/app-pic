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
}

export function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  variant = "default"
}: StatCardProps) {
  // Check if icon is a LucideIcon component or JSX element
  const isComponent = typeof icon === 'function';
  const Icon = isComponent ? (icon as LucideIcon) : null;
  const variantStyles = {
    default: "bg-card border-border",
    success: "bg-emerald-50 border-emerald-500", // Tailwind 4 color names or standard palette? Assuming standard.
    warning: "bg-amber-50 border-amber-500",
    accent: "bg-accent/10 border-accent",
    destructive: "bg-red-50 border-red-500",
  };

  // Adjust icon styles to match the bg
  const iconVariantStyles = {
    default: "bg-primary text-primary-foreground",
    success: "bg-emerald-500 text-white",
    warning: "bg-amber-500 text-white",
    accent: "bg-accent text-accent-foreground",
    destructive: "bg-red-500 text-white",
  };

  return (
    <Card className={`${variantStyles[variant]} border-2 transition-all hover:shadow-lg`}>
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-sm font-medium text-muted-foreground mb-1">{title}</p>
            <h3 className="text-3xl font-bold text-foreground mb-2">{value}</h3>
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
            {Icon ? <Icon className="h-6 w-6" /> : icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
