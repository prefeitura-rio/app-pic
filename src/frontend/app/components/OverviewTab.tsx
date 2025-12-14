import { memo } from "react";
import { Users, Loader2, AlertTriangle, CheckCircle, Home, BookOpen, Activity, Heart, Clock, TrendingUp, PieChart as PieChartIcon } from "lucide-react";
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

// Overlay de loading reutilizável (mesmo estilo do StatCard)
const LoadingOverlay = ({ show }: { show: boolean }) => {
  if (!show) return null;
  return <div className="loading-overlay" />;
};

// Componente para card de protocolo individual
const ProtocoloCard = ({ protocolo, loading }: { protocolo: ProtocoloIndicador; loading: boolean }) => {
  return (
    <Card className="relative">
      <LoadingOverlay show={loading} />
      <CardContent className="p-4">
        <p className="text-sm font-semibold mb-3 line-clamp-2">{protocolo.protocolo_descricao}</p>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold">{protocolo.percentual_regular.toFixed(1)}%</span>
          <span className="text-xs text-muted-foreground">regular</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {protocolo.numerador.toLocaleString("pt-BR")} de {protocolo.denominador.toLocaleString("pt-BR")} participantes
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
          description={`${(data.total_regulares || 0).toLocaleString("pt-BR")} regulares`}
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
      {/* SEÇÃO 2: INDICADORES POR DIMENSÃO */}
      {/* ===================================================================== */}
      {data.protocolos && data.protocolos.length > 0 && (
        <div className="space-y-6">
          {/* Dimensão Assistência Social */}
          {protocolosPorSecretaria.SMAS.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Home className="h-5 w-5 text-green-600" />
                Dimensão Assistência Social
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {protocolosPorSecretaria.SMAS.map((protocolo) => (
                  <ProtocoloCard key={protocolo.protocolo_id} protocolo={protocolo} loading={loading} />
                ))}
              </div>
            </div>
          )}

          {/* Dimensão Educação */}
          {protocolosPorSecretaria.SME.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <BookOpen className="h-5 w-5 text-amber-600" />
                Dimensão Educação
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {protocolosPorSecretaria.SME.map((protocolo) => (
                  <ProtocoloCard key={protocolo.protocolo_id} protocolo={protocolo} loading={loading} />
                ))}
              </div>
            </div>
          )}

          {/* Dimensão Saúde */}
          {protocolosPorSecretaria.SMS.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Activity className="h-5 w-5 text-red-600" />
                Dimensão Saúde
              </h2>
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
        <Card className="relative">
          <LoadingOverlay show={loading} />
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
      {/* SEÇÃO 4: ANÁLISE DE TEMPO DE IRREGULARIDADE */}
      {/* ===================================================================== */}
      <div className="space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Clock className="h-6 w-6 text-primary" />
            Análise de Tempo de Irregularidade
          </h2>
          <p className="text-sm text-muted-foreground">
            Métricas de tempo de permanência em situação irregular
          </p>
        </div>

        {/* Cards de Tempo Médio por Dimensão */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="relative border-2 bg-card">
            <LoadingOverlay show={loading} />
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-2">
                <Activity className="h-4 w-4 text-primary" />
                <p className="text-sm font-medium text-muted-foreground">Tempo Médio Geral</p>
              </div>
              <div className="flex items-center justify-center h-12 text-muted-foreground">
                <Clock className="h-4 w-4 mr-2" />
                <span className="text-sm">Em desenvolvimento</span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative border-2 border-green-200 bg-green-50 dark:bg-green-950/20">
            <LoadingOverlay show={loading} />
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-2">
                <Home className="h-4 w-4 text-green-600" />
                <p className="text-sm font-medium text-muted-foreground">Assistência Social</p>
              </div>
              <div className="flex items-center justify-center h-12 text-muted-foreground">
                <Clock className="h-4 w-4 mr-2" />
                <span className="text-sm">Em desenvolvimento</span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative border-2 border-amber-200 bg-amber-50 dark:bg-amber-950/20">
            <LoadingOverlay show={loading} />
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="h-4 w-4 text-amber-600" />
                <p className="text-sm font-medium text-muted-foreground">Educação</p>
              </div>
              <div className="flex items-center justify-center h-12 text-muted-foreground">
                <Clock className="h-4 w-4 mr-2" />
                <span className="text-sm">Em desenvolvimento</span>
              </div>
            </CardContent>
          </Card>

          <Card className="relative border-2 border-red-200 bg-red-50 dark:bg-red-950/20">
            <LoadingOverlay show={loading} />
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-2">
                <Heart className="h-4 w-4 text-red-600" />
                <p className="text-sm font-medium text-muted-foreground">Saúde</p>
              </div>
              <div className="flex items-center justify-center h-12 text-muted-foreground">
                <Clock className="h-4 w-4 mr-2" />
                <span className="text-sm">Em desenvolvimento</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Gráficos de Análise de Tempo - Grid 2x1 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Distribuição por Faixas de Tempo */}
          <Card className="relative">
            <LoadingOverlay show={loading} />
            <CardHeader>
              <CardTitle className="text-lg">Distribuição por Tempo de Irregularidade</CardTitle>
              <CardDescription>
                Quantos participantes estão irregulares em cada faixa de tempo
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center h-[350px] text-muted-foreground">
                <div className="text-center">
                  <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium">Em desenvolvimento</p>
                  <p className="text-sm mt-2">Gráfico de barras: faixas 0-30, 31-60, 61-90, 90+ dias</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Taxa de Resolução Mensal */}
          <Card className="relative">
            <LoadingOverlay show={loading} />
            <CardHeader>
              <CardTitle className="text-lg">Taxa de Resolução Mensal</CardTitle>
              <CardDescription>
                Percentual de protocolos irregulares resolvidos por mês
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-center h-[350px] text-muted-foreground">
                <div className="text-center">
                  <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium">Em desenvolvimento</p>
                  <p className="text-sm mt-2">Gráfico de linha: evolução mensal da taxa de resolução</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Evolução do Tempo Médio de Irregularidade */}
        <Card className="relative">
          <LoadingOverlay show={loading} />
          <CardHeader>
            <CardTitle className="text-lg">Evolução do Tempo Médio de Irregularidade</CardTitle>
            <CardDescription>
              Como o tempo médio de irregularidade tem evoluído ao longo dos meses por dimensão
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center h-[400px] text-muted-foreground">
              <div className="text-center">
                <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-lg font-medium">Em desenvolvimento</p>
                <p className="text-sm mt-2">Gráfico de linha: tempo médio por dimensão ao longo dos meses</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ===================================================================== */}
      {/* SEÇÃO 5: PARTICIPANTES POR SAFRA E MOTIVOS DE SAÍDA (lado a lado) */}
      {/* ===================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Participantes por Safra */}
        <Card className="relative">
          <LoadingOverlay show={loading} />
          <CardHeader>
            <CardTitle className="text-xl">Participantes por Safra</CardTitle>
            <CardDescription>
              Acompanhamento de entrada e saída de participantes do programa ao longo do tempo
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.distribuicao_por_safra && data.distribuicao_por_safra.length > 0 ? (
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
                    label={{ value: 'Participantes', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const d = payload[0].payload;
                        return (
                          <div className="bg-background border rounded-lg p-3 shadow-lg">
                            <p className="font-semibold mb-2">Safra: {d.safra}</p>
                            <p className="text-sm" style={{ color: '#3b82f6' }}>
                              Ativos: {(d.total_ativos || 0).toLocaleString("pt-BR")}
                            </p>
                            <p className="text-sm" style={{ color: '#ef4444' }}>
                              Inativos: {(d.total_inativos || 0).toLocaleString("pt-BR")}
                            </p>
                            <p className="text-sm text-muted-foreground mt-1">
                              Total: {(d.total_participantes || 0).toLocaleString("pt-BR")}
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
            ) : (
              <div className="flex items-center justify-center h-[450px] text-muted-foreground">
                <div className="text-center">
                  <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium">Em desenvolvimento</p>
                  <p className="text-sm mt-2">Gráfico de barras: participantes ativos/inativos por safra</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Motivos de Saída do Programa */}
        <Card className="relative">
          <LoadingOverlay show={loading} />
          <CardHeader>
            <CardTitle className="text-xl flex items-center gap-2">
              <PieChartIcon className="h-5 w-5" />
              Motivos de Saída do Programa
            </CardTitle>
            <CardDescription>
              Distribuição dos motivos pelos quais participantes saíram do programa
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center h-[450px] text-muted-foreground">
              <div className="text-center">
                <PieChartIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-lg font-medium">Em desenvolvimento</p>
                <p className="text-sm mt-2">Gráfico de pizza: motivos de inativação dos participantes</p>
                <div className="mt-4 text-xs text-left max-w-md mx-auto">
                  <p className="font-medium mb-2">Motivos previstos:</p>
                  <ul className="list-disc list-inside space-y-1">
                    <li>Criança ultrapassou os 6 anos de idade</li>
                    <li>Saiu da base do CadÚnico Rio de Janeiro</li>
                    <li>Mulher com gravidez concluída</li>
                    <li>Óbito</li>
                  </ul>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

    </div>
  );
};

export const OverviewTab = memo(OverviewTabComponent);
