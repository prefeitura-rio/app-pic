import { useState, useMemo, useEffect } from "react";
import { Individual, bairros, unidadesPorBairro, coordenadoriasAP, coordenadoriasCRE, coordenadoriasCRAS } from "@/lib/csvLoader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Users, Search, ChevronLeft, ChevronRight, Eye, ChevronsUpDown } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";

interface ProfessionalTabProps {
  data: Individual[];
}

// Lista de protocolos disponíveis
const protocolOptions = [
  { value: "protocolo_smas_cadunico_atualizado", label: "CadÚnico Atualizado" },
  { value: "protocolo_sme_frequencia_escolar", label: "Frequência Escolar" },
  { value: "protocolo_sme_matriculado_creche", label: "Matriculado Creche" },
  { value: "protocolo_sme_matriculado_pre_escola", label: "Matriculado Pré-Escola" },
  { value: "protocolo_sms_consulta_puerperal", label: "Consulta Puerperal" },
  { value: "protocolo_sms_consultas_minimas_infantil", label: "Consultas Mínimas Infantil" },
  { value: "protocolo_sms_consultas_pre_natal", label: "Consultas Pré-Natal" },
  { value: "protocolo_sms_gestantes_testes_rapidos", label: "Testes Rápidos Gestantes" },
  { value: "protocolo_sms_possui_equipe_familia", label: "Possui Equipe Família" },
  { value: "protocolo_sms_vacinacao_pentavalente", label: "Vacinação Pentavalente" },
  { value: "protocolo_sms_visitas_domiciliares_infantil", label: "Visitas Domiciliares Infantil" },
  { value: "protocolo_sms_visitas_domiciliares_puerperio", label: "Visitas Domiciliares Puerpério" }
];

