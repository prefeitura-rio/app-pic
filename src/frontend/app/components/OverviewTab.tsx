import { memo } from "react";
import { Users, Loader2, AlertTriangle, CheckCircle } from "lucide-react";
import {
  Dashboard,
  SmartFilterOptions,
} from "../types";
import { StatCard } from "./StatCard";
import { DashboardFilterCard, DashboardFilterValues } from "./DashboardFilterCard";
import { Card, CardContent } from "@/app/components/ui/card";

interface OverviewTabProps {
  data: Dashboard | null;
  filterOptions: SmartFilterOptions;
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

const OverviewTabComponent = ({
  data,
  filterOptions,
  filters,
  onFilterChange,
  onRefresh,
  loading = false,
}: OverviewTabProps) => {

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Nenhum dado disponível</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Filtros do Dashboard */}
      <DashboardFilterCard
        filterOptions={filterOptions}
        filters={filters}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
        loading={loading}
      />

      {/* Indicadores Principais */}
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-foreground">Indicadores Principais</h2>
        <p className="text-sm text-muted-foreground">
          Visão macro para lideranças das secretarias (Saúde, Educação, Assistência e Casa Civil)
        </p>
      </div>

      {/* Métricas Principais */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          title="Total de Participantes"
          value={data.total_participantes_geral || 0}
          description={`${data.total_participantes_ativos || 0} ativos`}
          icon={<Users className="h-6 w-6" />}
          variant="default"
          isLoading={loading}
        />
        <StatCard
          title="% Regular"
          value={`${(data.percentual_regular || 0).toFixed(1)}%`}
          description="Cumprindo todos os protocolos"
          icon={<CheckCircle className="h-6 w-6" />}
          variant="success"
          isLoading={loading}
        />
        <StatCard
          title="% Irregular"
          value={`${(data.percentual_irregular || 0).toFixed(1)}%`}
          description="Com protocolos irregulares"
          icon={<AlertTriangle className="h-6 w-6" />}
          variant="destructive"
          isLoading={loading}
        />
      </div>

      {/* Completude por Dimensão */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          Completude por Dimensão
        </h3>
        <p className="text-sm text-muted-foreground">
          Percentual de participantes cumprindo todos os protocolos de cada dimensão
        </p>
        <div className="grid gap-4 md:grid-cols-3">
          {/* Assistência Social */}
          <Card className="bg-muted/50 relative">
            {loading && <div className="loading-overlay" />}
            <CardContent className="p-4">
              <p className="text-sm font-medium text-muted-foreground">Assistência Social</p>
              <p className="text-3xl font-bold mt-1">
                {(data.assistencia_completude_percentual || 0).toFixed(1)}%
              </p>
            </CardContent>
          </Card>

          {/* Educação */}
          <Card className="bg-muted/50 relative">
            {loading && <div className="loading-overlay" />}
            <CardContent className="p-4">
              <p className="text-sm font-medium text-muted-foreground">Educação</p>
              <p className="text-3xl font-bold mt-1">
                {(data.educacao_completude_percentual || 0).toFixed(1)}%
              </p>
            </CardContent>
          </Card>

          {/* Saúde */}
          <Card className="bg-muted/50 relative">
            {loading && <div className="loading-overlay" />}
            <CardContent className="p-4">
              <p className="text-sm font-medium text-muted-foreground">Saúde</p>
              <p className="text-3xl font-bold mt-1">
                {(data.saude_completude_percentual || 0).toFixed(1)}%
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export const OverviewTab = memo(OverviewTabComponent);
