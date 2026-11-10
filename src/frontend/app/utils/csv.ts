/**
 * CSV no cliente — mesmo formato dos exports de streaming do backend
 * (`src/pic/infrastructure/export/csv_generator.py`): BOM UTF-8, delimitador
 * `;`, todo valor entre aspas e `""` para nulo. Números seguem crus (ponto
 * decimal) para a planilha somar direto.
 */

export type CsvValue = string | number | null | undefined;

function escapeCsvCell(value: CsvValue): string {
  if (value === null || value === undefined) {
    return '""';
  }
  const text = String(value)
    .replace(/\r?\n/g, " ")
    .replace(/"/g, '""');
  return `"${text}"`;
}

/** Monta o conteúdo CSV (com BOM e quebra de linha final). */
export function buildCsv(cabecalho: string[], linhas: CsvValue[][]): string {
  const registros = [cabecalho, ...linhas].map((linha) =>
    linha.map(escapeCsvCell).join(";"),
  );
  return `\ufeff${registros.join("\n")}\n`;
}

/** Baixa um CSV via Blob + âncora (mesma mecânica dos outros downloads). */
export function downloadCsv(
  nomeArquivo: string,
  cabecalho: string[],
  linhas: CsvValue[][],
): void {
  const blob = new Blob([buildCsv(cabecalho, linhas)], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nomeArquivo;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
