"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import {
	keepPreviousData,
	useQuery,
	useQueryClient,
} from "@tanstack/react-query";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import { WebMercatorViewport } from "@deck.gl/core";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { Map as MapGL } from "react-map-gl/maplibre";
import {
	Activity,
	ArrowDown,
	Filter,
	Layers,
	Loader2,
	RefreshCw,
	X,
} from "lucide-react";
import { apiService } from "@/app/services/api";
import { EvolucaoSemanal } from "@/app/components/monitoring/EvolucaoSemanal";
import { REGULARIDADE_SCALE, taxaToHex } from "@/app/components/monitoring/escala";
import { LazyFilterMultiSelect, LazyFilterSelect } from "@/app/components/LazyFilterSelects";
import { Badge } from "@/app/components/ui/badge";
import { Button } from "@/app/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/app/components/ui/card";
import { Skeleton } from "@/app/components/ui/skeleton";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";
import {
	Tabs,
	TabsList,
	TabsTrigger,
} from "@/app/components/ui/tabs";
import type {
	CamadaTerritorial,
	DashboardFilterValues,
	RegiaoRegularidadeProperties,
	RegiaoRegularidadeResponse,
} from "@/app/types";
import "maplibre-gl/dist/maplibre-gl.css";

const INITIAL_VIEW_STATE = {
	longitude: -43.2096, // Rio de Janeiro
	latitude: -22.9035,
	zoom: 10,
	pitch: 0,
	bearing: 0,
};

// Extensão da cidade do Rio (bbox das geometrias oficiais — todas as
// camadas cobrem o município inteiro) e a versão com folga de ~2% usada
// no maxBounds para travar pan/zoom dentro do desenho.
const CIDADE_BOUNDS: [[number, number], [number, number]] = [
	[-43.7955, -23.0829],
	[-43.0969, -22.746],
];
const CIDADE_MAX_BOUNDS: [[number, number], [number, number]] = [
	[-43.81, -23.09],
	[-43.08, -22.74],
];

/**
 * Trava um view state dentro da área do desenho (CIDADE_MAX_BOUNDS).
 * Pitch/bearing são 0 no app, então a view é um retângulo alinhado aos
 * eixos e o clamp é simples:
 * - zoom-out além do enquadramento → volta ao fit exato da cidade;
 * - pan além da borda → desloca o centro de volta para dentro.
 * Sem el/medidas do container, devolve o estado sem alteração.
 */
function clampToCidade(
	vs: MapViewState,
	el: HTMLDivElement | null,
): MapViewState {
	if (!el) {
		return vs;
	}
	const { width, height } = el.getBoundingClientRect();
	if (width === 0 || height === 0) {
		return vs;
	}

	const [bWest, bSouth] = CIDADE_MAX_BOUNDS[0];
	const [bEast, bNorth] = CIDADE_MAX_BOUNDS[1];
	const boundW = bEast - bWest;
	const boundH = bNorth - bSouth;

	const vp = new WebMercatorViewport({
		width,
		height,
		longitude: vs.longitude,
		latitude: vs.latitude,
		zoom: vs.zoom,
	});
	const [west, south, east, north] = vp.getBounds();

	if (east - west > boundW || north - south > boundH) {
		// Zoom-out além do limite: trava no enquadramento da cidade.
		const fit = new WebMercatorViewport().fitBounds(CIDADE_MAX_BOUNDS, {
			width,
			height,
			padding: 0,
		});
		return {
			...vs,
			longitude: fit.longitude,
			latitude: fit.latitude,
			zoom: fit.zoom,
		};
	}

	let { longitude, latitude } = vs;
	if (west < bWest) {
		longitude += bWest - west;
	}
	if (east > bEast) {
		longitude -= east - bEast;
	}
	if (south < bSouth) {
		latitude += bSouth - south;
	}
	if (north > bNorth) {
		latitude -= north - bNorth;
	}
	return { ...vs, longitude, latitude };
}

