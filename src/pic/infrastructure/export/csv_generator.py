import polars as pl

from src.pic.infrastructure.export.config import _CHUNK_ROWS, _DELIMITER

_CSV_HEADERS = [
    "nome",
    "cpf",
    "nascimento_data",
    "idade",
    "raca",
    "endereco_smas_endereco",
    "endereco_smas_complemento",
    "endereco_smas_bairro",
    "endereco_sms_endereco",
    "endereco_sms_complemento",
    "endereco_sms_bairro",
    "telefone_1_ddd",
    "telefone_1_numero",
    "telefone_2_ddd",
    "telefone_2_numero",
    "subprefeitura",
    "regiao_administrativa",
    "grupo",
    "cohort",
    "has_bolsa_familia",
    "has_cartao_pic",
    "status",
    "status_inativo_motivo",
    "situacao",
    "total_protocolos",
    "total_protocolos_regular",
    "total_protocolos_irregular",
    "total_protocolos_atencao",
    "total_fracao",
    "assistencia_protocolos_total",
    "assistencia_protocolos_regular",
    "assistencia_protocolos_irregular",
    "assistencia_protocolos_atencao",
    "assistencia_fracao",
    "educacao_protocolos_total",
    "educacao_protocolos_regular",
    "educacao_protocolos_irregular",
    "educacao_protocolos_atencao",
    "educacao_fracao",
    "saude_protocolos_total",
    "saude_protocolos_regular",
    "saude_protocolos_irregular",
    "saude_protocolos_atencao",
    "saude_fracao",
    "id_cras",
    "nome_cras",
    "source_cras",
    "id_cas",
    "nome_cas",
    "id_escola",
    "nome_escola",
    "source_escola",
    "id_cre",
    "nome_cre",
    "id_ap",
    "nome_ap",
    "id_clinica_familia",
    "nome_clinica_familia",
    "source_clinica_familia",
    "has_cobertura_clinica_familia",
    "id_equipe_familia",
    "nome_equipe_familia",
    "source_equipe_familia",
    "has_cobertura_equipe_familia",
    "equipe_familia",
    "protocolo_id",
    "protocolo_secretaria",
    "protocolo_descricao",
    "protocolo_status",
    "protocolo_irregular_indicador",
    "protocolo_status_label",
]


def _escape_csv(value: object) -> str:
    if value is None:
        return '""'
    s = str(value).replace("\r", "").replace("\n", " ").replace('"', '""')
    return f'"{s}"'


def _df_to_csv_stream(df: pl.DataFrame):
    DELIM = _DELIMITER

    header_line = DELIM.join(_CSV_HEADERS)
    yield ("\uFEFF" + header_line + "\n").encode("utf-8")

    rows_buffer: list[str] = []

    for row in df.iter_rows(named=True):
        endereco_sms = row.get("endereco_sms") or {}
        if isinstance(endereco_sms, dict):
            sms_end = endereco_sms.get("endereco")
            sms_comp = endereco_sms.get("complemento")
            sms_bairro = endereco_sms.get("bairro")
        else:
            sms_end = sms_comp = sms_bairro = None

        protocolos = row.get("protocolo_listagem") or []

        participant_cells = [
            _escape_csv(row.get("nome")),
            _escape_csv(row.get("cpf")),
            _escape_csv(row.get("nascimento_data")),
            _escape_csv(row.get("idade")),
            _escape_csv(row.get("raca")),
            _escape_csv(row.get("endereco")),
            _escape_csv(row.get("complemento")),
            _escape_csv(row.get("bairro")),
            _escape_csv(sms_end),
            _escape_csv(sms_comp),
            _escape_csv(sms_bairro),
            _escape_csv(row.get("telefone_1_ddd")),
            _escape_csv(row.get("telefone_1_numero")),
            _escape_csv(row.get("telefone_2_ddd")),
            _escape_csv(row.get("telefone_2_numero")),
            _escape_csv(row.get("subprefeitura")),
            _escape_csv(row.get("regiao_administrativa")),
            _escape_csv(row.get("grupo")),
            _escape_csv(row.get("cohort")),
            _escape_csv(row.get("has_bolsa_familia")),
            _escape_csv(row.get("has_cartao_pic")),
            _escape_csv(row.get("status")),
            _escape_csv(row.get("status_inativo_motivo")),
            _escape_csv(row.get("situacao")),
            _escape_csv(row.get("total_protocolos")),
            _escape_csv(row.get("total_protocolos_regular")),
            _escape_csv(row.get("total_protocolos_irregular")),
            _escape_csv(row.get("total_protocolos_atencao")),
            _escape_csv(row.get("total_fracao")),
            _escape_csv(row.get("assistencia_protocolos_total")),
            _escape_csv(row.get("assistencia_protocolos_regular")),
            _escape_csv(row.get("assistencia_protocolos_irregular")),
            _escape_csv(row.get("assistencia_protocolos_atencao")),
            _escape_csv(row.get("assistencia_fracao")),
            _escape_csv(row.get("educacao_protocolos_total")),
            _escape_csv(row.get("educacao_protocolos_regular")),
            _escape_csv(row.get("educacao_protocolos_irregular")),
            _escape_csv(row.get("educacao_protocolos_atencao")),
            _escape_csv(row.get("educacao_fracao")),
            _escape_csv(row.get("saude_protocolos_total")),
            _escape_csv(row.get("saude_protocolos_regular")),
            _escape_csv(row.get("saude_protocolos_irregular")),
            _escape_csv(row.get("saude_protocolos_atencao")),
            _escape_csv(row.get("saude_fracao")),
            _escape_csv(row.get("id_cras")),
            _escape_csv(row.get("nome_cras")),
            _escape_csv(row.get("source_cras")),
            _escape_csv(row.get("id_cas")),
            _escape_csv(row.get("nome_cas")),
            _escape_csv(row.get("id_escola")),
            _escape_csv(row.get("nome_escola")),
            _escape_csv(row.get("source_escola")),
            _escape_csv(row.get("id_cre")),
            _escape_csv(row.get("nome_cre")),
            _escape_csv(row.get("id_ap")),
            _escape_csv(row.get("nome_ap")),
            _escape_csv(row.get("id_clinica_familia")),
            _escape_csv(row.get("nome_clinica_familia")),
            _escape_csv(row.get("source_clinica_familia")),
            _escape_csv(row.get("has_cobertura_clinica_familia")),
            _escape_csv(row.get("id_equipe_familia")),
            _escape_csv(row.get("nome_equipe_familia")),
            _escape_csv(row.get("source_equipe_familia")),
            _escape_csv(row.get("has_cobertura_equipe_familia")),
            _escape_csv(row.get("equipe_familia")),
        ]

        if protocolos:
            for prot in protocolos:
                if not isinstance(prot, dict):
                    continue
                protocol_cells = [
                    _escape_csv(prot.get("id")),
                    _escape_csv(prot.get("secretaria")),
                    _escape_csv(prot.get("descricao")),
                    _escape_csv(prot.get("status")),
                    _escape_csv(prot.get("irregular_indicador")),
                    _escape_csv(prot.get("protocolo_status_label")),
                ]
                rows_buffer.append(DELIM.join(participant_cells + protocol_cells))
        else:
            empty_protocol = ['""'] * 6
            rows_buffer.append(DELIM.join(participant_cells + empty_protocol))

        if len(rows_buffer) >= _CHUNK_ROWS:
            yield ("\n".join(rows_buffer) + "\n").encode("utf-8")
            rows_buffer = []

    if rows_buffer:
        yield ("\n".join(rows_buffer) + "\n").encode("utf-8")
