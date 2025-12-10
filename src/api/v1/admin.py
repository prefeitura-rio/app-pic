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
import polars as pl
from datetime import datetime, timezone

from src.core.security.jwt import CurrentUserPermissions
from src.core.security.permissions_models import IdWithName, UserPermissions
from src.config import env
from src.utils.log import logger
from src.utils.data_manager import DataManager
from src.utils.bigquery import execute_query, build_update_query
from google.cloud import bigquery
from src.api.v1.queries import GOVERNANCE_TABLE_QUERY, PARTICIPANTS_TABLE_QUERY
from src.api.v1.schemas import PaginatedResponse, PaginationParams
from pydantic import BaseModel, Field

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


# ========================================================================
# HELPERS
# ========================================================================


def refresh_governance_cache():
    """
    Invalidate governance cache após modificações na tabela (INSERT/UPDATE/DELETE).

    USO: Chamar apenas após modificar dados no BigQuery (não em requests de leitura).
    Para requests de leitura com bypass, use o parâmetro bypass_cache=True diretamente.

    SEGURANÇA: Invalida o cache para que próximas requests busquem dados frescos.
    Isso evita que usuários vejam dados desatualizados após modificações.

    IMPORTANTE: Não é necessário chamar esta função quando já está usando
    bypass_cache=True no endpoint, pois o bypass já ignora o cache automaticamente.
    """
    from src.utils.cache_manager import query_cache

    query_cache.delete(GOVERNANCE_TABLE_QUERY)
    logger.info("🔄 Governance cache invalidated (lazy refresh)")


# ========================================================================
# SCHEMAS
# ========================================================================


class AvailableIds(BaseModel):
    """IDs disponíveis para atribuição (extraídos da tabela de participantes)"""

    cras: List[IdWithName] = Field(default_factory=list)
    escolas: List[IdWithName] = Field(default_factory=list)
    cres: List[IdWithName] = Field(default_factory=list)
    aps: List[IdWithName] = Field(default_factory=list)
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
    id_ap_list: Optional[List[IdWithName]] = None
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
    id_ap_list: Optional[List[IdWithName]] = None
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


