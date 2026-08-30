"use client";

import * as React from "react";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { List } from "react-window";
import { cn } from "@/app/utils/utils";
import { Button } from "@/app/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/app/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
} from "@/app/components/ui/command";

interface Option {
  id: string;
  label: string;
}

interface VirtualizedSelectProps {
  options: Option[];
  value?: string;
  onSelect: (value: string) => void;
  placeholder?: string;
  defaultLabel?: string;
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
  /** Controla a visibilidade do componente. Se false, retorna null. Default: true */
  show?: boolean;
  /** Mostra opção "Todos" no topo. Default: true */
  showAllOption?: boolean;
  /** Mostra skeleton no dropdown (e no trigger com valor sem label) */
  loading?: boolean;
  /** Dispara quando o dropdown abre (para carregar opções sob demanda) */
  onOpen?: () => void;
}

export function VirtualizedSelect({
  options,
  value,
  onSelect,
  placeholder,
  defaultLabel = placeholder ?? "Todos",
  disabled = false,
  className,
  style,
  show = true,
  showAllOption = true,
  loading = false,
  onOpen,
}: VirtualizedSelectProps) {
  const [open, setOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const [triggerWidth, setTriggerWidth] = React.useState(0);

  // Medir a largura do trigger quando abrir o popover
  React.useEffect(() => {
    if (open && triggerRef.current) {
      setTriggerWidth(triggerRef.current.offsetWidth);
    }
  }, [open]);

  const handleOpenChange = React.useCallback(
    (nextOpen: boolean) => {
      setOpen(nextOpen);
      if (nextOpen) onOpen?.();
    },
    [onOpen]
  );

  // Filtragem local
  const [searchTerm, setSearchInput] = React.useState("");

  const filteredOptions = React.useMemo(() => {
    if (!searchTerm) return options;
    const lower = searchTerm.toLowerCase();
    return options.filter((opt) => opt.label.toLowerCase().includes(lower));
  }, [options, searchTerm]);

  const selectedLabel = React.useMemo(
    () => options.find((opt) => opt.id === value)?.label,
    [options, value]
  );

  // Texto a ser exibido no botão
  const displayText = value && value !== "todos" && value !== "todas"
    ? selectedLabel || value
    : defaultLabel;

  // Row component para react-window
  const Row = React.useCallback((props: {
    index: number;
    style: React.CSSProperties;
    ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  }) => {
    const option = filteredOptions[props.index];
    const isSelected = value === option.id;
    return (
      <div
        style={props.style}
        title={option.label}
        className={cn(
          "flex items-center cursor-pointer px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground rounded-sm mx-1",
          isSelected && "bg-accent text-accent-foreground"
        )}
        onClick={() => {
          onSelect(option.id);
          setOpen(false);
        }}
      >
        <Check
          className={cn(
            "mr-2 h-4 w-4 shrink-0",
            isSelected ? "opacity-100" : "opacity-0"
          )}
        />
        <span className="truncate">{option.label}</span>
      </div>
    );
  }, [filteredOptions, value, onSelect]);

  const listHeight = Math.min(280, filteredOptions.length * 32);

  // Se show=false, não renderiza nada (após todos os hooks, conforme Rules of Hooks)
  if (!show) return null;

  return (
    <div className={className} style={style}>
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <Button
            ref={triggerRef}
            variant="outline"
            role="combobox"
            aria-expanded={open}
            title={displayText}
            className="w-full justify-between font-normal px-3"
            disabled={disabled}
          >
            <span className="truncate">{displayText}</span>
            {loading ? (
              <Loader2 className="ml-2 h-4 w-4 shrink-0 animate-spin opacity-70" />
            ) : (
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="p-0"
          align="start"
          style={{ width: triggerWidth > 0 ? triggerWidth : 300 }}
          aria-busy={loading}
        >
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Buscar..."
              value={searchTerm}
              onValueChange={setSearchInput}
            />
            {loading && (
              <div className="flex flex-col items-center justify-center gap-1.5 py-4">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
                <p className="text-xs text-muted-foreground">
                  Calculando Opções Possíveis
                </p>
              </div>
            )}
            {!loading && filteredOptions.length === 0 && (
              <CommandEmpty>Nenhum resultado.</CommandEmpty>
            )}

            {/* Opção "Todos" fixa no topo (opcional) */}
            {!loading && showAllOption && (
              <CommandItem
                value="todos"
                onSelect={() => {
                  onSelect("todos");
                  setOpen(false);
                }}
                className="mx-1"
              >
                <Check
                  className={cn(
                    "mr-2 h-4 w-4",
                    (value === "todos" || value === "todas" || !value) ? "opacity-100" : "opacity-0"
                  )}
                />
                {defaultLabel}
              </CommandItem>
            )}

            {/* Lista virtualizada */}
            {!loading && filteredOptions.length > 0 && (
              <List
                rowComponent={Row}
                rowCount={filteredOptions.length}
                rowHeight={32}
                rowProps={{}}
                style={{ height: listHeight, width: '100%', overflowX: 'hidden' }}
              />
            )}
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
