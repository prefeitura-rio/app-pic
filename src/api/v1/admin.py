"""
Admin endpoints para gerenciamento de governança de dados.

Permite admins criar/editar/deletar permissões de CPFs, controlando
quais IDs (CRAS, escolas, CRE, etc) cada usuário pode acessar.

REGRAS:
- Super admin: Acesso total, pode gerenciar qualquer usuário
- Admin segmentado: Só pode atribuir IDs que ele mesmo possui
- Auditoria completa: created_by, updated_by em todas as operações
"""

from fastapi import APIRouter, HTTPException, Query
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
    is_admin: bool = False
    is_super_admin: bool = False

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


# Mantidos para compatibilidade (deprecated)
class CreateUserRequest(UpsertUserRequest):
    """[DEPRECATED] Use PUT /users/{cpf} ao invés de POST /users"""

    cpf: str = Field(
        ..., min_length=11, max_length=11, description="CPF sem pontos ou traços"
    )


class UpdateUserRequest(BaseModel):
    """[DEPRECATED] Use PUT /users/{cpf} ao invés de PATCH /users/{cpf}"""

    is_admin: Optional[bool] = None

    id_cras_list: Optional[List[IdWithName]] = None
    id_escola_list: Optional[List[IdWithName]] = None
    id_cre_list: Optional[List[IdWithName]] = None
    id_cap_list: Optional[List[IdWithName]] = None
    id_cas_list: Optional[List[IdWithName]] = None
    id_clinica_familia_list: Optional[List[IdWithName]] = None

    notes: Optional[str] = None
    active: Optional[bool] = None


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


@router.get("/users", response_model=List[UserAccessRecord])
async def list_users(
    permissions: CurrentUserPermissions,
    active_only: bool = Query(True, description="Filtrar apenas usuários ativos"),
):
    """
    Lista usuários que o admin pode gerenciar.

    REGRAS:
    - Super admin: Vê todos os usuários
    - Admin segmentado: Vê apenas usuários com subset de seus IDs

    OTIMIZAÇÃO: Usa get_dataset() com cache compartilhado.
    """
    require_admin(permissions)

    logger.info(
        f"Admin {permissions.cpf} listando usuários (active_only={active_only})"
    )

    try:
        # Query da tabela de governança (usa cache do DataManager)
        users_df, cache_hit = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
        logger.info(f"Governance table fetched (cache_hit={cache_hit})")

        # Filtrar por status ativo se solicitado (em memória)
        if active_only:
            users_df = users_df[users_df["active"] == True]

        # Super admin vê todos
        if permissions.is_super_admin:
            pass  # Já tem todos os dados
        else:
            # Admin segmentado: filtrar usuários que ele pode gerenciar
            # (usuários que só têm IDs que são subset dos IDs do admin)
            # Por simplicidade inicial, vamos mostrar todos e validar na edição
            # TODO: Implementar filtro mais sofisticado se necessário
            pass

        # Converter para lista de UserAccessRecord
        users = []
        for _, row in users_df.iterrows():
            # Converter row para dict, tratando STRUCT arrays
            row_dict = row.to_dict()

            # Sanitizar valores NaN/NA do pandas (converte para None)
            for key, value in row_dict.items():
                # Verificar se não é lista/array antes de chamar pd.isna
                if not isinstance(value, (list, dict)):
                    try:
                        if pd.isna(value):
                            row_dict[key] = None
                    except (ValueError, TypeError):
                        # Se pd.isna falhar, deixar o valor como está
                        pass

            # Converter booleanos explicitamente (pandas pode retornar float/int)
            if "active" in row_dict and row_dict["active"] is not None:
                row_dict["active"] = bool(row_dict["active"])
            if "is_admin" in row_dict and row_dict["is_admin"] is not None:
                row_dict["is_admin"] = bool(row_dict["is_admin"])
            if "is_super_admin" in row_dict and row_dict["is_super_admin"] is not None:
                row_dict["is_super_admin"] = bool(row_dict["is_super_admin"])

            # Converter timestamps para datetime (pandas pode retornar Timestamp)
            if "created_at" in row_dict and row_dict["created_at"] is not None:
                if hasattr(row_dict["created_at"], "to_pydatetime"):
                    row_dict["created_at"] = row_dict["created_at"].to_pydatetime()
            if "updated_at" in row_dict and row_dict["updated_at"] is not None:
                if hasattr(row_dict["updated_at"], "to_pydatetime"):
                    row_dict["updated_at"] = row_dict["updated_at"].to_pydatetime()

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
                if row_dict.get(list_key) is not None:
                    # Se é lista de dicts (do BigQuery STRUCT)
                    if isinstance(row_dict[list_key], list):
                        row_dict[list_key] = [
                            IdWithName(**item) if isinstance(item, dict) else item
                            for item in row_dict[list_key]
                        ]

            try:
                users.append(UserAccessRecord(**row_dict))
            except Exception as e:
                logger.error(f"Erro ao converter usuário {row_dict.get('cpf')}: {e}")
                logger.error(
                    f"Row dict types: {[(k, type(v)) for k, v in row_dict.items()]}"
                )
                raise

        logger.info(f"Retornando {len(users)} usuários")
        return users

    except Exception as e:
        logger.error(f"Erro ao listar usuários: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{cpf}", response_model=UserAccessRecord)
