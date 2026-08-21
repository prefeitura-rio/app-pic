"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

export const SECRETARIA_OPTIONS: { id: string; label: string }[] = [
  { id: "SME", label: "📚 Educação (SME)" },
  { id: "SMS", label: "🏥 Saúde (SMS)" },
  { id: "SMAS", label: "🤝 Assistência Social (SMAS)" },
];

interface SecretariasAcessoFieldProps {
  value: string[];
  onChange: (value: string[]) => void;
  /** Secretarias que o usuário logado pode atribuir (subset boundary). */
  allowedValues: string[];
  disabled?: boolean;
}

/**
 * Checkboxes para o campo `secretarias_acesso` (array). Um admin segmentado só
 * pode marcar secretarias que estejam em `allowedValues` (subset da sua própria
 * `secretarias_acesso`); super admin recebe as 3 opções em `allowedValues`.
 */
export function SecretariasAcessoField({
  value,
  onChange,
  allowedValues,
  disabled,
}: SecretariasAcessoFieldProps) {
  const toggle = (id: string, checked: boolean) => {
    onChange(checked ? [...value, id] : value.filter((v) => v !== id));
  };

  return (
    <div className="space-y-2">
      {SECRETARIA_OPTIONS.filter((opt) => allowedValues.includes(opt.id)).map((opt) => (
        <div key={opt.id} className="flex items-center gap-2">
          <Checkbox
            id={`secretaria-acesso-${opt.id}`}
            checked={value.includes(opt.id)}
            onCheckedChange={(checked) => toggle(opt.id, checked as boolean)}
            disabled={disabled}
          />
          <Label
            htmlFor={`secretaria-acesso-${opt.id}`}
            className="text-sm font-normal cursor-pointer"
          >
            {opt.label}
          </Label>
        </div>
      ))}
      {allowedValues.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Você não tem secretarias disponíveis para atribuir.
        </p>
      )}
    </div>
  );
}