// Cinza neutro (CSS "gray") para regiões sem dados — opaco.
const SEM_DADOS_COLOR: [number, number, number, number] = [128, 128, 128, 255];

const BORDER_COLOR: [number, number, number, number] = [15, 23, 42, 120];

// Borda do HOVER (só a borda — o preenchimento continua na cor da escala):
// branca, neutra sobre todas as cores da escala e sobre o cinza sem dados.
const HOVER_BORDER_COLOR: [number, number, number, number] = [255, 255, 255, 255];

// Borda da SELEÇÃO (clique) — azul-marinho sólido, prioridade sobre o hover.
const SELECTION_BORDER_COLOR: [number, number, number, number] = [15, 23, 42, 255];

// Labels completos das camadas territoriais (seção "Camada Territorial").
const CAMADA_LABEL: Record<CamadaTerritorial, string> = {
	bairro: "Bairros",
	ra: "Regiões Administrativas",
	cas: "CAS · Assistência Social",
	cre: "CRE · Educação",
	ap: "APs · Saúde",
};

const CAMADA_DESCRICAO: Record<CamadaTerritorial, string> = {
	bairro: "167 bairros do Rio de Janeiro (limites oficiais do IPP/datario).",
	ra: "33 Regiões Administrativas (limites oficiais do IPP/datario).",
	cas: "10 CAS — Coordenadorias de Assistência Social (SMAS).",
	cre: "11 CRE — Coordenadorias Regionais de Educação (SME).",
	ap: "10 APs — Áreas Programáticas de Saúde (SMS).",
};

/** Converte "#RRGGBB" em RGB. */
function hexToRgb(hex: string): [number, number, number] {
	const value = hex.replace("#", "");
	return [
		parseInt(value.slice(0, 2), 16),
		parseInt(value.slice(2, 4), 16),
		parseInt(value.slice(4, 6), 16),
	];
}

/** Mapeia taxa_regularidade (0-100) para a cor RGBA da escala; null → cinza. */
function taxaToColor(
	taxa: number | null | undefined,
): [number, number, number, number] {
	if (taxa === null || taxa === undefined) {
		return SEM_DADOS_COLOR;
	}
	return [...hexToRgb(taxaToHex(taxa)), 255];
}

/** Chave estável da região (id oficial, com fallback no nome). */
function regiaoKey(
	properties: RegiaoRegularidadeProperties | null | undefined,
): string | null {
	if (!properties) {
		return null;
	}
	return properties.id ?? properties.nome;
}

/** Ordena seleções multiselect — chaves de cache estáveis independentes
 *  da ordem de seleção (o backend também ordena no hash do Redis; aqui
 *  evita refetch quando o usuário seleciona os mesmos valores em outra
 *  ordem). */
