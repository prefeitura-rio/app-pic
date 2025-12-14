import { memo } from "react";
import { Users, Loader2, AlertTriangle, CheckCircle, Home, BookOpen, Activity } from "lucide-react";
import {
  Dashboard,
  SmartFilterOptions,
  ProtocoloIndicador,
} from "../types";
import { StatCard } from "./StatCard";
import { DashboardFilterCard, DashboardFilterValues } from "./DashboardFilterCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/app/components/ui/card";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface OverviewTabProps {
  data: Dashboard | null;
  filterOptions: SmartFilterOptions;
  filters: DashboardFilterValues;
  onFilterChange: (filters: DashboardFilterValues) => void;
  onRefresh?: () => void;
  loading?: boolean;
}

// Componente para card de protocolo individual
const ProtocoloCard = ({ protocolo, loading }: { protocolo: ProtocoloIndicador; loading: boolean }) => {
  return (
    <Card className="relative">
      {loading && <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10"><Loader2 className="h-4 w-4 animate-spin" /></div>}
      <CardContent className="p-4">
        <p className="text-sm font-semibold mb-3 line-clamp-2">{protocolo.protocolo_descricao}</p>
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
      {/* SEÇÃO 3: RESULTADO DO PROGRAMA (gráfico de linha) */}
      {/* ===================================================================== */}
      {data.resultado_programa && data.resultado_programa.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Resultado do Programa</CardTitle>
            <CardDescription>
              Evolução mensal da completude de protocolos por dimensão
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart
                data={data.resultado_programa}
                margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="mes_label" />
                <YAxis label={{ value: '% Completude', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="todos"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  name="Todos os Protocolos"
                />
                <Line
                  type="monotone"
                  dataKey="saude"
                  stroke="#ef4444"
                  strokeWidth={2}
                  name="Protocolos da Saúde"
                />
                <Line
                  type="monotone"
                  dataKey="educacao"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  name="Protocolos da Educação"
                />
                <Line
                  type="monotone"
                  dataKey="assistencia"
                  stroke="#10b981"
                  strokeWidth={2}
                  name="Protocolos da Assistência"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* ===================================================================== */}
      {/* SEÇÃO 4: PARTICIPANTES POR SAFRA (gráfico de barras) */}
      {/* ===================================================================== */}
      {data.distribuicao_por_safra && data.distribuicao_por_safra.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Participantes por Safra</CardTitle>
            <CardDescription>
              Acompanhamento de entrada e saída de participantes do programa ao longo do tempo
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={450}>
              <BarChart
                data={data.distribuicao_por_safra}
                margin={{ top: 20, right: 30, left: 20, bottom: 40 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="safra"
                  label={{ value: 'Safra', position: 'insideBottom', offset: -5 }}
                />
                <YAxis 
                  label={{ value: 'Número de Participantes', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="bg-background border rounded-lg p-3 shadow-lg">
                          <p className="font-semibold mb-2">Safra: {data.safra}</p>
                          <p className="text-sm" style={{ color: '#3b82f6' }}>
                            Ativos: {data.total_ativos || 0}
                          </p>
                          <p className="text-sm" style={{ color: '#ef4444' }}>
                            Inativos: {data.total_inativos || 0}
                          </p>
                          <p className="text-sm text-muted-foreground mt-1">
                            Total: {data.total_participantes || 0}
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Legend wrapperStyle={{ paddingTop: '20px' }} />
                <Bar dataKey="total_ativos" fill="#3b82f6" name="Participantes Ativos" />
                <Bar dataKey="total_inativos" fill="#ef4444" name="Participantes Inativos" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

    </div>
  );
};

export const OverviewTab = memo(OverviewTabComponent);
