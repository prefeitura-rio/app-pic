GEOSPATIAL_FILTER_COLUMN_MAP: dict[str, str] = {
    "tipo_camada": "tipo_camada",
    "categoria": "categoria",
    "regional": "regional",
    "bairro": "bairro",
    "regiao_administrativa": "regiao_administrativa",
    "subprefeitura": "subprefeitura",
    "nome": "nome",
}

GEOSPATIAL_FILTER_OPTIONS_CONFIG: dict[str, dict[str, str]] = {
    "tipos_camada": {"column": "tipo_camada"},
    "categorias": {"column": "categoria"},
    "regionais": {"column": "regional"},
    "bairros": {"column": "bairro"},
    "regioes_administrativas": {"column": "regiao_administrativa"},
    "subprefeituras": {"column": "subprefeitura"},
    "nomes": {"column": "nome"},
}
