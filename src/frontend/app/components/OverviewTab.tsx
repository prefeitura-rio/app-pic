import { memo, useMemo } from "react";
import { Baby, Heart, Activity, Users, TrendingUp, Home, Loader2, AlertTriangle, CheckCircle } from "lucide-react";
import { Skeleton } from "@/app/components/ui/skeleton";
import {
  Dashboard,
  SmartFilterOptions,
  DashboardFilters,
} from "../types";
import { StatCard } from "./StatCard";
import { FilterCard } from "./FilterCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import dynamic from "next/dynamic";

// OTIMIZAÇÃO CRÍTICA: Lazy load dos gráficos (só carrega quando necessário)
const BarChart = dynamic(() => import("recharts").then(mod => ({ default: mod.BarChart })), { ssr: false });
const Bar = dynamic(() => import("recharts").then(mod => ({ default: mod.Bar })), { ssr: false });
const XAxis = dynamic(() => import("recharts").then(mod => ({ default: mod.XAxis })), { ssr: false });
const YAxis = dynamic(() => import("recharts").then(mod => ({ default: mod.YAxis })), { ssr: false });
const CartesianGrid = dynamic(() => import("recharts").then(mod => ({ default: mod.CartesianGrid })), { ssr: false });
const Tooltip = dynamic(() => import("recharts").then(mod => ({ default: mod.Tooltip })), { ssr: false });
const Legend = dynamic(() => import("recharts").then(mod => ({ default: mod.Legend })), { ssr: false });
const ResponsiveContainer = dynamic(() => import("recharts").then(mod => ({ default: mod.ResponsiveContainer })), { ssr: false });
const PieChart = dynamic(() => import("recharts").then(mod => ({ default: mod.PieChart })), { ssr: false });
const Pie = dynamic(() => import("recharts").then(mod => ({ default: mod.Pie })), { ssr: false });
const Cell = dynamic(() => import("recharts").then(mod => ({ default: mod.Cell })), { ssr: false });
const LineChart = dynamic(() => import("recharts").then(mod => ({ default: mod.LineChart })), { ssr: false });
const Line = dynamic(() => import("recharts").then(mod => ({ default: mod.Line })), { ssr: false });

interface OverviewTabProps {
  data: Dashboard | null;
  filterOptions: SmartFilterOptions;
  filters: DashboardFilters;
  onFilterChange: (filters: DashboardFilters) => void;
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

  // Memoizar dados dos gráficos para evitar re-processamento
  const chartData = useMemo(() => {
    const pieColors = ["#0088FE", "#00C49F", "#FFBB28", "#FF8042"];
    const grupoData = (data?.distribuicao_por_grupo || []).map((item, index) => ({
      ...item,
      fill: pieColors[index % pieColors.length]
    }));

    return {
      grupoDistribution: grupoData,
      topBairros: data?.top_bairros || [],
      safraDistribution: data?.distribuicao_por_safra || [],
      motivosSaida: data?.distribuicao_motivo_saida || [],
    };
  }, [data]);

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
    <div className="space-y-8">
      <FilterCard
        filterOptions={filterOptions}
        filters={filters}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
        loading={loading}
      />

