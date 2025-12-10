"use client";

import { memo } from "react";
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

// Largura mínima total da tabela para garantir scroll horizontal
const MIN_TABLE_WIDTH = 1000;

export const ParticipantTable = memo(({
  data,
  onRowClick,
  getBadgeVariant,
  isLoading,
}: ParticipantTableProps) => {
  if (!data || !Array.isArray(data) || data.length === 0) {
    return null;
  }

  return (
    <div
      className="relative rounded-lg border bg-card"
      style={{ maxWidth: '100%', overflow: 'hidden' }}
    >
      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-background/50 z-10 flex items-center justify-center">
          <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      )}

      {/* Wrapper com scroll horizontal */}
      <div
        style={{
          display: 'block',
          maxWidth: '100%',
          overflowX: 'auto',
          overflowY: 'hidden'
        }}
      >
        <table style={{ minWidth: MIN_TABLE_WIDTH, width: '100%' }} className="text-sm border-collapse">
          <thead className="bg-muted/50">
            <tr className="border-b">
              <th className="px-3 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">Nome</th>
              <th className="px-3 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">CPF</th>
              <th className="px-3 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">Grupo</th>
              <th className="px-3 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">Bairro</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Idade</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Status</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Total</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Assist.</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Educ.</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Saúde</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap">Situação</th>
            </tr>
          </thead>
          <tbody>
            {data.map((participant, index) => (
              <tr
                key={participant.cpf || index}
                className="border-b last:border-b-0 hover:bg-muted/50 cursor-pointer transition-colors"
                onClick={() => onRowClick(participant)}
              >
                <td className="px-3 py-3 font-medium max-w-[200px]">
                  <span className="line-clamp-2">{participant.nome || "-"}</span>
                </td>
                <td className="px-3 py-3 font-mono whitespace-nowrap">
                  {participant.cpf || "-"}
                </td>
                <td className="px-3 py-3 whitespace-nowrap">
                  {renderGrupo(participant.grupo)}
                </td>
                <td className="px-3 py-3 max-w-[150px]">
                  <span className="line-clamp-2">{participant.bairro || "-"}</span>
                </td>
                <td className="px-3 py-3 text-center whitespace-nowrap">
                  {participant.idade != null ? `${participant.idade} anos` : "-"}
                </td>
                <td className="px-3 py-3 text-center capitalize whitespace-nowrap">
                  {participant.status || "-"}
                </td>
                <td className={`px-3 py-3 text-center font-mono whitespace-nowrap ${getTotalColor(participant.total_fracao)}`}>
                  {participant.total_fracao || "-"}
                </td>
                <td className="px-3 py-3 text-center font-mono whitespace-nowrap">
                  {participant.assistencia_fracao || "-"}
                </td>
                <td className="px-3 py-3 text-center font-mono whitespace-nowrap">
                  {participant.educacao_fracao || "-"}
                </td>
                <td className="px-3 py-3 text-center font-mono whitespace-nowrap">
                  {participant.saude_fracao || "-"}
                </td>
                <td className="px-3 py-3 text-center whitespace-nowrap">
                  <Badge variant={getBadgeVariant(participant.situacao)} className="text-xs">
                    {capitalizeSituacao(participant.situacao)}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});

ParticipantTable.displayName = "ParticipantTable";
