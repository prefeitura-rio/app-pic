import { useMemo, useState } from "react";
import { Baby, Heart, Activity, Users, Filter, TrendingUp, Home } from "lucide-react";
import {
  Participante,
  SmartFilterOptions,
  DashboardFilters,
  FilterOptionItem,
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

interface OverviewTabProps {
  allParticipants: Participante[];
  filterOptions: SmartFilterOptions;
  filters: DashboardFilters;
  onFilterChange: (filters: DashboardFilters) => void;
}

export function OverviewTab({
  allParticipants,
  filterOptions,
  filters,
  onFilterChange,
}: OverviewTabProps) {
  const [selectedGrupo, setSelectedGrupo] = useState<string>("todos");

  /**
   * Apply filters to participants in-memory
   */
  const filteredParticipants = useMemo(() => {
    let result = allParticipants;

    // Apply filters
    if (filters.bairro && filters.bairro !== "todos") {
      result = result.filter((p) => p.bairro === filters.bairro);
    }

    if (filters.cre && filters.cre !== "todas") {
      result = result.filter((p) => p.id_cre === filters.cre);
    }

    if (filters.cras && filters.cras !== "todas") {
      result = result.filter((p) => p.id_cras === filters.cras);
    }

    if (filters.safra && filters.safra !== "todas") {
      result = result.filter((p) => p.cohort === filters.safra);
    }

    if (filters.grupo && filters.grupo !== "todos") {
      result = result.filter(
        (p) =>
          p.grupo?.toLowerCase().includes(filters.grupo!.toLowerCase()) ?? false
      );
    }

    if (filters.status && filters.status !== "todos") {
      result = result.filter((p) => p.status === filters.status);
    }

    return result;
  }, [allParticipants, filters]);

  /**
   * Apply additional grupo filter (crianças/gestantes)
   */
  const displayedParticipants = useMemo(() => {
    if (selectedGrupo === "todos") return filteredParticipants;
    return filteredParticipants.filter((p) =>
      p.grupo?.toLowerCase().includes(selectedGrupo.toLowerCase())
    );
  }, [filteredParticipants, selectedGrupo]);

  /**
   * Calculate statistics
   */
  const stats = useMemo(() => {
    const ativos = displayedParticipants.filter((p) => p.status === "ativo");
    const inativos = displayedParticipants.filter((p) => p.status === "inativo");
    const criancas = displayedParticipants.filter((p) =>
      p.grupo?.toLowerCase().includes("crianca")
    );
    const gestantes = displayedParticipants.filter((p) =>
      p.grupo?.toLowerCase().includes("gestante")
    );

    // Protocol statistics
    const totalProtocolos = displayedParticipants.reduce(
      (acc, p) => acc + (p.total_protocolos || 0),
      0
    );
    const protocolosViolados = displayedParticipants.reduce(
      (acc, p) => acc + (p.total_protocolos_violados || 0),
      0
    );

    const protocolosSMAS = displayedParticipants.reduce(
      (acc, p) => acc + (p.assistencia_protocolos_total || 0),
      0
    );
    const protocolosSMASViolados = displayedParticipants.reduce(
      (acc, p) => acc + (p.assistencia_protocolos_violados || 0),
      0
    );

    const protocolosSME = displayedParticipants.reduce(
      (acc, p) => acc + (p.educacao_protocolos_total || 0),
      0
    );
    const protocolosSMEViolados = displayedParticipants.reduce(
      (acc, p) => acc + (p.educacao_protocolos_violados || 0),
      0
    );

    const protocolosSMS = displayedParticipants.reduce(
      (acc, p) => acc + (p.saude_protocolos_total || 0),
      0
    );
    const protocolosSMSViolados = displayedParticipants.reduce(
      (acc, p) => acc + (p.saude_protocolos_violados || 0),
      0
    );

    // Participants in attention (com protocolos violados)
    const participantesEmAtencao = displayedParticipants.filter(
      (p) => (p.total_protocolos_violados || 0) > 0
    );

    return {
      totalParticipantes: displayedParticipants.length,
      ativos: ativos.length,
      inativos: inativos.length,
      criancas: criancas.length,
      gestantes: gestantes.length,
      totalProtocolos,
      protocolosViolados,
      percentualViolados:
        totalProtocolos > 0
          ? ((protocolosViolados / totalProtocolos) * 100).toFixed(1)
          : "0",
      protocolosSMAS,
      protocolosSMASViolados,
      percentualSMASViolados:
        protocolosSMAS > 0
          ? ((protocolosSMASViolados / protocolosSMAS) * 100).toFixed(1)
          : "0",
      protocolosSME,
      protocolosSMEViolados,
      percentualSMEViolados:
        protocolosSME > 0
          ? ((protocolosSMEViolados / protocolosSME) * 100).toFixed(1)
          : "0",
      protocolosSMS,
      protocolosSMSViolados,
      percentualSMSViolados:
        protocolosSMS > 0
          ? ((protocolosSMSViolados / protocolosSMS) * 100).toFixed(1)
          : "0",
      participantesEmAtencao: participantesEmAtencao.length,
      percentualEmAtencao:
        displayedParticipants.length > 0
          ? (
              (participantesEmAtencao.length / displayedParticipants.length) *
              100
            ).toFixed(1)
          : "0",
    };
  }, [displayedParticipants]);

  /**
   * Generate chart data
   */
  const chartData = useMemo(() => {
    // Group distribution
    const grupoMap = new Map<string, number>();
    displayedParticipants.forEach((p) => {
      if (p.grupo) {
        grupoMap.set(p.grupo, (grupoMap.get(p.grupo) || 0) + 1);
      }
    });
    const distribuicaoGrupo = Array.from(grupoMap.entries()).map(
      ([grupo, total]) => ({ grupo, total })
    );

    // Top bairros
    const bairroMap = new Map<string, number>();
    displayedParticipants.forEach((p) => {
      if (p.bairro) {
        bairroMap.set(p.bairro, (bairroMap.get(p.bairro) || 0) + 1);
      }
    });
    const topBairros = Array.from(bairroMap.entries())
      .map(([bairro, total]) => ({ bairro, total }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10);

    // Safra distribution
    const safraMap = new Map<string, number>();
    displayedParticipants.forEach((p) => {
      if (p.cohort) {
        safraMap.set(p.cohort, (safraMap.get(p.cohort) || 0) + 1);
      }
    });
    const distribuicaoSafra = Array.from(safraMap.entries())
      .map(([safra, total]) => ({ safra, total }))
      .sort((a, b) => a.safra.localeCompare(b.safra));

    // Inactivity reasons
    const motivoMap = new Map<string, number>();
    displayedParticipants
      .filter((p) => p.status === "inativo" && p.status_inativo_motivo)
      .forEach((p) => {
        const motivo = p.status_inativo_motivo!;
        motivoMap.set(motivo, (motivoMap.get(motivo) || 0) + 1);
      });
    const motivosSaida = Array.from(motivoMap.entries()).map(
      ([motivo, total]) => ({ motivo, total })
    );

    return {
      distribuicaoGrupo,
      topBairros,
      distribuicaoSafra,
      motivosSaida,
    };
  }, [displayedParticipants]);

  const handleFilterUpdate = (key: keyof DashboardFilters, value: string) => {
    onFilterChange({
      ...filters,
      [key]: value,
    });
  };

  const clearFilters = () => {
    setSelectedGrupo("todos");
    onFilterChange({});
  };

  const COLORS = ["#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#8884d8"];

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
          >
            Limpar Filtros
          </Button>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-2">
            {/* Grupo (local filter) */}
            <Select
              value={selectedGrupo}
              onValueChange={(v) => setSelectedGrupo(v)}
            >
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Grupo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos</SelectItem>
                <SelectItem value="crianca">Crianças</SelectItem>
                <SelectItem value="gestante">Gestantes</SelectItem>
              </SelectContent>
            </Select>

            {/* Bairro */}
            <Select
              value={filters.bairro || "todos"}
              onValueChange={(v) => handleFilterUpdate("bairro", v)}
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
                      {item.label} ({item.counts.total})
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>

            {/* CRE */}
            <Select
              value={filters.cre || "todas"}
              onValueChange={(v) => handleFilterUpdate("cre", v)}
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
                      {item.label} ({item.counts.total})
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>

            {/* CRAS */}
            <Select
              value={filters.cras || "todas"}
              onValueChange={(v) => handleFilterUpdate("cras", v)}
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
                      {item.label} ({item.counts.total})
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>

            {/* Safra/Cohort */}
            <Select
              value={filters.safra || "todas"}
              onValueChange={(v) => handleFilterUpdate("safra", v)}
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
                      {item.label} ({item.counts.total})
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>

            {/* Status */}
            <Select
              value={filters.status || "todos"}
              onValueChange={(v) => handleFilterUpdate("status", v)}
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
                      {item.label} ({item.counts.total})
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total de Participantes"
          value={stats.totalParticipantes}
          icon={<Users className="h-4 w-4" />}
          trend={{
            value: `${stats.ativos} ativos`,
            isPositive: true,
          }}
        />
        <StatCard
          title="Crianças"
          value={stats.criancas}
          icon={<Baby className="h-4 w-4" />}
          trend={{
            value: `${((stats.criancas / stats.totalParticipantes) * 100).toFixed(1)}%`,
            isPositive: true,
          }}
        />
        <StatCard
          title="Gestantes"
          value={stats.gestantes}
          icon={<Heart className="h-4 w-4" />}
          trend={{
            value: `${((stats.gestantes / stats.totalParticipantes) * 100).toFixed(1)}%`,
            isPositive: true,
          }}
        />
        <StatCard
          title="Em Atenção"
          value={stats.participantesEmAtencao}
          icon={<Activity className="h-4 w-4" />}
          trend={{
            value: `${stats.percentualEmAtencao}%`,
            isPositive: false,
          }}
        />
      </div>

      {/* Protocol Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Protocolos Totais"
          value={stats.totalProtocolos}
          icon={<TrendingUp className="h-4 w-4" />}
          trend={{
            value: `${stats.percentualViolados}% violados`,
            isPositive: false,
          }}
        />
        <StatCard
          title="Assistência Social"
          value={stats.protocolosSMAS}
          icon={<Home className="h-4 w-4" />}
          trend={{
            value: `${stats.percentualSMASViolados}% violados`,
            isPositive: false,
          }}
        />
        <StatCard
          title="Educação"
          value={stats.protocolosSME}
          icon={<Baby className="h-4 w-4" />}
          trend={{
            value: `${stats.percentualSMEViolados}% violados`,
            isPositive: false,
          }}
        />
        <StatCard
          title="Saúde"
          value={stats.protocolosSMS}
          icon={<Heart className="h-4 w-4" />}
          trend={{
            value: `${stats.percentualSMSViolados}% violados`,
            isPositive: false,
          }}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Group Distribution */}
        <Card>
          <CardHeader>
            <CardTitle>Distribuição por Grupo</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={chartData.distribuicaoGrupo}
                  dataKey="total"
                  nameKey="grupo"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label
                >
                  {chartData.distribuicaoGrupo.map((entry, index) => (
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

        {/* Top Bairros */}
        <Card>
          <CardHeader>
            <CardTitle>Top 10 Bairros</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData.topBairros}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bairro" angle={-45} textAnchor="end" height={100} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="total" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Safra Distribution */}
        {chartData.distribuicaoSafra.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Distribuição por Safra</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData.distribuicaoSafra}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="safra" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="total" fill="#00C49F" />
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
                  <Bar dataKey="total" fill="#FF8042" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
