"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/app/components/ui/dialog";
import { Checkbox } from "@/app/components/ui/checkbox";
import { Button } from "@/app/components/ui/button";
import { ShieldCheck } from "lucide-react";

const TERMS_TEXT =
  "Declaro que os dados informados são de minha responsabilidade e estou ciente da importância de manter a confidencialidade e a segurança dessas informações, comprometendo-me a não compartilhar acessos, códigos ou dados sensíveis com terceiros.";

interface TermsDialogProps {
  onAccept: () => void;
}

export function TermsDialog({ onAccept }: TermsDialogProps) {
  const [checked, setChecked] = useState(false);

  return (
    <Dialog open modal>
      <DialogContent
        className="max-w-md"
        // Impede fechar ao clicar fora ou pressionar Escape
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <ShieldCheck className="h-5 w-5 text-primary shrink-0" />
            Termo de Responsabilidade
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground leading-relaxed">
          {TERMS_TEXT}
        </p>

        <div className="flex items-start gap-3 rounded-md border p-3 bg-muted/40">
          <Checkbox
            id="terms-checkbox"
            checked={checked}
            onCheckedChange={(v) => setChecked(v === true)}
            className="mt-0.5"
          />
          <label
            htmlFor="terms-checkbox"
            className="text-sm leading-snug cursor-pointer select-none"
          >
            Li e concordo com o termo de responsabilidade acima.
          </label>
        </div>

        <DialogFooter>
          <Button onClick={onAccept} disabled={!checked} className="w-full">
            Confirmar e acessar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
