
DASHBOARD_FILTER_OPTIONS_CONFIG: dict[str, dict[str, str]] = {
    "grupos": {"column": "pic_grupo"},
    "cohorts": {"column": "pic_cohort"},
    "status_list": {"column": "pic_status"},
    "subprefeituras": {"column": "subprefeitura"},
    "regioes_administrativas": {"column": "regiao_administrativa"},
    "bairros": {"column": "bairro"},
    "cres": {"column": "id_cre", "label_column": "nome_cre"},
    "aps": {"column": "id_ap", "label_column": "nome_ap"},
    "cas_list": {"column": "id_cas", "label_column": "nome_cas"},
    "cras": {"column": "id_cras", "label_column": "nome_cras"},
    "escolas": {"column": "id_escola", "label_column": "nome_escola"},
    "clinicas": {"column": "id_clinica_familia", "label_column": "nome_clinica_familia"},
    "equipes_familia": {"column": "id_equipe_familia", "label_column": "nome_equipe_familia"},
}

MESES_LABELS: dict[str, str] = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}