      {loading && !data && (
        <>
          {/* Skeleton for Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <Skeleton className="h-4 w-32" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-24 mb-2" />
                  <Skeleton className="h-3 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Skeleton for Protocol Stats */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <Skeleton className="h-4 w-32" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-24 mb-2" />
                  <Skeleton className="h-3 w-20" />
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Skeleton for Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-6 w-40" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-[300px] w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {data && (
        <>
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
              description={`${data.total_participantes_ativos || 0} ativos • ${data.total_participantes_inativos || 0} inativos`}
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

          {/* Dimensões - Completude apenas */}
          <div className="space-y-3">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              📊 Completude por Dimensão
            </h3>
            <p className="text-sm text-muted-foreground">
              Percentual de participantes cumprindo todos os protocolos de cada dimensão
            </p>
            <div className="grid gap-3 md:grid-cols-3">
              <Card className="bg-muted relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardContent className="p-4">
                  <p className="text-sm font-medium">🏠 Assistência Social</p>
                  <p className="text-2xl font-bold mt-1">
                    {(data.assistencia_completude_percentual || 0).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {data.assistencia_completude_total || 0} de {data.total_participantes_geral || 0} participantes
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardContent className="p-4">
                  <p className="text-sm font-medium">📚 Educação</p>
                  <p className="text-2xl font-bold mt-1">
                    {(data.educacao_completude_percentual || 0).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {data.educacao_completude_total || 0} de {data.total_participantes_geral || 0} participantes
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardContent className="p-4">
                  <p className="text-sm font-medium">❤️ Saúde</p>
                  <p className="text-2xl font-bold mt-1">
                    {(data.saude_completude_percentual || 0).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {data.saude_completude_total || 0} de {data.total_participantes_geral || 0} participantes
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Resultado do Programa */}
          {data.resultado_programa && data.resultado_programa.length > 0 && (
            <Card className="border-2 hover:shadow-lg transition-shadow relative">
              {loading && (
                <div className="loading-overlay"></div>
              )}
              <CardHeader className="pb-3">
                <CardTitle className="text-lg font-semibold flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-primary" />
                  Resultado do Programa
                </CardTitle>
                <p className="text-xs text-muted-foreground">Evolução temporal da completude por dimensão</p>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={data.resultado_programa}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="mes" />
                    <YAxis domain={[0, 100]} />
                    <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="todos"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      name="Todos"
                      dot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="saude"
                      stroke="#ef4444"
                      strokeWidth={2}
                      name="Saúde"
                      dot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="educacao"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      name="Educação"
                      dot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="assistencia"
                      stroke="#10b981"
                      strokeWidth={2}
                      name="Assistência"
                      dot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Protocol Statistics - com overlay se loading */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Protocolos Totais"
              value={data.total_protocolos || 0}
              icon={<TrendingUp className="h-4 w-4" />}
              trend={{
                value: `${(data.percentual_protocolos_irregular || 0).toFixed(1)}% irregulares`,
                isPositive: false,
              }}
              isLoading={loading}
            />
            <StatCard
              title="Assistência Social"
              value={data.total_protocolos_smas || 0}
              icon={<Home className="h-4 w-4" />}
              trend={{
                value: `${(data.percentual_smas_irregular || 0).toFixed(1)}% irregulares`,
                isPositive: false,
              }}
              isLoading={loading}
            />
            <StatCard
              title="Educação"
              value={data.total_protocolos_sme || 0}
              icon={<Baby className="h-4 w-4" />}
              trend={{
                value: `${(data.percentual_sme_irregular || 0).toFixed(1)}% irregulares`,
                isPositive: false,
              }}
              isLoading={loading}
            />
            <StatCard
              title="Saúde"
              value={data.total_protocolos_sms || 0}
              icon={<Heart className="h-4 w-4" />}
              trend={{
                value: `${(data.percentual_sms_irregular || 0).toFixed(1)}% irregulares`,
                isPositive: false,
              }}
              isLoading={loading}
            />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Group Distribution */}
            {chartData.grupoDistribution.length > 0 && (
              <Card className="border-2 hover:shadow-lg transition-shadow relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg font-semibold flex items-center gap-2">
                    <Users className="h-5 w-5 text-primary" />
                    Distribuição por Grupo
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">Total de participantes por grupo</p>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={chartData.grupoDistribution}
                        dataKey="total_participantes"
                        nameKey="grupo"
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        label={(props: any) => `${(props.percent * 100).toFixed(1)}%`}
                        isAnimationActive={false}
                      />
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Top Bairros */}
            {chartData.topBairros.length > 0 && (
              <Card className="border-2 hover:shadow-lg transition-shadow relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg font-semibold flex items-center gap-2">
                    <Home className="h-5 w-5 text-primary" />
                    Top Bairros
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">Bairros com maior número de participantes</p>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={chartData.topBairros}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="bairro" angle={-45} textAnchor="end" height={100} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="total_participantes" fill="#8884d8" isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Safra Distribution - Participantes por Safra */}
            {chartData.safraDistribution.length > 0 && (
              <Card className="border-2 hover:shadow-lg transition-shadow relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg font-semibold flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-primary" />
                    Participantes por Safra
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">Distribuição de participantes ativos e inativos por safra</p>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={chartData.safraDistribution}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="safra" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="total_ativos" stackId="a" fill="#10b981" name="Ativos" isAnimationActive={false} />
                      <Bar dataKey="total_inativos" stackId="a" fill="#6b7280" name="Inativos" isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Motivos de Saída */}
            {chartData.motivosSaida.length > 0 && (
              <Card className="border-2 hover:shadow-lg transition-shadow relative">
                {loading && (
                  <div className="loading-overlay"></div>
                )}
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg font-semibold flex items-center gap-2">
                    <Activity className="h-5 w-5 text-primary" />
                    Motivos de Inativação
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">Principais motivos de saída do programa</p>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={chartData.motivosSaida}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="motivo" angle={-45} textAnchor="end" height={100} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="total" fill="#FF8042" isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
};

// Exportar com React.memo para evitar re-renders quando props não mudarem
export const OverviewTab = memo(OverviewTabComponent);
