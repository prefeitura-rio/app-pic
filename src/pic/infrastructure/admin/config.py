
USER_FILTER_OPTIONS_CONFIG: dict[str, dict[str, str]] = {
    "ocupacoes": {"column": "ocupacao"},
    "secretarias": {"column": "secretaria"},
    "status_ativo": {"column": "active"},
    "permissions": {"column": "permission"},
}
# NOTE: secretarias_acesso_list is NOT auto-computed here since
# `secretarias_acesso` is a list[str] column (not scalar) - its options are
# a fixed, known set (SME/SMS/SMAS) built directly in ListUsersUseCase.
