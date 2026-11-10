"use client";

/**
 * Calendário semanal do período De/Até da Evolução semanal.
 *
 * Lista cronológica em que cada linha é UMA semana disponível (domingo a
 * sábado), agrupada por mês. Ao lado de cada semana, o dia de avaliação
 * (``snapshot_date``; fallback no domingo da própria semana).
 *
 * O 1º clique define o início e o 2º define o fim (troca automaticamente se
 * o segundo for anterior); a seleção destaca o intervalo de SEMANAS como uma
 * faixa vertical contínua (as linhas se encostam — sem vãos; só as pontas
 * arredondam). "Aplicar" confirma; fechar sem aplicar descarta o rascunho.
 *
 * Ao abrir, o período atual aparece selecionado e a lista rola até a semana
 * final. A lista só contém semanas da janela estável — não há lacunas para
 * desabilitar.
 */

import { addDays, format, startOfWeek } from "date-fns";
import { ptBR } from "date-fns/locale";
import { CalendarRange } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/app/components/ui/button";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@/app/components/ui/popover";
import { cn } from "@/app/utils/utils";
import { snapshotLabel } from "./format";

/** "2026-07-19" → Date local ao meio-dia (evita virada de dia por fuso). */
function dataDeIso(iso: string): Date {
	return new Date(`${iso}T12:00:00`);
}

function isoDeData(data: Date): string {
	return format(data, "yyyy-MM-dd");
}

/** "2026-07-19" → "19/07". */
function curta(iso: string): string {
	return format(dataDeIso(iso), "dd/MM");
}

/** "2026-07-19" (domingo) → "19/07 – 25/07". */
function semanaFaixa(weekStart: string): string {
	const sabado = isoDeData(addDays(dataDeIso(weekStart), 6));
	return `${curta(weekStart)} – ${curta(sabado)}`;
}

function semanaDeDia(dia: string): string {
	return isoDeData(startOfWeek(dataDeIso(dia), { weekStartsOn: 0 }));
}

/** Dia de referência da semana: a data de avaliação (snapshot), se válida e
 *  dentro da própria semana; senão, o domingo da semana. */
function diaReferencia(semana: string, snap: string | null | undefined): string {
	const dia = snap?.slice(0, 10);
	if (dia) {
		const data = dataDeIso(dia);
		if (!Number.isNaN(data.getTime()) && semanaDeDia(dia) === semana) {
			return dia;
		}
	}
	return semana;
}

/** Linhas da lista: separadores de mês + semanas. */
type Linha =
	| {
			tipo: "mes";
			chave: string;
			rotulo: string;
			semanaDepois: string;
			semanaAntes: string | null;
	  }
	| { tipo: "semana"; chave: string; semana: string };

interface CalendarioSemanalProps {
	/** Semanas disponíveis (domingos ISO, ascendentes). */
	semanas: string[];
	/** Semana → data da avaliação (o dia de referência exibido). */
	snapshotPorSemana: Map<string, string | null>;
	/** Período efetivo atual em SEMANAS (para inicializar o rascunho). */
	de: string;
	ate: string;
	onApply: (de: string, ate: string) => void;
	disabled?: boolean;
}

