
import polars as pl
from fastapi import HTTPException

from src.core.security.permissions_models import IdWithName, UserPermissions
from src.utils.log import logger


def require_admin(permissions: UserPermissions):
    if not permissions.is_admin and not permissions.is_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado: apenas admins podem gerenciar usuarios",
        )


def calculate_permission(is_admin: bool, is_super_admin: bool) -> str:
    if is_super_admin:
        return "super_admin"
    elif is_admin:
        return "admin"
    else:
        return "user"


def _sanitize_cpf(cpf_raw: str) -> str:
    if not cpf_raw:
        return ""
    digits = "".join(c for c in str(cpf_raw) if c.isdigit())
    if digits and len(digits) < 11:
        digits = digits.zfill(11)
    return digits


def _validate_cpf(cpf: str) -> str | None:
    if not cpf:
        return "CPF vazio"
    if len(cpf) != 11:
        return f"CPF deve ter 11 digitos (tem {len(cpf)})"
    if not cpf.isdigit():
        return "CPF deve conter apenas numeros"
    return None


def _filter_manageable_users(df: pl.DataFrame, admin_permissions: UserPermissions) -> pl.DataFrame:
    if df.is_empty():
        return df

    logger.info("Verificando permissoes do admin:")
    logger.info(f"  - is_super_admin: {admin_permissions.is_super_admin}")
    logger.info(f"  - is_admin: {admin_permissions.is_admin}")
    logger.info(f"  - secretarias_acesso: {admin_permissions.secretarias_acesso}")

    has_any_ids = any([
        admin_permissions.id_cras_list,
        admin_permissions.id_escola_list,
        admin_permissions.id_cre_list,
        admin_permissions.id_ap_list,
        admin_permissions.id_cas_list,
        admin_permissions.id_clinica_familia_list,
        admin_permissions.id_equipe_familia_list,
    ])

    if not has_any_ids:
        logger.warning("Admin nao possui nenhum ID - nao pode gerenciar usuarios")
        return df.head(0)

    df_non_super_admin = df.filter(~pl.col("is_super_admin"))

    # Boundary rule: an admin can only manage users whose secretarias_acesso
    # is a SUBSET of the admin's own secretarias_acesso (a user with no
    # protocol access, i.e. empty list, is always manageable since {} is a
    # subset of any set).
    admin_secretarias = admin_permissions.secretarias_acesso or []
    df_non_super_admin = df_non_super_admin.filter(
        pl.col("secretarias_acesso")
        .list.eval(pl.element().is_in(admin_secretarias))
        .list.all()
    )

    if df_non_super_admin.is_empty():
        return df.head(0)

    admin_id_sets = {
        "id_cras": set(admin_permissions.get_filter_ids("id_cras")),
        "id_escola": set(admin_permissions.get_filter_ids("id_escola")),
        "id_cre": set(admin_permissions.get_filter_ids("id_cre")),
        "id_ap": set(admin_permissions.get_filter_ids("id_ap")),
        "id_cas": set(admin_permissions.get_filter_ids("id_cas")),
        "id_clinica_familia": set(admin_permissions.get_filter_ids("id_clinica_familia")),
        "id_equipe_familia": set(admin_permissions.get_filter_ids("id_equipe_familia")),
    }

    manageable_cpfs = []
    for row in df_non_super_admin.to_dicts():
        is_manageable = True

        for id_type in [
            "id_cras", "id_escola", "id_cre", "id_ap", "id_cas",
            "id_clinica_familia", "id_equipe_familia",
        ]:
            list_key = f"{id_type}_list"
            user_id_list = row.get(list_key)
            admin_ids = admin_id_sets[id_type]

            if user_id_list is None or (isinstance(user_id_list, list) and len(user_id_list) == 0):
                continue

            user_ids = set()
            for item in user_id_list if isinstance(user_id_list, list) else []:
                if isinstance(item, dict):
                    user_ids.add(item.get("id"))

            if user_ids and not admin_ids:
                is_manageable = False
                break

            if user_ids and not user_ids.issubset(admin_ids):
                is_manageable = False
                break

        if is_manageable:
            manageable_cpfs.append(row["cpf"])

    df_filtered = df_non_super_admin.filter(pl.col("cpf").is_in(manageable_cpfs))
    logger.info(f"Admin segmentado - Usuarios gerenciáveis: {len(df)} -> {len(df_filtered)}")
    return df_filtered


