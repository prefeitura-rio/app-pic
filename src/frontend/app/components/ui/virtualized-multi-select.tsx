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
} from "@/app/components/ui/command";

interface Option {
  id: string;
  label: string;
}

interface VirtualizedMultiSelectProps {
  options: Option[];
  value: string[];
  onSelect: (values: string[]) => void;
  placeholder?: string;
  defaultLabel?: string;
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
  /** Controla a visibilidade do componente. Se false, retorna null. Default: true */
  show?: boolean;
  /** Mostra skeleton no dropdown (e no trigger com valor sem label) */
  loading?: boolean;
  /** Dispara quando o dropdown abre (para carregar opções sob demanda) */
  onOpen?: () => void;
}

export function VirtualizedMultiSelect({
  options,
  value = [],
  onSelect,
  placeholder,
  defaultLabel = placeholder ?? "Todos",
  disabled = false,
  className,
  style,
  show = true,
  loading = false,
  onOpen,
}: VirtualizedMultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const [triggerWidth, setTriggerWidth] = React.useState(0);
  const [searchTerm, setSearchInput] = React.useState("");

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

  const filteredOptions = React.useMemo(() => {
    if (!searchTerm) return options;
    const lower = searchTerm.toLowerCase();
    return options.filter((opt) => opt.label.toLowerCase().includes(lower));
  }, [options, searchTerm]);

  // Check if an option is selected
  const isOptionSelected = React.useCallback((optionId: string) => {
    return value.includes(optionId);
  }, [value]);

  // Toggle selection
  const toggleOption = React.useCallback((optionId: string) => {
    if (isOptionSelected(optionId)) {
      onSelect(value.filter((v) => v !== optionId));
    } else {
      onSelect([...value, optionId]);
    }
  }, [value, onSelect, isOptionSelected]);

  // Clear all
  const clearAll = () => {
    onSelect([]);
  };

  // Get label for an option
  const getLabel = (optionId: string) => {
    return options.find((opt) => opt.id === optionId)?.label || optionId;
  };

  // Display text for the button
  const displayText = value.length === 0
    ? defaultLabel
    : value.length === 1
      ? getLabel(value[0])
      : `${value.length} selecionados`;

  // Row component para react-window
  const Row = React.useCallback((props: {
    index: number;
    style: React.CSSProperties;
    ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  }) => {
    const option = filteredOptions[props.index];
    const isSelected = isOptionSelected(option.id);
    return (
      <div
        style={props.style}
        title={option.label}
        className={cn(
          "flex items-center cursor-pointer px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground rounded-sm mx-1",
          isSelected && "bg-accent/50"
        )}
        onClick={() => toggleOption(option.id)}
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
  }, [filteredOptions, isOptionSelected, toggleOption]);

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
          style={{ width: triggerWidth > 0 ? Math.max(triggerWidth, 300) : 300 }}
          aria-busy={loading}
        >
          <Command shouldFilter={false}>
            <CommandInput
              placeholder="Buscar..."
              value={searchTerm}
              onValueChange={setSearchInput}
            />

            {/* Header com ações */}
            {!loading && value.length > 0 && (
              <div className="flex items-center justify-between px-2 py-1.5 border-b">
                <span className="text-xs text-muted-foreground">
                  {value.length} selecionado(s)
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearAll}
                  className="h-auto p-1 text-xs text-muted-foreground hover:text-foreground"
                >
                  Limpar
                </Button>
              </div>
            )}

            {loading && (
              <div className="flex flex-col items-center justify-center gap-1.5 py-4">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
                <p className="text-xs text-muted-foreground">
                  Calculando Opções Possíveis
                </p>
              </div>
            )}

            {/* Opção "Todos" fixa no topo */}
            {!loading && (
              <div
                className={cn(
                  "flex items-center cursor-pointer px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground rounded-sm mx-1 my-1",
                  value.length === 0 && "bg-accent text-accent-foreground"
                )}
                onClick={() => {
                  clearAll();
                  setOpen(false);
                }}
              >
                <Check
                  className={cn(
                    "mr-2 h-4 w-4",
                    value.length === 0 ? "opacity-100" : "opacity-0"
                  )}
                />
                {defaultLabel}
              </div>
            )}

            {!loading && filteredOptions.length === 0 && (
              <CommandEmpty>Nenhum resultado.</CommandEmpty>
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
