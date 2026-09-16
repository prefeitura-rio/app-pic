"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiService } from "@/app/services/api";
import type {
	DashboardFilterValues,
	FilterFieldKey,
	FilterOptionItem,
	ParticipantFilters,
} from "@/app/types";
import { VirtualizedMultiSelect } from "@/app/components/ui/virtualized-multi-select";
import { VirtualizedSelect } from "@/app/components/ui/virtualized-select";

type AnyFilters = DashboardFilterValues | ParticipantFilters;

/**
 * Chave do filtro que o PRÓPRIO campo controla (o backend exclui esse filtro
 * do cascade ao calcular as opções do campo — mudá-lo não altera o resultado).
 */
const FIELD_OWN_FILTER_KEYS: Record<FilterFieldKey, string> = {
	bairros: "bairro",
	subprefeituras: "subprefeitura",
	regioes_administrativas: "regiao_administrativa",
	grupos: "grupo",
	cohorts: "safra",
	status_list: "status",
	situacoes: "situacao",
	racas: "raca",
	cres: "cre",
	aps: "ap",
	cas_list: "cas",
	cras: "cras",
	escolas: "escola",
	clinicas: "clinica",
	equipes_familia: "equipe_familia",
	protocolo_descricoes: "protocolo_descricao",
	protocolo_status_list: "protocolo_status",
	bolsa_familia: "has_bolsa_familia",
	protocolo_secretarias: "protocolo_secretaria",
};

// Filtros que o backend ignora no cálculo de opções (não entram na assinatura).
const IGNORED_FILTER_KEYS = new Set(["sort_by", "sort_order", "bypass_cache"]);

/**
 * Assinatura estável dos filtros que efetivamente alteram as opções do campo:
 * tudo exceto o filtro do próprio campo e as chaves ignoradas. Arrays são
 * ordenadas e valores vazios/undefined são descartados.
 */
function effectiveFiltersKey(
	filters: AnyFilters,
	field: FilterFieldKey
): string {
	const ownKey = FIELD_OWN_FILTER_KEYS[field];
	const normalized: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(filters)) {
		if (key === ownKey || IGNORED_FILTER_KEYS.has(key)) continue;
		if (value === undefined || value === null || value === "") continue;
		if (Array.isArray(value)) {
			if (value.length === 0) continue;
			normalized[key] = [...value].sort();
		} else {
			normalized[key] = value;
		}
	}
	return JSON.stringify(normalized);
}

/**
 * Hook que carrega as opções de UM campo de filtro sob demanda (lazy).
 *
 * Estratégia "lazy de verdade": a query key NÃO inclui os filtros — mudar
 * outro filtro não recalcula nada. O snapshot mais recente dos filtros vive
 * num ref e é lido apenas quando a query roda de fato, que acontece em dois
 * momentos: (1) montagem de um campo que já tem valor (para resolver o label
 * do trigger) e (2) quando o dropdown é aberto (`fetchIfNeeded`, via `onOpen`).
 *
 * Nada é recalculado sem necessidade: `staleTime: Infinity` (sem refetch por
 * tempo), `refetchOnMount: false` (sem refetch por remontagem) e
 * `fetchIfNeeded` só refaz quando os filtros efetivos mudaram desde o último
 * cálculo (comparado por `effectiveFiltersKey`, gravada apenas em sucesso).
 * O botão "Atualizar" recalcula via `invalidateQueries(["filterFieldOptions"])`
 * (DashboardClient), que marca a query como stale para a próxima abertura.
 */
