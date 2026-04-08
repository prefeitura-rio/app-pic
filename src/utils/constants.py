"""
Constantes globais do sistema.
Centraliza valores mágicos e configurações compartilhadas.
"""

# ============================================================================
# SECRETARIA ACCESS
# ============================================================================

# Valores válidos de secretaria_acesso
SECRETARIA_TODOS = "TODOS"
SECRETARIA_NULL = "NULL"
SECRETARIA_SME = "SME"
SECRETARIA_SMS = "SMS"
SECRETARIA_SMAS = "SMAS"

# Mapeamento de código para nome amigável
SECRETARIA_LABELS = {
    SECRETARIA_NULL: "🚫 Sem Acesso a Protocolos",
    SECRETARIA_TODOS: "🌐 Todos os Protocolos (TODOS)",
    SECRETARIA_SME: "📚 Apenas Educação (SME)",
    SECRETARIA_SMS: "🏥 Apenas Saúde (SMS)",
    SECRETARIA_SMAS: "🤝 Apenas Assistência Social (SMAS)",
}

# Mapeamento de secretaria_acesso para prefixo de coluna
SECRETARIA_COLUMN_PREFIX = {
    SECRETARIA_SME: "educacao",
    SECRETARIA_SMS: "saude",
    SECRETARIA_SMAS: "assistencia",
}

# Equipamentos permitidos por secretaria
SECRETARIA_EQUIPMENT = {
    SECRETARIA_SME: ["id_cre_list", "id_escola_list"],
    SECRETARIA_SMS: ["id_ap_list", "id_clinica_familia_list", "id_equipe_familia_list"],
    SECRETARIA_SMAS: ["id_cas_list", "id_cras_list"],
}

# Equipamentos legíveis por secretaria (para mensagens de erro)
SECRETARIA_EQUIPMENT_LABELS = {
    SECRETARIA_SME: "CREs e Escolas",
    SECRETARIA_SMS: "APs, Clínicas e Equipes de Saúde",
    SECRETARIA_SMAS: "CAS e CRAS",
}
