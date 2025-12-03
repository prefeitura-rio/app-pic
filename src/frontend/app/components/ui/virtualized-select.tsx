"use client";

import * as React from "react";
import { Check, ChevronsUpDown } from "lucide-react";
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
  CommandGroup,
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
}

export function VirtualizedSelect({
  options,
  value,
  onSelect,
  placeholder = "Selecione...",
  defaultLabel = "Todos",
  disabled = false,
}: VirtualizedSelectProps) {
  const [open, setOpen] = React.useState(false);

  // Otimização: Filtragem local simples para react-window
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

  // Tipo para os props customizados (sem index, style, ariaAttributes)
  interface CustomRowProps {
    options: Option[];
    value?: string;
    onSelect: (value: string) => void;
    setOpen: (open: boolean) => void;
  }

  const Row = (props: {
    index: number;
    style: React.CSSProperties;
    ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  } & CustomRowProps) => {
    const { index, style, options, value: selectedValue, onSelect: handleSelect, setOpen: handleSetOpen } = props;
    const option = options[index];
    const isSelected = selectedValue === option.id;
    return (
      <div
        style={style}
        className={cn(
          "flex items-center cursor-pointer px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground",
          isSelected && "bg-accent text-accent-foreground"
        )}
        onClick={() => {
          handleSelect(option.id);
          handleSetOpen(false);
        }}
      >
        <Check
          className={cn(
            "mr-2 h-4 w-4",
            isSelected ? "opacity-100" : "opacity-0"
          )}
        />
        <span className="truncate">{option.label}</span>
      </div>
    );
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal px-3"
          disabled={disabled}
        >
          <span className="truncate">
            {value && value !== "todos" && value !== "todas"
              ? selectedLabel || value
              : placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
        <Command shouldFilter={false}> {/* Desativa filtro nativo do cmkd */}
          <CommandInput
            placeholder="Buscar..."
            value={searchTerm}
            onValueChange={setSearchInput}
          />
          {filteredOptions.length === 0 && (
            <CommandEmpty>Nenhum resultado.</CommandEmpty>
          )}
          <CommandGroup>
             {/* Opção "Todos" fixa no topo */}
            <CommandItem
              value="todos"
              onSelect={() => {
                onSelect("todos");
                setOpen(false);
              }}
            >
              <Check
                className={cn(
                  "mr-2 h-4 w-4",
                  (value === "todos" || value === "todas" || !value) ? "opacity-100" : "opacity-0"
                )}
              />
              {defaultLabel}
            </CommandItem>

            {/* Lista Virtualizada */}
            {filteredOptions.length > 0 && (
              <div style={{ height: Math.min(250, filteredOptions.length * 32) }}>
                <List
                  rowComponent={Row}
                  rowCount={filteredOptions.length}
                  rowHeight={32}
                  rowProps={{ options: filteredOptions, value, onSelect, setOpen }}
                  style={{ height: Math.min(250, filteredOptions.length * 32), width: '100%' }}
                />
              </div>
            )}
          </CommandGroup>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