export function CalendarioSemanal({
	semanas,
	snapshotPorSemana,
	de,
	ate,
	onApply,
	disabled,
}: CalendarioSemanalProps) {
	const [open, setOpen] = useState(false);
	// Rascunho em SEMANAS; só é preenchido ao abrir o popover.
	const [draft, setDraft] = useState<{ de: string | null; ate: string | null }>({
		de: null,
		ate: null,
	});
	const fimRef = useRef<HTMLButtonElement | null>(null);

	const disponiveis = useMemo(() => new Set(semanas), [semanas]);

	/** Semana → dia de referência (avaliação; fallback domingo). */
	const referenciaPorSemana = useMemo(
		() =>
			new Map(
				semanas.map((w) => [w, diaReferencia(w, snapshotPorSemana.get(w))]),
			),
		[semanas, snapshotPorSemana],
	);

	/** Lista com separadores de mês (o mês é o do domingo da semana). */
	const linhas = useMemo<Linha[]>(() => {
		const out: Linha[] = [];
		semanas.forEach((w, i) => {
			const anterior = i > 0 ? semanas[i - 1] : null;
			const mesmoMes =
				anterior !== null &&
				format(dataDeIso(anterior), "yyyy-MM") ===
					format(dataDeIso(w), "yyyy-MM");
			if (!mesmoMes) {
				out.push({
					tipo: "mes",
					chave: `mes-${w}`,
					rotulo: format(dataDeIso(w), "MMMM 'de' yyyy", { locale: ptBR }),
					semanaDepois: w,
					semanaAntes: anterior,
				});
			}
			out.push({ tipo: "semana", chave: w, semana: w });
		});
		return out;
	}, [semanas]);

	/** Abre com o período efetivo selecionado (trocado se de > até). */
	const aoAbrirFechar = (next: boolean) => {
		if (next) {
			let d = de && disponiveis.has(de) ? de : null;
			let a = ate && disponiveis.has(ate) ? ate : null;
			if (d !== null && a !== null && d > a) {
				[d, a] = [a, d];
			}
			setDraft({ de: d, ate: a });
		}
		setOpen(next);
	};

	// Ao abrir, rola até a semana final do período atual.
	useEffect(() => {
		if (open) {
			fimRef.current?.scrollIntoView({ block: "nearest" });
		}
	}, [open]);

	const clicarSemana = (w: string) => {
		setDraft((prev) => {
			if (prev.de === null || prev.ate !== null) {
				// Inicia um novo intervalo.
				return { de: w, ate: null };
			}
			if (w < prev.de) {
				return { de: w, ate: prev.de };
			}
			return { de: prev.de, ate: w };
		});
	};

	const aplicar = () => {
		if (draft.de !== null && draft.ate !== null) {
			onApply(draft.de, draft.ate);
			setOpen(false);
		}
	};

	const draftDe = draft.de;
	const draftAte = draft.ate;
	const semanasNoRange =
		draftDe !== null && draftAte !== null
			? semanas.filter((w) => w >= draftDe && w <= draftAte).length
			: 0;

	// Contagem do GATILHO usa o período efetivo aplicado (não o rascunho):
	// os atalhos "12 semanas"/"Todas" mudam o período sem abrir o popover.
	const semanasNoRangeEfetivo =
		de && ate ? semanas.filter((w) => w >= de && w <= ate).length : 0;

	const inicioRotulo = de ? curta(de) : "—";
	const fimRotulo = ate ? curta(isoDeData(addDays(dataDeIso(ate), 6))) : "—";
	const titulo =
		de && ate
			? `Semanas de ${format(dataDeIso(de), "dd/MM/yyyy")} a ${format(
					addDays(dataDeIso(ate), 6),
					"dd/MM/yyyy",
				)}`
			: "Selecionar período";

	// Linha alvo do scroll: a semana final do rascunho (ou a última).
	const alvoFim =
		draftAte ?? (semanas.length > 0 ? semanas[semanas.length - 1] : null);

	return (
		<Popover open={open} onOpenChange={aoAbrirFechar}>
			<PopoverTrigger asChild>
				<Button
					variant="outline"
					size="sm"
					className="h-9 text-xs font-normal"
					disabled={disabled || semanas.length === 0}
					aria-haspopup="dialog"
					aria-label="Selecionar período"
					title={titulo}
				>
					<CalendarRange className="mr-1 h-3.5 w-3.5 shrink-0 opacity-70" />
					<span className="truncate">
						{inicioRotulo} – {fimRotulo}
					</span>
					{semanasNoRangeEfetivo > 0 ? (
						<span className="ml-1 shrink-0 opacity-70">
							({semanasNoRangeEfetivo} sem.)
						</span>
					) : null}
				</Button>
			</PopoverTrigger>
			<PopoverContent
				align="end"
				className="w-[min(360px,calc(100vw-2rem))] p-3"
			>
				<div className="flex items-baseline justify-between">
					<span className="text-sm font-medium">Semanas</span>
					<span className="text-xs text-muted-foreground">
						{semanas.length} disponíveis
					</span>
				</div>

				{/* Lista de semanas — sem vãos: o fundo do intervalo encosta
				    na linha vizinha e vira uma faixa contínua. */}
				<div
					className="mt-2 max-h-72 overflow-y-auto pr-1"
					role="group"
					aria-label="Semanas disponíveis"
				>
					{linhas.map((linha) => {
						if (linha.tipo === "mes") {
							const dentro =
								linha.semanaAntes !== null &&
								draftDe !== null &&
								draftAte !== null &&
								linha.semanaAntes >= draftDe &&
								linha.semanaAntes <= draftAte &&
								linha.semanaDepois >= draftDe &&
								linha.semanaDepois <= draftAte;
							return (
								<div
									key={linha.chave}
									className={cn(
										"flex h-6 items-center px-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground",
										dentro && "bg-primary/20",
									)}
								>
									<span className="capitalize">{linha.rotulo}</span>
								</div>
							);
						}
						const w = linha.semana;
						const dentro =
							draftDe !== null &&
							draftAte !== null &&
							w >= draftDe &&
							w <= draftAte;
						const ehInicio = w === draftDe;
						const ehFim = w === draftAte;
						const ehPonta = ehInicio || ehFim;
						const referencia = referenciaPorSemana.get(w) ?? w;
						const snap = snapshotPorSemana.get(w);
						return (
							<button
								key={linha.chave}
								type="button"
								ref={w === alvoFim ? fimRef : undefined}
								onClick={() => clicarSemana(w)}
								aria-pressed={ehPonta}
								aria-label={`Semana de ${semanaFaixa(w)}, avaliação em ${curta(
									referencia,
								)}`}
								title={
									snap
										? `Avaliação: ${snapshotLabel(snap)}`
										: "Sem data de avaliação — usa o domingo da semana"
								}
								className={cn(
									"flex h-9 w-full items-center justify-between gap-2 px-3 text-xs transition-colors",
									!dentro && "hover:bg-muted",
									dentro && !ehPonta && "bg-primary/20",
									ehInicio &&
										!ehFim &&
										"rounded-t-xl rounded-b-none bg-primary text-primary-foreground hover:bg-primary",
									ehFim &&
										!ehInicio &&
										"rounded-b-xl rounded-t-none bg-primary text-primary-foreground hover:bg-primary",
									ehInicio &&
										ehFim &&
										"rounded-full bg-primary text-primary-foreground hover:bg-primary",
								)}
							>
								<span className="font-medium">{semanaFaixa(w)}</span>
								<span
									className={cn(
										"shrink-0 text-[11px]",
										ehPonta
											? "text-primary-foreground/80"
											: "text-muted-foreground",
									)}
								>
									aval. {curta(referencia)}
								</span>
							</button>
						);
					})}
				</div>

				<p className="mt-2 text-[11px] leading-snug text-muted-foreground">
					Clique na semana inicial e depois na final — o intervalo vira
					uma faixa contínua. “aval.” é o dia da avaliação de cada
					semana.
				</p>

				{/* Rodapé: resumo + aplicar/cancelar */}
				<div className="mt-3 flex items-center justify-between gap-2 border-t pt-2">
					<span className="text-xs text-muted-foreground">
						{draftDe !== null && draftAte !== null
							? `${semanasNoRange} ${
									semanasNoRange === 1 ? "semana" : "semanas"
								}`
							: draftDe !== null
								? "Escolha a semana final"
								: "Escolha a semana inicial"}
					</span>
					<div className="flex shrink-0 gap-2">
						<Button
							variant="ghost"
							size="sm"
							className="h-7 text-xs"
							onClick={() => setOpen(false)}
						>
							Cancelar
						</Button>
						<Button
							size="sm"
							className="h-7 text-xs"
							onClick={aplicar}
							disabled={draftDe === null || draftAte === null}
						>
							Aplicar
						</Button>
					</div>
				</div>
			</PopoverContent>
		</Popover>
	);
}
