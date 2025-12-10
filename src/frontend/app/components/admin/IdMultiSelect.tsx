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
  CommandItem,
} from "@/components/ui/command";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { cn } from "@/app/utils/utils";

interface IdMultiSelectProps {
  label: string;
  options: IdWithName[];
  selected: IdWithName[];
  onChange: (selected: IdWithName[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function IdMultiSelect({
  label,
  options,
  selected,
  onChange,
  placeholder = "Selecione...",
  disabled = false,
}: IdMultiSelectProps) {
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
          <PopoverContent className="w-full p-0" align="start">
            <Command>
              <CommandInput
                placeholder="Buscar..."
                value={search}
                onValueChange={setSearch}
              />
              <CommandEmpty>Nenhum resultado encontrado</CommandEmpty>
              <CommandGroup className="max-h-64 overflow-auto">
                {filteredOptions.map((option) => {
                  const selected = isSelected(option);
                  return (
                    <CommandItem
                      key={option.id}
                      value={option.id}
                      onSelect={() => toggleOption(option)}
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4",
                          selected ? "opacity-100" : "opacity-0"
                        )}
                      />
                      <div className="flex flex-col">
                        <span className="font-medium">{option.nome}</span>
                        <span className="text-xs text-muted-foreground">
                          {option.id}
                        </span>
                      </div>
                    </CommandItem>
                  );
                })}
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
