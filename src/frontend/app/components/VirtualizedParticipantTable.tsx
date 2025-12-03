"use client";

import { memo } from "react";
import { List } from "react-window";
import AutoSizer from "react-virtualized-auto-sizer";
import { Participante } from "../types";
import { Badge } from "@/app/components/ui/badge";

interface ParticipantTableProps {
  data: Participante[];
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => "outline" | "default" | "secondary" | "destructive";
}

// Componente Row para react-window
const Row = (props: {
  index: number;
  style: React.CSSProperties;
  ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  items: Participante[];
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => "outline" | "default" | "secondary" | "destructive";
}) => {
  const { index, style, items, onRowClick, getBadgeVariant } = props;
  const participant: Participante = items[index];

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
      style={style}
      className="flex items-center border-b hover:bg-muted/50 cursor-pointer transition-colors text-sm"
      onClick={() => onRowClick(participant)}
    >
      <div className="w-[20%] px-4 truncate">{participant.nome || "-"}</div>
      <div className="w-[12%] px-2 font-mono text-xs">{participant.cpf || "-"}</div>
      <div className="w-[10%] px-2 truncate text-xs">
        {participant.grupo?.toLowerCase().includes("crianca")
          ? "👶 Criança"
          : participant.grupo?.toLowerCase().includes("gestante")
          ? "🤰 Gestante"
          : participant.grupo || "-"}
      </div>
      <div className="w-[12%] px-2 truncate">{participant.bairro || "-"}</div>
      <div className="w-[8%] px-2">{participant.idade ? `${participant.idade} anos` : "0 anos"}</div>
      <div className="w-[8%] px-2">
        <Badge variant={participant.status === "ativo" ? "default" : "secondary"} className="text-[10px] h-5 px-1">
          {participant.status || "-"}
        </Badge>
      </div>
      <div className="w-[10%] px-2 text-center">
        <Badge variant={getBadgeVariant(participant.situacao)} className="text-[10px] h-5 px-1">
          {participant.situacao || "-"}
        </Badge>
      </div>
      <div className={`w-[5%] text-center font-mono text-xs ${getTotalColor(participant.total_fracao)}`}>
        {participant.total_fracao || "-"}
      </div>
      <div className="w-[5%] text-center font-mono text-xs">{participant.assistencia_fracao || "-"}</div>
      <div className="w-[5%] text-center font-mono text-xs">{participant.educacao_fracao || "-"}</div>
      <div className="w-[5%] text-center font-mono text-xs">{participant.saude_fracao || "-"}</div>
    </div>
  );
};

export const VirtualizedParticipantTable = memo(({
  data,
  onRowClick,
  getBadgeVariant,
}: ParticipantTableProps) => {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border overflow-hidden h-[600px] bg-card flex flex-col">
      {/* Header Estático */}
      <div className="flex items-center bg-muted border-b font-medium text-sm px-0 py-3 h-10 shrink-0">
        <div className="w-[20%] px-4">Nome</div>
        <div className="w-[12%] px-2">CPF</div>
        <div className="w-[10%] px-2">Grupo</div>
        <div className="w-[12%] px-2">Bairro</div>
        <div className="w-[8%] px-2">Idade</div>
        <div className="w-[8%] px-2">Status</div>
        <div className="w-[10%] text-center">Situação</div>
        <div className="w-[5%] text-center">Total</div>
        <div className="w-[5%] text-center">Assis.</div>
        <div className="w-[5%] text-center">Educ.</div>
        <div className="w-[5%] text-center">Saúde</div>
      </div>

      {/* Área Virtualizada */}
      <div className="flex-1" style={{ minHeight: 0 }}>
        <AutoSizer>
          {({ height, width }) => (
            <div style={{ height, width }}>
              <List
                rowComponent={Row}
                rowCount={data.length}
                rowHeight={48}
                rowProps={{ items: data, onRowClick, getBadgeVariant }}
                style={{ height, width }}
              />
            </div>
          )}
        </AutoSizer>
      </div>
    </div>
  );
});

VirtualizedParticipantTable.displayName = "VirtualizedParticipantTable";