export function ProfessionalTab({ data }: ProfessionalTabProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedBairro, setSelectedBairro] = useState<string>("todos");
  const [selectedEscola, setSelectedEscola] = useState<string>("todas");
  const [selectedClinica, setSelectedClinica] = useState<string>("todas");
  const [selectedCRASUnidade, setSelectedCRASUnidade] = useState<string>("todas");
  const [selectedGrupo, setSelectedGrupo] = useState<string>("todos");
  const [selectedStatus, setSelectedStatus] = useState<string>("ativo");
  const [selectedAP, setselectedAP] = useState<string>("todas");
  const [selectedCRE, setSelectedCRE] = useState<string>("todas");
  const [selectedCRAS, setSelectedCRAS] = useState<string>("todas");
  const [selectedSituacao, setSelectedSituacao] = useState<string>("todos");
  const [selectedProtocolos, setSelectedProtocolos] = useState<string[]>([]);
  const [openProtocolPopover, setOpenProtocolPopover] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(50);
  const [selectedIndividual, setSelectedIndividual] = useState<Individual | null>(null);

  // Resetar página quando filtros mudarem
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, selectedBairro, selectedEscola, selectedClinica, selectedCRASUnidade, selectedGrupo, selectedStatus, selectedAP, selectedCRE, selectedCRAS, selectedSituacao, selectedProtocolos]);

  // Categorizar todas as unidades
  const todasUnidades = useMemo(() => {
    return Object.values(unidadesPorBairro).flat();
  }, []);

  const escolas = useMemo(() => {
    return todasUnidades.filter(u => u.includes("EDI") || u.includes("Creche"));
  }, [todasUnidades]);

  const clinicas = useMemo(() => {
    return todasUnidades.filter(u => u.includes("CF") || u.includes("ESF") || u.includes("Clínica"));
  }, [todasUnidades]);

  const crasUnidades = useMemo(() => {
    return todasUnidades.filter(u => u.includes("CRAS"));
  }, [todasUnidades]);

  const getCompletudePorDimensao = (individual: Individual) => {
    const isCrianca = individual.grupo.includes("crianca");
    const isGestante = individual.grupo.includes("gestante");

    // Protocolos de Assistência
    const assistenciaProtocols = [
      "protocolo_smas_cadunico_atualizado",
      "protocolo_sms_possui_equipe_familia",
    ];

    // Protocolos de Educação
    const educacaoProtocols = isCrianca ? [
      "protocolo_sme_frequencia_escolar",
      "protocolo_sme_matriculado_creche",
      "protocolo_sme_matriculado_pre_escola",
    ] : [];

    // Protocolos de Saúde
    const saudeProtocols = [];
    if (isCrianca) {
      saudeProtocols.push(
        "protocolo_sms_consultas_minimas_infantil",
        "protocolo_sms_vacinacao_pentavalente"
      );
    }
    if (isGestante) {
      saudeProtocols.push(
        "protocolo_sms_consultas_pre_natal",
        "protocolo_sms_gestantes_testes_rapidos"
      );
    }

    const calcularCompletude = (protocols: string[]) => {
      let regular = 0;
      let total = 0;
      
      protocols.forEach(key => {
        const value = individual[key as keyof Individual] as string;
        if (value === "nao_aplica") return;
        total++;
        if (value === "regular" || value === "atencao") regular++;
      });
      
      const percentage = total > 0 ? (regular / total) * 100 : 0;
      return { percentage, regular, total };
    };

    const assistencia = calcularCompletude(assistenciaProtocols);
    const educacao = calcularCompletude(educacaoProtocols);
    const saude = calcularCompletude(saudeProtocols);
    
    const allProtocols = [...assistenciaProtocols, ...educacaoProtocols, ...saudeProtocols];
    const total = calcularCompletude(allProtocols);

    return { total, assistencia, educacao, saude };
  };

  const getSituacaoGeral = (individual: Individual): { status: string; completude: number } => {
    const { total } = getCompletudePorDimensao(individual);
    
    // Coletar todos os protocolos relevantes
    const protocolKeys = [
      "protocolo_smas_cadunico_atualizado",
      "protocolo_sme_frequencia_escolar",
      "protocolo_sme_matriculado_creche",
      "protocolo_sme_matriculado_pre_escola",
      "protocolo_sms_consulta_puerperal",
      "protocolo_sms_consultas_minimas_infantil",
      "protocolo_sms_consultas_pre_natal",
      "protocolo_sms_gestantes_testes_rapidos",
      "protocolo_sms_possui_equipe_familia",
      "protocolo_sms_vacinacao_pentavalente",
      "protocolo_sms_visitas_domiciliares_infantil",
      "protocolo_sms_visitas_domiciliares_puerperio"
    ];
    
    let temIrregular = false;
    let temAtencao = false;
    
    protocolKeys.forEach(key => {
      const value = individual[key as keyof Individual];
      if (value === "irregular") temIrregular = true;
      if (value === "atencao") temAtencao = true;
    });
    
    let status: string;
    if (temIrregular) {
      status = "Irregular";
    } else if (temAtencao) {
      status = "Atenção";
    } else {
      status = "Regular";
    }
    
    return {
      status,
      completude: total.percentage
    };
  };

  const filteredData = useMemo(() => {
    return data.filter(d => {
      // Filtro de status
      if (d.status !== selectedStatus) return false;
      
      // Filtros de agrupadores regionais
      if (selectedAP !== "todas") {
        const bairrosAP = coordenadoriasAP[selectedAP] || [];
        if (!bairrosAP.includes(d.bairro)) return false;
      }
      
      if (selectedCRE !== "todas") {
        const bairrosCRE = coordenadoriasCRE[selectedCRE] || [];
        if (!bairrosCRE.includes(d.bairro)) return false;
      }
      
      if (selectedCRAS !== "todas") {
        const bairrosCRAS = coordenadoriasCRAS[selectedCRAS] || [];
        if (!bairrosCRAS.includes(d.bairro)) return false;
      }
      
      // Filtro de bairro
      if (selectedBairro !== "todos" && d.bairro !== selectedBairro) return false;
      
      // Filtros de unidades por tipo
      if (selectedEscola !== "todas" && d.unidade !== selectedEscola) return false;
      if (selectedClinica !== "todas" && d.unidade !== selectedClinica) return false;
      if (selectedCRASUnidade !== "todas" && d.unidade !== selectedCRASUnidade) return false;
      
      // Filtro de grupo
      if (selectedGrupo !== "todos") {
        if (selectedGrupo === "criança" && !d.grupo.includes("crianca")) return false;
        if (selectedGrupo === "gestante" && !d.grupo.includes("gestante")) return false;
      }
      
      // Filtro de situação
      if (selectedSituacao !== "todos") {
        const { status } = getSituacaoGeral(d);
        if (status !== selectedSituacao) return false;
      }
      
      // Filtro de protocolos específicos violados
      if (selectedProtocolos.length > 0) {
        const todosProtocolosViolados = selectedProtocolos.every(protocolo => {
          const value = d[protocolo as keyof Individual];
          return value === "irregular";
        });
        
        if (!todosProtocolosViolados) return false;
      }
      
      // Filtro de busca (CPF ou nome)
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        if (!d.nome.toLowerCase().includes(query) && !d.cpf.includes(query)) {
          return false;
        }
      }
      
      return true;
    });
  }, [data, searchQuery, selectedBairro, selectedEscola, selectedClinica, selectedCRASUnidade, selectedGrupo, selectedStatus, selectedAP, selectedCRE, selectedCRAS, selectedSituacao, selectedProtocolos]);

  // Paginação
  const totalPages = Math.ceil(filteredData.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedData = filteredData.slice(startIndex, endIndex);

  const getProtocolBadge = (value: string) => {
    if (value === "regular") {
      return { variant: "default" as const, text: "✓ Regular" };
    } else if (value === "atencao") {
      return { variant: "warning" as const, text: "⚠ Atenção" };
    } else if (value === "irregular") {
      return { variant: "destructive" as const, text: "✗ Irregular" };
    } else {
      return { variant: "secondary" as const, text: "N/A" };
    }
  };


  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground mb-2">Busca Individual</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Busque por CPF ou nome para ver os detalhes de uma pessoa específica
        </p>
      </div>

      {/* Filtros e Busca */}
      <Card className="border-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-primary" />
            Filtros e Busca
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Campo de Busca */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <Input
              placeholder="Buscar por CPF ou nome..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Filtros principais: Grupo, Situação e Protocolos Violados */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Principais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Select value={selectedGrupo} onValueChange={setSelectedGrupo}>
              <SelectTrigger>
                <SelectValue placeholder="Grupo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Grupos</SelectItem>
                <SelectItem value="criança">Crianças</SelectItem>
                <SelectItem value="gestante">Gestantes</SelectItem>
              </SelectContent>
            </Select>

            <Select value={selectedSituacao} onValueChange={setSelectedSituacao}>
              <SelectTrigger>
                <SelectValue placeholder="Situação" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todas as Situações</SelectItem>
                <SelectItem value="Regular">Regular</SelectItem>
                <SelectItem value="Atenção">Atenção</SelectItem>
                <SelectItem value="Irregular">Irregular</SelectItem>
              </SelectContent>
            </Select>

            <Popover open={openProtocolPopover} onOpenChange={setOpenProtocolPopover}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={openProtocolPopover}
                  className="justify-between w-full"
                >
                  {selectedProtocolos.length > 0
                    ? `${selectedProtocolos.length} protocolo(s) violado(s) selecionado(s)`
                    : "Filtrar por protocolos violados específicos"}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[400px] p-0">
                <Command>
                  <CommandInput placeholder="Buscar protocolo..." />
                  <CommandList>
                    <CommandEmpty>Nenhum protocolo encontrado.</CommandEmpty>
                    <CommandGroup>
                      {protocolOptions.map((protocol) => (
                        <CommandItem
                          key={protocol.value}
                          onSelect={() => {
                            setSelectedProtocolos((prev) =>
                              prev.includes(protocol.value)
                                ? prev.filter((p) => p !== protocol.value)
                                : [...prev, protocol.value]
                            );
                          }}
                        >
                          <div className="flex items-center gap-2 w-full">
                            <Checkbox
                              checked={selectedProtocolos.includes(protocol.value)}
                              onCheckedChange={() => {}}
                            />
                            <span className="flex-1">{protocol.label}</span>
                          </div>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                  {selectedProtocolos.length > 0 && (
                    <div className="border-t p-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          setSelectedProtocolos([]);
                          setOpenProtocolPopover(false);
                        }}
                      >
                        Limpar seleção
                      </Button>
                    </div>
                  )}
                </Command>
              </PopoverContent>
            </Popover>
            </div>
          </div>

          {/* Filtros Regionais */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Filtros Regionais
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Select value={selectedAP} onValueChange={setselectedAP}>
              <SelectTrigger>
                <SelectValue placeholder="AP (Saúde)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as APs</SelectItem>
                {Object.keys(coordenadoriasAP).map(ap => (
                  <SelectItem key={ap} value={ap}>{ap}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedCRE} onValueChange={setSelectedCRE}>
              <SelectTrigger>
                <SelectValue placeholder="CRE (Educação)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as CREs</SelectItem>
                {Object.keys(coordenadoriasCRE).map(cre => (
                  <SelectItem key={cre} value={cre}>{cre}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedCRAS} onValueChange={setSelectedCRAS}>
              <SelectTrigger>
                <SelectValue placeholder="CRAS (Assistência)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todos os CAS</SelectItem>
                {Object.keys(coordenadoriasCRAS).map(cras => (
                  <SelectItem key={cras} value={cras}>{cras}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            </div>
          </div>

          {/* Filtros Locais */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Select value={selectedBairro} onValueChange={setSelectedBairro}>
              <SelectTrigger>
                <SelectValue placeholder="Bairro" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Bairros</SelectItem>
                {bairros.map(b => (
                  <SelectItem key={b} value={b}>{b}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedEscola} onValueChange={setSelectedEscola}>
              <SelectTrigger>
                <SelectValue placeholder="Escolas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as Escolas</SelectItem>
                {escolas.map(e => (
                  <SelectItem key={e} value={e}>{e}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedClinica} onValueChange={setSelectedClinica}>
              <SelectTrigger>
                <SelectValue placeholder="Clínicas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as Clínicas da Família</SelectItem>
                {clinicas.map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedCRASUnidade} onValueChange={setSelectedCRASUnidade}>
              <SelectTrigger>
                <SelectValue placeholder="CRAS" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todos os CRAS</SelectItem>
                {crasUnidades.map(cr => (
                  <SelectItem key={cr} value={cr}>{cr}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Contador de resultados */}
          <div className="flex items-center justify-between pt-2 border-t">
            <p className="text-sm text-muted-foreground">
              {filteredData.length} pessoa(s) encontrada(s)
            </p>
            {(searchQuery.trim() || selectedBairro !== "todos" || selectedEscola !== "todas" || selectedClinica !== "todas" || selectedCRASUnidade !== "todas" || selectedGrupo !== "todos" || selectedAP !== "todas" || selectedCRE !== "todas" || selectedCRAS !== "todas" || selectedSituacao !== "todos" || selectedProtocolos.length > 0) && (
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => {
                  setSearchQuery("");
                  setSelectedBairro("todos");
                  setSelectedEscola("todas");
                  setSelectedClinica("todas");
                  setSelectedCRASUnidade("todas");
                  setSelectedGrupo("todos");
                  setselectedAP("todas");
                  setSelectedCRE("todas");
                  setSelectedCRAS("todas");
                  setSelectedSituacao("todos");
                  setSelectedProtocolos([]);
                }}
              >
                Limpar filtros
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Resultados */}
      {filteredData.length > 0 && (
        <Card className="border-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              {searchQuery.trim() || selectedBairro !== "todos" || selectedEscola !== "todas" || selectedClinica !== "todas" || selectedCRASUnidade !== "todas" || selectedGrupo !== "todos" || selectedSituacao !== "todos" || selectedProtocolos.length > 0
                ? "Resultados da Busca" 
                : "Lista de Pessoas"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted">
                    <TableHead>Nome</TableHead>
                    <TableHead>CPF</TableHead>
                    <TableHead>Grupo</TableHead>
                    <TableHead>Bairro</TableHead>
                    <TableHead>Idade</TableHead>
                    <TableHead className="text-center">Total</TableHead>
                    <TableHead className="text-center">Assistência</TableHead>
                    <TableHead className="text-center">Educação</TableHead>
                    <TableHead className="text-center">Saúde</TableHead>
                    <TableHead>Situação</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedData.map((individual, idx) => {
                    const situacao = getSituacaoGeral(individual);
                    const completude = getCompletudePorDimensao(individual);
                    return (
                      <TableRow 
                        key={`${individual.cpf}-${idx}`} 
                        className="hover:bg-muted/50 cursor-pointer"
                        onClick={() => setSelectedIndividual(individual)}
                      >
                        <TableCell className="font-medium">{individual.nome}</TableCell>
                        <TableCell className="font-mono text-sm">{individual.cpf}</TableCell>
                        <TableCell>
                          {individual.grupo.includes("crianca") ? "👶 Criança" : "🤰 Gestante"}
                        </TableCell>
                        <TableCell>{individual.bairro}</TableCell>
                        <TableCell>
                          {individual.idade_anos !== undefined ? `${individual.idade_anos} anos` : "-"}
                        </TableCell>
                        <TableCell className="text-center">
                          <span className={`font-semibold ${
                            completude.total.percentage >= 80 ? "text-success" :
                            completude.total.percentage >= 50 ? "text-warning" : "text-destructive"
                          }`}>
                            {completude.total.regular} / {completude.total.total}
                          </span>
                        </TableCell>
                        <TableCell className="text-center">
                          <span className="text-sm">{completude.assistencia.regular} / {completude.assistencia.total}</span>
                        </TableCell>
                        <TableCell className="text-center">
                          <span className="text-sm">{completude.educacao.regular} / {completude.educacao.total}</span>
                        </TableCell>
                        <TableCell className="text-center">
                          <span className="text-sm">{completude.saude.regular} / {completude.saude.total}</span>
                        </TableCell>
                        <TableCell>
                          <Badge 
                            variant={
                              situacao.status === "Regular" ? "default" : 
                              situacao.status === "Atenção" ? "warning" : 
                              "destructive"
                            }
                            className="whitespace-nowrap"
                          >
                            {situacao.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {/* Paginação */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-muted-foreground">
                  Mostrando {startIndex + 1} a {Math.min(endIndex, filteredData.length)} de {filteredData.length} registros
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Anterior
                  </Button>
                  <div className="flex items-center gap-1">
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      let pageNum;
                      if (totalPages <= 5) {
                        pageNum = i + 1;
                      } else if (currentPage <= 3) {
                        pageNum = i + 1;
                      } else if (currentPage >= totalPages - 2) {
                        pageNum = totalPages - 4 + i;
                      } else {
                        pageNum = currentPage - 2 + i;
                      }
                      return (
                        <Button
                          key={pageNum}
                          variant={currentPage === pageNum ? "default" : "outline"}
                          size="sm"
                          onClick={() => setCurrentPage(pageNum)}
                          className="w-9"
                        >
                          {pageNum}
                        </Button>
                      );
                    })}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                  >
                    Próxima
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Mensagem quando não há resultados */}
      {filteredData.length === 0 && (
        <Card className="border-2 border-dashed">
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground">
              <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">Nenhum resultado encontrado</p>
              <p className="text-sm mt-2">Tente ajustar os filtros ou a busca</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Modal de Detalhamento */}
      <Dialog open={!!selectedIndividual} onOpenChange={() => setSelectedIndividual(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          {selectedIndividual && (
            <>
              <DialogHeader>
                <DialogTitle className="text-2xl flex items-center gap-2">
                  <Eye className="h-6 w-6 text-primary" />
                  Detalhamento Individual
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6 mt-4">
                {/* Informações Básicas */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Informações Básicas</h3>
                  <div className="grid grid-cols-2 gap-4 bg-muted/50 p-4 rounded-lg">
                    <div>
                      <p className="text-sm text-muted-foreground">Nome</p>
                      <p className="font-medium">{selectedIndividual.nome}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">CPF</p>
                      <p className="font-mono font-medium">{selectedIndividual.cpf}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Grupo</p>
                      <p className="font-medium">
                        {selectedIndividual.grupo.includes("crianca") ? "👶 Criança" : "🤰 Gestante"}
                        {selectedIndividual.bolsa_familia && " • Bolsa Família"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Idade</p>
                      <p className="font-medium">
                        {selectedIndividual.idade_anos !== undefined ? `${selectedIndividual.idade_anos} anos` : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Bairro</p>
                      <p className="font-medium">{selectedIndividual.bairro}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Escola</p>
                      <p className="font-medium">
                        {selectedIndividual.unidade.includes("EDI") || selectedIndividual.unidade.includes("Creche") 
                          ? selectedIndividual.unidade 
                          : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Clínica da Família</p>
                      <p className="font-medium">
                        {selectedIndividual.unidade.includes("CF") || selectedIndividual.unidade.includes("ESF") || selectedIndividual.unidade.includes("Clínica")
                          ? selectedIndividual.unidade 
                          : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">CRAS</p>
                      <p className="font-medium">
                        {selectedIndividual.unidade.includes("CRAS")
                          ? selectedIndividual.unidade 
                          : "-"}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Safra</p>
                      <p className="font-medium">{selectedIndividual.cohort}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Status</p>
                      <Badge variant={selectedIndividual.status === "ativo" ? "default" : "secondary"}>
                        {selectedIndividual.status}
                      </Badge>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Situação Geral */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">Situação Geral</h3>
                  <div className="bg-muted/50 p-4 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground mb-1">Status</p>
                        <Badge 
                          variant={
                            getSituacaoGeral(selectedIndividual).status === "Regular" ? "default" : 
                            getSituacaoGeral(selectedIndividual).status === "Atenção" ? "warning" : 
                            "destructive"
                          }
                          className="text-base"
                        >
                          {getSituacaoGeral(selectedIndividual).status}
                        </Badge>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground mb-1">Completude Total</p>
                        <p className="text-3xl font-bold text-primary">
                          {getSituacaoGeral(selectedIndividual).completude.toFixed(0)}%
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Dimensão Assistência Social */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">📋 Dimensão Assistência Social</h3>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                      <span className="text-sm">CadÚnico Atualizado</span>
                      <Badge variant={getProtocolBadge(selectedIndividual.protocolo_smas_cadunico_atualizado).variant}>
                        {getProtocolBadge(selectedIndividual.protocolo_smas_cadunico_atualizado).text}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                      <span className="text-sm">Possui Equipe da Família</span>
                      <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sms_possui_equipe_familia).variant}>
                        {getProtocolBadge(selectedIndividual.protocolo_sms_possui_equipe_familia).text}
                      </Badge>
                    </div>
                  </div>
                </div>

                <Separator />

                {/* Dimensão Educação */}
                {selectedIndividual.grupo.includes("crianca") && (
                  <>
                    <div>
                      <h3 className="text-lg font-semibold mb-3 text-foreground">📚 Dimensão Educação</h3>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Frequência Escolar</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sme_frequencia_escolar).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sme_frequencia_escolar).text}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Matriculado em Creche</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sme_matriculado_creche).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sme_matriculado_creche).text}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Matriculado em Pré-escola</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sme_matriculado_pre_escola).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sme_matriculado_pre_escola).text}
                          </Badge>
                        </div>
                      </div>
                    </div>
                    <Separator />
                  </>
                )}

                {/* Dimensão Saúde */}
                <div>
                  <h3 className="text-lg font-semibold mb-3 text-foreground">🏥 Dimensão Saúde</h3>
                  <div className="space-y-2">
                    {selectedIndividual.grupo.includes("crianca") && (
                      <>
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Consultas Mínimas Infantil</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sms_consultas_minimas_infantil).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sms_consultas_minimas_infantil).text}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Vacinação Pentavalente</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sms_vacinacao_pentavalente).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sms_vacinacao_pentavalente).text}
                          </Badge>
                        </div>
                      </>
                    )}
                    {selectedIndividual.grupo.includes("gestante") && (
                      <>
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Consultas Pré-natal</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sms_consultas_pre_natal).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sms_consultas_pre_natal).text}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-muted/30 rounded">
                          <span className="text-sm">Testes Rápidos</span>
                          <Badge variant={getProtocolBadge(selectedIndividual.protocolo_sms_gestantes_testes_rapidos).variant}>
                            {getProtocolBadge(selectedIndividual.protocolo_sms_gestantes_testes_rapidos).text}
                          </Badge>
                        </div>
                      </>
                    )}
                  </div>
                </div>

                <Separator />

                {/* Última Atualização */}
                <div className="text-sm text-muted-foreground text-center">
                  Última atualização: {new Date(selectedIndividual.datahora_atualizacao).toLocaleString('pt-BR')}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