def validate_equipment_secretaria_consistency(
    target_ids: dict[str, list[IdWithName]], target_secretarias_acesso: list[str] | None
):
    from src.utils.constants import SECRETARIA_EQUIPMENT, SECRETARIA_EQUIPMENT_LABELS

    secretarias = set(target_secretarias_acesso or [])

    # No protocol access, or full access (all secretarias) -> no equipment
    # restriction (the old NULL/TODOS cases).
    if not secretarias or secretarias >= set(SECRETARIA_EQUIPMENT.keys()):
        return

    # Union of every allowed equipment across all of the target's secretarias.
    allowed: set[str] = set()
    for secretaria in secretarias:
        allowed.update(SECRETARIA_EQUIPMENT.get(secretaria, []))

    equipment_names = {
        "id_cre_list": "CRE", "id_escola_list": "Escolas",
        "id_ap_list": "AP", "id_clinica_familia_list": "Clinicas",
        "id_cas_list": "CAS", "id_cras_list": "CRAS",
    }

    for id_type, id_list in target_ids.items():
        if id_list and len(id_list) > 0:
            if id_type not in allowed:
                equipment_name = equipment_names.get(id_type, id_type)
                allowed_names = ", ".join(
                    SECRETARIA_EQUIPMENT_LABELS.get(s, s) for s in sorted(secretarias)
                )
                secretarias_label = ", ".join(sorted(secretarias))
                raise HTTPException(
                    status_code=400,
                    detail=f"Inconsistencia: Nao e permitido atribuir {equipment_name} "
                    f"para usuario com acesso a {secretarias_label}. "
                    f"Usuarios com este acesso so podem ter: {allowed_names}.",
                )


def validate_secretarias_acesso_permission(
    admin_permissions: UserPermissions, target_secretarias_acesso: list[str] | None
):
    """An admin can only grant a subset of the secretarias_acesso they
    themselves have. Super admins (implicitly full access) can grant any
    combination."""
    if admin_permissions.is_super_admin:
        return

    target_set = set(target_secretarias_acesso or [])
    if not target_set:
        return

    admin_set = set(admin_permissions.secretarias_acesso or [])

    if not admin_set:
        raise HTTPException(
            status_code=403,
            detail="Voce nao possui acesso a protocolos e nao pode atribuir acesso a outros usuarios",
        )

    if not target_set.issubset(admin_set):
        raise HTTPException(
            status_code=403,
            detail=f"Voce so pode atribuir secretarias que voce mesmo possui: {sorted(admin_set)}",
        )


def validate_segmented_admin_can_manage(
    admin_permissions: UserPermissions, target_ids: dict[str, list[IdWithName]]
):
    if admin_permissions.is_super_admin:
        return

    has_any_ids = any([
        admin_permissions.id_cras_list,
        admin_permissions.id_escola_list,
        admin_permissions.id_cre_list,
        admin_permissions.id_ap_list,
        admin_permissions.id_cas_list,
        admin_permissions.id_clinica_familia_list,
        admin_permissions.id_equipe_familia_list,
    ])

    if not has_any_ids and target_ids:
        raise HTTPException(
            status_code=403,
            detail="Voce nao possui IDs para distribuir.",
        )

    for id_type in [
        "id_cras", "id_escola", "id_cre", "id_ap", "id_cas",
        "id_clinica_familia", "id_equipe_familia",
    ]:
        list_key = f"{id_type}_list"
        target_list = target_ids.get(list_key)

        if not target_list:
            continue

        admin_ids = set(admin_permissions.get_filter_ids(id_type))

        if not admin_ids:
            raise HTTPException(
                status_code=403,
                detail=f"Voce nao tem permissao para atribuir {id_type}",
            )

        target_ids_set = set()
        for item in target_list:
            id_value = None
            if isinstance(item, dict):
                id_value = item.get("id")
            elif hasattr(item, "id"):
                id_value = item.id
            else:
                id_value = str(item)

            if id_value:
                for single_id in str(id_value).split(","):
                    single_id = single_id.strip()
                    if single_id:
                        target_ids_set.add(single_id)

        unauthorized_ids = target_ids_set - admin_ids
        if unauthorized_ids:
            raise HTTPException(
                status_code=403,
                detail=f"Voce nao pode atribuir estes {id_type}: {unauthorized_ids}",
            )
