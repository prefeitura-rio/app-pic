"use client";

import { useState, useMemo } from "react";
import { IdWithName } from "@/app/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
} from "@/components/ui/command";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { cn } from "@/app/utils/utils";
import { List } from "react-window";

interface VirtualizedIdMultiSelectProps {
  label: string;
  options: IdWithName[];
  selected: IdWithName[];
  onChange: (selected: IdWithName[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function VirtualizedIdMultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = "Selecione...",
  disabled = false,
}: VirtualizedIdMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

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
  const isSelected = (option: IdWithName) => {
    return selected.some((s) => s.id === option.id);
  };

  // Toggle selection
  const toggleOption = (option: IdWithName) => {
    if (isSelected(option)) {
      onChange(selected.filter((s) => s.id !== option.id));
    } else {
      onChange([...selected, option]);
    }
  };

  // Remove selected item
  const removeItem = (option: IdWithName) => {
    onChange(selected.filter((s) => s.id !== option.id));
  };

  // Clear all
  const clearAll = () => {
    onChange([]);
  };

  // Virtualized row component
  interface CustomRowProps {
    options: IdWithName[];
    toggleOption: (option: IdWithName) => void;
    isSelected: (option: IdWithName) => boolean;
  }

  const Row = (props: {
    index: number;
    style: React.CSSProperties;
    ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  } & CustomRowProps) => {
    const { index, style, options, toggleOption: handleToggle, isSelected: checkSelected } = props;
    const option = options[index];
    const selected = checkSelected(option);

    return (
      <div
        style={style}
        className={cn(
          "flex items-start cursor-pointer px-2 py-2 hover:bg-secondary hover:text-secondary-foreground",
          selected && "bg-secondary/50"
        )}
        onClick={() => handleToggle(option)}
      >
        <Check
          className={cn(
            "mr-2 h-4 w-4 mt-0.5 shrink-0",
            selected ? "opacity-100" : "opacity-0"
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
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        {selected.length > 0 && !disabled && (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearAll}
            className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
          >
            Limpar todos
          </Button>
        )}
      </div>

      {/* Selected items */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 p-2 border rounded-md bg-muted/50 min-h-[2.5rem]">
          {selected.map((item) => (
            <Badge
              key={item.id}
              variant="secondary"
              className="gap-1"
            >
              {item.nome}
              {!disabled && (
                <button
                  onClick={() => removeItem(item)}
                  className="ml-1 hover:text-destructive"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}

      {/* Combobox */}
      {!disabled && (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              aria-expanded={open}
              className="w-full justify-between"
              disabled={disabled}
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
              <CommandEmpty>Nenhum resultado encontrado</CommandEmpty>
              <CommandGroup className="p-0">
                {filteredOptions.length > 0 && (
                  <List
                    rowComponent={Row}
                    rowCount={filteredOptions.length}
                    rowHeight={48}
                    rowProps={{ options: filteredOptions, toggleOption, isSelected }}
                    style={{ height: Math.min(300, filteredOptions.length * 48), width: '100%' }}
                  />
                )}
              </CommandGroup>
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
