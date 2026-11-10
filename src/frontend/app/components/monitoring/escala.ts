/**
 * Escala oficial de cores da regularidade (0% → 100%), opaca (alpha FF):
 * 0% é o vermelho #BE2A3E e 100% é o verde #22763F, passando por tons de
 * amarelo. A taxa é mapeada por índice (round(taxa * (N - 1))).
 *
 * Compartilhada entre o mapa (MonitoramentoTab) e os cards do
 * Acompanhamento semanal (EvolucaoSemanal).
 */
export const REGULARIDADE_SCALE = [
	"#BE2A3E", "#C02E3F", "#C2323F", "#C53540", "#C73941",
	"#C93C41", "#CB3F42", "#CD4242", "#CF4643", "#D24944",
	"#D44C44", "#D64F45", "#D85245", "#DA5546", "#DD5847",
	"#DF5B47", "#E15E48", "#E36148", "#E46449", "#E56749",
	"#E76A49", "#E86D49", "#E9704A", "#EB724A", "#EC754A",
	"#EE784B", "#EF7B4B", "#F07E4B", "#F1814C", "#F3844C",
	"#F4874C", "#F5894C", "#F78C4D", "#F88F4D", "#F8934E",
	"#F89750", "#F89C51", "#F8A053", "#F8A454", "#F8A856",
	"#F8AC57", "#F7B059", "#F7B45A", "#F7B85C", "#F6BC5D",
	"#F6C05F", "#F6C361", "#F5C762", "#F5CB64", "#F4CF65",
	"#F1D066", "#EBCF65", "#E5CE65", "#DFCC65", "#DACB64",
	"#D4C964", "#CEC864", "#C8C763", "#C2C563", "#BCC463",
	"#B6C262", "#B0C162", "#A9BF61", "#A3BE61", "#9DBC61",
	"#96BB60", "#90B960", "#8CB760", "#88B560", "#84B460",
	"#81B260", "#7DB060", "#79AE60", "#75AC60", "#71AA60",
	"#6CA960", "#68A760", "#64A560", "#60A35F", "#5BA15F",
	"#57A05F", "#529E5F", "#4D9C5F", "#4A9A5E", "#47985C",
	"#45955A", "#439358", "#409156", "#3E8E54", "#3C8C52",
	"#398A50", "#37884E", "#34864C", "#32834A", "#2F8148",
	"#2D7F47", "#2A7D45", "#277A43", "#257841", "#22763F",
];

/**
 * Cor da taxa como hex CSS na escala oficial; null/undefined → cinza
 * "#808080" (sem dados). Usada tanto no mapa quanto nos cards de detalhe.
 */
export function taxaToHex(taxa: number | null | undefined): string {
	if (taxa === null || taxa === undefined) {
		return "#808080";
	}
	const t = Math.min(100, Math.max(0, taxa)) / 100; // 1 = 100% regular
	const index = Math.round(t * (REGULARIDADE_SCALE.length - 1));
	return REGULARIDADE_SCALE[index];
}
