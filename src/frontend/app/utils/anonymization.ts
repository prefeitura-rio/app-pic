export const MASKED_CPF = "***********";
export const MASKED_NAME = "***";

export type AnonymizableField =
	| "cpf"
	| "name"
	| "id_familia"
	| "id_membro_familia"
	| "nascimento_data";

export function maskCpf(): string {
	return MASKED_CPF;
}

export function maskName(): string {
	return MASKED_NAME;
}

export function maskId(value: string): string {
	return "*".repeat(value.length);
}

export function maskDate(value: string): string {
	return value.replace(/\d/g, "*");
}

const FIELD_PATTERNS: Record<AnonymizableField, (value: string) => string> = {
	cpf: maskCpf,
	name: maskName,
	id_familia: maskId,
	id_membro_familia: maskId,
	nascimento_data: maskDate,
};

export function maskField(value: string, fieldType: AnonymizableField): string {
	const masker = FIELD_PATTERNS[fieldType];
	return masker ? masker(value) : value;
}
