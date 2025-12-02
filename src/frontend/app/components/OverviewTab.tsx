import { StatCard } from "./StatCard";
import { Baby, Heart, Activity, BookOpen, Home, AlertTriangle, Users } from "lucide-react";
import { DashboardSummary } from "../types";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";

interface OverviewTabProps {
  data: DashboardSummary;
}

export function OverviewTab({ data }: OverviewTabProps) {
  // Mapping API data to charts
  
  // Grupos (Pie Chart)
  const gruposData = data.distribuicao_por_grupo || [];

  // Top Bairros (Bar Chart)
  const bairrosData = (data.top_bairros || []).slice(0, 10);

  // Motivos Saída (Pie Chart)
  const motivosData = data.distribuicao_motivo_saida || [];

  // Safra (Bar Chart)
  const safraData = (data.distribuicao_por_safra || []).map(d => ({
    ...d,
    safraDate: new Date(d.safra).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }) // Format timestamp to "Jan 24"
  }));

  return (
    <div className="space-y-8">
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