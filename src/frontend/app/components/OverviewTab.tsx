import { memo, useCallback } from "react";
import { Users, Loader2, AlertTriangle, CheckCircle, Home, BookOpen, Activity, Heart, Clock, TrendingUp, PieChart as PieChartIcon } from "lucide-react";
import {
  Dashboard,
  DashboardFilterValues,
  ProtocoloIndicador,
} from "../types";
import { StatCard } from "./StatCard";
import { DashboardFilterCard } from "./DashboardFilterCard";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/app/components/ui/card";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// Cores para o gráfico de pizza (ordem: crianca=vermelho, cadunico=amarelo, gravidez=verde, obito=azul)
const PIE_COLORS = [
  "#ef4444", // red - crianca ultrapassou os 6 anos
  "#f59e0b", // amber - saiu da base do CadÚnico
  "#10b981", // green - mulher com gravidez concluida
  "#3b82f6", // blue - obito
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#84cc16", // lime
];

interface OverviewTabProps {
  data: Dashboard | null;
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
  filters,
  onFilterChange,
  onRefresh,
  loading = false,
}: OverviewTabProps) => {

  /**
   * Download dos dados do dashboard como JSON
   * Nome do arquivo: visao_geral_YYYY_MM_DD_HH_MM_SS.json
   */
  const handleDownloadJson = useCallback(() => {
    if (!data) return;

    // Gerar timestamp no formato snake_case
    const now = new Date();
    const pad = (n: number) => n.toString().padStart(2, "0");
    const timestamp = `${now.getFullYear()}_${pad(now.getMonth() + 1)}_${pad(now.getDate())}_${pad(now.getHours())}_${pad(now.getMinutes())}_${pad(now.getSeconds())}`;
    const filename = `visao_geral_${timestamp}.json`;

    // Converter dados para JSON
    const jsonString = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonString], { type: "application/json" });

    // Criar link de download e acionar
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [data]);

  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-primary mb-4" />
        <p className="text-base font-semibold">Carregando indicadores...</p>
        <p className="text-sm text-muted-foreground mt-2 max-w-sm">
          Agregando métricas por secretaria, safra e protocolo. Isso pode
          levar alguns segundos na primeira abertura.
        </p>
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

  // Determinar quais seções mostrar baseado no filtro de secretaria
  const selectedSecretaria = filters.secretaria;
  const showSMAS = !selectedSecretaria || selectedSecretaria === "SMAS";
  const showSME = !selectedSecretaria || selectedSecretaria === "SME";
  const showSMS = !selectedSecretaria || selectedSecretaria === "SMS";

  return (
    <div className="space-y-8">
      {/* Filtros do Dashboard */}
      <DashboardFilterCard
        filters={filters}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
        onDownload={handleDownloadJson}
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
          {showSMAS && protocolosPorSecretaria.SMAS.length > 0 && (
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
          {showSME && protocolosPorSecretaria.SME.length > 0 && (
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
          {showSMS && protocolosPorSecretaria.SMS.length > 0 && (
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
                {showSMAS && (
                  <Line
                    type="monotone"
                    dataKey="assistencia"
                    stroke="#10b981"
                    strokeWidth={2}
                    name="Protocolos da Assistência"
                  />
                )}
                {showSME && (
                  <Line
                    type="monotone"
                    dataKey="educacao"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    name="Protocolos da Educação"
                  />
                )}
                {showSMS && (
                  <Line
                    type="monotone"
                    dataKey="saude"
                    stroke="#ef4444"
                    strokeWidth={2}
                    name="Protocolos da Saúde"
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="todos"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  name="Todos os Protocolos"
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
        {data.tempo_medio_irregularidade && data.tempo_medio_irregularidade.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {data.tempo_medio_irregularidade
              .filter(item => {
                if (item.secretaria === "geral") return true;
                if (item.secretaria === "smas" && showSMAS) return true;
                if (item.secretaria === "sme" && showSME) return true;
                if (item.secretaria === "sms" && showSMS) return true;
                return false;
              })
              .map((item) => {
                const iconMap: Record<string, { icon: typeof Activity; color: string; bgClass: string }> = {
                  geral: { icon: Activity, color: "text-primary", bgClass: "bg-card border-border" },
                  smas: { icon: Home, color: "text-success", bgClass: "bg-success/10" },
                  sme: { icon: BookOpen, color: "text-warning", bgClass: "bg-warning/10" },
                  sms: { icon: Heart, color: "text-destructive", bgClass: "bg-destructive/10" },
                };
                const { icon: IconComponent, color, bgClass } = iconMap[item.secretaria] || iconMap.geral;

                return (
                  <Card key={item.secretaria} className={`relative border-2 ${bgClass}`}>
                    <LoadingOverlay show={loading} />
                    <CardContent className="p-6">
                      <div className="flex items-center gap-2 mb-2">
                        <IconComponent className={`h-4 w-4 ${color}`} />
                        <p className="text-sm font-medium text-muted-foreground">{item.secretaria_label}</p>
                      </div>
                      <p className="text-3xl font-bold text-foreground mb-1">
                        {item.tempo_medio_dias.toFixed(0)} dias
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {item.total_irregulares.toLocaleString("pt-BR")} alertas
                      </p>
                    </CardContent>
                  </Card>
                );
              })}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="relative border-2 bg-card border-border">
              <LoadingOverlay show={loading} />
              <CardContent className="p-6">
                <div className="flex items-center gap-2 mb-2">
                  <Activity className="h-4 w-4 text-primary" />
                  <p className="text-sm font-medium text-muted-foreground">Tempo Médio Geral</p>
                </div>
                <div className="flex items-center justify-center h-12 text-muted-foreground">
                  <Clock className="h-4 w-4 mr-2" />
                  <span className="text-sm">Sem dados</span>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Gráficos de Análise de Tempo - Grid 2x1 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Distribuição por Faixas de Tempo (Histograma) */}
          <Card className="relative">
            <LoadingOverlay show={loading} />
            <CardHeader>
              <CardTitle className="text-lg">Distribuição por Tempo de Irregularidade</CardTitle>
              <CardDescription>
                Quantos participantes estão irregulares em cada faixa de tempo
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.distribuicao_tempo_irregularidade && data.distribuicao_tempo_irregularidade.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart
                    data={data.distribuicao_tempo_irregularidade}
                    margin={{ top: 20, right: 30, left: 20, bottom: 40 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="faixa_label" />
                    <YAxis />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const d = payload[0].payload;
                          return (
                            <div className="bg-background border rounded-lg p-3 shadow-lg">
                              <p className="font-semibold mb-2">{d.faixa_label}</p>
                              <p className="text-sm">Participantes: {d.count.toLocaleString("pt-BR")}</p>
                              <p className="text-sm">Percentual: {d.percentual.toFixed(1)}%</p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Bar dataKey="count" name="Participantes">
                      <Cell fill="#10b981" />
                      <Cell fill="#f59e0b" />
                      <Cell fill="#ef4444" />
                      <Cell fill="#991b1b" />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-[350px] text-muted-foreground">
                  <div className="text-center">
                    <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p className="text-lg font-medium">Sem dados</p>
                    <p className="text-sm mt-2">Nenhum dado de tempo de irregularidade disponível</p>
                  </div>
                </div>
              )}
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
              {data.taxa_resolucao_mensal && data.taxa_resolucao_mensal.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart
                    data={data.taxa_resolucao_mensal}
                    margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="mes_label" />
                    <YAxis label={{ value: '% Resolvidos', angle: -90, position: 'insideLeft' }} />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const d = payload[0].payload;
                          return (
                            <div className="bg-background border rounded-lg p-3 shadow-lg">
                              <p className="font-semibold mb-2">Mês: {d.mes_label}</p>
                              {showSMAS && <p className="text-sm" style={{ color: '#10b981' }}>Assistência: {d.assistencia.toFixed(1)}%</p>}
                              {showSME && <p className="text-sm" style={{ color: '#f59e0b' }}>Educação: {d.educacao.toFixed(1)}%</p>}
                              {showSMS && <p className="text-sm" style={{ color: '#ef4444' }}>Saúde: {d.saude.toFixed(1)}%</p>}
                              <p className="text-sm" style={{ color: '#8b5cf6' }}>Geral: {d.todos.toFixed(1)}%</p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Legend />
                    {showSMAS && (
                      <Line type="monotone" dataKey="assistencia" stroke="#10b981" strokeWidth={2} name="Assistência" />
                    )}
                    {showSME && (
                      <Line type="monotone" dataKey="educacao" stroke="#f59e0b" strokeWidth={2} name="Educação" />
                    )}
                    {showSMS && (
                      <Line type="monotone" dataKey="saude" stroke="#ef4444" strokeWidth={2} name="Saúde" />
                    )}
                    <Line type="monotone" dataKey="todos" stroke="#8b5cf6" strokeWidth={2} name="Taxa Geral" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-[350px] text-muted-foreground">
                  <div className="text-center">
                    <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p className="text-lg font-medium">Sem dados</p>
                    <p className="text-sm mt-2">Nenhum dado de taxa de resolução disponível</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* SEÇÃO 5: PARTICIPANTES POR SAFRA E MOTIVOS DE SAÍDA (lado a lado) */}
      {/* ===================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Participantes por Mês de Ingresso */}
        <Card className="relative">
          <LoadingOverlay show={loading} />
          <CardHeader>
            <CardTitle className="text-xl">Participantes por Mês de Ingresso no Programa</CardTitle>
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
                    label={{ value: 'Mês de Ingresso', position: 'insideBottom', offset: -5 }}
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
                            <p className="font-semibold mb-2">Mês de Ingresso: {d.safra}</p>
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
            {data.distribuicao_motivo_saida && data.distribuicao_motivo_saida.length > 0 ? (
              <div className="space-y-4">
                <ResponsiveContainer width="100%" height={380}>
                  <PieChart>
                    <Pie
                      data={data.distribuicao_motivo_saida as unknown as Record<string, unknown>[]}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      outerRadius={130}
                      innerRadius={65}
                      fill="#8884d8"
                      dataKey="total"
                      nameKey="motivo"
                      label={({ percent = 0, cx = 0, cy = 0, midAngle = 0, outerRadius = 0, index = 0 }) => {
                        const RADIAN = Math.PI / 180;
                        // Ponto de saída da fatia
                        const startX = cx + (outerRadius + 5) * Math.cos(-midAngle * RADIAN);
                        const startY = cy + (outerRadius + 5) * Math.sin(-midAngle * RADIAN);
                        // Distância maior para labels pequenos evitarem sobreposição
                        const radius = percent < 0.05 ? outerRadius + 45 : outerRadius + 30;
                        const endX = cx + radius * Math.cos(-midAngle * RADIAN);
                        let endY = cy + radius * Math.sin(-midAngle * RADIAN);
                        // Ajuste para o label verde (index 2) ficar mais abaixo
                        if (index === 2) endY += 15;
                        const color = PIE_COLORS[index % PIE_COLORS.length];
                        return (
                          <g>
                            <line
                              x1={startX}
                              y1={startY + (index === 2 ? 7 : 0)}
                              x2={endX}
                              y2={endY}
                              stroke={color}
                              strokeWidth={1.5}
                            />
                            <text
                              x={endX}
                              y={endY}
                              fill={color}
                              textAnchor={endX > cx ? "start" : "end"}
                              dominantBaseline="central"
                              fontSize={16}
                              fontWeight={600}
                            >
                              {(percent * 100).toFixed(1)}%
                            </text>
                          </g>
                        );
                      }}
                    >
                      {data.distribuicao_motivo_saida.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const d = payload[0].payload;
                          const total = data.distribuicao_motivo_saida.reduce((acc, item) => acc + (item.total || 0), 0);
                          const percent = total > 0 ? ((d.total || 0) / total * 100).toFixed(1) : 0;
                          return (
                            <div className="bg-background border rounded-lg p-3 shadow-lg">
                              <p className="font-semibold mb-1">{d.motivo}</p>
                              <p className="text-sm">
                                {(d.total || 0).toLocaleString("pt-BR")} participantes ({percent}%)
                              </p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Legenda customizada */}
                <div className="space-y-2 px-4">
                  {data.distribuicao_motivo_saida.map((item, index) => {
                    const total = data.distribuicao_motivo_saida.reduce((acc, i) => acc + (i.total || 0), 0);
                    const percent = total > 0 ? ((item.total || 0) / total * 100).toFixed(1) : 0;
                    const color = PIE_COLORS[index % PIE_COLORS.length];
                    return (
                      <div key={index} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          <div
                            className="w-3 h-3 rounded-full flex-shrink-0"
                            style={{ backgroundColor: color }}
                          />
                          <span style={{ color }}>{item.motivo}</span>
                        </div>
                        <span className="font-medium" style={{ color }}>
                          {(item.total || 0).toLocaleString("pt-BR")} ({percent}%)
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-[450px] text-muted-foreground">
                <div className="text-center">
                  <PieChartIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium">Sem dados de saída</p>
                  <p className="text-sm mt-2">Nenhum participante inativo no período selecionado</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

    </div>
  );
};

export const OverviewTab = memo(OverviewTabComponent);
