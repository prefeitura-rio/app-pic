"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import { WebMercatorViewport } from "@deck.gl/core";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { Map as MapGL } from "react-map-gl/maplibre";
import {
	Activity,
	Filter,
	Layers,
	Loader2,
	RefreshCw,
	TrendingDown,
	TrendingUp,
	X,
} from "lucide-react";
import { apiService } from "@/app/services/api";
import { LazyFilterMultiSelect } from "@/app/components/LazyFilterSelects";
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
	RegiaoDetalhesResponse,
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

/**
 * Escala oficial de cores da regularidade (0% → 100%), opaca (alpha FF):
 * 0% é o vermelho #BE2A3E e 100% é o verde #22763F, passando por tons de
 * amarelo. A taxa é mapeada por índice (round(taxa * (N - 1))).
 */
const REGULARIDADE_SCALE = [
	"#BE2A3E", "#C02E3F", "#C2323F", "#C53540", "#C73941",
	"#C93C41", "#CB3F42", "#CD4242", "#CF4643", "#D24944",
	"#D44C44", "#D64F45", "#D85245", "#DA5546", "#DD5847",
	"#DF5B47", "#E15E48", "#E36148", "#E46449", "#E56749",
	"#E76A49", "#E86D49", "#E9704A", "#EB724A", "#EC754A",
	"#EE784B", "#EF7B4B", "#F07E4B", "#F1814C", "#F3844C",
	"#F4874C", "#F5894C", "#F78C4D", "#F88F4D", "#F8934E",
	"#F89750", "#F89C51", "#F8A053", "#F8A454", "#F8A856",
	"#F8AC57", "#F7B059", "#F7B45A", "#F7B85C", "#F6BC5D",
	"#F6C05F", "#F6C361", "#F5C762", "#F5CB64", "#F4CF65",
	"#F1D066", "#EBCF65", "#E5CE65", "#DFCC65", "#DACB64",
	"#D4C964", "#CEC864", "#C8C763", "#C2C563", "#BCC463",
	"#B6C262", "#B0C162", "#A9BF61", "#A3BE61", "#9DBC61",
	"#96BB60", "#90B960", "#8CB760", "#88B560", "#84B460",
	"#81B260", "#7DB060", "#79AE60", "#75AC60", "#71AA60",
	"#6CA960", "#68A760", "#64A560", "#60A35F", "#5BA15F",
	"#57A05F", "#529E5F", "#4D9C5F", "#4A9A5E", "#47985C",
	"#45955A", "#439358", "#409156", "#3E8E54", "#3C8C52",
	"#398A50", "#37884E", "#34864C", "#32834A", "#2F8148",
	"#2D7F47", "#2A7D45", "#277A43", "#257841", "#22763F",
];

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

