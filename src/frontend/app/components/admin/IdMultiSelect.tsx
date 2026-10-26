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
import { Check, ChevronsUpDown, Search, X } from "lucide-react";
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
          <PopoverContent
            className="w-full p-0"
            align="start"
            onOpenAutoFocus={(event) => event.preventDefault()}
          >
            {/* Sem cmdk: o autofocus/scroll do Command era o que fazia a página
                rolar ao abrir o dropdown (conteúdo portalado no fim do body
                antes do posicionamento). Input simples, com a mesma aparência. */}
            <div className="flex h-full w-full flex-col overflow-hidden rounded-md bg-popover text-popover-foreground">
              <div className="flex items-center border-b px-3">
                <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
                <input
                  placeholder="Buscar..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                />
              </div>
              {filteredOptions.length === 0 && (
                <div className="py-6 text-center text-sm">
                  Nenhum resultado encontrado
                </div>
              )}
              <div className="max-h-64 overflow-auto p-1 text-foreground">
                {filteredOptions.map((option) => {
                  const optionIsSelected = isSelected(option);
                  return (
                    <div
                      key={option.id}
                      className={cn(
                        "flex items-center cursor-pointer px-2 py-1.5 text-sm rounded-sm mx-1 hover:bg-accent hover:text-accent-foreground",
                        optionIsSelected && "bg-accent/50"
                      )}
                      onClick={() => toggleOption(option)}
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4 shrink-0",
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
                })}
              </div>
            </div>
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
