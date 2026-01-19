import { useMemo, useState } from "react";
import { StatCard } from "./StatCard";
import { Baby, Heart, Activity, BookOpen, Home, AlertTriangle, Users, BarChart3, LineChart } from "lucide-react";
import { Individual, bairros, unidadesPorBairro, coordenadoriasAP, coordenadoriasCRE, coordenadoriasCRAS } from "@/lib/csvLoader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { BarChart, Bar, LineChart as RechartsLineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";

interface OverviewTabProps {
  data: Individual[];
}

export function OverviewTab({ data }: OverviewTabProps) {
  const [filtro, setFiltro] = useState<"todos" | "criancas" | "gestantes">("todos");
  const [graficoTipo, setGraficoTipo] = useState<"barras" | "linhas">("barras");
  const [selectedBairro, setSelectedBairro] = useState<string>("todos");
  const [selectedAP, setselectedAP] = useState<string>("todas");
  const [selectedCRE, setSelectedCRE] = useState<string>("todas");
  const [selectedCRAS, setSelectedCRAS] = useState<string>("todas");
  const [selectedCohort, setSelectedCohort] = useState<string>("todas");
  const [selectedSecretaria, setSelectedSecretaria] = useState<"todas" | "assistencia" | "educacao" | "saude">("todas");

  // Extract unique cohorts from data
  const cohorts = useMemo(() => {
    const uniqueCohorts = Array.from(new Set(data.map(d => d.cohort))).sort();
    return uniqueCohorts;
  }, [data]);

  const stats = useMemo(() => {
    // Aplicar filtros de região primeiro
    const filteredByRegion = data.filter(d => {
      if (d.status !== "ativo") return false;
      
      // Filtro por AP (Saúde)
      if (selectedAP !== "todas") {
        const bairrosAP = coordenadoriasAP[selectedAP] || [];
        if (!bairrosAP.includes(d.bairro)) return false;
      }
      
      // Filtro por CRE (Educação)
      if (selectedCRE !== "todas") {
        const bairrosCRE = coordenadoriasCRE[selectedCRE] || [];
        if (!bairrosCRE.includes(d.bairro)) return false;
      }
      
      // Filtro por CRAS (Assistência Social)
      if (selectedCRAS !== "todas") {
        const bairrosCRAS = coordenadoriasCRAS[selectedCRAS] || [];
        if (!bairrosCRAS.includes(d.bairro)) return false;
      }
      
      // Filtro por Bairro
      if (selectedBairro !== "todos" && d.bairro !== selectedBairro) return false;
      
      // Filtro por Cohort
      if (selectedCohort !== "todas" && d.cohort !== selectedCohort) return false;
      
      return true;
    });

    const ativos = filteredByRegion;
    const criancas = ativos.filter(d => d.grupo.includes("crianca"));
    const gestantes = ativos.filter(d => d.grupo.includes("gestante"));
    
    // Definir o subset baseado no filtro
    const subset = filtro === "criancas" ? criancas : filtro === "gestantes" ? gestantes : ativos;
    
    const gestantesSemBolsa = gestantes.filter(g => !g.bolsa_familia);
    const criancasComBolsa = criancas.filter(c => c.bolsa_familia);
    const comBolsa = subset.filter(d => d.bolsa_familia);
    
    // Calcular protocolos irregulares baseado no subset filtrado
    const calcIrregular = (field: keyof Individual, customFilter?: (d: Individual) => boolean) => {
      const dataToUse = customFilter ? subset.filter(customFilter) : subset;
      const irregular = dataToUse.filter(d => {
        const value = d[field];
        return value === "irregular";
      });
      const regular = dataToUse.filter(d => {
        const value = d[field];
        return value === "regular";
      });
      return {
        total: dataToUse.length,
        irregular: irregular.length,
        regular: regular.length,
        percentualIrregular: dataToUse.length > 0 ? ((irregular.length / dataToUse.length) * 100).toFixed(1) : "0",
        percentualRegular: dataToUse.length > 0 ? ((regular.length / dataToUse.length) * 100).toFixed(1) : "0"
      };
    };
    
    // Assistência Social
    const cadunico = calcIrregular("protocolo_smas_cadunico_atualizado");
    const equipeFamilia = calcIrregular("protocolo_sms_possui_equipe_familia");
    
    // Educação
    const frequencia = calcIrregular("protocolo_sme_frequencia_escolar");
    const matricula = calcIrregular("protocolo_sme_matriculado_creche");
    
    // Saúde
    const consultasInfantil = calcIrregular("protocolo_sms_consultas_minimas_infantil");
    const prenatal = calcIrregular("protocolo_sms_consultas_pre_natal");
    const vacinacao = calcIrregular("protocolo_sms_vacinacao_pentavalente");
    
    // Calcular completude geral baseado no subset filtrado
    const totalProtocolos = subset.reduce((acc, ind) => {
      const protocolFields = [
        ind.protocolo_smas_cadunico_atualizado,
        ind.protocolo_sme_frequencia_escolar,
        ind.protocolo_sme_matriculado_creche,
        ind.protocolo_sms_consultas_minimas_infantil,
        ind.protocolo_sms_consultas_pre_natal,
        ind.protocolo_sms_possui_equipe_familia,
        ind.protocolo_sms_vacinacao_pentavalente,
      ].filter(p => p !== "nao_aplica");
      return acc + protocolFields.length;
    }, 0);
    
    const regularCount = subset.reduce((acc, ind) => {
      const protocolFields = [
        ind.protocolo_smas_cadunico_atualizado,
        ind.protocolo_sme_frequencia_escolar,
        ind.protocolo_sme_matriculado_creche,
        ind.protocolo_sms_consultas_minimas_infantil,
        ind.protocolo_sms_consultas_pre_natal,
        ind.protocolo_sms_possui_equipe_familia,
        ind.protocolo_sms_vacinacao_pentavalente,
      ].filter(p => p === "regular");
      return acc + protocolFields.length;
    }, 0);
    
    const irregularCount = subset.reduce((acc, ind) => {
      const protocolFields = [
        ind.protocolo_smas_cadunico_atualizado,
        ind.protocolo_sme_frequencia_escolar,
        ind.protocolo_sme_matriculado_creche,
        ind.protocolo_sms_consultas_minimas_infantil,
        ind.protocolo_sms_consultas_pre_natal,
        ind.protocolo_sms_possui_equipe_familia,
        ind.protocolo_sms_vacinacao_pentavalente,
      ].filter(p => p === "irregular");
      return acc + protocolFields.length;
    }, 0);
    
    // Calcular participantes com todos protocolos conformes/não conformes
    const calcParticipantesStatus = (subset: Individual[]) => {
      let todosConformes = 0;
      let algumNaoConforme = 0;
      
      subset.forEach(ind => {
        const protocolos = [
          ind.protocolo_smas_cadunico_atualizado,
          ind.protocolo_sme_frequencia_escolar,
          ind.protocolo_sme_matriculado_creche,
          ind.protocolo_sms_consultas_minimas_infantil,
          ind.protocolo_sms_consultas_pre_natal,
          ind.protocolo_sms_possui_equipe_familia,
          ind.protocolo_sms_vacinacao_pentavalente,
        ].filter(p => p !== "nao_aplica");
        
        const todosRegulares = protocolos.every(p => p === "regular");
        const temIrregular = protocolos.some(p => p === "irregular");
        
        if (todosRegulares) todosConformes++;
        if (temIrregular) algumNaoConforme++;
      });
      
      return {
        total: subset.length,
        todosConformes,
        algumNaoConforme,
        percTodosConformes: subset.length > 0 ? ((todosConformes / subset.length) * 100).toFixed(1) : "0",
        percAlgumNaoConforme: subset.length > 0 ? ((algumNaoConforme / subset.length) * 100).toFixed(1) : "0"
      };
    };
    
    const todosPart = calcParticipantesStatus(ativos);
    const gestantesPart = calcParticipantesStatus(gestantes);
    const criancasPart = calcParticipantesStatus(criancas);

    // Gerar dados de entrada/saída por faixa etária (azul para ativos, vermelho para inativos)
    const faixasEtarias = ["0-1", "1-2", "2-3", "3-4", "4-5", "5-6"];
    const movimentacaoPorIdade = faixasEtarias.map((faixa, index) => {
      // Filtrar todos os dados (ativos e inativos) pela faixa etária e pelo filtro de grupo
      const todosDados = data.filter(d => d.faixa_etaria === faixa);
      const dadosFiltrados = filtro === "criancas" 
        ? todosDados.filter(d => d.grupo.includes("crianca"))
        : filtro === "gestantes" 
        ? todosDados.filter(d => d.grupo.includes("gestante"))
        : todosDados;
      
      // Ativos (azul): participantes ativos nessa faixa
      const ativos = dadosFiltrados.filter(d => d.status === "ativo").length;
      
      // Inativos (vermelho): gerar dados fictícios baseado em cohort
      const percentualInativo = 0.15 + (index * 0.03); // Varia de 15% a 30%
      const inativos = Math.floor(ativos * percentualInativo);
      
      return {
        faixa,
        ativos,
        inativos,
      };
    });

    // Participantes por Safra
    const participantesPorSafra = cohorts.map((cohort, index) => {
      const dadosCohort = data.filter(d => d.cohort === cohort);
      const [ano, mes] = cohort.split('-');
      
      // Multiplicadores especiais para julho e agosto
      const isJulhoAgosto = mes === '07' || mes === '08';
      const multiplicadorAtivos = isJulhoAgosto ? 5 : 3;
      const bonusInativos = isJulhoAgosto ? 200 : 50;
      
      const ativosCount = dadosCohort.filter(d => d.status === "ativo").length * multiplicadorAtivos;
      const inativosCount = Math.floor(ativosCount * (0.15 + index * 0.05)) + Math.floor(Math.random() * bonusInativos + bonusInativos);
      
      // Formatar cohort para "Mês / Ano" (ex: "Maio / 25")
      const mesesNomes = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
      const mesNome = mesesNomes[parseInt(mes) - 1];
      const anoAbrev = ano.substring(2); // "2025" -> "25"
      
      return {
        safra: `${mesNome} / ${anoAbrev}`,
        ativos: ativosCount,
        inativos: inativosCount
      };
    });

    // Resultado do Programa - Protocolos por mês
    // Gerar dados mensais simulados (últimos 6 meses)
    const meses = ["Mai", "Jun", "Jul", "Ago", "Set", "Out"];
    const resultadoPrograma = meses.map((mes, idx) => {
      const crescimento = idx * 4; // Maior crescimento gradual
      return {
        mes,
        todos: 70 + crescimento + Math.random() * 3,
        saude: 55 + crescimento + Math.random() * 3,
        educacao: 62 + crescimento + Math.random() * 3,
        assistencia: 48 + crescimento + Math.random() * 3
      };
    });

    // Motivos de Inativação - dados simulados mais expressivos
    const motivosInativacao = [
      { motivo: "Criança ultrapassou os 6 anos de idade", count: 245, percentual: "35.0" },
      { motivo: "Saiu da base do CadÚnico Rio de Janeiro", count: 189, percentual: "27.0" },
      { motivo: "Mulher com gravidez concluída", count: 154, percentual: "22.0" },
      { motivo: "Óbito", count: 112, percentual: "16.0" }
    ];

    // Análise de Tempo de Irregularidade
    const participantesComIrregularidade = subset.filter(d => d.dias_irregularidade && d.dias_irregularidade > 0);
    
    // 1. Tempo Médio de Irregularidade por Dimensão
    const calcTempoMedioPorDimensao = () => {
      const irregularesAssistencia = subset.filter(d => 
        d.protocolo_smas_cadunico_atualizado === "irregular" || 
        d.protocolo_sms_possui_equipe_familia === "irregular"
      );
      const irregularesEducacao = subset.filter(d => 
        d.protocolo_sme_frequencia_escolar === "irregular" || 
        d.protocolo_sme_matriculado_creche === "irregular"
      );
      const irregularesSaude = subset.filter(d => 
        d.protocolo_sms_consultas_minimas_infantil === "irregular" || 
        d.protocolo_sms_consultas_pre_natal === "irregular" || 
        d.protocolo_sms_vacinacao_pentavalente === "irregular"
      );

      const calcMedia = (arr: Individual[]) => {
        const comDias = arr.filter(d => d.dias_irregularidade);
        if (comDias.length === 0) return 0;
        return Math.round(comDias.reduce((acc, d) => acc + (d.dias_irregularidade || 0), 0) / comDias.length);
      };

      return {
        assistencia: calcMedia(irregularesAssistencia),
        educacao: calcMedia(irregularesEducacao),
        saude: calcMedia(irregularesSaude),
        geral: calcMedia(participantesComIrregularidade)
      };
    };

    const tempoMedioIrregularidade = calcTempoMedioPorDimensao();

    // 2. Distribuição por Faixas de Tempo
    const distribuicaoPorFaixa = {
      "0-30": participantesComIrregularidade.filter(d => (d.dias_irregularidade || 0) <= 30).length,
      "31-60": participantesComIrregularidade.filter(d => (d.dias_irregularidade || 0) > 30 && (d.dias_irregularidade || 0) <= 60).length,
      "61-90": participantesComIrregularidade.filter(d => (d.dias_irregularidade || 0) > 60 && (d.dias_irregularidade || 0) <= 90).length,
      "90+": participantesComIrregularidade.filter(d => (d.dias_irregularidade || 0) > 90).length
    };

    const totalIrregulares = participantesComIrregularidade.length;
    const distribuicaoPercentual = {
      "0-30": totalIrregulares > 0 ? ((distribuicaoPorFaixa["0-30"] / totalIrregulares) * 100).toFixed(1) : "0",
      "31-60": totalIrregulares > 0 ? ((distribuicaoPorFaixa["31-60"] / totalIrregulares) * 100).toFixed(1) : "0",
      "61-90": totalIrregulares > 0 ? ((distribuicaoPorFaixa["61-90"] / totalIrregulares) * 100).toFixed(1) : "0",
      "90+": totalIrregulares > 0 ? ((distribuicaoPorFaixa["90+"] / totalIrregulares) * 100).toFixed(1) : "0"
    };

    // 3. Taxa de Resolução - dados mensais simulados
    const taxaResolucaoMensal = meses.map((mes, idx) => {
      // Simular crescimento na taxa de resolução
      const baseResolucao = 15 + idx * 3; // Crescimento de 15% a 30%
      return {
        mes,
        taxa: baseResolucao + Math.random() * 2,
        resolvidos: Math.floor(50 + idx * 15 + Math.random() * 20)
      };
    });

    // 4. Histórico de Evolução - Tempo médio de irregularidade por mês
    const evolucaoTempoMedio = meses.map((mes, idx) => {
      // Simular tendência de aumento no tempo médio
      const tempoBase = tempoMedioIrregularidade.geral || 45;
      const variacao = idx * 3; // Aumenta ao longo do tempo
      return {
        mes,
        tempoMedio: Math.max(15, tempoBase - 20 + variacao + Math.random() * 5),
        assistencia: Math.max(10, (tempoMedioIrregularidade.assistencia || 40) - 15 + variacao + Math.random() * 5),
        educacao: Math.max(10, (tempoMedioIrregularidade.educacao || 42) - 15 + variacao + Math.random() * 5),
        saude: Math.max(10, (tempoMedioIrregularidade.saude || 48) - 15 + variacao + Math.random() * 5)
      };
    });

    return {
      subset,
      ativos,
      criancas,
      gestantes,
      gestantesSemBolsa,
      criancasComBolsa,
      comBolsa,
      cadunico,
      prenatal,
      consultasInfantil,
      vacinacao,
      frequencia,
      matricula,
      equipeFamilia,
      completudeGeral: totalProtocolos > 0 ? ((regularCount / totalProtocolos) * 100).toFixed(1) : "0",
      emAlertaGeral: totalProtocolos > 0 ? ((irregularCount / totalProtocolos) * 100).toFixed(1) : "0",
      todosPart,
      gestantesPart,
      criancasPart,
      movimentacaoPorIdade,
      participantesPorSafra,
      resultadoPrograma,
      motivosInativacao,
      tempoMedioIrregularidade,
      distribuicaoPorFaixa,
      distribuicaoPercentual,
      totalIrregulares,
      taxaResolucaoMensal,
      evolucaoTempoMedio
    };
  }, [data, filtro, selectedBairro, selectedAP, selectedCRE, selectedCRAS, selectedCohort, cohorts]);

  return (
    <div className="space-y-8">
      {/* Filtros */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Filtros</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {/* Primeiro Nível - Filtros Principais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Principais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <Select value={filtro} onValueChange={(v: "todos" | "criancas" | "gestantes") => setFiltro(v)}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Grupo" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todos">Todos os Grupos</SelectItem>
                  <SelectItem value="criancas">Crianças</SelectItem>
                  <SelectItem value="gestantes">Gestantes</SelectItem>
                </SelectContent>
              </Select>
              
              <Select value={selectedCohort} onValueChange={setSelectedCohort}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Safra" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todas">Todas as Safras</SelectItem>
                  {cohorts.map(cohort => (
                    <SelectItem key={cohort} value={cohort}>
                      {cohort.substring(0, 7)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedSecretaria} onValueChange={(v: "todas" | "assistencia" | "educacao" | "saude") => setSelectedSecretaria(v)}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Secretaria" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todas">Todas as Secretarias</SelectItem>
                  <SelectItem value="assistencia">Assistência Social</SelectItem>
                  <SelectItem value="educacao">Educação</SelectItem>
                  <SelectItem value="saude">Saúde</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Segundo Nível - Filtros Regionais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Regionais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
              <Select value={selectedBairro} onValueChange={setSelectedBairro}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Bairro" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todos">Todos os Bairros</SelectItem>
                  {bairros.map(b => (
                    <SelectItem key={b} value={b}>{b}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedAP} onValueChange={setselectedAP}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="AP" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todas">Todas as AP</SelectItem>
                  {Object.keys(coordenadoriasAP).map(ap => (
                    <SelectItem key={ap} value={ap}>{ap}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedCRE} onValueChange={setSelectedCRE}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="CRE" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todas">Todas as CRE</SelectItem>
                  {Object.keys(coordenadoriasCRE).map(cre => (
                    <SelectItem key={cre} value={cre}>{cre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedCRAS} onValueChange={setSelectedCRAS}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="CAS" />
                </SelectTrigger>
                <SelectContent className="bg-popover z-50">
                  <SelectItem value="todas">Todos as CAS</SelectItem>
                  {Object.keys(coordenadoriasCRAS).map(cras => (
                    <SelectItem key={cras} value={cras}>{cras}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Indicadores Principais */}
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">Indicadores Principais</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Visão macro para lideranças das secretarias (Saúde, Educação, Assistência e Casa Civil)
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <StatCard
            title="Total de Participantes"
            value={stats.subset.length.toLocaleString('pt-BR')}
            description={`Número total de ${filtro === "criancas" ? "crianças" : filtro === "gestantes" ? "gestantes" : "participantes"} ativos`}
            icon={filtro === "criancas" ? Baby : filtro === "gestantes" ? Heart : Users}
            variant="default"
          />
          <StatCard
            title="% Regular"
            value={`${stats.completudeGeral}%`}
            description="Protocolos marcados como regulares"
            icon={Activity}
            variant="success"
          />
          <StatCard
            title="% Irregular"
            value={`${stats.emAlertaGeral}%`}
            description="Protocolos não conformes"
            icon={AlertTriangle}
            variant="destructive"
          />
        </div>

        {/* Dimensão Assistência Social */}
        {(selectedSecretaria === "todas" || selectedSecretaria === "assistencia") && (
          <div className="mb-8">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground mb-4">
              <Home className="h-4 w-4 text-accent" />
              Dimensão Assistência Social
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">💰 Bolsa Família</p>
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.subset.length > 0 ? `${((stats.comBolsa.length / stats.subset.length) * 100).toFixed(1)}%` : "0%"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {stats.comBolsa.length} de {stats.subset.length} participantes
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">📋 CadÚnico Atualizado</p>
                  {parseFloat(stats.cadunico.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.cadunico.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  cadastros desatualizados ({stats.cadunico.irregular} de {stats.cadunico.total})
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">🏠 Equipe de Referência</p>
                  {parseFloat(stats.equipeFamilia.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.equipeFamilia.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  sem acompanhamento ativo ({stats.equipeFamilia.irregular} de {stats.equipeFamilia.total})
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Dimensão Educação */}
        {(selectedSecretaria === "todas" || selectedSecretaria === "educacao") && (
          <div className="mb-8">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground mb-4">
              <BookOpen className="h-4 w-4 text-warning" />
              Dimensão Educação
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">🎒 Frequência Escolar</p>
                  {parseFloat(stats.frequencia.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.frequencia.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  com frequência inferior ao mínimo ({stats.frequencia.irregular} de {stats.frequencia.total})
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">🏫 Matrícula em Creche</p>
                  {parseFloat(stats.matricula.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.matricula.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  fora da rede municipal ({stats.matricula.irregular} de {stats.matricula.total})
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Dimensão Saúde */}
        {(selectedSecretaria === "todas" || selectedSecretaria === "saude") && (
          <div className="mb-8">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground mb-4">
              <Activity className="h-4 w-4 text-destructive" />
              Dimensão Saúde
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">👶 Consultas Infantis</p>
                  {parseFloat(stats.consultasInfantil.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.consultasInfantil.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  crianças não conformes ({stats.consultasInfantil.irregular} de {stats.consultasInfantil.total})
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">👩‍⚕️ Consultas Pré-natal</p>
                  {parseFloat(stats.prenatal.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.prenatal.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  gestantes não conformes ({stats.prenatal.irregular} de {stats.prenatal.total})
                </p>
              </div>
              <div className="bg-muted rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-foreground">💉 Vacinação</p>
                  {parseFloat(stats.vacinacao.percentualIrregular) >= 30 && <AlertTriangle className="h-4 w-4 text-destructive" />}
                </div>
                <p className="text-2xl font-bold text-foreground mb-1">
                  {stats.vacinacao.percentualIrregular}%
                </p>
                <p className="text-xs text-muted-foreground">
                  cobertura não conforme ({stats.vacinacao.irregular} de {stats.vacinacao.total})
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Resultado do Programa */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Resultado do Programa</CardTitle>
            <p className="text-sm text-muted-foreground">
              Evolução mensal da completude de protocolos por dimensão
            </p>
          </CardHeader>
          <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <RechartsLineChart
                  data={stats.resultadoPrograma}
                  margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="mes" />
                  <YAxis label={{ value: '% Completude', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="todos" stroke="#8b5cf6" strokeWidth={2} name="Todos os Protocolos" />
                  {(selectedSecretaria === "todas" || selectedSecretaria === "saude") && (
                    <Line type="monotone" dataKey="saude" stroke="#ef4444" strokeWidth={2} name="Protocolos da Saúde" />
                  )}
                  {(selectedSecretaria === "todas" || selectedSecretaria === "educacao") && (
                    <Line type="monotone" dataKey="educacao" stroke="#f59e0b" strokeWidth={2} name="Protocolos da Educação" />
                  )}
                  {(selectedSecretaria === "todas" || selectedSecretaria === "assistencia") && (
                    <Line type="monotone" dataKey="assistencia" stroke="#10b981" strokeWidth={2} name="Protocolos da Assistência" />
                  )}
                </RechartsLineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

        {/* Análise de Tempo de Irregularidade */}
        <div className="space-y-6 mb-8">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            <h2 className="text-2xl font-bold text-foreground">
              Análise de Tempo de Irregularidade
            </h2>
          </div>

          {/* Cards de Tempo Médio por Dimensão */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {(selectedSecretaria === "todas") && (
              <Card className="border-2 bg-card">
                <CardContent className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="h-4 w-4 text-primary" />
                    <p className="text-sm font-medium text-muted-foreground">Tempo Médio Geral</p>
                  </div>
                  <p className="text-3xl font-bold text-foreground mb-1">
                    {stats.tempoMedioIrregularidade.geral} dias
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {stats.totalIrregulares} participantes irregulares
                  </p>
                </CardContent>
              </Card>
            )}

            {(selectedSecretaria === "todas" || selectedSecretaria === "assistencia") && (
              <Card className="border-2 bg-success-light border-success">
                <CardContent className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <Home className="h-4 w-4 text-success" />
                    <p className="text-sm font-medium text-muted-foreground">Assistência Social</p>
                  </div>
                  <p className="text-3xl font-bold text-foreground mb-1">
                    {stats.tempoMedioIrregularidade.assistencia} dias
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Média de tempo irregular
                  </p>
                </CardContent>
              </Card>
            )}

            {(selectedSecretaria === "todas" || selectedSecretaria === "educacao") && (
              <Card className="border-2 bg-warning-light border-warning">
                <CardContent className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="h-4 w-4 text-warning" />
                    <p className="text-sm font-medium text-muted-foreground">Educação</p>
                  </div>
                  <p className="text-3xl font-bold text-foreground mb-1">
                    {stats.tempoMedioIrregularidade.educacao} dias
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Média de tempo irregular
                  </p>
                </CardContent>
              </Card>
            )}

            {(selectedSecretaria === "todas" || selectedSecretaria === "saude") && (
              <Card className="border-2 bg-destructive/10 border-destructive">
                <CardContent className="p-6">
                  <div className="flex items-center gap-2 mb-2">
                    <Heart className="h-4 w-4 text-destructive" />
                    <p className="text-sm font-medium text-muted-foreground">Saúde</p>
                  </div>
                  <p className="text-3xl font-bold text-foreground mb-1">
                    {stats.tempoMedioIrregularidade.saude} dias
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Média de tempo irregular
                  </p>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Gráficos de Análise de Tempo */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Distribuição por Faixas de Tempo */}
            <Card>
              <CardHeader>
                <CardTitle>Distribuição por Tempo de Irregularidade</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Quantos participantes estão irregulares em cada faixa de tempo
                </p>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart
                    data={[
                      { faixa: "0-30 dias", count: stats.distribuicaoPorFaixa["0-30"], percentual: stats.distribuicaoPercentual["0-30"] },
                      { faixa: "31-60 dias", count: stats.distribuicaoPorFaixa["31-60"], percentual: stats.distribuicaoPercentual["31-60"] },
                      { faixa: "61-90 dias", count: stats.distribuicaoPorFaixa["61-90"], percentual: stats.distribuicaoPercentual["61-90"] },
                      { faixa: "90+ dias", count: stats.distribuicaoPorFaixa["90+"], percentual: stats.distribuicaoPercentual["90+"] }
                    ]}
                    margin={{ top: 20, right: 30, left: 20, bottom: 40 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="faixa" />
                    <YAxis />
                    <Tooltip 
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="bg-background border rounded-lg p-3 shadow-lg">
                              <p className="font-semibold mb-2">{data.faixa}</p>
                              <p className="text-sm">Participantes: {data.count}</p>
                              <p className="text-sm">Percentual: {data.percentual}%</p>
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
              </CardContent>
            </Card>

            {/* Taxa de Resolução Mensal */}
            <Card>
              <CardHeader>
                <CardTitle>Taxa de Resolução Mensal</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Percentual de protocolos irregulares resolvidos por mês
                </p>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <RechartsLineChart
                    data={stats.taxaResolucaoMensal}
                    margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="mes" />
                    <YAxis label={{ value: '% Resolvidos', angle: -90, position: 'insideLeft' }} />
                    <Tooltip 
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="bg-background border rounded-lg p-3 shadow-lg">
                              <p className="font-semibold mb-2">Mês: {data.mes}</p>
                              <p className="text-sm">Taxa: {data.taxa.toFixed(1)}%</p>
                              <p className="text-sm">Resolvidos: {data.resolvidos}</p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="taxa" stroke="#10b981" strokeWidth={2} name="Taxa de Resolução (%)" />
                  </RechartsLineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          {/* Histórico de Evolução do Tempo Médio */}
          <Card>
            <CardHeader>
              <CardTitle>Evolução do Tempo Médio de Irregularidade</CardTitle>
              <p className="text-sm text-muted-foreground">
                Como o tempo médio de irregularidade tem evoluído ao longo dos meses por dimensão
              </p>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <RechartsLineChart
                  data={stats.evolucaoTempoMedio}
                  margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="mes" />
                  <YAxis label={{ value: 'Dias', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="tempoMedio" stroke="#8b5cf6" strokeWidth={2} name="Tempo Médio Geral" />
                  {(selectedSecretaria === "todas" || selectedSecretaria === "assistencia") && (
                    <Line type="monotone" dataKey="assistencia" stroke="#10b981" strokeWidth={2} name="Assistência Social" />
                  )}
                  {(selectedSecretaria === "todas" || selectedSecretaria === "educacao") && (
                    <Line type="monotone" dataKey="educacao" stroke="#f59e0b" strokeWidth={2} name="Educação" />
                  )}
                  {(selectedSecretaria === "todas" || selectedSecretaria === "saude") && (
                    <Line type="monotone" dataKey="saude" stroke="#ef4444" strokeWidth={2} name="Saúde" />
                  )}
                </RechartsLineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Participantes por Safra e Motivos de Saída - lado a lado */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Participantes por Safra */}
          <Card>
            <CardHeader>
              <CardTitle>Participantes por Safra</CardTitle>
              <p className="text-sm text-muted-foreground">
                Acompanhamento de entrada e saída de participantes do programa ao longo do tempo
              </p>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={450}>
                <BarChart
                  data={stats.participantesPorSafra}
                  margin={{ top: 20, right: 30, left: 20, bottom: 40 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="safra" label={{ value: 'Safra', position: 'insideBottom', offset: -5 }} />
                  <YAxis label={{ value: 'Participantes', angle: -90, position: 'insideLeft' }} />
                  <Tooltip 
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-background border rounded-lg p-3 shadow-lg">
                            <p className="font-semibold mb-2">Safra: {data.safra}</p>
                            <p className="text-sm" style={{ color: '#3b82f6' }}>Ativos: {data.ativos}</p>
                            <p className="text-sm" style={{ color: '#ef4444' }}>Inativos: {data.inativos}</p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Legend wrapperStyle={{ paddingTop: '20px' }} />
                  <Bar dataKey="ativos" fill="#3b82f6" name="Participantes Ativos" />
                  <Bar dataKey="inativos" fill="#ef4444" name="Participantes Inativos" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Motivos de Saída do Programa */}
          <Card>
            <CardHeader>
              <CardTitle>Motivos de Saída do Programa</CardTitle>
              <p className="text-sm text-muted-foreground">
                Distribuição dos motivos pelos quais participantes saíram do programa
              </p>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={450}>
                <PieChart>
                  <Pie
                    data={stats.motivosInativacao}
                    dataKey="count"
                    nameKey="motivo"
                    cx="50%"
                    cy="50%"
                    outerRadius={140}
                    label={(entry) => `${entry.percentual}%`}
                    labelLine={true}
                  >
                    <Cell fill="#ef4444" />
                    <Cell fill="#f59e0b" />
                    <Cell fill="#10b981" />
                    <Cell fill="#3b82f6" />
                  </Pie>
                  <Tooltip 
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-background border rounded-lg p-3 shadow-lg">
                            <p className="font-semibold mb-2">{data.motivo}</p>
                            <p className="text-sm">Quantidade: {data.count}</p>
                            <p className="text-sm">Percentual: {data.percentual}%</p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Legend 
                    wrapperStyle={{ paddingTop: '20px' }}
                    formatter={(value, entry: any) => `${entry.payload.motivo}`}
                  />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </div>

    </div>
  );
}
