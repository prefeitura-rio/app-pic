"""Testes da regra do filtro Pilotos (constantes compartilhadas v1/v2)."""

from src.pic.domain.constants import PILOTO_REGIOES, aplicar_filtro_piloto


def test_piloto_regioes_raw_sem_acento():
    # Grafia conferida no BQ dev em 2026-11-17 — a base grava "14ª Iraja"
    # SEM acento; escrever "Irajá" retornaria vazio silenciosamente.
    assert PILOTO_REGIOES == ("13ª Meier", "14ª Iraja")


def test_aplicar_filtro_piloto_injeta_regioes():
    filtros: dict[str, object] = {"bairro": ["Tijuca"]}
    aplicar_filtro_piloto(filtros, "meier_iraja")
    assert filtros["regiao_administrativa"] == ["13ª Meier", "14ª Iraja"]


def test_aplicar_filtro_piloto_sobrescreve_ra_manual():
    filtros: dict[str, object] = {"regiao_administrativa": ["15ª Madureira"]}
    aplicar_filtro_piloto(filtros, "meier_iraja")
    assert filtros["regiao_administrativa"] == ["13ª Meier", "14ª Iraja"]


def test_aplicar_filtro_piloto_sem_valor_nao_altera():
    filtros: dict[str, object] = {"regiao_administrativa": ["15ª Madureira"]}
    aplicar_filtro_piloto(filtros, None)
    assert filtros["regiao_administrativa"] == ["15ª Madureira"]
