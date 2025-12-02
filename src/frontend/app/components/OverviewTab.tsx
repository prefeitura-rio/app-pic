import { useState, useMemo } from "react";
import { StatCard } from "./StatCard";
import { Baby, Heart, Activity, BookOpen, Home, AlertTriangle, Users, Filter } from "lucide-react";
import { DashboardSummary, FilterOption } from "../types";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/app/components/ui/select";
import { DashboardFilters } from "@/app/services/api";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";
import { Button } from "./ui/button";

interface OverviewTabProps {
  data: DashboardSummary;
  filterOptions: FilterOption[];
  onFilterChange: (filters: DashboardFilters) => void;
}

export function OverviewTab({ data, filterOptions, onFilterChange }: OverviewTabProps) {
  const [selectedBairro, setSelectedBairro] = useState<string>("todos");
  const [selectedCRE, setSelectedCRE] = useState<string>("todas");
  const [selectedCRAS, setSelectedCRAS] = useState<string>("todas");
  const [selectedCohort, setSelectedCohort] = useState<string>("todas");
  const [selectedGrupo, setSelectedGrupo] = useState<string>("todos");
  const [selectedStatus, setSelectedStatus] = useState<string>("todos");

  // --- Smart Filtering Logic ---
  
  // Extract unique options from the master list provided by the backend
  const allBairros = useMemo(() => filterOptions.filter(o => o.tipo === "bairro"), [filterOptions]);
  const allCREs = useMemo(() => filterOptions.filter(o => o.tipo === "cre"), [filterOptions]);
  const allCRAS = useMemo(() => filterOptions.filter(o => o.tipo === "cras"), [filterOptions]);
  const allCohorts = useMemo(() => filterOptions.filter(o => o.tipo === "safra"), [filterOptions]);
  const allGrupos = useMemo(() => filterOptions.filter(o => o.tipo === "grupo"), [filterOptions]);
  const allStatus = useMemo(() => filterOptions.filter(o => o.tipo === "status"), [filterOptions]);

  // Derived options (simulated dependency, real dependency needs hierarchy in FilterOption)
  // For now, we show all, but in a real smart filter, selecting CRE would filter Bairros.
  // Since we don't have the parent_id mapped in the backend response yet (it's optional), 
  // we will just display the lists. The Backend aggregation handles the combination.
  
  const handleFilterUpdate = (key: keyof DashboardFilters, value: string) => {
    // 1. Update local state
    if (key === "bairro") setSelectedBairro(value);
    if (key === "cre") setSelectedCRE(value);
    if (key === "cras") setSelectedCRAS(value);
    if (key === "safra") setSelectedCohort(value);
    if (key === "grupo") setSelectedGrupo(value);
    if (key === "status") setSelectedStatus(value);

    // 2. Trigger fetch
    const newFilters: DashboardFilters = {
      bairro: key === "bairro" ? value : selectedBairro,
      cre: key === "cre" ? value : selectedCRE,
      cras: key === "cras" ? value : selectedCRAS,
      safra: key === "safra" ? value : selectedCohort,
      grupo: key === "grupo" ? value : selectedGrupo,
      status: key === "status" ? value : selectedStatus,
    };
    onFilterChange(newFilters);
  };

  const clearFilters = () => {
    setSelectedBairro("todos");
    setSelectedCRE("todas");
    setSelectedCRAS("todas");
    setSelectedCohort("todas");
    setSelectedGrupo("todos");
    setSelectedStatus("todos");
    onFilterChange({});
  };

  // Mapping API data to charts
  const gruposData = data.distribuicao_por_grupo || [];
  const bairrosData = (data.top_bairros || []).slice(0, 10);
  const motivosData = data.distribuicao_motivo_saida || [];
  const safraData = (data.distribuicao_por_safra || []).map(d => ({
    ...d,
    safraDate: new Date(d.safra).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })
  }));

  return (
    <div className="space-y-8">
      {/* Filtros */}
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filtros Dinâmicos
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={clearFilters} className="h-8 text-xs">
            Limpar Filtros
          </Button>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-2">
            
            {/* Grupo */}
            <Select value={selectedGrupo} onValueChange={(v) => handleFilterUpdate("grupo", v)}>
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Grupo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Grupos</SelectItem>
                {allGrupos.map(opt => (
                  <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Status */}
            <Select value={selectedStatus} onValueChange={(v) => handleFilterUpdate("status", v)}>
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                {allStatus.map(opt => (
                  <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Safra */}
            <Select value={selectedCohort} onValueChange={(v) => handleFilterUpdate("safra", v)}>
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Safra" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as Safras</SelectItem>
                {allCohorts.map(opt => (
                  <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Regionais (CRE) */}
            <Select value={selectedCRE} onValueChange={(v) => handleFilterUpdate("cre", v)}>
              <SelectTrigger className="h-8">
                <SelectValue placeholder="CRE" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as CREs</SelectItem>
                {allCREs.map(opt => (
                  <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

             {/* CRAS */}
             <Select value={selectedCRAS} onValueChange={(v) => handleFilterUpdate("cras", v)}>
              <SelectTrigger className="h-8">
                <SelectValue placeholder="CRAS" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as CAS</SelectItem>
                {allCRAS.map(opt => (
                  <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Bairro */}
            <Select value={selectedBairro} onValueChange={(v) => handleFilterUpdate("bairro", v)}>
              <SelectTrigger className="h-8">
                <SelectValue placeholder="Bairro" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Bairros</SelectItem>
                {allBairros.sort((a,b) => a.label.localeCompare(b.label)).map(opt => (
                  <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

          </div>
        </CardContent>
      </Card>

      {/* Indicadores Principais */}
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">Indicadores Principais</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard
            title="Total de Participantes Ativos"
            value={data.total_participantes_ativos?.toLocaleString('pt-BR') || "0"}
            description="Participantes ativos no programa"
            icon={Users}
            variant="default"
          />
          <StatCard
            title="Participantes em Atenção"
            value={data.total_participantes_em_atencao?.toLocaleString('pt-BR') || "0"}
            description={`${data.percentual_em_atencao?.toFixed(1) || "0"}% do total`}
            icon={Activity}
            variant="warning"
          />
          <StatCard
            title="% Protocolos Violados"
            value={`${data.percentual_protocolos_violados?.toFixed(1) || "0"}%`}
            description={`${data.total_protocolos_violados?.toLocaleString('pt-BR') || "0"} protocolos violados`}
            icon={AlertTriangle}
            variant="destructive"
          />
        </div>

        {/* Dimensões */}
        <div className="mb-8">
          <h4 className="text-lg font-semibold text-foreground mb-4">Dimensões do Programa</h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Assistência Social */}
            <div className="bg-muted rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                 <h5 className="flex items-center gap-2 font-medium text-foreground">
                    <Home className="h-4 w-4 text-emerald-500" />
                    Assistência Social
                 </h5>
              </div>
              <p className="text-2xl font-bold text-foreground mb-1">
                {data.percentual_smas_violados?.toFixed(1) || "0"}%
              </p>
              <p className="text-xs text-muted-foreground">
                 de protocolos violados
              </p>
               <p className="text-xs text-muted-foreground mt-1">
                Total: {data.total_protocolos_smas?.toLocaleString('pt-BR')}
              </p>
            </div>

            {/* Educação */}
            <div className="bg-muted rounded-lg p-4">
               <div className="flex items-center justify-between mb-2">
                 <h5 className="flex items-center gap-2 font-medium text-foreground">
                    <BookOpen className="h-4 w-4 text-amber-500" />
                    Educação
                 </h5>
              </div>
              <p className="text-2xl font-bold text-foreground mb-1">
                {data.percentual_sme_violados?.toFixed(1) || "0"}%
              </p>
              <p className="text-xs text-muted-foreground">
                de protocolos violados
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Total: {data.total_protocolos_sme?.toLocaleString('pt-BR')}
              </p>
            </div>

            {/* Saúde */}
             <div className="bg-muted rounded-lg p-4">
               <div className="flex items-center justify-between mb-2">
                 <h5 className="flex items-center gap-2 font-medium text-foreground">
                    <Heart className="h-4 w-4 text-red-500" />
                    Saúde
                 </h5>
              </div>
              <p className="text-2xl font-bold text-foreground mb-1">
                {data.percentual_sms_violados?.toFixed(1) || "0"}%
              </p>
              <p className="text-xs text-muted-foreground">
                de protocolos violados
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Total: {data.total_protocolos_sms?.toLocaleString('pt-BR')}
              </p>
            </div>
          </div>
        </div>

        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
           {/* Distribuição por Grupo */}
           <Card>
            <CardHeader>
              <CardTitle>Distribuição por Grupo</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={gruposData}
                    dataKey="total_participantes"
                    nameKey="grupo"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={(entry) => entry.grupo}
                  >
                     <Cell fill="#3b82f6" />
                     <Cell fill="#ec4899" />
                  </Pie>
                  <Tooltip formatter={(value: number) => value.toLocaleString('pt-BR')} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Top Bairros */}
          <Card>
            <CardHeader>
              <CardTitle>Top 10 Bairros com Mais Participantes</CardTitle>
            </CardHeader>
             <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart
                  layout="vertical"
                  data={bairrosData}
                  margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" hide />
                  <YAxis dataKey="bairro" type="category" width={100} tick={{fontSize: 12}} />
                  <Tooltip formatter={(value: number) => value.toLocaleString('pt-BR')} />
                  <Bar dataKey="total_participantes" fill="#10b981" radius={[0, 4, 4, 0]} name="Participantes" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
           {/* Evolução por Safra */}
           <Card>
            <CardHeader>
              <CardTitle>Participantes por Safra</CardTitle>
            </CardHeader>
            <CardContent>
               <ResponsiveContainer width="100%" height={300}>
                <BarChart data={safraData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="safraDate" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => value.toLocaleString('pt-BR')} />
                  <Bar dataKey="total_participantes" fill="#8b5cf6" name="Participantes" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
           </Card>

            {/* Motivos de Saída */}
           <Card>
            <CardHeader>
              <CardTitle>Motivos de Inativação/Saída</CardTitle>
            </CardHeader>
             <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={motivosData}
                    dataKey="total"
                    nameKey="motivo"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={(entry) => `${entry.total}`}
                  >
                    <Cell fill="#94a3b8" />
                    <Cell fill="#ef4444" />
                    <Cell fill="#f59e0b" />
                    <Cell fill="#6366f1" />
                  </Pie>
                  <Tooltip formatter={(value: number) => value.toLocaleString('pt-BR')} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}