async def upsert_user(
    cpf: str, request: UpsertUserRequest, permissions: CurrentUserPermissions
):
    """
    Cria ou atualiza usuário (UPSERT).

    Se o CPF já existe:
    - Atualiza as permissões especificadas
    - Auditoria: updated_by, updated_at

    Se o CPF não existe:
    - Cria novo usuário
    - Auditoria: created_by, created_at

    VALIDAÇÕES:
    - Admin segmentado só pode atribuir IDs que ele possui
    - Super admin pode atribuir qualquer ID
    """
    require_admin(permissions)

    # Validar CPF format
    if len(cpf) != 11 or not cpf.isdigit():
        raise HTTPException(
            status_code=400, detail="CPF deve conter exatamente 11 dígitos"
        )

    logger.info(f"Admin {permissions.cpf} fazendo upsert do usuário {cpf}")

    # Validar que apenas super admin pode definir is_super_admin
    if request.is_super_admin and not permissions.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Apenas super admins podem criar ou promover outros super admins",
        )

    # Validar que admin pode atribuir esses IDs
    target_ids = request.model_dump(
        include={
            "id_cras_list",
            "id_escola_list",
            "id_cre_list",
            "id_cap_list",
            "id_cas_list",
            "id_clinica_familia_list",
        }
    )
    validate_segmented_admin_can_manage(permissions, target_ids)

    # Verificar se CPF já existe (usa cache da tabela de governança)
    governance_df, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
    user_exists = not governance_df[governance_df["cpf"] == cpf].empty

    # Converter listas de IDs para formato BigQuery
    id_cras_sql = _convert_id_list_to_bq_struct(request.id_cras_list)
    id_escola_sql = _convert_id_list_to_bq_struct(request.id_escola_list)
    id_cre_sql = _convert_id_list_to_bq_struct(request.id_cre_list)
    id_cap_sql = _convert_id_list_to_bq_struct(request.id_cap_list)
    id_cas_sql = _convert_id_list_to_bq_struct(request.id_cas_list)
    id_clinica_sql = _convert_id_list_to_bq_struct(request.id_clinica_familia_list)

    notes_sql = (
        f"'{request.notes.replace(chr(39), chr(92)+chr(39))}'"
        if request.notes
        else "NULL"
    )

    try:
        if user_exists:
            # UPDATE - Usuário já existe
            logger.info(f"Atualizando usuário existente: {cpf}")

            query = f"""
            UPDATE `{PROJECT_ID}.{DATASET_ID}.data_access`
            SET
                is_admin = {str(request.is_admin).upper()},
                is_super_admin = {str(request.is_super_admin).upper()},
                id_cras_list = {id_cras_sql},
                id_escola_list = {id_escola_sql},
                id_cre_list = {id_cre_sql},
                id_cap_list = {id_cap_sql},
                id_cas_list = {id_cas_sql},
                id_clinica_familia_list = {id_clinica_sql},
                notes = {notes_sql},
                active = {str(request.active).upper()},
                updated_by = '{permissions.cpf}',
                updated_at = CURRENT_TIMESTAMP()
            WHERE cpf = '{cpf}'
            """
            execute_query(query)
            logger.info(
                f"✅ Usuário {cpf} atualizado com sucesso por {permissions.cpf}"
            )

        else:
            # INSERT - Novo usuário
            logger.info(f"Criando novo usuário: {cpf}")

            query = f"""
            INSERT INTO `{PROJECT_ID}.{DATASET_ID}.data_access`
            (
                cpf,
                is_admin,
                is_super_admin,
                id_cras_list,
                id_escola_list,
                id_cre_list,
                id_cap_list,
                id_cas_list,
                id_clinica_familia_list,
                created_by,
                active,
                notes,
                created_at
            )
            VALUES (
                '{cpf}',
                {str(request.is_admin).upper()},
                {str(request.is_super_admin).upper()},
                {id_cras_sql},
                {id_escola_sql},
                {id_cre_sql},
                {id_cap_sql},
                {id_cas_sql},
                {id_clinica_sql},
                '{permissions.cpf}',
                {str(request.active).upper()},
                {notes_sql},
                CURRENT_TIMESTAMP()
            )
            """
            execute_query(query)
            logger.info(f"✅ Usuário {cpf} criado com sucesso por {permissions.cpf}")

        # Invalidar E renovar cache imediatamente
        refresh_governance_cache()

        # Buscar usuário para retornar
        governance_df, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
        user_row = governance_df[governance_df["cpf"] == cpf]

        if user_row.empty:
            raise HTTPException(
                status_code=500,
                detail=f"Usuário {cpf} foi salvo mas não foi encontrado no cache renovado",
            )

        # Converter para UserAccessRecord
        row_dict = user_row.iloc[0].to_dict()

        # Sanitizar valores
        for key, value in row_dict.items():
            if not isinstance(value, (list, dict)):
                try:
                    if pd.isna(value):
                        row_dict[key] = None
                except (ValueError, TypeError):
                    pass

        # Converter booleanos
        if "active" in row_dict and row_dict["active"] is not None:
            row_dict["active"] = bool(row_dict["active"])
        if "is_admin" in row_dict and row_dict["is_admin"] is not None:
            row_dict["is_admin"] = bool(row_dict["is_admin"])
        if "is_super_admin" in row_dict and row_dict["is_super_admin"] is not None:
            row_dict["is_super_admin"] = bool(row_dict["is_super_admin"])

        # Converter timestamps
        if "created_at" in row_dict and row_dict["created_at"] is not None:
            if hasattr(row_dict["created_at"], "to_pydatetime"):
                row_dict["created_at"] = row_dict["created_at"].to_pydatetime()
        if "updated_at" in row_dict and row_dict["updated_at"] is not None:
            if hasattr(row_dict["updated_at"], "to_pydatetime"):
                row_dict["updated_at"] = row_dict["updated_at"].to_pydatetime()

        # Converter arrays de structs
        for id_type in [
            "id_cras",
            "id_escola",
            "id_cre",
            "id_cap",
            "id_cas",
            "id_clinica_familia",
        ]:
            list_key = f"{id_type}_list"
            if row_dict.get(list_key) is not None:
                if isinstance(row_dict[list_key], list):
                    row_dict[list_key] = [
                        IdWithName(**item) if isinstance(item, dict) else item
                        for item in row_dict[list_key]
                    ]

        return UserAccessRecord(**row_dict)

    except Exception as e:
        logger.error(f"Erro ao fazer upsert do usuário {cpf}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users", response_model=UserAccessRecord, status_code=201)