export function useFilterFieldOptions(
	field: FilterFieldKey,
	filters: AnyFilters,
	enabled: boolean
) {
	const filtersRef = useRef(filters);
	useEffect(() => {
		filtersRef.current = filters;
	}, [filters]);

	const lastFetchedKeyRef = useRef<string | null>(null);

	const query = useQuery({
		queryKey: ["filterFieldOptions", field],
		queryFn: async () => {
			const snapshot = filtersRef.current;
			const data = await apiService.getFilterFieldOptions(field, snapshot);
			lastFetchedKeyRef.current = effectiveFiltersKey(snapshot, field);
			return data;
		},
		enabled,
		staleTime: Infinity,
		refetchOnMount: false,
		placeholderData: (prev) => prev,
	});

	const { data, isFetching, isFetched, refetch } = query;

	const fetchIfNeeded = useCallback(() => {
		const currentKey = effectiveFiltersKey(filtersRef.current, field);
		if (!isFetched || lastFetchedKeyRef.current !== currentKey) {
			refetch();
		}
	}, [field, isFetched, refetch]);

	// Remontagem com filtros diferentes (label do trigger) ou reabilitação
	// após abertura: refaz apenas quando a assinatura mudou desde o último
	// cálculo. Filtros iguais => cache intacto, nada acontece.
	useEffect(() => {
		if (!enabled || !isFetched) return;
		const currentKey = effectiveFiltersKey(filtersRef.current, field);
		if (lastFetchedKeyRef.current !== currentKey) {
			refetch();
		}
	}, [enabled, field, isFetched, refetch]);

	return { data, isFetching, isFetched, refetch, fetchIfNeeded };
}

function cleanOptions(options: FilterOptionItem[]): FilterOptionItem[] {
	return (options || []).filter((item) => item.id && item.id.trim() !== "");
}

interface LazyFilterMultiSelectProps {
	field: FilterFieldKey;
	filters: AnyFilters;
	value: string[];
	onSelect: (values: string[]) => void;
	placeholder?: string;
	defaultLabel?: string;
	disabled?: boolean;
	className?: string;
	show?: boolean;
	transformLabel?: (label: string) => string;
}

export function LazyFilterMultiSelect({
	field,
	filters,
	value,
	onSelect,
	placeholder,
	defaultLabel,
	disabled,
	className,
	show = true,
	transformLabel,
}: LazyFilterMultiSelectProps) {
	const [opened, setOpened] = useState(false);
	const hasValue = value.length > 0;
	const { data, isFetching, fetchIfNeeded } = useFilterFieldOptions(
		field,
		filters,
		opened || hasValue
	);

	const handleOpen = () => {
		setOpened(true);
		fetchIfNeeded();
	};

	const options = cleanOptions(data?.options || []).map((item) =>
		transformLabel ? { ...item, label: transformLabel(item.label) } : item
	);

	return (
		<VirtualizedMultiSelect
			options={options}
			value={value}
			onSelect={onSelect}
			placeholder={placeholder}
			defaultLabel={defaultLabel}
			disabled={disabled}
			className={className}
			show={show}
			loading={isFetching}
			onOpen={handleOpen}
		/>
	);
}

interface LazyFilterSelectProps {
	field: FilterFieldKey;
	filters: AnyFilters;
	value?: string;
	onSelect: (value: string) => void;
	placeholder?: string;
	defaultLabel?: string;
	disabled?: boolean;
	className?: string;
	show?: boolean;
	showAllOption?: boolean;
	transformLabel?: (label: string) => string;
}

export function LazyFilterSelect({
	field,
	filters,
	value,
	onSelect,
	placeholder,
	defaultLabel,
	disabled,
	className,
	show = true,
	showAllOption = true,
	transformLabel,
}: LazyFilterSelectProps) {
	const [opened, setOpened] = useState(false);
	const hasValue = !!value && value !== "todos" && value !== "todas";
	const { data, isFetching, fetchIfNeeded } = useFilterFieldOptions(
		field,
		filters,
		opened || hasValue
	);

	const handleOpen = () => {
		setOpened(true);
		fetchIfNeeded();
	};

	const options = cleanOptions(data?.options || []).map((item) =>
		transformLabel ? { ...item, label: transformLabel(item.label) } : item
	);

	return (
		<VirtualizedSelect
			options={options}
			value={value}
			onSelect={onSelect}
			placeholder={placeholder}
			defaultLabel={defaultLabel}
			disabled={disabled}
			className={className}
			show={show}
			showAllOption={showAllOption}
			loading={isFetching}
			onOpen={handleOpen}
		/>
	);
}
