import { memo, useMemo, useCallback } from "react";
import { Baby, Heart, Activity, Users, Filter, TrendingUp, Home, Loader2, AlertTriangle, CheckCircle } from "lucide-react";
import { Skeleton } from "@/app/components/ui/skeleton";
import {
  Dashboard,
  SmartFilterOptions,
  DashboardFilters,
} from "../types";
import { StatCard } from "./StatCard";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/app/components/ui/select";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from "recharts";

interface OverviewTabProps {
  data: Dashboard | null;
  filterOptions: SmartFilterOptions;
  filters: DashboardFilters;
  onFilterChange: (filters: DashboardFilters) => void;
  loading?: boolean;
}

const OverviewTabComponent = ({
  data,
  filterOptions,
  filters,
  onFilterChange,
  loading = false,
}: OverviewTabProps) => {

  // Memoizar callbacks para evitar re-criação
  const handleFilterUpdate = useCallback((key: keyof DashboardFilters, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  }, [filters, onFilterChange]);

  const clearFilters = useCallback(() => {
    onFilterChange({});
  }, [onFilterChange]);

  // Memoizar constantes
  const COLORS = useMemo(() => ["#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#8884d8"], []);

  // Memoizar dados dos gráficos para evitar re-processamento
  const chartData = useMemo(() => ({
    grupoDistribution: data?.distribuicao_por_grupo || [],
    topBairros: data?.top_bairros || [],
    safraDistribution: data?.distribuicao_por_safra || [],
    motivosSaida: data?.distribuicao_motivo_saida || [],
  }), [data]);

  // OTIMIZAÇÃO CRÍTICA: Pré-filtrar todas as opções de filtro UMA VEZ
  const filteredOptions = useMemo(() => ({
    grupos: filterOptions.grupos.filter((item) => item.id && item.id.trim() !== ""),
    status_list: filterOptions.status_list.filter((item) => item.id && item.id.trim() !== ""),
    cohorts: filterOptions.cohorts.filter((item) => item.id && item.id.trim() !== ""),
    caps: filterOptions.caps.filter((item) => item.id && item.id.trim() !== ""),
    cres: filterOptions.cres.filter((item) => item.id && item.id.trim() !== ""),
    cas_list: filterOptions.cas_list.filter((item) => item.id && item.id.trim() !== ""),
    bairros: filterOptions.bairros.filter((item) => item.id && item.id.trim() !== ""),
    escolas: filterOptions.escolas.filter((item) => item.id && item.id.trim() !== ""),
    clinicas: filterOptions.clinicas.filter((item) => item.id && item.id.trim() !== ""),
    cras: filterOptions.cras.filter((item) => item.id && item.id.trim() !== ""),
  }), [filterOptions]);

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
      {/* Filters */}
      <Card className="relative">
        {/* Indicador de loading nos filtros */}
        {loading && (
          <div className="absolute top-3 right-3 z-10">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
          </div>
        )}
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filtros
            {loading && <span className="text-xs text-muted-foreground ml-2">(carregando...)</span>}
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={clearFilters}
            className="h-8 text-xs"
            disabled={loading}
          >
            Limpar Filtros
          </Button>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {/* Primeiro Nível - Filtros Principais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Principais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {/* Grupo */}
              <Select
                value={filters.grupo || "todos"}
                onValueChange={(v) => handleFilterUpdate("grupo", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Grupo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os Grupos</SelectItem>
                  {filterOptions.grupos
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Safra */}
              <Select
                value={filters.safra || "todas"}
                onValueChange={(v) => handleFilterUpdate("safra", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Safra" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Safras</SelectItem>
                  {filterOptions.cohorts
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Status */}
              <Select
                value={filters.status || "todos"}
                onValueChange={(v) => handleFilterUpdate("status", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os Status</SelectItem>
                  {filterOptions.status_list
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Segundo Nível - Filtros Regionais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Regionais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {/* CAP */}
              <Select
                value={filters.cap || "todas"}
                onValueChange={(v) => handleFilterUpdate("cap", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="CAP" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as CAPs</SelectItem>
                  {filterOptions.caps
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* CRE (Educação) */}
              <Select
                value={filters.cre || "todas"}
                onValueChange={(v) => handleFilterUpdate("cre", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="CRE" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as CREs</SelectItem>
                  {filterOptions.cres
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* CAS */}
              <Select
                value={filters.cas || "todas"}
                onValueChange={(v) => handleFilterUpdate("cas", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="CAS" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as CAS</SelectItem>
                  {filterOptions.cas_list
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Bairro */}
              <Select
                value={filters.bairro || "todos"}
                onValueChange={(v) => handleFilterUpdate("bairro", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Bairro" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os Bairros</SelectItem>
                  {filterOptions.bairros
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Escolas */}
              <Select
                value={filters.escola || "todas"}
                onValueChange={(v) => handleFilterUpdate("escola", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Escola" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Escolas</SelectItem>
                  {filterOptions.escolas
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* Clínicas da Família */}
              <Select
                value={filters.clinica || "todas"}
                onValueChange={(v) => handleFilterUpdate("clinica", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Clínica da Família" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todas as Clínicas da Família</SelectItem>
                  {filterOptions.clinicas
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>

              {/* CRAS */}
              <Select
                value={filters.cras || "todas"}
                onValueChange={(v) => handleFilterUpdate("cras", v)}
                disabled={loading}
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="CRAS" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todas">Todos os CRAS</SelectItem>
                  {filterOptions.cras
                    .filter((item) => item.id && item.id.trim() !== "")
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

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
          {/* Métricas Principais - com overlay se loading */}
          <div className={`grid grid-cols-1 md:grid-cols-3 gap-4 relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}
            <StatCard
              title="Total de Participantes"
              value={data.total_participantes_geral || 0}
              description={`${data.total_participantes_ativos || 0} ativos • ${data.total_participantes_inativos || 0} inativos`}
              icon={<Users className="h-6 w-6" />}
              variant="default"
            />
            <StatCard
              title="% Regular"
              value={`${(data.percentual_regular || 0).toFixed(1)}%`}
              description="Cumprindo todos os protocolos"
              icon={<CheckCircle className="h-6 w-6" />}
              variant="success"
            />
            <StatCard
              title="% Irregular"
              value={`${(data.percentual_irregular || 0).toFixed(1)}%`}
              description="Com protocolos violados"
              icon={<AlertTriangle className="h-6 w-6" />}
              variant="destructive"
            />
          </div>

          {/* Dimensão Assistência Social */}
          <div className={`space-y-3 relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}
            <h3 className="text-lg font-semibold flex items-center gap-2">
              🏠 Dimensão Assistência Social
            </h3>
            <div className="grid gap-3 md:grid-cols-3">
              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">💰 Bolsa Família</p>
                  <p className="text-2xl font-bold mt-1">
                    {(data.assistencia_bolsa_familia_percentual || 0).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {data.assistencia_bolsa_familia_total || 0} de {data.total_participantes_geral || 0} participantes
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">📋 CadÚnico Atualizado</p>
                  <p className="text-2xl font-bold mt-1">
                    {(data.assistencia_cadunico_atualizado_percentual || 0).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    cadastros desatualizados ({(data.total_participantes_geral || 0) - (data.assistencia_cadunico_atualizado_total || 0)} de {data.total_participantes_geral || 0})
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">👥 Equipe de Referência</p>
                  <p className="text-2xl font-bold mt-1 text-muted-foreground/50">-</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Em desenvolvimento
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Dimensão Educação */}
          <div className={`space-y-3 relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}
            <h3 className="text-lg font-semibold flex items-center gap-2">
              📚 Dimensão Educação
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">🎒 Frequência Escolar</p>
                  <p className="text-2xl font-bold mt-1">
                    {((100 - (data.educacao_frequencia_adequada_percentual || 0))).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    com frequência inferior ao mínimo ({(data.total_participantes_geral || 0) - (data.educacao_frequencia_adequada_total || 0)} de {data.total_participantes_geral || 0})
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">🏫 Matrícula em Creche</p>
                  <p className="text-2xl font-bold mt-1 text-muted-foreground/50">-</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Em desenvolvimento
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Dimensão Saúde */}
          <div className={`space-y-3 relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}
            <h3 className="text-lg font-semibold flex items-center gap-2">
              ❤️ Dimensão Saúde
            </h3>
            <div className="grid gap-3 md:grid-cols-3">
              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">👶 Consultas Infantis</p>
                  <p className="text-2xl font-bold mt-1 text-muted-foreground/50">-</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Em desenvolvimento
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">🤰 Consultas Pré-natal</p>
                  <p className="text-2xl font-bold mt-1 text-muted-foreground/50">-</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Em desenvolvimento
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-muted">
                <CardContent className="p-4">
                  <p className="text-sm font-medium">💉 Vacinação</p>
                  <p className="text-2xl font-bold mt-1 text-muted-foreground/50">-</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Em desenvolvimento
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Resultado do Programa */}
          {data.resultado_programa && data.resultado_programa.length > 0 && (
            <Card className={`relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
              {loading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              )}
              <CardHeader>
                <CardTitle>Resultado do Programa</CardTitle>
                <p className="text-sm text-muted-foreground">Evolução temporal da completude por dimensão</p>
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
          <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}
            <StatCard
              title="Protocolos Totais"
              value={data.total_protocolos || 0}
              icon={<TrendingUp className="h-4 w-4" />}
              trend={{
                value: `${data.percentual_protocolos_violados || 0}% violados`,
                isPositive: false,
              }}
            />
            <StatCard
              title="Assistência Social"
              value={data.total_protocolos_smas || 0}
              icon={<Home className="h-4 w-4" />}
              trend={{
                value: `${data.percentual_smas_violados || 0}% violados`,
                isPositive: false,
              }}
            />
            <StatCard
              title="Educação"
              value={data.total_protocolos_sme || 0}
              icon={<Baby className="h-4 w-4" />}
              trend={{
                value: `${data.percentual_sme_violados || 0}% violados`,
                isPositive: false,
              }}
            />
            <StatCard
              title="Saúde"
              value={data.total_protocolos_sms || 0}
              icon={<Heart className="h-4 w-4" />}
              trend={{
                value: `${data.percentual_sms_violados || 0}% violados`,
                isPositive: false,
              }}
            />
          </div>

          {/* Charts - com overlay se loading */}
          <div className={`grid grid-cols-1 lg:grid-cols-2 gap-6 relative ${loading ? 'opacity-50 pointer-events-none' : ''}`}>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 rounded-lg">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )}
            {/* Group Distribution */}
            {chartData.grupoDistribution.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Distribuição por Grupo</CardTitle>
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
                        label
                        isAnimationActive={false}
                      >
                        {chartData.grupoDistribution.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={COLORS[index % COLORS.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Top Bairros */}
            {chartData.topBairros.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Top Bairros</CardTitle>
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
              <Card>
                <CardHeader>
                  <CardTitle>Participantes por Safra</CardTitle>
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
              <Card>
                <CardHeader>
                  <CardTitle>Motivos de Inativação</CardTitle>
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