def _filter_manageable_users(
    df: pl.DataFrame, admin_permissions: UserPermissions
) -> pl.DataFrame:
    """
    Filtra usuários que admin segmentado pode gerenciar.

    Regra: Admin segmentado só pode gerenciar usuários que possuem
    um subset dos IDs do admin (TODOS os IDs do usuário, de TODOS os tipos,
    devem estar contidos nos IDs do admin).

    Args:
        df: DataFrame com todos os usuários
        admin_permissions: Permissões do admin fazendo a request

    Returns:
        DataFrame filtrado com apenas usuários gerenciáveis
    """
    if df.is_empty():
        return df

    # Debug: Log permissões do admin (sem expor CPF completo)
    logger.info(f"🔍 Verificando permissões do admin:")
    logger.info(f"  - is_super_admin: {admin_permissions.is_super_admin}")
    logger.info(f"  - is_admin: {admin_permissions.is_admin}")
    logger.info(f"  - CRAS: {len(admin_permissions.id_cras_list or [])}")
    logger.info(f"  - Escolas: {len(admin_permissions.id_escola_list or [])}")
    logger.info(f"  - CRE: {len(admin_permissions.id_cre_list or [])}")
    logger.info(f"  - AP: {len(admin_permissions.id_ap_list or [])}")
    logger.info(f"  - CAS: {len(admin_permissions.id_cas_list or [])}")
    logger.info(f"  - Clínicas: {len(admin_permissions.id_clinica_familia_list or [])}")

    # REGRA: Admin sem nenhum ID não pode gerenciar usuários
    # (apenas super admin pode gerenciar sem restrição)
    has_any_ids = any(
        [
            admin_permissions.id_cras_list,
            admin_permissions.id_escola_list,
            admin_permissions.id_cre_list,
            admin_permissions.id_ap_list,
            admin_permissions.id_cas_list,
            admin_permissions.id_clinica_familia_list,
        ]
    )

    if not has_any_ids:
        logger.warning(f"❌ Admin não possui nenhum ID - não pode gerenciar usuários")
        return df.head(0)  # Retorna DataFrame vazio

    # OTIMIZAÇÃO: Usar operação vetorizada ao invés de iterrows()
    # Primeiro filtro: remover super admins (operação vetorizada)
    df_non_super_admin = df.filter(pl.col("is_super_admin") == False)

    if df_non_super_admin.is_empty():
        logger.info("Nenhum usuário gerenciável (todos são super admins)")
        return df.head(0)

    # Preparar sets de IDs do admin uma única vez (fora do loop)
    admin_id_sets = {
        "id_cras": set(admin_permissions.get_filter_ids("id_cras")),
        "id_escola": set(admin_permissions.get_filter_ids("id_escola")),
        "id_cre": set(admin_permissions.get_filter_ids("id_cre")),
        "id_ap": set(admin_permissions.get_filter_ids("id_ap")),
        "id_cas": set(admin_permissions.get_filter_ids("id_cas")),
        "id_clinica_familia": set(
            admin_permissions.get_filter_ids("id_clinica_familia")
        ),
    }

    # OTIMIZAÇÃO POLARS: Usar to_dicts() para iterar (governance table é pequena ~100 rows max)
    # Isso é aceitável porque a tabela de governança tem poucos usuários
    manageable_cpfs = []

    for row in df_non_super_admin.to_dicts():
        is_manageable = True

        for id_type in [
            "id_cras",
            "id_escola",
            "id_cre",
            "id_ap",
            "id_cas",
            "id_clinica_familia",
        ]:
            list_key = f"{id_type}_list"
            user_id_list = row.get(list_key)
            admin_ids = admin_id_sets[id_type]

            # Se usuário não tem IDs desse tipo, ok (pula)
            if user_id_list is None or (isinstance(user_id_list, list) and len(user_id_list) == 0):
                continue

            # Extrair IDs do usuário
            user_ids = set()
            for item in user_id_list if isinstance(user_id_list, list) else []:
                if isinstance(item, dict):
                    user_ids.add(item.get("id"))

            # REGRA: Se usuário tem IDs desse tipo, admin DEVE ter IDs desse tipo
            if user_ids and not admin_ids:
                is_manageable = False
                break

            # REGRA: Todos os IDs do usuário devem estar no subset do admin
            if user_ids and not user_ids.issubset(admin_ids):
                is_manageable = False
                break

        if is_manageable:
            manageable_cpfs.append(row["cpf"])

    # Filtrar DataFrame pelos CPFs gerenciáveis
    df_filtered = df_non_super_admin.filter(pl.col("cpf").is_in(manageable_cpfs))

    logger.info(
        f"Admin segmentado - Usuários gerenciáveis: {len(df)} -> {len(df_filtered)}"
    )

    return df_filtered


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

    logger.info(f"🔍 Validando atribuição de IDs por admin")
    logger.info(f"   IDs sendo atribuídos: {list(target_ids.keys())}")

    # REGRA: Admin sem nenhum ID não pode atribuir IDs a outros usuários
    has_any_ids = any(
        [
            admin_permissions.id_cras_list,
            admin_permissions.id_escola_list,
            admin_permissions.id_cre_list,
            admin_permissions.id_ap_list,
            admin_permissions.id_cas_list,
            admin_permissions.id_clinica_familia_list,
        ]
    )

    if not has_any_ids and target_ids:
        logger.warning(f"   ❌ BLOQUEADO: Admin sem IDs tentando atribuir IDs")
        raise HTTPException(
            status_code=403,
            detail="Você não possui IDs para distribuir. Apenas super admins podem criar usuários com IDs sem possuir IDs próprios.",
        )

    # Validar cada tipo de ID
    for id_type in [
        "id_cras",
        "id_escola",
        "id_cre",
        "id_ap",
        "id_cas",
        "id_clinica_familia",
    ]:
        list_key = f"{id_type}_list"
        target_list = target_ids.get(list_key)

        if not target_list:
            continue  # Nenhum ID desse tipo sendo atribuído

        # IDs que o admin possui
        admin_ids = set(admin_permissions.get_filter_ids(id_type))

        logger.info(
            f"   {id_type}: admin tem {len(admin_ids)}, tentando atribuir {len(target_list)}"
        )

        if not admin_ids:
            logger.warning(f"   ❌ BLOQUEADO: Admin não possui {id_type}")
            raise HTTPException(
                status_code=403,
                detail=f"Você não tem permissão para atribuir {id_type} (você não possui nenhum)",
            )

        # IDs que estão sendo atribuídos (pode vir como dict ou IdWithName)
        target_ids_set = set()
        for item in target_list:
            if isinstance(item, dict):
                target_ids_set.add(item.get("id"))
            elif hasattr(item, "id"):
                target_ids_set.add(item.id)
            else:
                # Fallback: tentar converter string diretamente
                target_ids_set.add(str(item))

        # Verificar se todos os IDs alvo estão no subset do admin
        unauthorized_ids = target_ids_set - admin_ids

        if unauthorized_ids:
            logger.warning(
                f"   ❌ BLOQUEADO: IDs não autorizados em {id_type}: {unauthorized_ids}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Você não pode atribuir estes {id_type}: {unauthorized_ids}",
            )

    logger.info(f"   ✅ Validação OK - admin pode atribuir esses IDs")