function ordenarFiltros(valores: string[]): string[] {
	return [...valores].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

/**
 * Aba "Monitoramento" — Visualização Geográfica por camada territorial.
 *
 * Pinta as regiões da camada selecionada (Bairro, Região Administrativa,
 * CAS, CRE ou AP) na escala oficial de cores conforme a taxa de regularidade
 * (participantes regulares / total por região, agregada no PostgREST com
 * RLS por usuário). Regiões sem dados ficam cinza. Tooltip no hover mostra
 * os valores; legenda fixa abaixo do mapa.
 *
 * Os filtros usam os MESMOS componentes e endpoint da aba Visão Geral
 * (multiselect lazy com cascata): Status (default todos) e Meses de
 * Ingresso. O filtro de protocolo troca a fonte da métrica (FR-007).
 *
 * A troca de camada mantém o mapa visível (placeholderData), com indicador
 * de loading não bloqueante — FR-011 do fluxo.
 *
 * Ações de clique (3i): clicar numa região a adiciona à seleção (multiselect
 * — as regiões são SOMADAS na Evolução semanal, OR na coluna da camada);
 * clicar numa região já selecionada a remove; clicar no vazio limpa tudo.
 * A seleção fica visível em chips abaixo do mapa e no badge da seção
 * "Evolução semanal". Trocar de camada OU de filtro limpa a seleção — o mapa
 * nunca fica com borda marcada "sobrando"; o botão Atualizar mantém a
 * seleção e renova os números. O scroll até a seção é explícito (botão
 * "Ver evolução") — sem rolagem automática, para não atrapalhar a escolha
 * de mais de uma região.
 *
 * O card de detalhes da região (3j/3k) foi removido: com OU sem protocolo,
 * os números vivem na seção "Evolução semanal" (fonte única
 * /v2/monitoring/series — semana final do período × INÍCIO do período).
 */
export const MonitoramentoTab = () => {
	const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);
	const [camada, setCamada] = useState<CamadaTerritorial>("bairro");
	const [statuses, setStatuses] = useState<string[]>([]);
	const [cohortes, setCohortes] = useState<string[]>([]);
	const [grupos, setGrupos] = useState<string[]>([]);
	const [hasBolsaFamilia, setHasBolsaFamilia] = useState<boolean | undefined>(
		undefined,
	);
	const [protocoloId, setProtocoloId] = useState("");
	const [bypassCache, setBypassCache] = useState(false);
	// Regiões clicadas no mapa (multiselect): guardamos as CHAVES (id oficial,
	// fallback nome); os dados exibidos são DERIVADOS da resposta atual (sem
	// efeito de sincronização). Múltiplas regiões são somadas na evolução
	// semanal (OR na coluna da camada).
	const [selecaoKeys, setSelecaoKeys] = useState<string[]>([]);
	// Região sob o mouse (borda branca no hover). O handler onHover dispara
	// a cada movimento, mas setar o MESMO valor não re-renderiza — só
	// entrar/sair de uma região muda o estado.
	const [hoverKey, setHoverKey] = useState<string | null>(null);
	// Alvo do scroll ao clicar numa região (seção "Evolução semanal").
	const evolucaoRef = useRef<HTMLDivElement | null>(null);
	// Container do mapa (medidas usadas no reenquadramento por camada).
	const mapContainerRef = useRef<HTMLDivElement | null>(null);

	const { data: protocolosData, isFetching: protocolosFetching } = useQuery({
		queryKey: ["protocolosVocabulario"],
		queryFn: ({ signal }) => apiService.getProtocolos(false, signal),
		staleTime: 30 * 60 * 1000, // lista estável; cache do backend cobre o resto
		refetchOnWindowFocus: false,
	});

	// Filtros ativos repassados aos multiselects lazy (mesmo formato da
	// Visão Geral — DashboardFilterValues).
	const lazyFilters: DashboardFilterValues = useMemo(
		() => ({
			status: statuses,
			cohort: cohortes,
			grupo: grupos,
			has_bolsa_familia: hasBolsaFamilia,
		}),
		[statuses, cohortes, grupos, hasBolsaFamilia],
	);

	const { data, isFetching, isError, error } =
		useQuery<RegiaoRegularidadeResponse>({
			queryKey: [
				"regularidadeCamada",
				camada,
				statuses,
				cohortes,
				grupos,
				hasBolsaFamilia,
				protocoloId,
				bypassCache,
			],
			queryFn: ({ signal }) =>
				apiService.getRegularidadePorCamada(
					camada,
					{
						statuses: statuses.length > 0 ? statuses : undefined,
						cohortes: cohortes.length > 0 ? cohortes : undefined,
						grupo: grupos.length > 0 ? grupos : undefined,
						hasBolsaFamilia,
						protocoloId: protocoloId || undefined,
					},
					bypassCache,
					signal,
				),
			staleTime: 5 * 60 * 1000, // cache do backend é 30 min
			placeholderData: keepPreviousData, // loading não bloqueante na troca de camada/filtros
			refetchOnWindowFocus: false,
		});

	// Dados das regiões selecionadas, DERIVADOS da resposta atual: a seleção
	// é limpa nos handlers de troca de camada/filtro, então a derivação só
	// acompanha trocas de DADOS com os mesmos filtros (ex.: Atualizar) — se a
	// região continua existindo, os números atualizam; se sumiu, sai da lista
	// sozinha.
	const selecaoDetalhes = useMemo(() => {
		if (selecaoKeys.length === 0 || !data) {
			return [];
		}
		const detalhes: { key: string; nome: string }[] = [];
		for (const k of selecaoKeys) {
			const feature = data.features.find(
				(f) => regiaoKey(f.properties) === k,
			);
			if (feature) {
				detalhes.push({ key: k, nome: feature.properties?.nome ?? k });
			}
		}
		return detalhes.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
	}, [data, selecaoKeys]);

	// Nomes exibidos (ordenados — chave de cache estável no backend/front).
	const regioesSelecionadas = useMemo(
		() => selecaoDetalhes.map((d) => d.nome),
		[selecaoDetalhes],
	);

	// Scroll explícito até a seção "Evolução semanal" (sem rolagem
	// automática: o multiselect não pode perder o mapa a cada clique).
	const scrollToEvolucao = useCallback(() => {
		requestAnimationFrame(() => {
			evolucaoRef.current?.scrollIntoView({
				behavior: "smooth",
				block: "start",
			});
		});
	}, []);

	const deckLayers = useMemo(() => {
		if (!data?.features?.length) return [];

		// Base e destaque têm tipos de dados diferentes (FeatureCollection
		// vs array de Feature), então o array é tipado como Layer genérico.
		const layers: Layer[] = [
			new GeoJsonLayer({
				id: "regularidade-camada",
				data,
				filled: true,
				stroked: true,
				getFillColor: (d) =>
					taxaToColor(d.properties?.taxa_regularidade),
				getLineColor: BORDER_COLOR,
				getLineWidth: 1,
				lineWidthUnits: "pixels",
				pickable: true,
			}),
		];

		// Destaque (hover OU seleções) numa camada overlay DESENHADA POR
		// CIMA: a borda opaca cobre a borda padrão semi-transparente do
		// vizinho — sem blend (que gerava cinza na aresta compartilhada).
		if (selecaoKeys.length > 0 || hoverKey !== null) {
			const selecao = new Set(selecaoKeys);
			layers.push(
				new GeoJsonLayer({
					// id ÚNICO por conjunto de chaves: força o deck.gl a
					// recriar a camada a cada mudança de seleção/hover —
					// elimina qualquer resquício de estado/cache interno.
					id: `regularidade-destaque-${
						[...selecaoKeys].sort().join("|") || hoverKey || "vazio"
					}`,
					data: data.features.filter((f) => {
						const key = regiaoKey(f.properties);
						return (
							(key !== null && selecao.has(key)) || key === hoverKey
						);
					}),
					filled: false, // só borda — o fill continua na cor da escala
					stroked: true,
					// Seleção tem prioridade sobre o hover (mesma região).
					getLineColor: (d) => {
						const key = regiaoKey(d.properties);
						return key !== null && selecao.has(key)
							? SELECTION_BORDER_COLOR
							: HOVER_BORDER_COLOR;
					},
					getLineWidth: (d) => {
						const key = regiaoKey(d.properties);
						return key !== null && selecao.has(key) ? 2.5 : 2;
					},
					lineWidthUnits: "pixels",
					pickable: false, // picking/clique continuam na camada base
				}),
			);
		}

		return layers;
	}, [data, selecaoKeys, hoverKey]);

	/**
	 * Clique no mapa: alterna a região clicada na seleção (multiselect);
	 * clique no vazio limpa todas.
	 * Sem guarda anti-drag: no deck.gl 9 o evento "click" vem do Hammer
	 * TapRecognizer, que só dispara se o ponteiro quase não se moveu entre
	 * down/up — pan e zoom não geram clique.
	 */
	const handleMapClick = useCallback(({ object }: PickingInfo) => {
		// Clique também limpa o hover: sem borda residual na região
		// anterior (o deck.gl pode não informar hover nulo em todo fluxo —
		// ex.: sair do canvas direto, toque, movimento rápido).
		setHoverKey(null);
		const key = regiaoKey(object?.properties);
		if (key === null) {
			setSelecaoKeys([]);
			return;
		}
		setSelecaoKeys((prev) =>
			prev.includes(key)
				? prev.filter((k) => k !== key)
				: ordenarFiltros([...prev, key]),
		);
	}, []);

	const handleMapHover = useCallback(({ object }: PickingInfo) => {
		setHoverKey(regiaoKey(object?.properties));
	}, []);

	const getTooltip = useCallback(({ object }: PickingInfo) => {
		if (!object?.properties) {
			return null;
		}
		const p = object.properties as RegiaoRegularidadeResponse["features"][number]["properties"];
		const taxa = p.taxa_regularidade;
		const taxaLabel =
			taxa === null || taxa === undefined
				? "Sem dados"
				: `${taxa.toFixed(1).replace(".", ",")}% regular`;
		const key = regiaoKey(p);
		const selecionada = key !== null && selecaoKeys.includes(key);

		return {
			html: `
				<div style="padding: 10px; font-size: 12px; line-height: 1.6; max-width: 260px;">
					<strong style="font-size: 13px;">${p.nome}</strong><br/>
					${p.nome_regiao_administrativa ? `<span style="color: #94a3b8;">${p.nome_regiao_administrativa}</span><br/>` : ""}
					<span style="color: #60a5fa;">Participantes:</span> ${p.total_participantes ?? 0}<br/>
					<span style="color: #60a5fa;">Regulares:</span> ${p.total_regulares ?? 0}<br/>
					<span style="color: #60a5fa;">Irregulares:</span> ${p.total_irregulares ?? 0}<br/>
					<span style="color: #4ade80; font-weight: 600;">${taxaLabel}</span><br/>
					${
						selecionada
							? `<span style="color: #fbbf24;">Selecionada — clique para remover</span>`
							: `<span style="color: #94a3b8;">Clique para adicionar à seleção</span>`
					}
				</div>
			`,
			style: {
				backgroundColor: "rgba(0, 0, 0, 0.9)",
				color: "#fff",
				borderRadius: "6px",
				boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
			},
		};
	}, [selecaoKeys]);

	const queryClient = useQueryClient();

	/**
	 * Atualizar: roda uma rodada com `bypass_cache` (dados frescos da
	 * fonte) e depois volta às chaves normais. O bypass NÃO fica
	 * permanente — as chaves sem bypass são invalidadas ao final para
	 * revalidarem do cache do backend, que acabou de ser regravado com
	 * dados frescos (o backend grava no cache mesmo em bypass).
	 */
	const handleRefresh = async () => {
		if (bypassCache) {
			return; // rodada já em andamento
		}
		setBypassCache(true);
		// Deixa o render com as novas chaves (bypass) disparar os fetches
		// e aguarda TODOS concluírem antes de voltar às chaves normais.
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
		await Promise.all([
			queryClient.refetchQueries({ queryKey: ["regularidadeCamada"] }),
			queryClient.refetchQueries({ queryKey: ["monitoringSeries"] }),
		]);
		setBypassCache(false);
		await Promise.all([
			queryClient.invalidateQueries({ queryKey: ["regularidadeCamada"] }),
			queryClient.invalidateQueries({ queryKey: ["monitoringSeries"] }),
		]);
	};

	// Handler estável para o EvolucaoSemanal (memo): recriado a cada
	// render, invalidaria o memo a cada pan/hover do mapa.
	const handleClearProtocolo = useCallback(() => {
		setProtocoloId("");
		setSelecaoKeys([]);
	}, []);

	const clearFilters = () => {
		setStatuses([]);
		setCohortes([]);
		setGrupos([]);
		setHasBolsaFamilia(undefined);
		setProtocoloId("");
		setSelecaoKeys([]);
	};

	const meta = data?.meta;
	const camadaLabel = CAMADA_LABEL[camada];

	// Reenquadra o mapa na extensão da cidade (chamado ao trocar de camada:
	// o usuário pode estar com zoom num bairro ao mudar para CAS/CRE/AP).
	const fitCamada = useCallback(() => {
		const el = mapContainerRef.current;
		if (!el) {
			return;
		}
		const { width, height } = el.getBoundingClientRect();
		if (width === 0 || height === 0) {
			return;
		}
		const view = new WebMercatorViewport().fitBounds(CIDADE_BOUNDS, {
			width,
			height,
			padding: 24,
		});
		setViewState({
			longitude: view.longitude,
			latitude: view.latitude,
			zoom: view.zoom,
			pitch: 0,
			bearing: 0,
		});
	}, []);

	return (
		<div className="space-y-4">
			{/* Camada Territorial — separada dos filtros */}
			<Card className="border-2">
				<CardHeader className="pb-3">
					<CardTitle className="text-2xl font-bold flex items-center gap-2">
						<Layers className="h-6 w-6" />
						Camada Territorial
					</CardTitle>
				</CardHeader>
				<CardContent className="pt-0 space-y-3">
					<Tabs
						value={camada}
						onValueChange={(value) => {
							// Trocar de camada limpa a seleção (ids podem colidir
							// entre camadas, ex.: id_bairro vs id_ra) e reenquadra
							// o mapa na extensão da cidade.
							setCamada(value as CamadaTerritorial);
							setSelecaoKeys([]);
							fitCamada();
						}}
					>
						<TabsList>
							<TabsTrigger value="bairro">Bairros</TabsTrigger>
							<TabsTrigger value="ra">Regiões Administrativas</TabsTrigger>
							<TabsTrigger value="cas">CAS · Assistência Social</TabsTrigger>
							<TabsTrigger value="cre">CRE · Educação</TabsTrigger>
							<TabsTrigger value="ap">APs · Saúde</TabsTrigger>
						</TabsList>
					</Tabs>
					<p className="text-xs text-muted-foreground">
						{CAMADA_DESCRICAO[camada]}
					</p>
				</CardContent>
			</Card>

			{/* Filtros — mesmo padrão visual/comportamental da Visão Geral */}
			<Card className="relative border-2">
				<CardHeader className="pb-4 flex flex-row items-center justify-between">
					<CardTitle className="text-2xl font-bold flex items-center gap-2">
						<Filter className="h-6 w-6" />
						Filtros
					</CardTitle>
					<div className="flex gap-2">
						<Button
							variant="outline"
							size="sm"
							onClick={clearFilters}
							className="h-8 text-xs"
							disabled={isFetching}
						>
							<X className="h-3 w-3 mr-1" />
							Limpar Filtros
						</Button>
						<Button
							variant="outline"
							size="sm"
							onClick={handleRefresh}
							className="h-8 text-xs"
							disabled={isFetching}
						>
							<RefreshCw
								className={`h-3 w-3 mr-1 ${isFetching ? "animate-spin" : ""}`}
							/>
							Atualizar
						</Button>
					</div>
				</CardHeader>
				<CardContent className="pt-0 space-y-4">
					{/* Filtros Principais — mesmos componentes da Visão Geral */}
					<div className="space-y-1.5">
						<div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
							Filtros Principais
						</div>
						<div className="grid grid-cols-2 md:grid-cols-4 gap-2">
							<LazyFilterMultiSelect
								field="status_list"
								filters={lazyFilters}
								value={statuses}
								onSelect={(v) => {
									setSelecaoKeys([]);
									setStatuses(ordenarFiltros(v));
								}}
								disabled={isFetching}
								placeholder="Status"
								defaultLabel="Todos os Status"
							/>

							<LazyFilterMultiSelect
								field="cohorts"
								filters={lazyFilters}
								value={cohortes}
								onSelect={(v) => {
									setSelecaoKeys([]);
									setCohortes(ordenarFiltros(v));
								}}
								disabled={isFetching}
								placeholder="Meses de Ingresso"
								defaultLabel="Todos os Meses de Ingresso"
							/>

							<LazyFilterMultiSelect
								field="grupos"
								filters={lazyFilters}
								value={grupos}
								onSelect={(v) => {
									setSelecaoKeys([]);
									setGrupos(ordenarFiltros(v));
								}}
								disabled={isFetching}
								placeholder="Grupos"
								defaultLabel="Todos os Grupos"
							/>

							<LazyFilterSelect
								field="bolsa_familia"
								filters={lazyFilters}
								value={
									hasBolsaFamilia !== undefined
										? String(hasBolsaFamilia)
										: "todas"
								}
								onSelect={(v) => {
									setSelecaoKeys([]);
									setHasBolsaFamilia(
										v === "todas" ? undefined : v === "true",
									);
								}}
								disabled={isFetching}
								placeholder="Todos Bolsa Família"
								defaultLabel="Todos Bolsa Família"
							/>

							<VirtualizedSelect
								options={(protocolosData?.protocolos ?? []).map((p) => ({
									id: p.protocolo_id,
									label: `${p.protocolo_secretaria} — ${p.protocolo_descricao}`,
								}))}
								value={protocoloId || "todos"}
								onSelect={(value) => {
									setSelecaoKeys([]);
									setProtocoloId(value === "todos" ? "" : value);
								}}
								disabled={isFetching}
								placeholder="Protocolo"
								defaultLabel="Regularidade geral"
								loading={protocolosFetching}
							/>
						</div>
					</div>
				</CardContent>
			</Card>

			{isError ? (
				<Card>
					<CardContent className="flex flex-col items-center gap-3 py-12 text-center">
						<p className="text-sm font-semibold">
							Não foi possível carregar a camada {camadaLabel}.
						</p>
						<p className="text-xs text-muted-foreground max-w-md">
							{error instanceof Error
								? error.message
								: "Erro ao consultar a API."}
						</p>
						<Button variant="outline" size="sm" onClick={handleRefresh}>
							<RefreshCw className="h-4 w-4 mr-2" />
							Tentar novamente
						</Button>
					</CardContent>
				</Card>
			) : isFetching && !data ? (
				<Card>
					<CardContent className="py-4">
						<Skeleton className="h-[600px] w-full rounded-lg" />
					</CardContent>
				</Card>
			) : (
				<>
					{/* FR-012: conjunto vazio com os filtros ativos */}
					{meta && meta.regioes_com_dados === 0 && !isFetching && (
						<Card className="border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30">
							<CardContent className="py-3 text-sm text-amber-800 dark:text-amber-200">
								Sem dados para os filtros selecionados nesta camada. As
								regiões são exibidas em cinza.
							</CardContent>
						</Card>
					)}
					<Card>
						<CardHeader className="pb-2">
							<CardTitle className="flex items-center gap-2">
								<Activity className="h-5 w-5 text-primary" />
								Monitoramento de {CAMADA_LABEL[camada]} — Regularidade
							</CardTitle>
							<p className="text-sm text-muted-foreground">
								{protocoloId
									? "Regularidade do protocolo selecionado por região (substitui a regularidade geral)."
									: "Taxa de regularidade por região (participantes regulares / total de participantes) — visualização geográfica."}{" "}
								Clique em uma ou mais regiões para somá-las na evolução
								semanal; clique numa região selecionada para removê-la.
							</p>
						</CardHeader>
						<CardContent className="pt-4">
							<div
								ref={mapContainerRef}
								className="relative h-[600px] w-full rounded-lg overflow-hidden border-2"
								// Sair do mapa (ex.: para os cards abaixo) limpa o
								// hover — sem borda branca pendurada na região.
								onPointerLeave={() => setHoverKey(null)}
							>
								<DeckGL
									viewState={viewState}
									// Este app usa apenas MapView (sem views customizadas),
									// então o viewState recebido é sempre MapViewState.
									// O clamp trava pan/zoom dentro da área do desenho
									// ANTES do setState — desenho e fundo param juntos
									// (o maxBounds do MapLibre sozinho divergia: o
									// basemap travava e os polígonos seguiam o gesto).
									onViewStateChange={(params) =>
										setViewState(
											clampToCidade(
												params.viewState as MapViewState,
												mapContainerRef.current,
											),
										)
									}
									controller={true}
									layers={deckLayers}
									getTooltip={getTooltip}
									onClick={handleMapClick}
									onHover={handleMapHover}
								>
									<MapGL
										mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
										attributionControl={false}
									/>
								</DeckGL>

								{isFetching && (
									<div className="absolute right-2 top-2 z-10 flex items-center gap-2 rounded-md bg-background/90 px-2 py-1 text-xs text-muted-foreground shadow">
										<Loader2 className="h-3.5 w-3.5 animate-spin" />
										Carregando…
									</div>
								)}
							</div>

							{/* Legenda — mesma escala de cores do mapa */}
							<div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
								<div className="flex items-center gap-2">
									<span>Menos regular</span>
									<div
										className="h-3 w-48 rounded-full"
										style={{
											background: `linear-gradient(to right, ${REGULARIDADE_SCALE.join(", ")})`,
										}}
									/>
									<span>Mais regular</span>
								</div>
								<div className="flex items-center gap-2">
									<span
										className="inline-block h-3 w-3 rounded-sm"
										style={{ background: "#808080" }}
									/>
									<span>Sem dados</span>
								</div>
							</div>

							{/* Seleção de regiões (multiselect) — chips removíveis */}
							{selecaoDetalhes.length > 0 && (
								<div className="mt-3 flex flex-wrap items-center gap-1.5">
									<span className="text-xs text-muted-foreground">
										Selecionadas:
									</span>
									{selecaoDetalhes.map(({ key, nome }) => (
										<Badge
											key={key}
											variant="secondary"
											className="gap-1 pr-1 text-xs font-normal"
										>
											{nome}
											<button
												type="button"
												onClick={() =>
													setSelecaoKeys((prev) =>
														prev.filter((k) => k !== key),
													)
												}
												aria-label={`Remover ${nome} da seleção`}
												className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
											>
												<X className="h-3 w-3" />
											</button>
										</Badge>
									))}
									<Button
										variant="ghost"
										size="sm"
										className="h-6 text-xs text-muted-foreground"
										onClick={() => setSelecaoKeys([])}
									>
										Limpar
									</Button>
								</div>
							)}

							<div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
								<span>
									{meta
										? `${meta.regioes_com_dados} regiões com dados · ${meta.regioes_sem_dados} sem dados · ${meta.total_regioes} no mapa`
										: `${data?.features?.length ?? 0} regiões carregadas`}
								</span>
								<div className="flex items-center gap-2">
									<Button
										variant="outline"
										size="sm"
										className="h-7 text-xs"
										onClick={scrollToEvolucao}
									>
										<ArrowDown className="mr-1 h-3 w-3" />
										Ver evolução
										{selecaoKeys.length > 0
											? ` (${selecaoKeys.length})`
											: ""}
									</Button>
									{bypassCache && (
										<span className="text-primary">consulta fresca</span>
									)}
								</div>
							</div>
						</CardContent>
					</Card>

					{/* Acompanhamento — evolução semanal. Consome a seleção do
					    mapa (camada + regiões) e os filtros compartilhados; sem
					    seleção, a série é da cidade inteira; com várias, elas
					    são somadas (OR). O protocolo é compartilhado com o
					    filtro do mapa. */}
					<div ref={evolucaoRef}>
						<EvolucaoSemanal
							camada={camada}
							regioes={regioesSelecionadas}
							statuses={statuses}
							cohortes={cohortes}
							grupos={grupos}
							hasBolsaFamilia={hasBolsaFamilia}
							protocoloId={protocoloId}
							onClearProtocolo={handleClearProtocolo}
							bypassCache={bypassCache}
						/>
					</div>
				</>
			)}
		</div>
	);
};
