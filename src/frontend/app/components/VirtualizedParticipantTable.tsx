"use client";

import { memo, useCallback, useMemo } from "react";
import { List } from "react-window";
import { Participante } from "../types";
import { Badge } from "@/app/components/ui/badge";

interface VirtualizedParticipantTableProps {
  data: Participante[];
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => "outline" | "default" | "secondary" | "destructive";
}

// OTIMIZAÇÃO: Componente de linha memoizado
const VirtualRow = memo(({
  index,
  onRowClick,
  getBadgeVariant,
  data,
}: {
  index: number;
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => "outline" | "default" | "secondary" | "destructive";
  data: Participante[];
}) => {
  const participant = data[index];

  if (!participant) return null;
  // Função para colorir as frações
  const getTotalColor = (fracao?: string) => {
    if (!fracao) return "text-muted-foreground";
    const [num, den] = fracao.split('/').map(Number);
    if (isNaN(num) || isNaN(den) || den === 0) return "text-muted-foreground";
    const percent = (num / den) * 100;
    if (percent === 100) return "text-green-600 font-semibold";
    if (percent >= 60) return "text-yellow-600 font-semibold";
    return "text-red-600 font-semibold";
  };

  return (
    <div
      className="flex items-center border-b hover:bg-muted/50 cursor-pointer transition-colors"
      onClick={() => onRowClick(participant)}
    >
      <div className="flex-1 min-w-0 px-4 py-3 flex gap-4">
        {/* Nome - 20% */}
        <div className="w-[20%] min-w-0">
          <p className="font-medium truncate text-sm">{participant.nome || "-"}</p>
        </div>

        {/* CPF - 12% */}
        <div className="w-[12%] min-w-0">
          <p className="font-mono text-xs truncate">{participant.cpf || "-"}</p>
        </div>

        {/* Grupo - 10% */}
        <div className="w-[10%] min-w-0">
          <p className="text-sm truncate">
            {participant.grupo?.toLowerCase().includes("crianca")
              ? "👶 Criança"
              : participant.grupo?.toLowerCase().includes("gestante")
              ? "🤰 Gestante"
              : participant.grupo || "-"}
          </p>
        </div>

        {/* Bairro - 12% */}
        <div className="w-[12%] min-w-0">
          <p className="text-sm truncate">{participant.bairro || "-"}</p>
        </div>

        {/* Idade - 8% */}
        <div className="w-[8%] min-w-0">
          <p className="text-sm">{participant.idade ? `${participant.idade} anos` : "0 anos"}</p>
        </div>

        {/* Status - 8% */}
        <div className="w-[8%] min-w-0">
          <Badge
            variant={participant.status === "ativo" ? "default" : "secondary"}
            className="text-xs"
          >
            {participant.status || "-"}
          </Badge>
        </div>

        {/* Situação - 10% */}
        <div className="w-[10%] min-w-0 text-center">
          <Badge variant={getBadgeVariant(participant.situacao)} className="text-xs">
            {participant.situacao || "-"}
          </Badge>
        </div>

        {/* Frações - 20% (4 colunas de 5% cada) */}
        <div className="w-[5%] text-center">
          <p className={`font-mono text-xs ${getTotalColor(participant.total_fracao)}`}>
            {participant.total_fracao || "-"}
          </p>
        </div>

        <div className="w-[5%] text-center">
          <p className="font-mono text-xs">{participant.assistencia_fracao || "-"}</p>
        </div>

        <div className="w-[5%] text-center">
          <p className="font-mono text-xs">{participant.educacao_fracao || "-"}</p>
        </div>

        <div className="w-[5%] text-center">
          <p className="font-mono text-xs">{participant.saude_fracao || "-"}</p>
        </div>
      </div>
    </div>
  );
});
VirtualRow.displayName = "VirtualRow";

export const VirtualizedParticipantTable = memo(({
  data,
  onRowClick,
  getBadgeVariant,
}: VirtualizedParticipantTableProps) => {
  // Validação de segurança
  if (!data || !Array.isArray(data) || data.length === 0) {
    return null;
  }

  // Row props que serão passados para cada linha
  const rowProps = useMemo(() => ({
    onRowClick,
    getBadgeVariant,
    data,
  }), [onRowClick, getBadgeVariant, data]);

  // Height da lista baseado no tamanho da janela (max 600px)
  const listHeight = useMemo(() => Math.min(data.length * 60 + 48, 600), [data.length]);

  return (
    <div className="rounded-lg border overflow-hidden">
      {/* Header fixo */}
      <div className="flex items-center bg-muted border-b font-medium text-sm">
        <div className="flex-1 px-4 py-3 flex gap-4">
          <div className="w-[20%]">Nome</div>
          <div className="w-[12%]">CPF</div>
          <div className="w-[10%]">Grupo</div>
          <div className="w-[12%]">Bairro</div>
          <div className="w-[8%]">Idade</div>
          <div className="w-[8%]">Status</div>
          <div className="w-[10%] text-center">Situação</div>
          <div className="w-[5%] text-center">Total</div>
          <div className="w-[5%] text-center">Assist.</div>
          <div className="w-[5%] text-center">Educ.</div>
          <div className="w-[5%] text-center">Saúde</div>
        </div>
      </div>

      {/* Lista virtualizada */}
      <List
        defaultHeight={listHeight}
        rowCount={data.length}
        rowHeight={60}
        overscanCount={5}
        rowComponent={VirtualRow}
        rowProps={rowProps}
      />
    </div>
  );
});
VirtualizedParticipantTable.displayName = "VirtualizedParticipantTable";
