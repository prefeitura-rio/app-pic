import { Baby, Heart, Activity, Users, Filter, TrendingUp, Home } from "lucide-react";
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
} from "recharts";
import { Loader2 } from "lucide-react";

interface OverviewTabProps {
  data: Dashboard | null;
  filterOptions: SmartFilterOptions;
  filters: DashboardFilters;
  onFilterChange: (filters: DashboardFilters) => void;
  loading?: boolean;
}

export function OverviewTab({
  data,
  filterOptions,
  filters,
  onFilterChange,
  loading = false,
}: OverviewTabProps) {

  const handleFilterUpdate = (key: keyof DashboardFilters, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  };

  const clearFilters = () => {
    onFilterChange({});
  };

  const COLORS = ["#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#8884d8"];

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
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filtros
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
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-2">
            {/* Grupo */}
            <Select
              value={filters.grupo || "todos"}
              onValueChange={(v) => handleFilterUpdate("grupo", v)}
              disabled={loading}
            >
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Grupo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
                {filterOptions.grupos
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
              <SelectTrigger className="h-8">
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

            {/* CRE */}
            <Select
              value={filters.cre || "todas"}
              onValueChange={(v) => handleFilterUpdate("cre", v)}
              disabled={loading}
            >
              <SelectTrigger className="h-8">
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

            {/* CRAS */}
            <Select
              value={filters.cras || "todas"}
              onValueChange={(v) => handleFilterUpdate("cras", v)}
              disabled={loading}
            >
              <SelectTrigger className="h-8">
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

            {/* Safra/Cohort */}
            <Select
              value={filters.safra || "todas"}
              onValueChange={(v) => handleFilterUpdate("safra", v)}
              disabled={loading}
            >
              <SelectTrigger className="h-8">
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
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
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
        </CardContent>
      </Card>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}

      {!loading && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Total de Participantes"
              value={data.total_participantes_geral || 0}
              icon={<Users className="h-4 w-4" />}
              trend={{
                value: `${data.total_participantes_ativos || 0} ativos`,
                isPositive: true,
              }}
            />
            <StatCard
              title="Participantes Ativos"
              value={data.total_participantes_ativos || 0}
              icon={<Activity className="h-4 w-4" />}
              variant="success"
            />
            <StatCard
              title="Participantes Inativos"
              value={data.total_participantes_inativos || 0}
              icon={<Users className="h-4 w-4" />}
              variant="secondary"
            />
            <StatCard
              title="Em Atenção"
              value={data.total_participantes_em_atencao || 0}
              icon={<Activity className="h-4 w-4" />}
              trend={{
                value: `${data.percentual_em_atencao || 0}%`,
                isPositive: false,
              }}
              variant="warning"
            />
          </div>

          {/* Protocol Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Group Distribution */}
            {data.distribuicao_por_grupo && data.distribuicao_por_grupo.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Distribuição por Grupo</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={data.distribuicao_por_grupo}
                        dataKey="total_participantes"
                        nameKey="grupo"
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        label
                      >
                        {data.distribuicao_por_grupo.map((entry, index) => (
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
            {data.top_bairros && data.top_bairros.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Top Bairros</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={data.top_bairros}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="bairro" angle={-45} textAnchor="end" height={100} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="total_participantes" fill="#8884d8" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Safra Distribution */}
            {data.distribuicao_por_safra && data.distribuicao_por_safra.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Distribuição por Safra</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={data.distribuicao_por_safra}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="safra" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="total_participantes" fill="#00C49F" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Motivos de Saída */}
            {data.distribuicao_motivo_saida && data.distribuicao_motivo_saida.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Motivos de Inativação</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={data.distribuicao_motivo_saida}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="motivo" angle={-45} textAnchor="end" height={100} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="total" fill="#FF8042" />
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
}