async def create_user(request: CreateUserRequest, permissions: CurrentUserPermissions):
    """
    Cria novo usuário com permissões especificadas.

    VALIDAÇÕES:
    - CPF não pode já existir
    - Admin segmentado só pode atribuir IDs que ele possui
    - Super admin pode atribuir qualquer ID
    """
    require_admin(permissions)

    logger.info(f"Admin {permissions.cpf} criando usuário {request.cpf}")

    # Validar que admin pode atribuir esses IDs
    target_ids = request.model_dump(
        include={
            "id_cras_list",
            "id_escola_list",
            "id_cre_list",
            "id_cap_list",
            "id_cas_list",
            "id_clinica_familia_list",
        }
    )
    validate_segmented_admin_can_manage(permissions, target_ids)

    # Verificar se CPF já existe (usa cache da tabela de governança)
    governance_df, _ = DataManager.get_dataset(GOVERNANCE_TABLE_QUERY)
    if not governance_df[governance_df["cpf"] == request.cpf].empty:
        raise HTTPException(
            status_code=409, detail=f"CPF {request.cpf} já está cadastrado"
        )

    # Converter listas de IDs para formato BigQuery
    id_cras_sql = _convert_id_list_to_bq_struct(request.id_cras_list)
    id_escola_sql = _convert_id_list_to_bq_struct(request.id_escola_list)
    id_cre_sql = _convert_id_list_to_bq_struct(request.id_cre_list)
    id_cap_sql = _convert_id_list_to_bq_struct(request.id_cap_list)
    id_cas_sql = _convert_id_list_to_bq_struct(request.id_cas_list)
    id_clinica_sql = _convert_id_list_to_bq_struct(request.id_clinica_familia_list)

    notes_sql = f"'{request.notes}'" if request.notes else "NULL"

    # INSERT no BigQuery
    query = f"""
    INSERT INTO `{PROJECT_ID}.{DATASET_ID}.data_access`
    (
        cpf,
        is_admin,
        is_super_admin,
        id_cras_list,
        id_escola_list,
        id_cre_list,
        id_cap_list,
        id_cas_list,
        id_clinica_familia_list,
        created_by,
        active,
        notes,
        created_at
    )
    VALUES (
        '{request.cpf}',
        {str(request.is_admin).upper()},
        FALSE,
        {id_cras_sql},
        {id_escola_sql},
        {id_cre_sql},
        {id_cap_sql},
        {id_cas_sql},
        {id_clinica_sql},
        '{permissions.cpf}',
        TRUE,
        {notes_sql},
        CURRENT_TIMESTAMP()
    )
    """

    try:
        execute_query(query)
        logger.info(
            f"✅ Usuário {request.cpf} criado com sucesso por {permissions.cpf}"
        )

        # Invalidar E renovar cache imediatamente
        refresh_governance_cache()

        # Buscar usuário criado para retornar
        created_user = DataManager.get_user_permissions(request.cpf)

        return UserAccessRecord(
            cpf=created_user.cpf,
            is_admin=created_user.is_admin,
            is_super_admin=created_user.is_super_admin,
            id_cras_list=created_user.id_cras_list,
            id_escola_list=created_user.id_escola_list,
            id_cre_list=created_user.id_cre_list,
            id_cap_list=created_user.id_cap_list,
            id_cas_list=created_user.id_cas_list,
            id_clinica_familia_list=created_user.id_clinica_familia_list,
            active=created_user.active,
            notes=created_user.notes,
            created_by=permissions.cpf,
            created_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(f"Erro ao criar usuário: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{cpf}", response_model=UserAccessRecord)
async def update_user(
    cpf: str, request: UpdateUserRequest, permissions: CurrentUserPermissions
):
    """
    Atualiza permissões de um usuário existente.

    REGRAS:
    - Não pode alterar is_super_admin (apenas via script direto)
    - Admin segmentado só pode atribuir IDs que ele possui
    - Auditoria: updated_by, updated_at
    """
    require_admin(permissions)

    logger.info(f"Admin {permissions.cpf} atualizando usuário {cpf}")

    # Verificar que usuário existe
    try:
        existing_user = DataManager.get_user_permissions(cpf)
    except:
        raise HTTPException(status_code=404, detail=f"Usuário {cpf} não encontrado")

    # Validar que admin pode atribuir esses IDs
    target_ids = request.model_dump(
        include={
            "id_cras_list",
            "id_escola_list",
            "id_cre_list",
            "id_cap_list",
            "id_cas_list",
            "id_clinica_familia_list",
        },
        exclude_none=True,
    )
    if target_ids:
        validate_segmented_admin_can_manage(permissions, target_ids)

    # Construir SET clauses dinamicamente
    set_clauses = []

    if request.is_admin is not None:
        set_clauses.append(f"is_admin = {str(request.is_admin).upper()}")

    if request.id_cras_list is not None:
        set_clauses.append(
            f"id_cras_list = {_convert_id_list_to_bq_struct(request.id_cras_list)}"
        )

    if request.id_escola_list is not None:
        set_clauses.append(
            f"id_escola_list = {_convert_id_list_to_bq_struct(request.id_escola_list)}"
        )

    if request.id_cre_list is not None:
        set_clauses.append(
            f"id_cre_list = {_convert_id_list_to_bq_struct(request.id_cre_list)}"
        )

    if request.id_cap_list is not None:
        set_clauses.append(
            f"id_cap_list = {_convert_id_list_to_bq_struct(request.id_cap_list)}"
        )

    if request.id_cas_list is not None:
        set_clauses.append(
            f"id_cas_list = {_convert_id_list_to_bq_struct(request.id_cas_list)}"
        )

    if request.id_clinica_familia_list is not None:
        set_clauses.append(
            f"id_clinica_familia_list = {_convert_id_list_to_bq_struct(request.id_clinica_familia_list)}"
        )

    if request.active is not None:
        set_clauses.append(f"active = {str(request.active).upper()}")

    if request.notes is not None:
        notes_escaped = request.notes.replace("'", "\\'")
        set_clauses.append(f"notes = '{notes_escaped}'")

    # Sempre atualizar auditoria
    set_clauses.append(f"updated_by = '{permissions.cpf}'")
    set_clauses.append("updated_at = CURRENT_TIMESTAMP()")

    if not set_clauses:
        raise HTTPException(status_code=400, detail="Nenhuma alteração fornecida")

    # UPDATE no BigQuery
    query = f"""
    UPDATE `{PROJECT_ID}.{DATASET_ID}.data_access`
    SET {', '.join(set_clauses)}
    WHERE cpf = '{cpf}'
    """

    try:
        execute_query(query)
        logger.info(f"✅ Usuário {cpf} atualizado com sucesso por {permissions.cpf}")

        # Invalidar E renovar cache imediatamente
        refresh_governance_cache()

        # Buscar usuário atualizado para retornar
        updated_user = DataManager.get_user_permissions(cpf)

        return UserAccessRecord(
            cpf=updated_user.cpf,
            is_admin=updated_user.is_admin,
            is_super_admin=updated_user.is_super_admin,
            id_cras_list=updated_user.id_cras_list,
            id_escola_list=updated_user.id_escola_list,
            id_cre_list=updated_user.id_cre_list,
            id_cap_list=updated_user.id_cap_list,
            id_cas_list=updated_user.id_cas_list,
            id_clinica_familia_list=updated_user.id_clinica_familia_list,
            active=updated_user.active,
            notes=updated_user.notes,
            created_by=existing_user.cpf,  # Preservar original
            created_at=datetime.now(
                timezone.utc
            ),  # Aproximação (não temos o original aqui)
            updated_by=permissions.cpf,
            updated_at=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(f"Erro ao atualizar usuário: {e}")
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
