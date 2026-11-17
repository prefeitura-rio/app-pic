"""Tests do filtro de protocolos por secretaria (`protocol_secretarias_filter`).

A RLS do data-proxy recorta **unidade**, não secretaria — o filtro de
``protocolo_secretaria`` nas consultas de protocolo é responsabilidade do
backend. O filtro usa SEMPRE a lista ``secretarias_acesso``, nunca o shim
``secretaria_acesso`` (que devolve ``"TODOS"`` — permissivo — para 2 de 3).
"""

from src.core.security.permissions_models import UserPermissions


def _perms(**kwargs):
    return UserPermissions(cpf="1", **kwargs)


def test_super_admin_sem_filtro():
    assert _perms(is_super_admin=True, secretarias_acesso=[]).protocol_secretarias_filter() is None


def test_tres_secretarias_sem_filtro():
    assert (
        _perms(secretarias_acesso=["SME", "SMS", "SMAS"]).protocol_secretarias_filter()
        is None
    )


def test_uma_secretaria_vira_lista():
    assert _perms(secretarias_acesso=["SMAS"]).protocol_secretarias_filter() == ["SMAS"]


def test_duas_secretarias_viram_lista_e_nao_none():
    # O shim devolveria "TODOS" aqui — o filtro não pode herdar isso.
    filtro = _perms(secretarias_acesso=["SME", "SMAS"]).protocol_secretarias_filter()
    assert filtro == ["SME", "SMAS"]


def test_sem_secretarias_vira_lista_vazia():
    assert _perms(secretarias_acesso=[]).protocol_secretarias_filter() == []
