"""
Utilitários para manipulação e normalização de texto.
"""
import unicodedata


class TextNormalizer:
    """
    Classe para normalização de texto com cache.

    Normaliza strings removendo acentos e convertendo para lowercase.
    Mantém cache em memória para otimização de strings repetidas.
    """

    _cache: dict[str, str] = {}
    MAX_CACHE_SIZE = 10000

    @classmethod
    def normalize(cls, text: str) -> str:
        """
        Normaliza string removendo acentos e convertendo para lowercase.

        Utiliza cache em memória para evitar recalcular strings repetidas.
        Comum em colunas com valores categóricos (ex: "Criança" aparece milhares de vezes).

        Examples:
            >>> TextNormalizer.normalize('Criança')
            'crianca'
            >>> TextNormalizer.normalize('São Paulo')
            'sao paulo'
            >>> TextNormalizer.normalize('GESTANTE')
            'gestante'

        Args:
            text: String a ser normalizada

        Returns:
            String normalizada (sem acentos, lowercase)
        """
        if text in cls._cache:
            return cls._cache[text]

        # Normaliza para NFD (decompõe caracteres acentuados)
        nfd = unicodedata.normalize("NFD", text)
        # Remove marcas diacríticas (acentos) - categoria Mn (Mark, Nonspacing)
        without_accents = "".join(
            char for char in nfd if unicodedata.category(char) != "Mn"
        )
        # Converte para lowercase
        result = without_accents.lower()

        # Cache limitado para evitar memory leak
        if len(cls._cache) < cls.MAX_CACHE_SIZE:
            cls._cache[text] = result

        return result

    @classmethod
    def clear_cache(cls) -> int:
        """
        Limpa cache de normalização.

        Útil para liberar memória em ambientes de longa execução.

        Returns:
            Número de entradas removidas do cache
        """
        size = len(cls._cache)
        cls._cache.clear()
        return size

    @classmethod
    def cache_stats(cls) -> dict[str, int]:
        """
        Retorna estatísticas do cache.

        Returns:
            Dict com 'size' (tamanho atual) e 'max_size' (limite)
        """
        return {
            "size": len(cls._cache),
            "max_size": cls.MAX_CACHE_SIZE,
        }


# Função de conveniência para compatibilidade
def normalize_string(text: str) -> str:
    """
    Wrapper de conveniência para TextNormalizer.normalize().

    Mantido para compatibilidade com código existente.
    """
    return TextNormalizer.normalize(text)
