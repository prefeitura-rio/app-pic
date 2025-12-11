import { memo } from "react";
import { Users, Loader2, AlertTriangle, CheckCircle, Home, BookOpen, Activity } from "lucide-react";
import {
  Dashboard,
  SmartFilterOptions,
  ProtocoloIndicador,
} from "../types";
import { StatCard } from "./StatCard";
import { DashboardFilterCard, DashboardFilterValues } from "./DashboardFilterCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import dynamic from "next/dynamic";

// Lazy load dos gráficos (só carrega quando necessário)
const LineChart = dynamic(() => import("recharts").then(mod => ({ default: mod.LineChart })), { ssr: false });
const Line = dynamic(() => import("recharts").then(mod => ({ default: mod.Line })), { ssr: false });
const XAxis = dynamic(() => import("recharts").then(mod => ({ default: mod.XAxis })), { ssr: false });
const YAxis = dynamic(() => import("recharts").then(mod => ({ default: mod.YAxis })), { ssr: false });
const CartesianGrid = dynamic(() => import("recharts").then(mod => ({ default: mod.CartesianGrid })), { ssr: false });
const Tooltip = dynamic(() => import("recharts").then(mod => ({ default: mod.Tooltip })), { ssr: false });
const Legend = dynamic(() => import("recharts").then(mod => ({ default: mod.Legend })), { ssr: false });
const ResponsiveContainer = dynamic(() => import("recharts").then(mod => ({ default: mod.ResponsiveContainer })), { ssr: false });

interface OverviewTabProps {
  data: Dashboard | null;
  filterOptions: SmartFilterOptions;
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

// Mapeamento de secretarias para cores e ícones
const SECRETARIA_CONFIG: Record<string, { color: string; bgColor: string; icon: React.ElementType; label: string }> = {
  SMAS: { color: "text-green-600", bgColor: "bg-green-50 dark:bg-green-950/20", icon: Home, label: "Assistência Social" },
  SME: { color: "text-amber-600", bgColor: "bg-amber-50 dark:bg-amber-950/20", icon: BookOpen, label: "Educação" },
  SMS: { color: "text-red-600", bgColor: "bg-red-50 dark:bg-red-950/20", icon: Activity, label: "Saúde" },
};

// Componente para card de protocolo individual
const ProtocoloCard = ({ protocolo, loading }: { protocolo: ProtocoloIndicador; loading: boolean }) => {
  const config = SECRETARIA_CONFIG[protocolo.protocolo_secretaria] || SECRETARIA_CONFIG.SMS;
  const Icon = config.icon;

  return (
    <Card className={`relative ${config.bgColor} border-l-4`} style={{ borderLeftColor: `var(--${protocolo.protocolo_secretaria.toLowerCase()}-color, currentColor)` }}>
      {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10"><Loader2 className="h-4 w-4 animate-spin" /></div>}
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Icon className={`h-4 w-4 ${config.color}`} />
          <p className="text-xs font-medium text-muted-foreground">{config.label}</p>
        </div>
        <p className="text-sm font-semibold mb-2 line-clamp-2">{protocolo.protocolo_descricao}</p>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold">{protocolo.percentual_regular.toFixed(1)}%</span>
          <span className="text-xs text-muted-foreground">regular</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {protocolo.numerador} de {protocolo.denominador} participantes
        </p>
      </CardContent>
    </Card>
  );
};

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

  // Agrupar protocolos por secretaria
  const protocolosPorSecretaria = {
    SMAS: data.protocolos?.filter(p => p.protocolo_secretaria === "SMAS") || [],
    SME: data.protocolos?.filter(p => p.protocolo_secretaria === "SME") || [],
    SMS: data.protocolos?.filter(p => p.protocolo_secretaria === "SMS") || [],
  };

  // Verificar se temos dados para o gráfico de evolução
  const hasResultadoPrograma = data.resultado_programa && data.resultado_programa.length > 0;

  return (
    <div className="space-y-8">
      {/* Filtros do Dashboard */}
      <DashboardFilterCard
        filterOptions={filterOptions}
        filters={filters}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
        loading={loading}
      />

      {/* ===================================================================== */}
      {/* SEÇÃO 1: INDICADORES PRINCIPAIS */}
      {/* ===================================================================== */}
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-foreground">Indicadores Principais</h2>
        <p className="text-sm text-muted-foreground">
          Visão macro para lideranças das secretarias (Saúde, Educação, Assistência e Casa Civil)
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          title="Total de Participantes"
          value={data.total_participantes || 0}
          description={`${data.total_regulares || 0} regulares`}
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

      {/* ===================================================================== */}
      {/* SEÇÃO 2: INDICADORES POR PROTOCOLO */}
      {/* ===================================================================== */}
      {data.protocolos && data.protocolos.length > 0 && (
        <div className="space-y-6">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-foreground">Indicadores por Protocolo</h2>
            <p className="text-sm text-muted-foreground">
              Percentual de regularidade em cada protocolo monitorado
            </p>
          </div>

          {/* Assistência Social */}
          {protocolosPorSecretaria.SMAS.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Home className="h-5 w-5 text-green-600" />
                Assistência Social (SMAS)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {protocolosPorSecretaria.SMAS.map((protocolo) => (
                  <ProtocoloCard key={protocolo.protocolo_id} protocolo={protocolo} loading={loading} />
                ))}
              </div>
            </div>
          )}

          {/* Educação */}
          {protocolosPorSecretaria.SME.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <BookOpen className="h-5 w-5 text-amber-600" />
                Educação (SME)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {protocolosPorSecretaria.SME.map((protocolo) => (
                  <ProtocoloCard key={protocolo.protocolo_id} protocolo={protocolo} loading={loading} />
                ))}
              </div>
            </div>
          )}

          {/* Saúde */}
          {protocolosPorSecretaria.SMS.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <Activity className="h-5 w-5 text-red-600" />
                Saúde (SMS)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {protocolosPorSecretaria.SMS.map((protocolo) => (
                  <ProtocoloCard key={protocolo.protocolo_id} protocolo={protocolo} loading={loading} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* SEÇÃO 3: RESULTADO DO PROGRAMA (Gráfico de Evolução) */}
      {/* ===================================================================== */}
      {hasResultadoPrograma && (
        <div className="space-y-4">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-foreground">Resultado do Programa</h2>
            <p className="text-sm text-muted-foreground">
              Evolução mensal da completude de protocolos por dimensão
            </p>
          </div>

          <Card className="relative">
            {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10"><Loader2 className="h-6 w-6 animate-spin" /></div>}
            <CardHeader>
              <CardTitle className="text-lg">Evolução da Completude (%)</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart
                  data={data.resultado_programa}
                  margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                  <XAxis
                    dataKey="mes_label"
                    tick={{ fontSize: 12 }}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 12 }}
                    tickLine={false}
                    label={{ value: '% Completude', angle: -90, position: 'insideLeft', fontSize: 12 }}
                  />
                  <Tooltip
                    formatter={(value) => [`${Number(value).toFixed(1)}%`, '']}
                    labelFormatter={(label) => `Mês: ${label}`}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="todos"
                    stroke="#8b5cf6"
                    strokeWidth={3}
                    name="Todos"
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="assistencia"
                    stroke="#22c55e"
                    strokeWidth={2}
                    name="Assistência Social"
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="educacao"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    name="Educação"
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="saude"
                    stroke="#ef4444"
                    strokeWidth={2}
                    name="Saúde"
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export const OverviewTab = memo(OverviewTabComponent);