def _extract_unique_ids(
    df: pl.DataFrame, id_col: str, nome_col: str
) -> List[IdWithName]:
    """Helper para extrair IDs únicos com nomes de um DataFrame"""
    if df.is_empty() or id_col not in df.columns:
        return []

    # Se nome_col não existe ou é igual a id_col, usar id_col para ambos
    if nome_col not in df.columns or id_col == nome_col:
        unique_df = df.select(id_col).drop_nulls().unique().sort(id_col)
        return [
            IdWithName(id=str(row[id_col]), nome=str(row[id_col]))
            for row in unique_df.to_dicts()
        ]

    # Caso normal: colunas diferentes
    unique_df = (
        df.select([id_col, nome_col])
        .drop_nulls()
        .unique(subset=[id_col])
        .sort(nome_col)
    )

    return [
        IdWithName(id=str(row[id_col]), nome=str(row[nome_col]))
        for row in unique_df.to_dicts()
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
    Retorna IDs disponíveis para atribuição.

    REGRAS:
    - Super admin: Vê todos os IDs existentes no sistema
    - Admin segmentado: Vê apenas os IDs que ele mesmo possui (pode distribuir seus próprios acessos)

    OTIMIZAÇÃO: Reutiliza cache da tabela de participantes.
    """
    require_admin(permissions)

    logger.info(
        f"Admin buscando IDs disponíveis (is_super_admin={permissions.is_super_admin})"
    )

    # OTIMIZAÇÃO: Reutiliza a mesma query que /participants (aproveita cache existente!)
    try:
        # Super admin: buscar todos os IDs disponíveis no sistema
        if permissions.is_super_admin:
            # Buscar dados de participantes (usa cache compartilhado)
            df, _, _ = DataManager.get_dataset(PARTICIPANTS_TABLE_QUERY)

            # Extrair IDs únicos com nomes
            available_ids = AvailableIds(
                cras=_extract_unique_ids(df, "id_cras", "nome_cras"),
                escolas=_extract_unique_ids(df, "id_escola", "nome_escola"),
                cres=_extract_unique_ids(
                    df, "id_cre", "id_cre"
                ),  # CRE não tem nome, usa id_cre como nome
                aps=_extract_unique_ids(df, "id_ap", "nome_ap"),
                cas=_extract_unique_ids(df, "id_cas", "nome_cas"),
                clinicas=_extract_unique_ids(
                    df, "id_clinica_familia", "nome_clinica_familia"
                ),
            )

            logger.info(
                f"Super admin - Retornando {len(available_ids.cras)} CRAS, "
                f"{len(available_ids.escolas)} escolas, "
                f"{len(available_ids.cres)} CREs, "
                f"{len(available_ids.aps)} APs, "
                f"{len(available_ids.cas)} CAS, "
                f"{len(available_ids.clinicas)} clínicas"
            )

            return available_ids

        # Admin segmentado: retornar apenas IDs que ele possui (pode distribuir seus próprios acessos)
        else:
            available_ids = AvailableIds(
                cras=permissions.id_cras_list or [],
                escolas=permissions.id_escola_list or [],
                cres=permissions.id_cre_list or [],
                aps=permissions.id_ap_list or [],
                cas=permissions.id_cas_list or [],
                clinicas=permissions.id_clinica_familia_list or [],
            )

            logger.info(
                f"Admin segmentado - Retornando apenas IDs que o admin possui: "
                f"{len(available_ids.cras)} CRAS, "
                f"{len(available_ids.escolas)} escolas, "
                f"{len(available_ids.cres)} CREs, "
                f"{len(available_ids.aps)} APs, "
                f"{len(available_ids.cas)} CAS, "
                f"{len(available_ids.clinicas)} clínicas"
            )

            return available_ids

    except Exception as e:
        logger.error(f"❌ Erro ao buscar IDs disponíveis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me", response_model=UserAccessRecord)
async def get_current_user(permissions: CurrentUserPermissions):
    """
    Retorna informações do usuário atual (incluindo se é admin/super admin).

    Usado pelo frontend para determinar permissões de UI.
    Acessível a qualquer usuário autenticado.
    """
    logger.info(f"Retornando informações do usuário atual")

    return UserAccessRecord(
        cpf=permissions.cpf,
        is_admin=permissions.is_admin,
        is_super_admin=permissions.is_super_admin,
        permission=permissions.permission,
        id_cras_list=permissions.id_cras_list,
        id_escola_list=permissions.id_escola_list,
        id_cre_list=permissions.id_cre_list,
        id_ap_list=permissions.id_ap_list,
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
    "permissions": {
        "column": "permission"
    },  # super_admin, admin, user (coluna gerada no BQ)
}


@router.get("/users", response_model=PaginatedResponse[UserAccessRecord])
async def list_users(
    permissions: CurrentUserPermissions,
    pagination: PaginationParams = Depends(),
    active: Optional[bool] = Query(
        None, description="Filtrar por status ativo (true/false)"
    ),
    ocupacao: Optional[str] = Query(None, description="Filtrar por ocupação"),
    secretaria: Optional[str] = Query(None, description="Filtrar por secretaria"),
    permission: Optional[str] = Query(
        None, description="Filtrar por tipo de permissão (super_admin/admin/user)"
    ),
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
        f"Admin listando usuários - "
        f"is_super_admin={permissions.is_super_admin}, "
        f"Page: {pagination.page}, Size: {pagination.page_size}, "
        f"Active: {active}, Bypass Cache: {bypass_cache}"
    )

    try:
        # Log bypass cache (não precisa mais invalidar explicitamente)
        if bypass_cache:
            logger.info("🔄 Bypass cache solicitado - forçando query no BigQuery")

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
        # IMPORTANTE: Para admins segmentados, aplicar governança APÓS buscar dados
        # Se bypass_cache=True, força query no BigQuery para garantir dados frescos
        df_data, meta, filter_options = DataManager.fetch_filter_paginate(
            query=GOVERNANCE_TABLE_QUERY,
            filters_dict=filters_dict,
            page=pagination.page,
            page_size=pagination.page_size,
            search_term=search,
            search_columns=["cpf", "nome"] if search else None,
            filter_columns_config=USER_FILTER_OPTIONS_CONFIG,
            user_permissions=None,  # Não usar governança automática (tabela diferente)
            bypass_cache=bypass_cache,  # IMPORTANTE: Passa bypass_cache para forçar refresh
        )

        # Filtrar usuários gerenciáveis por admin segmentado (APÓS paginação)
        # Super admin vê todos, admin segmentado vê apenas subset
        logger.info(
            f"🔍 Verificando filtro de governança: is_super_admin={permissions.is_super_admin}"
        )
        if not permissions.is_super_admin:
            logger.info(
                f"🚨 Admin segmentado detectado - aplicando filtro de usuários gerenciáveis"
            )
            df_data = _filter_manageable_users(df_data, permissions)
            # Recalcular meta após filtro de governança
            total_after_filter = len(df_data)
            meta.total_rows = total_after_filter
            meta.total_pages = (
                (total_after_filter + meta.page_size - 1) // meta.page_size
                if meta.page_size
                else 1
            )
        else:
            logger.info(f"✅ Super admin - sem filtro de governança")

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
                    "id_ap",
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
                logger.error(
                    f"❌ Erro ao converter usuário {user_dict.get('cpf')}: {e}"
                )
                import traceback

                logger.error(f"❌ Traceback: {traceback.format_exc()}")
                raise

        logger.info(f"Retornando {len(users)} usuários (página {pagination.page})")

        return PaginatedResponse(
            data=users,
            meta=meta,
            filters=filter_options,
        )

    except Exception as e:
        logger.error(f"❌ Erro ao listar usuários: {e}")
        import traceback

        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
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

    logger.info(f"Admin fazendo upsert de usuário")
    logger.info(f"  Request recebido:")
    logger.info(f"    - is_admin: {request.is_admin}")
    logger.info(f"    - is_super_admin: {request.is_super_admin}")
    logger.info(
        f"    - id_cras_list: (len={len(request.id_cras_list) if request.id_cras_list else 0})"
    )
    logger.info(
        f"    - id_escola_list: (len={len(request.id_escola_list) if request.id_escola_list else 0})"
    )
    logger.info(
        f"    - id_cre_list: (len={len(request.id_cre_list) if request.id_cre_list else 0})"
    )
    logger.info(f"    - active: {request.active}")
    logger.info(f"    - is_update: {request.is_update}")

    # Verificar se CPF já existe (usa cache da tabela de governança)
    governance_df, _, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
    existing_user = governance_df.filter(pl.col("cpf") == cpf)
    user_exists = not existing_user.is_empty()

    # PROTEÇÃO: Impedir criação acidental de usuário que já existe (se não for update intencional)
    if user_exists and not request.is_update:
        existing_row = existing_user.row(0, named=True)
        nome_existente = existing_row.get("nome", "Sem nome")
        raise HTTPException(
            status_code=409,  # Conflict
            detail=f"CPF {cpf} já está cadastrado no sistema (Usuário: {nome_existente}). Use a função de edição para atualizar este usuário.",
        )

    # PROTEÇÃO: Impedir edição de super admins
    if user_exists:
        existing_row = existing_user.row(0, named=True)
        is_target_super_admin = bool(existing_row["is_super_admin"])
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
            "id_ap_list",
            "id_cas_list",
            "id_clinica_familia_list",
        },
        exclude_unset=True,  # Importante: só valida o que foi enviado
    )

    # Filtrar None values do dict para validação
    target_ids_to_validate = {k: v for k, v in target_ids_dict.items() if v is not None}

    if target_ids_to_validate:
        validate_segmented_admin_can_manage(permissions, target_ids_to_validate)

    try:
        if user_exists:
            # UPDATE - Dinâmico (só atualiza campos não nulos)
            logger.info(f"Atualizando usuário existente")

            # SEGURANÇA: Usar parametrized queries para campos simples
            # ARRAY<STRUCT> ainda usa f-string por limitação do BigQuery
            update_dict = {}
            struct_updates = []  # Para ARRAY<STRUCT> que precisam de f-string

            if request.nome is not None:
                update_dict["nome"] = request.nome

            if request.ocupacao is not None:
                update_dict["ocupacao"] = request.ocupacao

            if request.secretaria is not None:
                update_dict["secretaria"] = request.secretaria

            # Detectar se é full update ou apenas toggle de active
            is_full_update = (
                request.nome is not None
                or request.ocupacao is not None
                or request.secretaria is not None
                or request.id_cras_list is not None
                or request.id_escola_list is not None
            )

            # Se for full update, atualiza permissões. Se não, mantém.
            if is_full_update:
                update_dict["is_admin"] = request.is_admin
                update_dict["is_super_admin"] = request.is_super_admin

                # Recalcula permission string
                permission_value = calculate_permission(
                    request.is_admin, request.is_super_admin
                )
                update_dict["permission"] = permission_value

            # Listas - SEMPRE atualiza em full updates (None vira NULL para limpar)
            if is_full_update:
                logger.info(
                    f"  Full update detectado - atualizando todas as listas de IDs"
                )
                logger.info(
                    f"    CRAS: {len(request.id_cras_list) if request.id_cras_list else 0} IDs"
                )
                logger.info(
                    f"    Escolas: {len(request.id_escola_list) if request.id_escola_list else 0} IDs"
                )
                logger.info(
                    f"    CRE: {len(request.id_cre_list) if request.id_cre_list else 0} IDs"
                )
                logger.info(
                    f"    AP: {len(request.id_ap_list) if request.id_ap_list else 0} IDs"
                )
                logger.info(
                    f"    CAS: {len(request.id_cas_list) if request.id_cas_list else 0} IDs"
                )
                logger.info(
                    f"    Clínicas: {len(request.id_clinica_familia_list) if request.id_clinica_familia_list else 0} IDs"
                )

                # ARRAY<STRUCT> não pode ser parametrizado facilmente no BigQuery
                struct_updates.append(
                    f"id_cras_list = {_convert_id_list_to_bq_struct(request.id_cras_list)}"
                )
                struct_updates.append(
                    f"id_escola_list = {_convert_id_list_to_bq_struct(request.id_escola_list)}"
                )
                struct_updates.append(
                    f"id_cre_list = {_convert_id_list_to_bq_struct(request.id_cre_list)}"
                )
                struct_updates.append(
                    f"id_ap_list = {_convert_id_list_to_bq_struct(request.id_ap_list)}"
                )
                struct_updates.append(
                    f"id_cas_list = {_convert_id_list_to_bq_struct(request.id_cas_list)}"
                )
                struct_updates.append(
                    f"id_clinica_familia_list = {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)}"
                )

            if request.notes is not None:
                update_dict["notes"] = request.notes

            # Active sempre atualiza
            update_dict["active"] = request.active

            # Metadata
            update_dict["updated_by"] = permissions.cpf

            if not update_dict and not struct_updates:
                logger.info("Nenhum campo para atualizar")
                return UserAccessRecord(**existing_user.row(0, named=True))

            # Build parametrized query para campos simples
            if update_dict:
                query, parameters = build_update_query(
                    table=f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}",
                    updates=update_dict,
                    where_field="cpf",
                    where_value=cpf,
                )

                # Se temos struct updates, precisamos adicionar manualmente
                if struct_updates:
                    # Inserir struct_updates E updated_at antes do WHERE
                    query_parts = query.split("WHERE")
                    set_clause = query_parts[0].rstrip()
                    # Adicionar vírgula e struct updates
                    set_clause += ",\n        " + ",\n        ".join(struct_updates)
                    # Adicionar updated_at
                    set_clause += ",\n        updated_at = CURRENT_TIMESTAMP()"
                    query = set_clause + "\n    WHERE" + query_parts[1]
                else:
                    # Apenas campos simples - adicionar updated_at ao SET
                    # A query gerada por build_update_query tem formato:
                    # UPDATE `table` SET campo1 = @campo1, campo2 = @campo2 WHERE cpf = @cpf
                    # Precisamos adicionar ", updated_at = CURRENT_TIMESTAMP()" antes do WHERE
                    query_parts = query.split("WHERE")
                    set_clause = query_parts[0].rstrip()
                    set_clause += ",\n        updated_at = CURRENT_TIMESTAMP()"
                    query = set_clause + "\n    WHERE" + query_parts[1]
            else:
                # Apenas struct updates (raro, mas possível)
                all_updates = struct_updates + ["updated_at = CURRENT_TIMESTAMP()"]
                query = f"""
                UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
                SET {', '.join(all_updates)}
                WHERE cpf = @cpf
                """
                parameters = [bigquery.ScalarQueryParameter("cpf", "STRING", cpf)]

            logger.info(
                f"✅ Usando parametrized query (campos simples parametrizados, ARRAY<STRUCT> inline)"
            )
            execute_query(query, parameters)
            logger.info(f"✅ Usuário atualizado dinamicamente")

        else:
            # INSERT - Novo usuário (precisa de todos os campos)
            logger.info(f"Criando novo usuário")

            # Calcular permission
            permission_value = calculate_permission(
                request.is_admin, request.is_super_admin
            )

            # SEGURANÇA: Usar parametrized queries para campos simples
            # ARRAY<STRUCT> ainda usa f-string inline por limitação do BigQuery
            query = f"""
            INSERT INTO `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
            (
                cpf, nome, ocupacao, secretaria, is_admin, is_super_admin, permission,
                id_cras_list, id_escola_list, id_cre_list, id_ap_list, id_cas_list, id_clinica_familia_list,
                created_by, active, notes, created_at
            )
            VALUES (
                @cpf, @nome, @ocupacao, @secretaria,
                @is_admin, @is_super_admin, @permission,
                {_convert_id_list_to_bq_struct(request.id_cras_list)},
                {_convert_id_list_to_bq_struct(request.id_escola_list)},
                {_convert_id_list_to_bq_struct(request.id_cre_list)},
                {_convert_id_list_to_bq_struct(request.id_ap_list)},
                {_convert_id_list_to_bq_struct(request.id_cas_list)},
                {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)},
                @created_by, @active, @notes, CURRENT_TIMESTAMP()
            )
            """

            # Build parameters list
            parameters = [
                bigquery.ScalarQueryParameter("cpf", "STRING", cpf),
                bigquery.ScalarQueryParameter("nome", "STRING", request.nome),
                bigquery.ScalarQueryParameter("ocupacao", "STRING", request.ocupacao),
                bigquery.ScalarQueryParameter(
                    "secretaria", "STRING", request.secretaria
                ),
                bigquery.ScalarQueryParameter("is_admin", "BOOL", request.is_admin),
                bigquery.ScalarQueryParameter(
                    "is_super_admin", "BOOL", request.is_super_admin
                ),
                bigquery.ScalarQueryParameter("permission", "STRING", permission_value),
                bigquery.ScalarQueryParameter("created_by", "STRING", permissions.cpf),
                bigquery.ScalarQueryParameter("active", "BOOL", request.active),
                bigquery.ScalarQueryParameter("notes", "STRING", request.notes),
            ]

            logger.info(
                f"✅ Usando parametrized query para INSERT (campos simples parametrizados)"
            )
            execute_query(query, parameters)
            logger.info(f"✅ Usuário criado com sucesso")

        # Invalidar cache (lazy refresh)
        refresh_governance_cache()

        # IMPORTANTE: Aguardar 100ms para BigQuery propagar o UPDATE/INSERT
        # Isso previne race condition onde a query abaixo executa antes da propagação
        import time

        time.sleep(0.1)

        # Buscar usuário para retornar (força bypass_cache para garantir dados frescos)
        governance_df, _, _ = DataManager.get_dataset(
            GOVERNANCE_TABLE_QUERY, bypass_cache=True
        )
        user_row = governance_df.filter(pl.col("cpf") == cpf)

        if user_row.is_empty():
            # Fallback se cache refresh falhar ou tiver delay (raro com bypass_cache=True)
            # Retorna o que temos em memória do existing_user se possível, ou erro
            if user_exists:
                logger.warning(
                    "User not found in refreshed cache, returning old data + updates"
                )
                # Aqui idealmente faríamos um merge manual, mas vamos lançar erro para ser seguro

            raise HTTPException(
                status_code=500,
                detail=f"Usuário {cpf} salvo, mas não encontrado no cache renovado",
            )

        # Converter para UserAccessRecord (Polars já converte null para None)
        row_dict = user_row.row(0, named=True)

        # Bool conv
        if "active" in row_dict:
            row_dict["active"] = bool(row_dict["active"])
        if "is_admin" in row_dict:
            row_dict["is_admin"] = bool(row_dict["is_admin"])
        if "is_super_admin" in row_dict:
            row_dict["is_super_admin"] = bool(row_dict["is_super_admin"])

        # Timestamp conv
        if "created_at" in row_dict and hasattr(
            row_dict["created_at"], "to_pydatetime"
        ):
            row_dict["created_at"] = row_dict["created_at"].to_pydatetime()
        if "updated_at" in row_dict and hasattr(
            row_dict["updated_at"], "to_pydatetime"
        ):
            row_dict["updated_at"] = row_dict["updated_at"].to_pydatetime()

        # Struct conv
        for id_type in [
            "id_cras",
            "id_escola",
            "id_cre",
            "id_ap",
            "id_cas",
            "id_clinica_familia",
        ]:
            list_key = f"{id_type}_list"
            if row_dict.get(list_key) is not None and isinstance(
                row_dict[list_key], list
            ):
                row_dict[list_key] = [
                    IdWithName(**item) if isinstance(item, dict) else item
                    for item in row_dict[list_key]
                ]

        return UserAccessRecord(**row_dict)

    except Exception as e:
        logger.error(f"❌ Erro ao fazer upsert do usuário {cpf}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{cpf}", status_code=204)
async def delete_user(cpf: str, permissions: CurrentUserPermissions):
    """
    Soft-delete de um usuário (marca active=FALSE).

    IMPORTANTE: Não deleta fisicamente, apenas marca como inativo.
    Isso preserva auditoria e permite reativação futura.
    """
    require_admin(permissions)

    logger.info(f"Admin deletando usuário")

    # Verificar que usuário existe
    try:
        DataManager.get_user_permissions(cpf)
    except:
        raise HTTPException(status_code=404, detail=f"Usuário {cpf} não encontrado")

    # SEGURANÇA: Soft delete com parametrized query
    query = f"""
    UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
    SET
        active = @active,
        updated_by = @updated_by,
        updated_at = CURRENT_TIMESTAMP()
    WHERE cpf = @cpf
    """

    parameters = [
        bigquery.ScalarQueryParameter("active", "BOOL", False),
        bigquery.ScalarQueryParameter("updated_by", "STRING", permissions.cpf),
        bigquery.ScalarQueryParameter("cpf", "STRING", cpf),
    ]

    try:
        execute_query(query, parameters)
        logger.info(f"✅ Usuário marcado como inativo")

        # Invalidar E renovar cache imediatamente
        refresh_governance_cache()

    except Exception as e:
        logger.error(f"❌ Erro ao deletar usuário: {e}")
        raise HTTPException(status_code=500, detail=str(e))
