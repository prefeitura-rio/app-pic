from datetime import date

from src.pic.domain.models.endereco import EnderecoSMS
from src.pic.domain.models.participante import Participante, ParticipanteListItem


def test_list_item_create_minimal():
    item = ParticipanteListItem(nome="Teste")
    assert item.nome == "Teste"
    assert item.cpf is None
    assert item.grupo is None


def test_list_item_create_full(sample_participante_list_item):
    assert sample_participante_list_item.nome == "Maria Silva"
    assert sample_participante_list_item.cpf == "12345678900"
    assert sample_participante_list_item.id_familia == "FAM123"
    assert sample_participante_list_item.id_membro_familia == "MEM456"


def test_list_item_serialization():
    item = ParticipanteListItem(nome="Maria", cpf="123", idade=2)
    data = item.model_dump()
    assert data["nome"] == "Maria"
    assert data["cpf"] == "123"
    assert data["idade"] == 2
    assert data["id_familia"] is None
    assert data["id_membro_familia"] is None


def test_list_item_extra_fields_ignored():
    item = ParticipanteListItem(
        **{"nome": "Joao", "extra_field": "should_be_ignored"}
    )
    assert item.nome == "Joao"
    assert not hasattr(item, "extra_field")


def test_list_item_total_irregular():
    item = ParticipanteListItem(nome="Test", total_protocolos_irregular=5)
    assert item.total_protocolos_irregular == 5
    data = item.model_dump()
    assert data["total_protocolos_irregular"] == 5


def test_list_item_total_irregular_default():
    item = ParticipanteListItem(nome="Test")
    assert item.total_protocolos_irregular is None


def test_participante_detail_minimal():
    p = Participante(nome="Maria")
    assert p.nome == "Maria"
    assert p.cpf is None
    assert p.endereco_sms is None
    assert p.protocolo_listagem is None


def test_participante_detail_full():
    p = Participante(
        id_familia="FAM1",
        id_membro_familia="MEM1",
        nome="Maria Silva",
        cpf="12345678900",
        grupo="crianca_bf_0_3",
        idade=2,
        nascimento_data=date(2023, 3, 15),
        endereco="Rua A",
        complemento="Apto 1",
        bairro="Centro",
        endereco_sms=EnderecoSMS(
            endereco="Rua B", complemento="Apto 2", bairro="Copacabana"
        ),
        telefone_1_ddd="21",
        telefone_1_numero="999999999",
        nome_cre="1ª CRE",
        nome_escola="Escola X",
        source_escola="rmi",
        nome_cas="CAS Centro",
        nome_cras="CRAS Sul",
        source_cras="rmi",
        nome_clinica_familia="Clinica A",
        source_clinica_familia="geo",
        nome_equipe_familia="Equipe B",
        source_equipe_familia="geo",
        equipe_familia="MEDICOS:\nDr. Joao\n\nENFERMEIROS:\nEnf. Maria",
        has_bolsa_familia=True,
        has_cartao_pic=False,
        cohort=date(2024, 1, 1),
        status="ativo",
        situacao="regular",
        latitude=-22.9,
        longitude=-43.2,
        total_protocolos=5,
        total_protocolos_regular=3,
        total_protocolos_irregular=1,
        total_protocolos_atencao=1,
        total_fracao="3/5",
        assistencia_protocolos_total=2,
        assistencia_protocolos_regular=1,
        assistencia_fracao="1/2",
        educacao_protocolos_total=1,
        educacao_protocolos_regular=1,
        educacao_fracao="1/1",
        saude_protocolos_total=2,
        saude_protocolos_regular=1,
        saude_fracao="1/2",
    )
    assert p.nome == "Maria Silva"
    assert p.endereco_sms.endereco == "Rua B"
    assert p.total_protocolos == 5
    assert p.protocolo_listagem is None


def test_participante_parses_endereco_sms_json_string():
    raw_json = '{"endereco": "Rua X", "complemento": "Apto Y", "bairro": "Lapa"}'
    p = Participante(
        nome="Joao",
        endereco_sms=raw_json,
    )
    assert isinstance(p.endereco_sms, EnderecoSMS)
    assert p.endereco_sms.endereco == "Rua X"
    assert p.endereco_sms.complemento == "Apto Y"
    assert p.endereco_sms.bairro == "Lapa"


def test_participante_invalid_endereco_sms_json():
    p = Participante(nome="Joao", endereco_sms="not valid json")
    assert p.endereco_sms is None
