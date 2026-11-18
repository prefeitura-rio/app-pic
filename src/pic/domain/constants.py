"""Constantes de regra de negócio compartilhadas entre endpoints (v1 e v2)."""

# Piloto do programa (filtro "Pilotos" da Visão Geral e da Busca Individual —
# opção "Apenas Piloto Meier-Iraja"). Valores RAW da coluna
# ``regiao_administrativa`` conferidos no BQ dev em 2026-11-17: a base grava
# "14ª Iraja" SEM acento (grafia com "Irajá" retornaria vazio). Fica no
# domínio porque tanto o dashboard (v2) quanto a busca individual (v1 + v2)
# precisam da mesma lista.
PILOTO_REGIOES: tuple[str, ...] = ("13ª Meier", "14ª Iraja")


def aplicar_filtro_piloto(
    column_filters: dict[str, object], piloto: object | None
) -> None:
    """Sobrescreve ``column_filters["regiao_administrativa"]`` com as regiões
    do piloto quando o filtro está ativo.

    Regra única: o piloto **vence** a seleção manual de RA (a UI mantém
    exclusão mútua entre os dois, então não há combinação a resolver).
    """
    if piloto:
        column_filters["regiao_administrativa"] = list(PILOTO_REGIOES)
