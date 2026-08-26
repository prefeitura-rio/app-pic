from src.pic.infrastructure.mappers.participant_mapper import (
    row_to_list_item,
    row_to_participante,
)
from src.pic.infrastructure.repositories.helpers.participant_query_mapping import (
    LIST_ITEM_FIELDS,
)


def test_row_to_list_item_keeps_only_the_envelope_fields():
    row = {
        "id_familia": "02159929700",
        "id_membro_familia": "00325420412",
        "nome": "ANA JULIA DE SOUZA DA SILVA",
        "cpf": "23131727756",
        "grupo": "Criança",
        "bairro": "Engenho da Rainha",
        "idade": 3,
        "status": "Ativo",
        "situacao": "Atenção",
        "total_fracao": "7/7",
        "assistencia_fracao": "3/3",
        "educacao_fracao": "0/0",
        "saude_fracao": "4/4",
        "total_protocolos_irregular": 0,
        "raca": "branca",
        # Extra columns must be discarded.
        "id_cras": "1",
        "latitude": -22.8,
        "protocolo_listagem": [{"id": "x"}],
    }
    item = row_to_list_item(row)

    assert set(item.model_dump().keys()) == set(LIST_ITEM_FIELDS)
    assert item.id_membro_familia == "00325420412"
    assert item.idade == 3
    assert item.total_protocolos_irregular == 0


def test_row_to_list_item_preserves_nulls():
    item = row_to_list_item({"id_membro_familia": "1", "cpf": None})
    assert item.cpf is None


def test_row_to_participante_maps_nested_json_columns():
    row = {
        "id_familia": "02159929700",
        "id_membro_familia": "00325420412",
        "nome": "ANA JULIA DE SOUZA DA SILVA",
        "cpf": "23131727756",
        "grupo": "Criança",
        "idade": 3,
        "raca": "branca",
        "nascimento_data": "2022-09-22",
        "endereco": "RUA  MOREIA 6",
        "complemento": None,
        "bairro": "Engenho da Rainha",
        "endereco_sms": {
            "endereco": "RUA PRACA",
            "complemento": None,
            "bairro": "ENGENHO DA RAINHA",
        },
        "cohort": "2025-09-01",
        "status": "Ativo",
        "situacao": "Atenção",
        "latitude": -22.867801,
        "longitude": -43.2931916,
        "total_protocolos": 7,
        "total_protocolos_irregular": 0,
        "total_fracao": "7/7",
        "saude_fracao": "4/4",
        "protocolo_listagem": [
            {
                "id": "sms_visitas_domiciliares_infantil",
                "secretaria": "SMS",
                "descricao": "Criança com 2 visitas domiciliares anuais",
                "status": "regular",
                "irregular_indicador": False,
                "protocolo_status_label": "Regular",
            }
        ],
        # RLS unit columns must be ignored by the domain model.
        "id_cras": "03",
        "id_escola": "e1",
    }

    participante = row_to_participante(row)

    assert participante.id_membro_familia == "00325420412"
    assert participante.nascimento_data.isoformat() == "2022-09-22"
    assert participante.cohort.isoformat() == "2025-09-01"
    assert participante.endereco_sms is not None
    assert participante.endereco_sms.bairro == "ENGENHO DA RAINHA"
    assert participante.complemento is None
    assert len(participante.protocolo_listagem) == 1
    protocolo = participante.protocolo_listagem[0]
    assert protocolo.id == "sms_visitas_domiciliares_infantil"
    assert protocolo.irregular_indicador is False
    assert protocolo.protocolo_motivo is None
    # `protocolo_motivo` is dropped from serialization when None.
    assert "protocolo_motivo" not in protocolo.model_dump()


def test_row_to_participante_handles_missing_nested_columns():
    participante = row_to_participante(
        {"id_membro_familia": "1", "endereco_sms": None, "protocolo_listagem": None}
    )
    assert participante.endereco_sms is None
    assert participante.protocolo_listagem is None
