"""
Admin endpoints para gerenciamento de governança de dados.

Permite admins criar/editar/deletar permissões de CPFs, controlando
quais IDs (CRAS, escolas, CRE, etc) cada usuário pode acessar.

REGRAS:
- Super admin: Acesso total, pode gerenciar qualquer usuário
- Admin segmentado: Só pode atribuir IDs que ele mesmo possui
- Auditoria completa: created_by, updated_by em todas as operações
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict
import pandas as pd
from datetime import datetime, timezone

from src.core.security.jwt import CurrentUserPermissions
from src.core.security.permissions_models import IdWithName, UserPermissions
from src.config import env
from src.utils.log import logger
from src.utils.data_manager import DataManager
from src.utils.bigquery import execute_query
from src.api.v1.queries import GOVERNANCE_TABLE_QUERY, PARTICIPANTS_TABLE_QUERY
from src.api.v1.schemas import PaginatedResponse, PaginationParams
from pydantic import BaseModel, Field

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


# ========================================================================
# HELPERS
# ========================================================================


def refresh_governance_cache():
    """
    Force refresh da governance cache após modificações na tabela.

    Usa bypass_cache=True para forçar query no BigQuery e atualizar cache.
    """
    DataManager.get_dataset(GOVERNANCE_TABLE_QUERY, bypass_cache=True)
    logger.info("🔄 Governance cache refreshed")


# ========================================================================
# SCHEMAS
# ========================================================================


class AvailableIds(BaseModel):
    """IDs disponíveis para atribuição (extraídos da tabela de participantes)"""

    cras: List[IdWithName] = Field(default_factory=list)
    escolas: List[IdWithName] = Field(default_factory=list)
    cres: List[IdWithName] = Field(default_factory=list)
    caps: List[IdWithName] = Field(default_factory=list)
    cas: List[IdWithName] = Field(default_factory=list)
    clinicas: List[IdWithName] = Field(default_factory=list)


class UserAccessRecord(BaseModel):
    """Registro de acesso de um usuário (usado em GET /users)"""

    cpf: str
    nome: Optional[str] = None
    ocupacao: Optional[str] = None
    secretaria: Optional[str] = None
    is_admin: bool = False
    is_super_admin: bool = False
    permission: Optional[str] = None

    id_cras_list: Optional[List[IdWithName]] = None
    id_escola_list: Optional[List[IdWithName]] = None
    id_cre_list: Optional[List[IdWithName]] = None
    id_cap_list: Optional[List[IdWithName]] = None
    id_cas_list: Optional[List[IdWithName]] = None
    id_clinica_familia_list: Optional[List[IdWithName]] = None

    active: bool = True
    notes: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class UpsertUserRequest(BaseModel):
    """Request para criar ou atualizar usuário (UPSERT)"""

    nome: Optional[str] = None
    ocupacao: Optional[str] = None
    secretaria: Optional[str] = None
    is_admin: bool = False
    is_super_admin: bool = False  # Apenas super admins podem definir isso

    id_cras_list: Optional[List[IdWithName]] = None
    id_escola_list: Optional[List[IdWithName]] = None
    id_cre_list: Optional[List[IdWithName]] = None
    id_cap_list: Optional[List[IdWithName]] = None
    id_cas_list: Optional[List[IdWithName]] = None
    id_clinica_familia_list: Optional[List[IdWithName]] = None

    notes: Optional[str] = None
    active: bool = True
    is_update: bool = False  # Se True, indica que é uma atualização intencional




# ========================================================================
# HELPERS
# ========================================================================


def require_admin(permissions: UserPermissions):
    """Valida que usuário é admin ou super admin"""
    if not permissions.is_admin and not permissions.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: apenas admins podem gerenciar usuários",
        )


def calculate_permission(is_admin: bool, is_super_admin: bool) -> str:
    """
    Calcula o valor da coluna permission baseado em is_admin e is_super_admin.

    Returns:
        "super_admin" se is_super_admin=True
        "admin" se is_admin=True e is_super_admin=False
        "user" caso contrário
    """
    if is_super_admin:
        return "super_admin"
    elif is_admin:
        return "admin"
    else:
        return "user"


def validate_segmented_admin_can_manage(
    admin_permissions: UserPermissions, target_ids: Dict[str, List[IdWithName]]
):
    """
    Valida que admin segmentado só está atribuindo IDs que ele mesmo possui.

    Super admins podem atribuir qualquer ID.
    Admins segmentados só podem atribuir subset de seus IDs.
    """
    if admin_permissions.is_super_admin:
        return  # Super admin pode tudo

    # Validar cada tipo de ID
    for id_type in [
        "id_cras",
        "id_escola",
        "id_cre",
        "id_cap",
        "id_cas",
        "id_clinica_familia",
    ]:
        list_key = f"{id_type}_list"
        target_list = target_ids.get(list_key)

        if not target_list:
            continue  # Nenhum ID desse tipo sendo atribuído

        # IDs que o admin possui
        admin_ids = set(admin_permissions.get_filter_ids(id_type))

        if not admin_ids:
            raise HTTPException(
                status_code=403,
                detail=f"Você não tem permissão para atribuir {id_type} (você não possui nenhum)",
            )

        # IDs que estão sendo atribuídos
        target_ids_set = {item.id for item in target_list}

        # Verificar se todos os IDs alvo estão no subset do admin
        unauthorized_ids = target_ids_set - admin_ids

        if unauthorized_ids:
            raise HTTPException(
                status_code=403,
                detail=f"Você não pode atribuir estes {id_type}: {unauthorized_ids}",
            )


def _extract_unique_ids(
    df: pd.DataFrame, id_col: str, nome_col: str
) -> List[IdWithName]:
    """Helper para extrair IDs únicos com nomes de um DataFrame"""
    if df.empty or id_col not in df.columns:
        return []

    # Se nome_col não existe ou é igual a id_col, usar id_col para ambos
    if nome_col not in df.columns or id_col == nome_col:
        unique_df = df[[id_col]].dropna().drop_duplicates().sort_values(id_col)
        return [
            IdWithName(id=str(row[id_col]), nome=str(row[id_col]))
            for _, row in unique_df.iterrows()
        ]

    # Caso normal: colunas diferentes
    unique_df = (
        df[[id_col, nome_col]]
        .dropna()
        .drop_duplicates(subset=[id_col])
        .sort_values(nome_col)
    )

    return [
        IdWithName(id=str(row[id_col]), nome=str(row[nome_col]))
        for _, row in unique_df.iterrows()
    ]


def _convert_id_list_to_bq_struct(id_list: Optional[List[IdWithName]]) -> str:
    """
    Converte lista de IdWithName para formato BigQuery ARRAY<STRUCT>.

    Args:
        id_list: Lista de IdWithName ou None

    Returns:
        String SQL com ARRAY<STRUCT> ou "NULL"

    Example:
        >>> ids = [IdWithName(id="CRAS_001", nome="CRAS Centro")]
        >>> _convert_id_list_to_bq_struct(ids)
        "[STRUCT('CRAS_001' AS id, 'CRAS Centro' AS nome)]"
    """
    if not id_list:
        return "NULL"

    structs = []
    for item in id_list:
        # Escapar aspas simples no nome (SQL injection prevention)
        nome_escaped = item.nome.replace("'", "\\'")
        id_escaped = item.id.replace("'", "\\'")
        structs.append(f"STRUCT('{id_escaped}' AS id, '{nome_escaped}' AS nome)")

    return f"[{', '.join(structs)}]"


# ========================================================================
# ENDPOINTS
# ========================================================================


@router.get("/available-ids", response_model=AvailableIds)
async def get_available_ids(permissions: CurrentUserPermissions):
    """
    Retorna todos os IDs disponíveis para atribuição.

    Busca IDs únicos da tabela endpoint_participante para facilitar
    atribuição de permissões pelos admins.

    OTIMIZAÇÃO: Reutiliza cache da tabela de participantes.
    """
    require_admin(permissions)

    logger.info(f"Admin {permissions.cpf} buscando IDs disponíveis")

    # OTIMIZAÇÃO: Reutiliza a mesma query que /participants (aproveita cache existente!)
    try:
        # Buscar dados de participantes (usa cache compartilhado)
        df, _ = DataManager.get_dataset(PARTICIPANTS_TABLE_QUERY)

        # Extrair IDs únicos com nomes
        available_ids = AvailableIds(
            cras=_extract_unique_ids(df, "id_cras", "nome_cras"),
            escolas=_extract_unique_ids(df, "id_escola", "nome_escola"),
            cres=_extract_unique_ids(
                df, "id_cre", "id_cre"
            ),  # CRE não tem nome, usa id_cre como nome
            caps=_extract_unique_ids(df, "id_cap", "nome_cap"),
            cas=_extract_unique_ids(df, "id_cas", "nome_cas"),
            clinicas=_extract_unique_ids(
                df, "id_clinica_familia", "nome_clinica_familia"
            ),
        )

        logger.info(
            f"Retornando {len(available_ids.cras)} CRAS, "
            f"{len(available_ids.escolas)} escolas, "
            f"{len(available_ids.cres)} CREs, "
            f"{len(available_ids.caps)} CAPs, "
            f"{len(available_ids.cas)} CAS, "
            f"{len(available_ids.clinicas)} clínicas disponíveis"
        )

        return available_ids

    except Exception as e:
        logger.error(f"Erro ao buscar IDs disponíveis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me", response_model=UserAccessRecord)
async def get_current_user(permissions: CurrentUserPermissions):
    """
    Retorna informações do usuário atual (incluindo se é admin/super admin).

    Usado pelo frontend para determinar permissões de UI.
    """
    require_admin(permissions)

    logger.info(f"Retornando informações do usuário {permissions.cpf}")

    return UserAccessRecord(
        cpf=permissions.cpf,
        is_admin=permissions.is_admin,
        is_super_admin=permissions.is_super_admin,
        permission=permissions.permission,
        id_cras_list=permissions.id_cras_list,
        id_escola_list=permissions.id_escola_list,
        id_cre_list=permissions.id_cre_list,
        id_cap_list=permissions.id_cap_list,
        id_cas_list=permissions.id_cas_list,
        id_clinica_familia_list=permissions.id_clinica_familia_list,
        active=permissions.active,
        notes=permissions.notes if hasattr(permissions, "notes") else None,
        created_by=permissions.cpf,  # Placeholder (não temos essa info em UserPermissions)
        created_at=datetime.now(timezone.utc),  # Placeholder
    )


# Configuração de filtros para usuários (seguindo padrão de participants)
USER_FILTER_OPTIONS_CONFIG = {
    "ocupacoes": {"column": "ocupacao"},
    "secretarias": {"column": "secretaria"},
    "status_ativo": {"column": "active"},  # true/false para status ativo
    "permissions": {"column": "permission"},  # super_admin, admin, user (coluna gerada no BQ)
}


@router.get("/users", response_model=PaginatedResponse[UserAccessRecord])
async def list_users(
    permissions: CurrentUserPermissions,
    pagination: PaginationParams = Depends(),
    active: Optional[bool] = Query(None, description="Filtrar por status ativo (true/false)"),
    ocupacao: Optional[str] = Query(None, description="Filtrar por ocupação"),
    secretaria: Optional[str] = Query(None, description="Filtrar por secretaria"),
    permission: Optional[str] = Query(None, description="Filtrar por tipo de permissão (super_admin/admin/user)"),
    search: Optional[str] = Query(None, description="Buscar por CPF ou nome"),
    bypass_cache: bool = Query(False, description="Forçar refresh do cache"),
):
    """
    Lista usuários com paginação e filtros em cascata (TUDO via fetch_filter_paginate).

    REGRAS:
    - Super admin: Vê todos os usuários
    - Admin segmentado: Vê apenas usuários com subset de seus IDs

    OTIMIZAÇÃO: Usa fetch_filter_paginate com cache compartilhado.

    Filtros disponíveis (todos em cascata via DataManager):
    - active: true/false (filtra por status ativo)
    - ocupacao: string (filtra por ocupação)
    - secretaria: string (filtra por secretaria)
    - permission: super_admin/admin/user (filtra por tipo de permissão)
    - search: busca parcial em CPF ou nome
    - page, page_size: paginação
    - bypass_cache: força refresh do cache (usado pelo botão Atualizar do frontend)
    """
    require_admin(permissions)

    logger.info(
        f"Admin {permissions.cpf} listando usuários - "
        f"Page: {pagination.page}, Size: {pagination.page_size}, "
        f"Active: {active}, Ocupacao: {ocupacao}, Secretaria: {secretaria}, "
        f"Permission: {permission}, Search: {search}, Bypass Cache: {bypass_cache}"
    )

    try:
        # Force refresh do cache se solicitado
        if bypass_cache:
            logger.info("🔄 Bypass cache solicitado - forçando refresh")
            refresh_governance_cache()

        # Preparar filtros (seguindo padrão de participants.py)
        filters_dict = {}

        if active is not None:
            filters_dict["active"] = active
        if ocupacao:
            filters_dict["ocupacao"] = ocupacao
        if secretaria:
            filters_dict["secretaria"] = secretaria
        if permission:
            filters_dict["permission"] = permission

        # Pipeline completo: fetch → filter → search → filter_options → paginate
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=GOVERNANCE_TABLE_QUERY,
            filters_dict=filters_dict,
            page=pagination.page,
            page_size=pagination.page_size,
            search_term=search,
            search_columns=["cpf", "nome"] if search else None,
            filter_columns_config=USER_FILTER_OPTIONS_CONFIG,
            user_permissions=None,  # Não aplicar governança (admin vê todos)
        )

        # OTIMIZAÇÃO: Converter DataFrame para JSON apenas aqui (última etapa)
        users_json = DataManager.df_to_json(df_data)

        # Converter JSON para UserAccessRecord
        users = []
        for user_dict in users_json:
            try:
                # Converter arrays de structs para List[IdWithName]
                for id_type in [
                    "id_cras",
                    "id_escola",
                    "id_cre",
                    "id_cap",
                    "id_cas",
                    "id_clinica_familia",
                ]:
                    list_key = f"{id_type}_list"
                    if list_key in user_dict and user_dict[list_key]:
                        user_dict[list_key] = [
                            IdWithName(**item) if isinstance(item, dict) else item
                            for item in user_dict[list_key]
                        ]

                users.append(UserAccessRecord(**user_dict))
            except Exception as e:
                logger.error(f"Erro ao converter usuário {user_dict.get('cpf')}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise

        logger.info(f"Retornando {len(users)} usuários (página {pagination.page})")

        return PaginatedResponse(
            data=users,
            meta=meta,
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"Erro ao listar usuários: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{cpf}", response_model=UserAccessRecord)
async def upsert_user(
    cpf: str, request: UpsertUserRequest, permissions: CurrentUserPermissions
):
    """
    Cria ou atualiza usuário (UPSERT).

    Se o CPF já existe:
    - Atualiza APENAS os campos fornecidos (PATCH logic).
    - Preserva valores existentes para campos não enviados.
    - Auditoria: updated_by, updated_at

    Se o CPF não existe:
    - Cria novo usuário (todos os campos obrigatórios devem ser válidos).
    - Auditoria: created_by, created_at

    VALIDAÇÕES:
    - Admin segmentado só pode atribuir IDs que ele possui.
    - Super admin pode atribuir qualquer ID.
    """
    require_admin(permissions)

    # Validar CPF format
    if len(cpf) != 11 or not cpf.isdigit():
        raise HTTPException(
            status_code=400, detail="CPF deve conter exatamente 11 dígitos"
        )

    logger.info(f"Admin {permissions.cpf} fazendo upsert do usuário {cpf}")

    # Verificar se CPF já existe (usa cache da tabela de governança)
    governance_df, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
    existing_user = governance_df[governance_df["cpf"] == cpf]
    user_exists = not existing_user.empty

    # PROTEÇÃO: Impedir criação acidental de usuário que já existe (se não for update intencional)
    if user_exists and not request.is_update:
        nome_existente = existing_user.iloc[0].get("nome", "Sem nome")
        raise HTTPException(
            status_code=409,  # Conflict
            detail=f"CPF {cpf} já está cadastrado no sistema (Usuário: {nome_existente}). Use a função de edição para atualizar este usuário.",
        )

    # PROTEÇÃO: Impedir edição de super admins
    if user_exists:
        is_target_super_admin = bool(existing_user.iloc[0]["is_super_admin"])
        # Apenas permite editar se o próprio usuário for super admin, mas ainda assim com cuidado
        # (regra atual: super admins não editáveis via UI)
        if is_target_super_admin:
            raise HTTPException(
                status_code=403,
                detail="Super admins não podem ser editados via interface",
            )

    # PROTEÇÃO: Impedir que admin edite a si mesmo
    if cpf == permissions.cpf:
        raise HTTPException(
            status_code=403,
            detail="Você não pode editar suas próprias permissões",
        )

    # Validar que apenas super admin pode definir is_super_admin
    if request.is_super_admin and not permissions.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas super admins podem criar ou promover outros super admins",
        )

    # PROTEÇÃO: Impedir criação de novos super admins
    if request.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Criação de super admins não é permitida via interface",
        )

    # Validar que admin pode atribuir esses IDs
    # Apenas valida listas que foram explicitamente enviadas (não None)
    target_ids_dict = request.model_dump(
        include={
            "id_cras_list",
            "id_escola_list",
            "id_cre_list",
            "id_cap_list",
            "id_cas_list",
            "id_clinica_familia_list",
        },
        exclude_unset=True # Importante: só valida o que foi enviado
    )
    
    # Filtrar None values do dict para validação
    target_ids_to_validate = {k: v for k, v in target_ids_dict.items() if v is not None}
    
    if target_ids_to_validate:
        validate_segmented_admin_can_manage(permissions, target_ids_to_validate)

    try:
        if user_exists:
            # UPDATE - Dinâmico (só atualiza campos não nulos)
            logger.info(f"Atualizando usuário existente: {cpf}")
            
            update_fields = []
            
            if request.nome is not None:
                safe_nome = request.nome.replace("'", "\\'")
                update_fields.append(f"nome = '{safe_nome}'")
                
            if request.ocupacao is not None:
                safe_ocupacao = request.ocupacao.replace("'", "\\'")
                update_fields.append(f"ocupacao = '{safe_ocupacao}'")
                
            if request.secretaria is not None:
                safe_secretaria = request.secretaria.replace("'", "\\'")
                update_fields.append(f"secretaria = '{safe_secretaria}'")
            
            # Booleans sempre atualizam se enviados (mesmo false)
            # Precisamos checar se foram setados no request (Pydantic model_dump(exclude_unset=True) seria melhor mas vamos checar explicitamente)
            # Assumindo que o frontend envia o estado completo do form, ou apenas o que mudou.
            # No caso do toggle active, só active é enviado.
            
            # ATENÇÃO: Pydantic por padrão tem defaults (False). 
            # Se for um patch parcial, precisamos saber o que foi enviado.
            # O frontend toggle envia apenas {active: false, is_update: true}.
            # Os outros campos virão com default do modelo (None ou False).
            # UpsertUserRequest define defaults como None para opcionais, mas False para booleans.
            # Isso é perigoso para partial updates.
            # CORREÇÃO: Vamos considerar que booleans só devem ser atualizados se outros campos do form também vierem,
            # OU se for explicitamente a intenção (difícil saber sem mudar o modelo para Optional[bool]).
            
            # Para corrigir o bug do toggle apagar permissões:
            # O toggle envia apenas active. Os outros campos virão como None (listas/strings) ou False (booleans).
            # Listas e Strings já são None por default no modelo, ok.
            # Booleans (is_admin, is_super_admin) são False por default.
            
            # ESTRATÉGIA SEGURA:
            # 1. Se notes, nome, ocupacao, secretaria E listas forem TODOS None, assumimos que é uma operação de toggle de status.
            # 2. Nesse caso, ignoramos is_admin/is_super_admin (mantemos o atual).
            
            is_full_update = (
                request.nome is not None or 
                request.ocupacao is not None or 
                request.secretaria is not None or
                request.id_cras_list is not None or
                request.id_escola_list is not None
            )
            
            # Se for full update, atualiza permissões. Se não, mantém.
            if is_full_update:
                update_fields.append(f"is_admin = {str(request.is_admin).upper()}")
                update_fields.append(f"is_super_admin = {str(request.is_super_admin).upper()}")
                
                # Recalcula permission string
                permission_value = calculate_permission(request.is_admin, request.is_super_admin)
                update_fields.append(f"permission = '{permission_value}'")
            
            # Listas - só atualiza se não for None
            if request.id_cras_list is not None:
                update_fields.append(f"id_cras_list = {_convert_id_list_to_bq_struct(request.id_cras_list)}")
            if request.id_escola_list is not None:
                update_fields.append(f"id_escola_list = {_convert_id_list_to_bq_struct(request.id_escola_list)}")
            if request.id_cre_list is not None:
                update_fields.append(f"id_cre_list = {_convert_id_list_to_bq_struct(request.id_cre_list)}")
            if request.id_cap_list is not None:
                update_fields.append(f"id_cap_list = {_convert_id_list_to_bq_struct(request.id_cap_list)}")
            if request.id_cas_list is not None:
                update_fields.append(f"id_cas_list = {_convert_id_list_to_bq_struct(request.id_cas_list)}")
            if request.id_clinica_familia_list is not None:
                update_fields.append(f"id_clinica_familia_list = {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)}")
                
            if request.notes is not None:
                safe_notes = request.notes.replace("'", "\\'")
                update_fields.append(f"notes = '{safe_notes}'")
                
            # Active sempre atualiza
            update_fields.append(f"active = {str(request.active).upper()}")
            
            # Metadata
            update_fields.append(f"updated_by = '{permissions.cpf}'")
            update_fields.append("updated_at = CURRENT_TIMESTAMP()")
            
            if not update_fields:
                logger.info("Nenhum campo para atualizar")
                return UserAccessRecord(**existing_user.iloc[0].to_dict())

            query = f"""
            UPDATE `{PROJECT_ID}.{DATASET_ID}.data_access`
            SET {', '.join(update_fields)}
            WHERE cpf = '{cpf}'
            """
            
            execute_query(query)
            logger.info(f"✅ Usuário {cpf} atualizado dinamicamente")

        else:
            # INSERT - Novo usuário (precisa de todos os campos)
            logger.info(f"Criando novo usuário: {cpf}")
            
            # Calcular permission
            permission_value = calculate_permission(request.is_admin, request.is_super_admin)

            # Preparar valores SQL
            nome_sql = f"'{request.nome.replace(chr(39), chr(92)+chr(39))}'" if request.nome else "NULL"
            ocupacao_sql = f"'{request.ocupacao.replace(chr(39), chr(92)+chr(39))}'" if request.ocupacao else "NULL"
            secretaria_sql = f"'{request.secretaria.replace(chr(39), chr(92)+chr(39))}'" if request.secretaria else "NULL"
            notes_sql = f"'{request.notes.replace(chr(39), chr(92)+chr(39))}'" if request.notes else "NULL"

            query = f"""
            INSERT INTO `{PROJECT_ID}.{DATASET_ID}.data_access`
            (
                cpf, nome, ocupacao, secretaria, is_admin, is_super_admin, permission,
                id_cras_list, id_escola_list, id_cre_list, id_cap_list, id_cas_list, id_clinica_familia_list,
                created_by, active, notes, created_at
            )
            VALUES (
                '{cpf}', {nome_sql}, {ocupacao_sql}, {secretaria_sql},
                {str(request.is_admin).upper()}, {str(request.is_super_admin).upper()}, '{permission_value}',
                {_convert_id_list_to_bq_struct(request.id_cras_list)},
                {_convert_id_list_to_bq_struct(request.id_escola_list)},
                {_convert_id_list_to_bq_struct(request.id_cre_list)},
                {_convert_id_list_to_bq_struct(request.id_cap_list)},
                {_convert_id_list_to_bq_struct(request.id_cas_list)},
                {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)},
                '{permissions.cpf}', {str(request.active).upper()}, {notes_sql}, CURRENT_TIMESTAMP()
            )
            """
            execute_query(query)
            logger.info(f"✅ Usuário {cpf} criado com sucesso")

        # Invalidar E renovar cache
        refresh_governance_cache()

        # Buscar usuário para retornar
        governance_df, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
        user_row = governance_df[governance_df["cpf"] == cpf]

        if user_row.empty:
            # Fallback se cache refresh falhar ou tiver delay (raro com bypass_cache=True)
            # Retorna o que temos em memória do existing_user se possível, ou erro
            if user_exists:
                 logger.warning("User not found in refreshed cache, returning old data + updates")
                 # Aqui idealmente faríamos um merge manual, mas vamos lançar erro para ser seguro
            
            raise HTTPException(
                status_code=500,
                detail=f"Usuário {cpf} salvo, mas não encontrado no cache renovado",
            )

        # Converter para UserAccessRecord (mesma lógica de antes)
        row_dict = user_row.iloc[0].to_dict()
        for key, value in row_dict.items():
            if not isinstance(value, (list, dict)):
                try:
                    if pd.isna(value):
                        row_dict[key] = None
                except (ValueError, TypeError):
                    pass

        # Bool conv
        if "active" in row_dict: row_dict["active"] = bool(row_dict["active"])
        if "is_admin" in row_dict: row_dict["is_admin"] = bool(row_dict["is_admin"])
        if "is_super_admin" in row_dict: row_dict["is_super_admin"] = bool(row_dict["is_super_admin"])

        # Timestamp conv
        if "created_at" in row_dict and hasattr(row_dict["created_at"], "to_pydatetime"):
            row_dict["created_at"] = row_dict["created_at"].to_pydatetime()
        if "updated_at" in row_dict and hasattr(row_dict["updated_at"], "to_pydatetime"):
            row_dict["updated_at"] = row_dict["updated_at"].to_pydatetime()

        # Struct conv
        for id_type in ["id_cras", "id_escola", "id_cre", "id_cap", "id_cas", "id_clinica_familia"]:
            list_key = f"{id_type}_list"
            if row_dict.get(list_key) is not None and isinstance(row_dict[list_key], list):
                row_dict[list_key] = [
                    IdWithName(**item) if isinstance(item, dict) else item
                    for item in row_dict[list_key]
                ]

        return UserAccessRecord(**row_dict)

    except Exception as e:
        logger.error(f"Erro ao fazer upsert do usuário {cpf}: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@router.delete("/users/{cpf}", status_code=204)
async def delete_user(cpf: str, permissions: CurrentUserPermissions):
    """
    Soft-delete de um usuário (marca active=FALSE).

    IMPORTANTE: Não deleta fisicamente, apenas marca como inativo.
    Isso preserva auditoria e permite reativação futura.
    """
    require_admin(permissions)

    logger.info(f"Admin {permissions.cpf} deletando usuário {cpf}")

    # Verificar que usuário existe
    try:
        DataManager.get_user_permissions(cpf)
    except:
        raise HTTPException(status_code=404, detail=f"Usuário {cpf} não encontrado")

    # Soft delete (active = FALSE)
    query = f"""
    UPDATE `{PROJECT_ID}.{DATASET_ID}.data_access`
    SET
        active = FALSE,
        updated_by = '{permissions.cpf}',
        updated_at = CURRENT_TIMESTAMP()
    WHERE cpf = '{cpf}'
    """

    try:
        execute_query(query)
        logger.info(f"✅ Usuário {cpf} marcado como inativo por {permissions.cpf}")

        # Invalidar E renovar cache imediatamente
        refresh_governance_cache()

    except Exception as e:
        logger.error(f"Erro ao deletar usuário: {e}")
        raise HTTPException(status_code=500, detail=str(e))