// Secretaria das camadas especializadas: os cards "Protocolos nesta região"
// exibem apenas protocolos da secretaria da camada (bairro/RA mostram todos).
const CAMADA_SECRETARIA: Partial<Record<CamadaTerritorial, string>> = {
	cas: "SMAS",
	cre: "SME",
	ap: "SMS",
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

/**
 * Cor da taxa como hex CSS na escala oficial; null/undefined → cinza
 * "#808080" (sem dados). Usada tanto no mapa quanto nos cards de detalhe.
 */
function taxaToHex(taxa: number | null | undefined): string {
	if (taxa === null || taxa === undefined) {
		return "#808080";
	}
	const t = Math.min(100, Math.max(0, taxa)) / 100; // 1 = 100% regular
	const index = Math.round(t * (REGULARIDADE_SCALE.length - 1));
	return REGULARIDADE_SCALE[index];
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

/**
 * Mini-card de métrica com faixa lateral na cor da região no mapa.
 * ``trend`` (3k) adiciona a linha de variação padrão do MetaCard — seta +
 * delta colorido + rótulo — mantendo o estilo dos cards daqui.
 */
function MetricaCard({
	rotulo,
	valor,
	detalhe,
	cor,
	trend,
}: {
	rotulo: string;
	valor: string;
	detalhe?: string;
	cor: string;
	trend?: {
		valor: string;
		positivo: boolean;
		label?: string;
	};
}) {
	return (
		<div
			className="flex flex-col justify-center rounded-lg border bg-muted/40 p-3"
			style={{ borderLeft: `4px solid ${cor}` }}
		>
			<p className="text-xs font-medium text-muted-foreground">{rotulo}</p>
			<p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
				{valor}
			</p>
			{trend && (
				<p
					className={`mt-1 flex items-center gap-1 text-xs font-semibold ${
						trend.positivo ? "text-emerald-600" : "text-red-600"
					}`}
				>
					{trend.positivo ? (
						<TrendingUp className="h-3.5 w-3.5 shrink-0" />
					) : (
						<TrendingDown className="h-3.5 w-3.5 shrink-0" />
					)}
					{trend.valor}
					{trend.label && (
						<span className="ml-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
							{trend.label}
						</span>
					)}
				</p>
			)}
			{detalhe && (
				<p className="mt-1 text-xs text-muted-foreground">{detalhe}</p>
			)}
		</div>
	);
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
 * (multiselect lazy com cascata): Status (default Ativos) e Meses de
 * Ingresso. O filtro de protocolo troca a fonte da métrica (FR-007).
 *
 * A troca de camada mantém o mapa visível (placeholderData), com indicador
 * de loading não bloqueante — FR-011 do fluxo.
 *
 * Ações de clique (3i): clicar numa região rola a página até um card de
 * detalhes abaixo do mapa. Trocar de camada OU de filtro limpa a seleção —
 * o mapa nunca fica com borda marcada "sobrando"; o botão Atualizar mantém
 * a seleção e renova os números.
 *
 * Card de detalhes (3j/3k): 3 cards principais — Participantes,
 * % Regulares (+ quantidade) e % Irregulares (+ quantidade), com faixa na
 * cor da região. Com "Regularidade geral" (sem protocolo), lista os cards
 * de CADA protocolo com dados na região (fonte /geospatial/regiao/
 * detalhes). Com protocolo selecionado, o "% Regulares" ganha a variação
 * "VS MÉDIA GERAL" (p.p., acima/abaixo) e a seção de comparativo mostra
 * apenas 2 cards: média geral do protocolo em todas as regiões e a
 * quantidade de regulares acima/abaixo do esperado.
 */
export const MonitoramentoTab = () => {
	const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);
	const [camada, setCamada] = useState<CamadaTerritorial>("bairro");
	const [statuses, setStatuses] = useState<string[]>(["Ativo"]);
	const [cohortes, setCohortes] = useState<string[]>([]);
	const [protocoloId, setProtocoloId] = useState("");
	const [bypassCache, setBypassCache] = useState(false);
	// Região clicada no mapa: guardamos a CHAVE (id oficial, fallback nome);
	// os dados exibidos no card são DERIVADOS da resposta atual (sem efeito
	// de sincronização).
	const [selecaoKey, setSelecaoKey] = useState<string | null>(null);
	// Região sob o mouse (borda branca no hover). O handler onHover dispara
	// a cada movimento, mas setar o MESMO valor não re-renderiza — só
	// entrar/sair de uma região muda o estado.
	const [hoverKey, setHoverKey] = useState<string | null>(null);
	// Alvo do scroll ao clicar numa região.
	const detalheRef = useRef<HTMLDivElement | null>(null);
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
		() => ({ status: statuses, cohort: cohortes }),
		[statuses, cohortes],
	);

	const { data, isFetching, isError, error, refetch } =
		useQuery<RegiaoRegularidadeResponse>({
			queryKey: [
				"regularidadeCamada",
				camada,
				statuses,
				cohortes,
				protocoloId,
				bypassCache,
			],
			queryFn: ({ signal }) =>
				apiService.getRegularidadePorCamada(
					camada,
					{
						statuses: statuses.length > 0 ? statuses : undefined,
						cohortes: cohortes.length > 0 ? cohortes : undefined,
						protocoloId: protocoloId || undefined,
					},
					bypassCache,
					signal,
				),
			staleTime: 5 * 60 * 1000, // cache do backend é 30 min
			placeholderData: keepPreviousData, // loading não bloqueante na troca de camada/filtros
			refetchOnWindowFocus: false,
		});

	// Dados da região selecionada, DERIVADOS da resposta atual: a seleção é
	// limpa nos handlers de troca de camada/filtro, então a derivação só
	// acompanha trocas de DADOS com os mesmos filtros (ex.: Atualizar) — se
	// a região continua existindo, os números atualizam; se sumiu, o card
	// some sozinho.
	const regiaoSelecionada = useMemo(() => {
		if (selecaoKey === null) {
			return null;
		}
		return (
			data?.features.find((f) => regiaoKey(f.properties) === selecaoKey)
				?.properties ?? null
		);
	}, [data, selecaoKey]);

	// Rola a página até o card de detalhes quando uma região é clicada.
	// (Efeito só sincroniza sistema externo — o scroll — sem setState.)
	useEffect(() => {
		if (selecaoKey === null) {
			return;
		}
		requestAnimationFrame(() => {
			detalheRef.current?.scrollIntoView({
				behavior: "smooth",
				block: "start",
			});
		});
	}, [selecaoKey]);

	// Detalhes da região clicada (3j): geral + protocolos da região.
	// Liga apenas com região selecionada; a seleção é limpa ao trocar
	// camada/filtros, então a query desliga sozinha nesses casos.
	const { data: detalhesData, isFetching: detalhesFetching } =
		useQuery<RegiaoDetalhesResponse>({
			queryKey: [
				"regiaoDetalhes",
				camada,
				regiaoSelecionada?.nome ?? null,
				statuses,
				cohortes,
				protocoloId,
				bypassCache,
			],
			queryFn: ({ signal }) => {
				if (!regiaoSelecionada) {
					throw new Error("Região não selecionada");
				}
				return apiService.getRegiaoDetalhes(
					camada,
					regiaoSelecionada.nome,
					{
						statuses: statuses.length > 0 ? statuses : undefined,
						cohortes: cohortes.length > 0 ? cohortes : undefined,
						protocoloId: protocoloId || undefined,
					},
					bypassCache,
					signal,
				);
			},
			enabled: regiaoSelecionada !== null,
			staleTime: 5 * 60 * 1000, // cache do backend é 30 min
			refetchOnWindowFocus: false,
		});

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

		// Destaque (hover OU seleção) numa camada overlay DESENHADA POR
		// CIMA: a borda opaca cobre a borda padrão semi-transparente do
		// vizinho — sem blend (que gerava cinza na aresta compartilhada).
		if (selecaoKey !== null || hoverKey !== null) {
			layers.push(
				new GeoJsonLayer({
					// id ÚNICO por chave: força o deck.gl a recriar a camada
					// a cada mudança de seleção/hover — elimina qualquer
					// resquício de estado/cache interno entre regiões.
					id: `regularidade-destaque-${selecaoKey ?? hoverKey ?? "vazio"}`,
					data: data.features.filter((f) => {
						const key = regiaoKey(f.properties);
						return (
							(selecaoKey !== null && key === selecaoKey) ||
							(hoverKey !== null && key === hoverKey)
						);
					}),
					filled: false, // só borda — o fill continua na cor da escala
					stroked: true,
					// Seleção tem prioridade sobre o hover (mesma região).
					getLineColor: (d) =>
						regiaoKey(d.properties) === selecaoKey
							? SELECTION_BORDER_COLOR
							: HOVER_BORDER_COLOR,
					getLineWidth: (d) =>
						regiaoKey(d.properties) === selecaoKey ? 2.5 : 2,
					lineWidthUnits: "pixels",
					pickable: false, // picking/clique continuam na camada base
				}),
			);
		}

		return layers;
	}, [data, selecaoKey, hoverKey]);

	/**
	 * Clique no mapa: seleciona a região clicada (clique no vazio limpa).
	 * Sem guarda anti-drag: no deck.gl 9 o evento "click" vem do Hammer
	 * TapRecognizer, que só dispara se o ponteiro quase não se moveu entre
	 * down/up — pan e zoom não geram clique.
	 */
	const handleMapClick = useCallback(({ object }: PickingInfo) => {
		// Clique também limpa o hover: sem borda residual na região
		// anterior (o deck.gl pode não informar hover nulo em todo fluxo —
		// ex.: sair do canvas direto, toque, movimento rápido).
		setHoverKey(null);
		setSelecaoKey(regiaoKey(object?.properties));
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

		return {
			html: `
				<div style="padding: 10px; font-size: 12px; line-height: 1.6; max-width: 260px;">
					<strong style="font-size: 13px;">${p.nome}</strong><br/>
					${p.nome_regiao_administrativa ? `<span style="color: #94a3b8;">${p.nome_regiao_administrativa}</span><br/>` : ""}
					<span style="color: #60a5fa;">Participantes:</span> ${p.total_participantes ?? 0}<br/>
					<span style="color: #60a5fa;">Regulares:</span> ${p.total_regulares ?? 0}<br/>
					<span style="color: #60a5fa;">Irregulares:</span> ${p.total_irregulares ?? 0}<br/>
					<span style="color: #4ade80; font-weight: 600;">${taxaLabel}</span>
				</div>
			`,
			style: {
				backgroundColor: "rgba(0, 0, 0, 0.9)",
				color: "#fff",
				borderRadius: "6px",
				boxShadow: "0 4px 6px rgba(0, 0, 0, 0.3)",
			},
		};
	}, []);

	const handleRefresh = () => {
		setBypassCache(true);
		refetch();
	};

	const clearFilters = () => {
		setStatuses([]);
		setCohortes([]);
		setProtocoloId("");
		setSelecaoKey(null);
	};

	const meta = data?.meta;
	const camadaLabel = CAMADA_LABEL[camada];

	// Valores derivados da região selecionada (card de detalhes abaixo do mapa).
	const taxaSelecionada = regiaoSelecionada?.taxa_regularidade;
	const temDadosSelecao =
		taxaSelecionada !== null && taxaSelecionada !== undefined;
	const corSelecao = taxaToHex(taxaSelecionada);
	const formatarNumero = (valor: number | null | undefined) =>
		temDadosSelecao ? (valor ?? 0).toLocaleString("pt-BR") : "—";
	const formatarTaxa = (valor: number | null | undefined) =>
		valor === null || valor === undefined
			? "—"
			: `${valor.toFixed(1).replace(".", ",")}%`;

	// 3k: comparativo da região × média geral do protocolo selecionado.
	const comparativo = useMemo(() => {
		const geral = detalhesData?.protocolo_geral;
		if (
			!regiaoSelecionada ||
			!geral ||
			!temDadosSelecao ||
			geral.total_participantes === 0 ||
			geral.taxa_regularidade === null
		) {
			return null;
		}
		const taxaRegiao = taxaSelecionada ?? 0;
		const taxaGeral = geral.taxa_regularidade;
		const deltaPP = taxaRegiao - taxaGeral;
		const acima = deltaPP >= 0;
		// Quantidade acima/abaixo do esperado pela média geral (mesma
		// fórmula do "Gap para a Meta" do Acordo de Resultados).
		const gap = Math.round(
			(regiaoSelecionada.total_regulares ?? 0) -
				(taxaGeral / 100) * (regiaoSelecionada.total_participantes ?? 0),
		);
		return {
			deltaLabel: `${acima ? "+" : "-"}${Math.abs(deltaPP).toFixed(1).replace(".", ",")} p.p.`,
			acima,
			gap,
			taxaGeral,
			geral,
		};
	}, [detalhesData, regiaoSelecionada, taxaSelecionada, temDadosSelecao]);

	// Protocolos com dados na região, restritos à secretaria da camada
	// (CAS→SMAS, CRE→SME, AP→SMS; bairro/RA mostram todos).
	const protocolosRegiao = useMemo(() => {
		const secretaria = CAMADA_SECRETARIA[camada];
		return (detalhesData?.protocolos ?? []).filter(
			(p) =>
				p.total_participantes > 0 &&
				(!secretaria || p.protocolo_secretaria === secretaria),
		);
	}, [detalhesData, camada]);

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
							setSelecaoKey(null);
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
									setSelecaoKey(null);
									setStatuses(v);
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
									setSelecaoKey(null);
									setCohortes(v);
								}}
								disabled={isFetching}
								placeholder="Meses de Ingresso"
								defaultLabel="Todos os Meses de Ingresso"
							/>

							<VirtualizedSelect
								options={(protocolosData?.protocolos ?? []).map((p) => ({
									id: p.protocolo_id,
									label: `${p.protocolo_secretaria} — ${p.protocolo_descricao}`,
								}))}
								value={protocoloId || "todos"}
								onSelect={(value) => {
									setSelecaoKey(null);
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
								Clique em uma região para ver os detalhes abaixo.
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

							<div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
								<span>
									{meta
										? `${meta.regioes_com_dados} regiões com dados · ${meta.regioes_sem_dados} sem dados · ${meta.total_regioes} no mapa`
										: `${data?.features?.length ?? 0} regiões carregadas`}
								</span>
								{bypassCache && (
									<span className="text-primary">consulta fresca</span>
								)}
							</div>
						</CardContent>
					</Card>

					{/* Detalhes da região clicada (3i) — scroll alvo do clique */}
					{regiaoSelecionada && (
						<Card
							ref={detalheRef}
							className="scroll-mt-4"
							style={{ borderLeft: `4px solid ${corSelecao}` }}
						>
							<CardHeader className="pb-3">
								<div className="flex items-start justify-between gap-3">
									<div className="flex min-w-0 items-center gap-2">
										<CardTitle className="truncate text-xl font-bold">
											{regiaoSelecionada.nome}
										</CardTitle>
										<Badge variant="outline" className="shrink-0">
											{CAMADA_LABEL[camada]}
										</Badge>
									</div>
									<Button
										variant="ghost"
										size="sm"
										onClick={() => setSelecaoKey(null)}
										aria-label="Fechar detalhes da região"
										className="h-8 w-8 shrink-0 p-0"
									>
										<X className="h-4 w-4" />
									</Button>
								</div>
								<p className="text-sm text-muted-foreground">
									{camada === "bairro" &&
									regiaoSelecionada.nome_regiao_administrativa
										? `${regiaoSelecionada.nome_regiao_administrativa} · `
										: ""}
									{temDadosSelecao
										? protocoloId
											? "Regularidade do protocolo selecionado"
											: "Regularidade geral"
										: "Sem dados para os filtros selecionados"}
								</p>
							</CardHeader>
							<CardContent className="pt-0">
								{/* 3j: Participantes → % Regulares (+qtd) → % Irregulares (+qtd) */}
								<div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
									<MetricaCard
										rotulo="Participantes"
										valor={formatarNumero(
											regiaoSelecionada.total_participantes,
										)}
										cor={corSelecao}
									/>
									<MetricaCard
										rotulo="% Regulares"
										valor={formatarTaxa(taxaSelecionada)}
										trend={
											protocoloId && comparativo
												? {
														valor: comparativo.deltaLabel,
														positivo: comparativo.acima,
														label: "vs média geral",
													}
												: undefined
										}
										detalhe={
											temDadosSelecao
												? `${formatarNumero(regiaoSelecionada.total_regulares)} regulares de ${formatarNumero(regiaoSelecionada.total_participantes)} participantes`
												: undefined
										}
										cor={corSelecao}
									/>
									<MetricaCard
										rotulo="% Irregulares"
										valor={
											temDadosSelecao
												? formatarTaxa(100 - (taxaSelecionada ?? 0))
												: "—"
										}
										detalhe={
											temDadosSelecao
												? `${formatarNumero(regiaoSelecionada.total_irregulares)} irregulares de ${formatarNumero(regiaoSelecionada.total_participantes)} participantes`
												: undefined
										}
										cor={corSelecao}
									/>
								</div>

								{/* 3j: modo Regularidade geral → cards de cada protocolo
								    com dados na região */}
								{!protocoloId && (
									<div className="mt-6 space-y-3">
										<h3 className="text-sm font-semibold text-foreground">
											Protocolos nesta região
										</h3>
										{detalhesFetching && !detalhesData ? (
											<div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
												<Loader2 className="h-4 w-4 animate-spin" />
												Carregando protocolos…
											</div>
										) : protocolosRegiao.length > 0 ? (
											<div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
												{protocolosRegiao.map((p) => (
														<div
															key={p.protocolo_id}
															className="flex flex-col justify-center rounded-lg border bg-muted/40 p-3"
															style={{
																borderLeft: `4px solid ${taxaToHex(p.taxa_regularidade)}`,
															}}
														>
															<p className="text-sm font-semibold line-clamp-2">
																{p.protocolo_secretaria
																	? `${p.protocolo_secretaria} — ${p.protocolo_descricao ?? p.protocolo_id}`
																	: (p.protocolo_descricao ?? p.protocolo_id)}
															</p>
															<div className="mt-2 flex items-baseline gap-2">
																<span className="text-xl font-bold tabular-nums">
																	{formatarTaxa(p.taxa_regularidade)}
																</span>
																<span className="text-xs text-muted-foreground">
																	regular
																</span>
															</div>
															<p className="mt-1 text-xs text-muted-foreground">
																{p.total_regulares.toLocaleString("pt-BR")} de{" "}
																{p.total_participantes.toLocaleString("pt-BR")}{" "}
																participantes
															</p>
														</div>
													))}
											</div>
										) : (
											<p className="text-sm text-muted-foreground">
												Sem dados de protocolo nesta região.
											</p>
										)}
									</div>
								)}

								{/* 3k: modo protocolo específico → comparativo com a
								    média geral do protocolo. A variação vive no card
								    "% Regulares" acima (sem repetição); aqui ficam
								    apenas os 2 cards: média geral + quantidade. */}
								{protocoloId && (
									<div className="mt-6 space-y-3">
										<h3 className="text-sm font-semibold text-foreground">
											Comparativo com a média geral do protocolo
										</h3>
										{detalhesFetching && !detalhesData ? (
											<div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
												<Loader2 className="h-4 w-4 animate-spin" />
												Carregando comparativo…
											</div>
										) : comparativo ? (
											<div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
												<MetricaCard
													rotulo="Média geral do protocolo"
													valor={formatarTaxa(
														comparativo.geral.taxa_regularidade,
													)}
													cor={corSelecao}
													detalhe={`${formatarNumero(comparativo.geral.total_regulares)} regulares de ${formatarNumero(comparativo.geral.total_participantes)} participantes em todas as regiões`}
												/>
												<MetricaCard
													rotulo="Acima/Abaixo da média"
													valor={Math.abs(
														comparativo.gap,
													).toLocaleString("pt-BR")}
													cor={corSelecao}
													trend={{
														valor: comparativo.acima
															? "ACIMA DA MÉDIA"
															: "ABAIXO DA MÉDIA",
														positivo: comparativo.acima,
													}}
													detalhe={`participantes regulares ${comparativo.acima ? "acima" : "abaixo"} do esperado pela média geral de ${formatarTaxa(comparativo.taxaGeral)}`}
												/>
											</div>
										) : (
											<p className="text-sm text-muted-foreground">
												Sem dados da média geral deste protocolo.
											</p>
										)}
									</div>
								)}
							</CardContent>
						</Card>
					)}
				</>
			)}
		</div>
	);
};
