/**
 * Cores compartilhadas dos gráficos do Acompanhamento semanal.
 * (Extraídas de ProtocolSeriesChart/EvolucaoSemanal, que as duplicavam.)
 */

export const COR_REGULAR = "#15803d"; // green-700
export const COR_IRREGULAR = "#dc2626"; // red-600
export const COR_ATIVO = "#16a34a"; // green-600
export const COR_INATIVO = "#f59e0b"; // amber-500

/**
 * Série "ativo irregular" do gráfico de classificação (amarelo) e série
 * "inativo" do mesmo gráfico (vermelho). Separadas das cores globais para
 * não recolorir as barras de composição do modo grupo (COR_INATIVO âmbar).
 */
export const COR_ATIVO_IRREGULAR = "#eab308"; // yellow-500
export const COR_INATIVO_ALERTA = "#dc2626"; // red-600

/** Barras do gráfico de composição do grupo (EvolucaoSemanal). */
export const ATIVOS_COR = COR_ATIVO;
export const INATIVOS_COR = COR_INATIVO;
