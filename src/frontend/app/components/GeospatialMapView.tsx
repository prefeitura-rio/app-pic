"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import { Map as MapGL } from "react-map-gl/maplibre";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { Button } from "@/app/components/ui/button";
import { Skeleton } from "@/app/components/ui/skeleton";
import { Badge } from "@/app/components/ui/badge";
import { VirtualizedMultiSelect } from "@/app/components/ui/virtualized-multi-select";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/app/components/ui/select";
import { MapPin, Layers, Filter, X } from "lucide-react";
import { GeospatialLayer, SmartFilterOptions } from "@/app/types";
import "maplibre-gl/dist/maplibre-gl.css";

const INITIAL_VIEW_STATE = {
  longitude: -43.2096, // Rio de Janeiro
  latitude: -22.9035,
  zoom: 10,
  pitch: 0,
  bearing: 0,
};

// Cor padrão para todas as camadas - mesma do bairro (opacidade baixa para ver ruas)
const DEFAULT_LAYER_COLOR: [number, number, number, number] = [100, 116, 139, 30]; // slate-500 com opacidade 30

interface ParticipantLocation {
  latitude: number;
  longitude: number;
  nome: string;
  idade?: number;
  grupo?: string;
  bairro?: string;
  situacao?: string;
  status?: string;
  nome_escola?: string;
  nome_cras?: string;
  nome_clinica_familia?: string;
  nome_equipe_familia?: string;
  equipe_familia?: string; // String com médicos e enfermeiros
}

interface GeospatialMapViewProps {
  onBack?: () => void;
  loading?: boolean;
  layers?: GeospatialLayer[]; // Camadas já filtradas do backend
  filters?: Record<string, any>; // Filtros atuais
  availableFilters?: SmartFilterOptions; // Opções de filtros disponíveis do backend
  onFilterChange?: (filters: Record<string, any>) => void; // Callback para atualizar filtros
  participantLocation?: ParticipantLocation; // Localização do participante para sobrepor no mapa
  hideHeader?: boolean; // Esconder o header com título quando embedded no modal
}

