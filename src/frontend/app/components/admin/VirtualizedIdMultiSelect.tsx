"use client";

import { useState, useMemo, useCallback } from "react";
import { IdWithName } from "@/app/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandInput,
} from "@/components/ui/command";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/app/utils/utils";
import { List } from "react-window";

interface VirtualizedIdMultiSelectProps {
  label: string;
  options: IdWithName[];
  selected: IdWithName[];
  onChange: (selected: IdWithName[]) => void;
  placeholder?: string;
  disabled?: boolean;
  tooltip?: string;
  onOpen?: () => void;
  loading?: boolean;
}

export function VirtualizedIdMultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = "Selecione...",
  disabled = false,
  tooltip,
  onOpen,
  loading = false,
}: VirtualizedIdMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  // Trigger the lazy load on first open (filters pattern)
  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      setOpen(nextOpen);
      if (nextOpen) {
        onOpen?.();
      }
    },
    [onOpen]
  );

  // Filter options based on search
  const filteredOptions = useMemo(() => {
    if (!search) return options;

    const searchLower = search.toLowerCase();
    return options.filter(
      (opt) =>
        opt.id.toLowerCase().includes(searchLower) ||
        opt.nome.toLowerCase().includes(searchLower)
    );
  }, [options, search]);

  // Check if an option is selected
  const isOptionSelected = useCallback((option: IdWithName) => {
    return selected.some((s) => s.id === option.id);
  }, [selected]);

  // Toggle selection
  const toggleOption = useCallback((option: IdWithName) => {
    if (isOptionSelected(option)) {
      onChange(selected.filter((s) => s.id !== option.id));
    } else {
      onChange([...selected, option]);
    }
  }, [selected, onChange, isOptionSelected]);

  // Clear all
  const clearAll = () => {
    onChange([]);
  };

  // Select all
  const selectAll = () => {
    onChange([...options]);
  };

  // Row component para react-window
  const Row = useCallback((props: {
    index: number;
    style: React.CSSProperties;
    ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  }) => {
    const option = filteredOptions[props.index];
    const optionIsSelected = isOptionSelected(option);
    return (
      <div
        style={props.style}
        className={cn(
          "flex items-start cursor-pointer px-2 py-2 rounded-sm mx-1 hover:bg-accent hover:text-accent-foreground",
          optionIsSelected && "bg-accent/50"
        )}
        onClick={() => toggleOption(option)}
        title={`${option.nome} (${option.id})`}
      >
        <Check
          className={cn(
            "mr-2 h-4 w-4 mt-0.5 shrink-0",
            optionIsSelected ? "opacity-100" : "opacity-0"
          )}
        />
        <div className="flex flex-col min-w-0">
          <span className="font-medium truncate">{option.nome}</span>
          <span className="text-xs text-muted-foreground truncate">
            {option.id}
          </span>
        </div>
      </div>
    );
  }, [filteredOptions, isOptionSelected, toggleOption]);

  const listHeight = Math.min(300, filteredOptions.length * 48);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label title={tooltip}>{label}</Label>
        {!disabled && (
          <div className="flex gap-2">
            {selected.length < options.length && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={selectAll}
                className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
                title={`Selecionar todos os ${options.length} itens disponíveis`}
              >
                Selecionar todos
              </Button>
            )}
            {selected.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={clearAll}
                className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
                title="Remover todas as seleções"
              >
                Limpar todos
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Selected count chip — individual items are shown inside the dropdown */}
      {selected.length > 0 && (
        <div className="flex items-center gap-2 p-2 border rounded-md bg-muted/50">
          <Badge variant="secondary" title={`${selected.length} itens selecionados`}>
            {selected.length} selecionado(s)
          </Badge>
        </div>
      )}

      {/* Combobox */}
      {!disabled && (
        <Popover open={open} onOpenChange={handleOpenChange}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={open}
              className="w-full justify-between"
              disabled={disabled}
              title={tooltip || `Clique para selecionar ${label.toLowerCase()}`}
            >
              {selected.length === 0 ? (
                <span className="text-muted-foreground">{placeholder}</span>
              ) : (
                <span>{selected.length} selecionado(s)</span>
              )}
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[600px] p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput
                placeholder="Buscar..."
                value={search}
                onValueChange={setSearch}
              />
              {loading && (
                <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Carregando opções...
                </div>
              )}
              {!loading && filteredOptions.length === 0 && (
                <CommandEmpty>Nenhum resultado encontrado</CommandEmpty>
              )}
              {!loading && filteredOptions.length > 0 && (
                <List
                  rowComponent={Row}
                  rowCount={filteredOptions.length}
                  rowHeight={48}
                  rowProps={{}}
                  style={{ height: listHeight, width: '100%' }}
                />
              )}
            </Command>
          </PopoverContent>
        </Popover>
      )}

      {/* Help text */}
      <p className="text-xs text-muted-foreground">
        {selected.length === 0
          ? "Nenhum selecionado (sem restrições para este tipo)"
          : `${selected.length} de ${options.length} selecionado(s)`}
      </p>
    </div>
  );
}
