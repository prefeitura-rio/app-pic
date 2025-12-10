"use client";

import { memo } from "react";
import { List } from "react-window";
import { Participante } from "../types";
import { Badge } from "@/app/components/ui/badge";

type BadgeVariant = "outline" | "default" | "secondary" | "destructive" | "warning" | "success";

interface ParticipantTableProps {
  data: Participante[];
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => BadgeVariant;
  isLoading?: boolean;
}

// Função para capitalizar situação
const capitalizeSituacao = (situacao?: string) => {
  if (!situacao) return "-";
  return situacao.charAt(0).toUpperCase() + situacao.slice(1).toLowerCase();
};

// Função para renderizar o grupo com emoji
const renderGrupo = (grupo?: string) => {
  if (!grupo) return "-";
  const lower = grupo.toLowerCase();
  if (lower.includes("crian") || lower.includes("criança")) return "👶 Criança";
  if (lower.includes("gestante")) return "🤰 Gestante";
  return grupo;
};

const getTotalColor = (fracao?: string) => {
  if (!fracao) return "text-muted-foreground";
  const [num, den] = fracao.split('/').map(Number);
  if (isNaN(num) || isNaN(den) || den === 0) return "text-muted-foreground";
  const percent = (num / den) * 100;
  if (percent === 100) return "text-green-600 font-semibold";
  if (percent >= 60) return "text-amber-600 font-semibold";
  return "text-red-600 font-semibold";
};

// Props customizadas passadas para cada row
interface CustomRowProps {
  items: Participante[];
  onRowClick: (participant: Participante) => void;
  getBadgeVariant: (situacao?: string) => BadgeVariant;
}

// Componente Row para react-window v2
const Row = (props: {
  ariaAttributes: { "aria-posinset": number; "aria-setsize": number; role: "listitem" };
  index: number;
  style: React.CSSProperties;
} & CustomRowProps) => {
  const { index, style, items, onRowClick, getBadgeVariant } = props;
  const participant = items[index];

  return (
    <div
      style={style}
      className="flex items-center border-b hover:bg-muted/50 cursor-pointer transition-colors text-sm"
      onClick={() => onRowClick(participant)}
    >
      <div style={{ flex: '3 1 0%', minWidth: 180 }} className="px-2 font-medium">
        <span className="line-clamp-2">{participant.nome || "-"}</span>
      </div>
      <div style={{ flex: '1 1 0%', minWidth: 95 }} className="px-2 font-mono">
        {participant.cpf || "-"}
      </div>
      <div style={{ flex: '0.8 1 0%', minWidth: 75 }} className="px-2">
        <span className="line-clamp-2">{renderGrupo(participant.grupo)}</span>
      </div>
      <div style={{ flex: '1.1 1 0%', minWidth: 90 }} className="px-2">
        <span className="line-clamp-2">{participant.bairro || "-"}</span>
      </div>
      <div style={{ flex: '0.5 1 0%', minWidth: 55 }} className="px-2">
        {participant.idade != null ? `${participant.idade} anos` : "-"}
      </div>
      <div style={{ flex: '0.5 1 0%', minWidth: 55 }} className="px-1 text-center capitalize">
        {participant.status || "-"}
      </div>
      <div style={{ flex: '0.4 1 0%', minWidth: 45 }} className={`px-1 text-center font-mono ${getTotalColor(participant.total_fracao)}`}>
        {participant.total_fracao || "-"}
      </div>
      <div style={{ flex: '0.6 1 0%', minWidth: 55 }} className="px-1 text-center font-mono">
        {participant.assistencia_fracao || "-"}
      </div>
      <div style={{ flex: '0.6 1 0%', minWidth: 55 }} className="px-1 text-center font-mono">
        {participant.educacao_fracao || "-"}
      </div>
      <div style={{ flex: '0.4 1 0%', minWidth: 45 }} className="px-1 text-center font-mono">
        {participant.saude_fracao || "-"}
      </div>
      <div style={{ flex: '1 1 0%', minWidth: 85 }} className="px-2 text-center">
        <Badge variant={getBadgeVariant(participant.situacao)} className="text-xs h-5 px-2">
          {capitalizeSituacao(participant.situacao)}
        </Badge>
      </div>
    </div>
  );
};

export const VirtualizedParticipantTable = memo(({
  data,
  onRowClick,
  getBadgeVariant,
  isLoading,
}: ParticipantTableProps) => {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border overflow-hidden h-[700px] bg-card flex flex-col relative">
      {/* Loading overlay */}
      {isLoading && <div className="loading-overlay"></div>}

      {/* Header - mesmos flex values que as rows */}
      <div
        className="flex items-center bg-muted/50 border-b font-medium text-sm text-muted-foreground h-11 shrink-0"
      >
        <div style={{ flex: '3 1 0%', minWidth: 180 }} className="px-2">Nome</div>
        <div style={{ flex: '1 1 0%', minWidth: 95 }} className="px-2">CPF</div>
        <div style={{ flex: '0.8 1 0%', minWidth: 75 }} className="px-2">Grupo</div>
        <div style={{ flex: '1.1 1 0%', minWidth: 90 }} className="px-2">Bairro</div>
        <div style={{ flex: '0.5 1 0%', minWidth: 55 }} className="px-2">Idade</div>
        <div style={{ flex: '0.5 1 0%', minWidth: 55 }} className="px-1 text-center">Status</div>
        <div style={{ flex: '0.4 1 0%', minWidth: 45 }} className="px-1 text-center">Total</div>
        <div style={{ flex: '0.6 1 0%', minWidth: 55 }} className="px-1 text-center">Assist.</div>
        <div style={{ flex: '0.6 1 0%', minWidth: 55 }} className="px-1 text-center">Educ.</div>
        <div style={{ flex: '0.4 1 0%', minWidth: 45 }} className="px-1 text-center">Saúde</div>
        <div style={{ flex: '1 1 0%', minWidth: 85 }} className="px-2 text-center">Situação</div>
      </div>

      {/* Área Virtualizada - react-window v2 auto-sizes */}
      <div className="flex-1 overflow-hidden">
        <List
          rowComponent={Row}
          rowCount={data.length}
          rowHeight={56}
          rowProps={{ items: data, onRowClick, getBadgeVariant } as CustomRowProps}
          className="h-full"
        />
      </div>
    </div>
  );
});

VirtualizedParticipantTable.displayName = "VirtualizedParticipantTable";