export const GeospatialMapView = ({
  onBack,
  loading = false,
  layers = [],
  filters = {},
  availableFilters,
  onFilterChange,
  participantLocation,
  hideHeader = false,
}: GeospatialMapViewProps) => {
  const [viewState, setViewState] = useState(
    participantLocation
      ? {
          ...INITIAL_VIEW_STATE,
          longitude: participantLocation.longitude,
          latitude: participantLocation.latitude,
          zoom: 14, // Zoom mais próximo quando mostrando participante
        }
      : INITIAL_VIEW_STATE
  );

  // Inicializar com BAIRRO como filtro padrão se nenhum filtro estiver ativo
  useEffect(() => {
    const tiposCamada = availableFilters?.tipos_camada;
    if (onFilterChange && !filters.tipo_camada && tiposCamada && tiposCamada.length > 0) {
      // Verificar se BAIRRO existe nas opções
      const hasBairro = tiposCamada.some(
        (opt: any) => opt.id === "BAIRRO" || opt.label === "BAIRRO"
      );
      if (hasBairro) {
        onFilterChange({ ...filters, tipo_camada: "BAIRRO" });
      }
    }
  }, [availableFilters?.tipos_camada]); // Executar apenas quando tipos_camada estiver disponível

  // Converter availableFilters do backend para formato esperado pelos dropdowns
  const filterOptions = useMemo(() => {
    const toOptions = (items: any[]) =>
      (items || []).map((item) =>
        typeof item === "string"
          ? { id: item, label: item }
          : { id: item.id || item.value, label: item.label || item.name || item.id || item.value }
      );

    const options = {
      tipoCamada: toOptions(availableFilters?.tipos_camada || []),
      categoria: toOptions(availableFilters?.categorias || []),
      regional: toOptions(availableFilters?.regionais || []),
      bairro: toOptions(availableFilters?.bairros || []),
      regiaoAdm: toOptions(availableFilters?.regioes_administrativas || []),
      subprefeitura: toOptions(availableFilters?.subprefeituras || []),
      nome: toOptions(availableFilters?.nomes || []),
    };

    return options;
  }, [availableFilters]);

  // Helper para atualizar filtros (suporta string ou array)
  const updateFilter = useCallback(
    (key: string, value: string[] | string | undefined) => {
      if (onFilterChange) {
        let newValue: string | undefined;
        if (Array.isArray(value)) {
          // Multi-select: array vazio = undefined
          newValue = value.length > 0 ? value.join(",") : undefined;
        } else {
          // Single-select: string vazia = undefined
          newValue = value && value !== "" ? value : undefined;
        }
        onFilterChange({
          ...filters,
          [key]: newValue,
        });
      }
    },
    [filters, onFilterChange]
  );

  // Extrair valores atuais dos filtros (convertendo de string para array)
  const getFilterValue = useCallback(
    (key: string): string[] => {
      const value = filters[key];
      if (!value) return [];
      return typeof value === "string" ? value.split(",") : value;
    },
    [filters]
  );

  // Extrair valor single-select (retorna string ao invés de array)
  const getSingleFilterValue = useCallback(
    (key: string): string | undefined => {
      const value = filters[key];
      if (!value) return undefined;
      // Se for array (multi-select anterior), pega o primeiro
      if (Array.isArray(value)) return value[0];
      // Se for string com vírgulas, pega o primeiro
      if (typeof value === "string" && value.includes(",")) {
        return value.split(",")[0];
      }
      return value;
    },
    [filters]
  );

  // Processar camadas para deck.gl
  const deckLayers = useMemo(() => {
    if (!layers.length) return [];

    const result = [];

    // Filtrar camadas válidas (não-null nos campos essenciais)
    // Nome pode ser null - vamos renderizar mesmo assim
    const validLayers = layers.filter(
      (layer) =>
        layer.categoria &&
        layer.tipo_geometria &&
        layer.geometry_geojson
    );

    // Agrupar por categoria
    const layersByCategory = validLayers.reduce((acc, layer) => {
      if (!acc[layer.categoria!]) {
        acc[layer.categoria!] = [];
      }
      acc[layer.categoria!].push(layer);
      return acc;
    }, {} as Record<string, GeospatialLayer[]>);

    // Separar categorias por tipo (polígonos primeiro, pontos depois)
    const polygonCategories: string[] = [];
    const pointCategories: string[] = [];

    Object.entries(layersByCategory).forEach(([categoria, layers]) => {
      const tipoGeometria = layers[0]?.tipo_geometria?.toLowerCase() || "";
      const isPoint = tipoGeometria === "point" || tipoGeometria === "ponto";
      if (isPoint) {
        pointCategories.push(categoria);
      } else {
        polygonCategories.push(categoria);
      }
    });

    // Renderizar polígonos PRIMEIRO (camada de baixo)
    const categoriesToRender = [...polygonCategories, ...pointCategories];

    // Criar deck.gl layers para cada categoria na ordem correta
    for (const categoria of categoriesToRender) {
      const categoryLayers = layersByCategory[categoria];

      // Log para debug: quantas camadas temos antes do parse
      const beforeParse = categoryLayers.length;
      const withoutGeometry = categoryLayers.filter(layer => !layer.geometry_geojson).length;

      // Converter geometry_geojson string para objeto GeoJSON
      let parseErrors = 0;
      const features = categoryLayers
        .filter(layer => layer.geometry_geojson) // Garantir que geometry existe
        .map(layer => {
          try {
            const geometry = JSON.parse(layer.geometry_geojson!);
            return {
              type: "Feature",
              properties: {
                id: layer.id,
                id_unico: layer.id_unico,
                nome: layer.nome,
                categoria: layer.categoria,
                tipo_camada: layer.tipo_camada,
                regional: layer.regional,
                bairro: layer.bairro,
                regiao_administrativa: layer.regiao_administrativa,
                subprefeitura: layer.subprefeitura,
              },
              geometry,
            };
          } catch (e) {
            parseErrors++;
            console.error(
              `Failed to parse geometry for ${layer.nome || layer.id || "unknown"} ` +
              `(ID: ${layer.id}, ${categoria}):`,
              e
            );
            return null;
          }
        })
        .filter((f): f is NonNullable<typeof f> => f !== null);

      const geojson = {
        type: "FeatureCollection" as const,
        features,
      };

      // Determinar tipo de geometria (POINT vs POLYGON)
      const tipoGeometria = categoryLayers[0]?.tipo_geometria?.toLowerCase() || "";
      const isPoint = tipoGeometria === "point" || tipoGeometria === "ponto";

      // Usar cor padrão para todas as camadas
      const color = DEFAULT_LAYER_COLOR;

      if (isPoint) {
        // Usar IconLayer ou ScatterplotLayer para pontos
        const opacity = color[3] / 255;

        // Raio adaptativo baseado no zoom - aumenta quando dá zoom out
        const baseRadius = 50; // Raio base no zoom 14
        const baseZoom = 14;
        const adaptiveRadius = baseRadius * Math.pow(1.3, baseZoom - viewState.zoom);

        result.push(
          new GeoJsonLayer({
            id: `geojson-${categoria}`,
            data: geojson as any,
            pointType: "circle",
            getPointRadius: adaptiveRadius,
            opacity: opacity,
            getFillColor: [color[0], color[1], color[2]], // RGB sem alpha
            getLineColor: [60, 60, 60, 255], // Cinza escuro opaco para mais destaque
            getLineWidth: 2.5, // Outline mais grosso para visibilidade
            pickable: true,
            autoHighlight: true,
            highlightColor: [100, 116, 139, 80], // cinza com opacidade baixa
          })
        );
      } else {
        // GeoJsonLayer para polígonos
        const opacity = color[3] / 255; // Converter alpha para opacity
        result.push(
          new GeoJsonLayer({
            id: `geojson-${categoria}`,
            data: geojson as any,
            stroked: true,
            filled: true,
            extruded: false,
            wireframe: false,
            lineWidthMinPixels: 0.5,
            lineWidthMaxPixels: 1,
            opacity: opacity,
            getFillColor: [color[0], color[1], color[2]], // RGB sem alpha
            getLineColor: [100, 116, 139, 100], // Cinza claro com transparência
            getLineWidth: 0.5,
            pickable: true,
            autoHighlight: true,
            highlightColor: [100, 116, 139, 80], // cinza com opacidade baixa
          })
        );
      }
    }

    // Adicionar layer do participante (quadrado vermelho) se disponível
    if (participantLocation) {
      // Tamanho adaptativo baseado no zoom - inversamente proporcional
      // Zoom baixo (longe) = quadrado maior em graus
      // Zoom alto (perto) = quadrado menor em graus
      const baseSize = 0.00036; // Tamanho base no zoom 14
      const baseZoom = 14;
      const size = baseSize * Math.pow(2, baseZoom - viewState.zoom);
      const { latitude, longitude, nome } = participantLocation;

      const participantSquare = {
        type: "FeatureCollection" as const,
        features: [
          {
            type: "Feature" as const,
            properties: {
              nome: participantLocation.nome,
              tipo: "Participante",
              latitude: latitude,
              longitude: longitude,
              idade: participantLocation.idade,
              grupo: participantLocation.grupo,
              bairro: participantLocation.bairro,
              situacao: participantLocation.situacao,
              status: participantLocation.status,
              nome_escola: participantLocation.nome_escola,
              nome_cras: participantLocation.nome_cras,
              nome_clinica_familia: participantLocation.nome_clinica_familia,
              nome_equipe_familia: participantLocation.nome_equipe_familia,
              equipe_familia: participantLocation.equipe_familia,
            },
            geometry: {
              type: "Polygon" as const,
              coordinates: [
                [
                  [longitude - size, latitude - size], // Bottom-left
                  [longitude + size, latitude - size], // Bottom-right
                  [longitude + size, latitude + size], // Top-right
                  [longitude - size, latitude + size], // Top-left
                  [longitude - size, latitude - size], // Close polygon
                ],
              ],
            },
          },
        ],
      };

      result.push(
        new GeoJsonLayer({
          id: "participant-location",
          data: participantSquare as any,
          stroked: true,
          filled: true,
          lineWidthMinPixels: 3,
          opacity: 0.4,
          getFillColor: [239, 68, 68], // red-500
          getLineColor: [185, 28, 28], // red-700
          getLineWidth: 2,
          pickable: true,
          autoHighlight: true,
          highlightColor: [100, 116, 139, 80], // cinza com opacidade baixa
        })
      );
    }

    return result;
  }, [layers, participantLocation, viewState.zoom]);

  // Tooltip customizado com mais informações
  const getTooltip = ({ object }: any) => {
    if (!object) return null;

    const props = object.properties;
    const parts: string[] = [];

    // Verificar se é o layer do participante
    if (props.tipo === "Participante") {
      parts.push(`<strong style="font-size: 14px; color: #ef4444;">📍 ${props.nome}</strong>`);
      parts.push(`<em style="color: #a8a8a8;">Localização do Participante</em>`);

      // Informações básicas
      if (props.idade !== undefined) parts.push(`<span style="color: #60a5fa;">Idade:</span> ${props.idade} anos`);
      if (props.grupo) parts.push(`<span style="color: #60a5fa;">Grupo:</span> ${props.grupo}`);
      if (props.bairro) parts.push(`<span style="color: #60a5fa;">Bairro:</span> ${props.bairro}`);

      // Equipamentos públicos
      if (props.nome_escola) parts.push(`<span style="color: #60a5fa;">Escola:</span> ${props.nome_escola}`);
      if (props.nome_cras) parts.push(`<span style="color: #60a5fa;">CRAS:</span> ${props.nome_cras}`);
      if (props.nome_clinica_familia) parts.push(`<span style="color: #60a5fa;">Clínica:</span> ${props.nome_clinica_familia}`);
      if (props.nome_equipe_familia) parts.push(`<span style="color: #60a5fa;">Equipe:</span> ${props.nome_equipe_familia}`);

      // Processar médicos e enfermeiros
      if (props.equipe_familia && props.equipe_familia !== "SEM VÍNCULO" && props.equipe_familia !== "0") {
        const lines = props.equipe_familia.split("\\n").map((l: string) => l.trim()).filter((l: string) => l);
        const medicos: string[] = [];
        const enfermeiros: string[] = [];
        let currentSection = "";

        for (const line of lines) {
          if (line.startsWith("MEDICOS:") || line === "MEDICOS") {
            currentSection = "medicos";
          } else if (line.startsWith("ENFERMEIROS:") || line === "ENFERMEIROS") {
            currentSection = "enfermeiros";
          } else if (line !== "SEM MÉDICOS" && line !== "SEM ENFERMEIROS") {
            if (currentSection === "medicos") {
              medicos.push(line);
            } else if (currentSection === "enfermeiros") {
              enfermeiros.push(line);
            }
          }
        }

        if (medicos.length > 0) {
          parts.push(`<span style="color: #60a5fa;">Médicos:</span> ${medicos.join(", ")}`);
        }
        if (enfermeiros.length > 0) {
          parts.push(`<span style="color: #60a5fa;">Enfermeiros:</span> ${enfermeiros.join(", ")}`);
        }
      }

      // Status e situação
      if (props.status) parts.push(`<span style="color: #60a5fa;">Status:</span> ${props.status}`);
      if (props.situacao) {
        const situacaoColor = props.situacao.toLowerCase().includes("irregular") ? "#ef4444" :
                              props.situacao.toLowerCase().includes("atenção") ? "#f59e0b" : "#10b981";
        parts.push(`<span style="color: #60a5fa;">Situação:</span> <span style="color: ${situacaoColor}; font-weight: 600;">${props.situacao}</span>`);
      }

      if (props.latitude && props.longitude) {
        parts.push(`<span style="color: #9ca3af; font-size: 11px; margin-top: 4px; display: block;">Lat: ${props.latitude}, Long: ${props.longitude}</span>`);
      }
    } else {
      // Tooltip para camadas geoespaciais normais
      parts.push(`<strong style="font-size: 13px;">${props.nome || props.id || "Sem identificação"}</strong>`);
      if (props.id) parts.push(`<span style="color: #9ca3af; font-size: 11px;">ID: ${props.id}</span>`);

      // Informações adicionais
      if (props.tipo_camada) parts.push(`<span style="color: #60a5fa;">Tipo: ${props.tipo_camada}</span>`);
      if (props.regional) parts.push(`Regional: ${props.regional}`);
      if (props.bairro) parts.push(`Bairro: ${props.bairro}`);
      if (props.regiao_administrativa) parts.push(`Região: ${props.regiao_administrativa}`);
      if (props.subprefeitura) parts.push(`Subprefeitura: ${props.subprefeitura}`);
    }

    return {
      html: `
        <div style="padding: 12px; font-size: 12px; max-width: ${props.tipo === "Participante" ? "400px" : "280px"}; line-height: 1.6;">
          ${parts.join('<br/>')}
        </div>
      `,
      style: {
        backgroundColor: "rgba(0, 0, 0, 0.9)",
        color: "#fff",
        borderRadius: "6px",
        boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
      },
    };
  };

  // Limpar todos os filtros
  const clearAllFilters = useCallback(() => {
    if (onFilterChange) {
      onFilterChange({});
    }
  }, [onFilterChange]);

  // Verificar se há algum filtro ativo
  const hasActiveFilters = Object.keys(filters).some(
    (key) => filters[key] !== undefined && filters[key] !== null && filters[key] !== ""
  );

  // Estatísticas das camadas filtradas
  const layerStats = useMemo(() => {
    // Filtrar camadas válidas primeiro (mesma lógica do deckLayers)
    // Nome pode ser null - vamos contar mesmo assim
    const validLayers = layers.filter(
      (layer) =>
        layer.categoria &&
        layer.tipo_geometria &&
        layer.geometry_geojson
    );

    const totalValid = validLayers.length;
    const byTipoCamada = new Map<string, number>();
    const byCategoria = new Map<string, number>();

    validLayers.forEach(layer => {
      if (layer.tipo_camada) {
        byTipoCamada.set(layer.tipo_camada, (byTipoCamada.get(layer.tipo_camada) || 0) + 1);
      }
      if (layer.categoria) {
        byCategoria.set(layer.categoria, (byCategoria.get(layer.categoria) || 0) + 1);
      }
    });

    return {
      totalValid,
      totalRaw: layers.length,
      byTipoCamada,
      byCategoria,
    };
  }, [layers]);

  if (loading && layers.length === 0) {
    return (
      <Card className="border-2">
        <CardHeader>
          <Skeleton className="h-8 w-64" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-[600px] w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header com controles */}
      <Card className="border-2">
        {!hideHeader && (
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-2xl font-bold flex items-center gap-2">
                <MapPin className="h-6 w-6" />
                Visualização Geoespacial
              </CardTitle>
              <div className="flex gap-2">
                {onBack && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onBack}
                    className="h-8 text-xs"
                  >
                    Voltar para Tabela
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
        )}
        <CardContent className="space-y-4">
          {/* Filtros multi-select */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <p className="text-sm font-medium">Filtros</p>
                {hasActiveFilters && (
                  <Badge variant="secondary" className="text-xs">
                    {Object.keys(filters).filter((k) => filters[k]).length} ativos
                  </Badge>
                )}
              </div>
              {hasActiveFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearAllFilters}
                  className="h-7 text-xs"
                >
                  <X className="h-3 w-3 mr-1" />
                  Limpar Filtros
                </Button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* Tipo de Camada - Single Select */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Tipo de Camada</label>
                <Select
                  value={getSingleFilterValue("tipo_camada") || "BAIRRO"}
                  onValueChange={(value) => updateFilter("tipo_camada", value)}
                >
                  <SelectTrigger className="text-sm h-9">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {filterOptions.tipoCamada.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Nome */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Nome</label>
                <VirtualizedMultiSelect
                  options={filterOptions.nome}
                  value={getFilterValue("nome")}
                  onSelect={(value) => updateFilter("nome", value)}
                  placeholder="Todos"
                  className="text-sm"
                />
              </div>

              {/* Categoria */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Categoria</label>
                <VirtualizedMultiSelect
                  options={filterOptions.categoria}
                  value={getFilterValue("categoria")}
                  onSelect={(value) => updateFilter("categoria", value)}
                  placeholder="Todas"
                  className="text-sm"
                />
              </div>

              {/* Regional */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Regional</label>
                <VirtualizedMultiSelect
                  options={filterOptions.regional}
                  value={getFilterValue("regional")}
                  onSelect={(value) => updateFilter("regional", value)}
                  placeholder="Todas"
                  className="text-sm"
                />
              </div>

              {/* Bairro */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Bairro</label>
                <VirtualizedMultiSelect
                  options={filterOptions.bairro}
                  value={getFilterValue("bairro")}
                  onSelect={(value) => updateFilter("bairro", value)}
                  placeholder="Todos"
                  className="text-sm"
                />
              </div>

              {/* Região Administrativa */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Região Administrativa</label>
                <VirtualizedMultiSelect
                  options={filterOptions.regiaoAdm}
                  value={getFilterValue("regiao_administrativa")}
                  onSelect={(value) => updateFilter("regiao_administrativa", value)}
                  placeholder="Todas"
                  className="text-sm"
                />
              </div>

              {/* Subprefeitura */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Subprefeitura</label>
                <VirtualizedMultiSelect
                  options={filterOptions.subprefeitura}
                  value={getFilterValue("subprefeitura")}
                  onSelect={(value) => updateFilter("subprefeitura", value)}
                  placeholder="Todas"
                  className="text-sm"
                />
              </div>
            </div>
          </div>

          {/* Mapa */}
          <div className="relative h-[600px] w-full rounded-lg overflow-hidden border-2">
            <DeckGL
              viewState={viewState}
              onViewStateChange={({ viewState }) => setViewState(viewState as any)}
              controller={true}
              layers={deckLayers}
              getTooltip={getTooltip}
            >
              <MapGL
                mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
                attributionControl={false}
              />
            </DeckGL>
          </div>

          {/* Legenda e Estatísticas */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-muted-foreground mb-1">Total de Camadas</p>
              <p className="text-lg font-semibold">
                {layerStats.totalValid}
                {layerStats.totalValid !== layerStats.totalRaw && (
                  <span className="text-xs text-muted-foreground ml-1">/ {layerStats.totalRaw}</span>
                )}
              </p>
            </div>
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-muted-foreground mb-1">Por Tipo</p>
              <div className="flex flex-wrap gap-2">
                {Array.from(layerStats.byTipoCamada.entries()).map(([tipo, count]) => (
                  <Badge key={tipo} variant="secondary" className="text-xs">
                    {tipo}: {count}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-muted-foreground mb-1">Por Categoria</p>
              <div className="flex flex-wrap gap-2">
                {Array.from(layerStats.byCategoria.entries()).slice(0, 3).map(([cat, count]) => (
                  <Badge key={cat} variant="outline" className="text-xs">
                    {cat}: {count}
                  </Badge>
                ))}
                {layerStats.byCategoria.size > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{layerStats.byCategoria.size - 3} mais
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
