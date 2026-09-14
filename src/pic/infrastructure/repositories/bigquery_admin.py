from typing import Any

import polars as pl
from google.cloud import bigquery

from src.api.v1.queries import GOVERNANCE_TABLE_QUERY, PARTICIPANTS_TABLE_QUERY
from src.config import env
from src.core.security.permissions_models import IdWithName
from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.infrastructure.admin.governance_cache import refresh_governance_cache
from src.pic.infrastructure.admin.id_utils import _convert_id_list_to_bq_struct
from src.utils.bigquery import build_update_query, execute_query
from src.utils.data_manager import DataManager
from src.utils.log import logger

PROJECT_ID = env.BQ_PROJECT_ID
DATASET_ID = env.BQ_DATASET_ID
TABLE_ID_DATA_ACCESS = env.BQ_TABLE_ID_DATA_ACCESS


class BigQueryAdminRepository(IAdminRepository):
    async def fetch_governance_df(self, bypass_cache: bool = False) -> tuple[pl.DataFrame, Any, Any]:
        return await DataManager.get_dataset(GOVERNANCE_TABLE_QUERY, bypass_cache=bypass_cache)

    async def fetch_participants_df(self, bypass_cache: bool = False) -> tuple[pl.DataFrame, Any, Any]:
        return await DataManager.get_dataset(PARTICIPANTS_TABLE_QUERY, bypass_cache=bypass_cache)

    async def find_paginated_users(
        self,
        filters_dict: dict[str, Any],
        page: int,
        page_size: int,
        search: str | None,
        filter_columns_config: dict[str, Any],
        bypass_cache: bool,
    ) -> tuple[pl.DataFrame, Any, Any]:
        return await DataManager.fetch_filter_paginate(
            query=GOVERNANCE_TABLE_QUERY,
            filters_dict=filters_dict,
            page=page,
            page_size=page_size,
            search_term=search,
            search_columns=["cpf", "nome"] if search else None,
            filter_columns_config=filter_columns_config,
            user_permissions=None,
            bypass_cache=bypass_cache,
        )

    async def find_users_by_cpfs(self, cpfs: list[str]) -> pl.DataFrame:
        cpf_list_sql = ", ".join([f"'{cpf}'" for cpf in cpfs])
        query = (
            f"SELECT cpf, is_admin, is_super_admin "
            f"FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}` "
            f"WHERE cpf IN ({cpf_list_sql})"
        )
        return execute_query(query)

    async def update_user(
        self,
        cpf: str,
        fields: dict[str, Any],
        id_lists: dict[str, list[IdWithName] | None],
        updated_by: str,
    ) -> None:
        update_dict = {**fields}
        update_dict["updated_by"] = updated_by

        struct_updates = []
        for list_key, col_suffix in [
            ("id_cras_list", "id_cras"),
            ("id_escola_list", "id_escola"),
            ("id_cre_list", "id_cre"),
            ("id_ap_list", "id_ap"),
            ("id_cas_list", "id_cas"),
            ("id_clinica_familia_list", "id_clinica_familia"),
            ("id_equipe_familia_list", "id_equipe_familia"),
        ]:
            id_list = id_lists.get(list_key)
            struct_updates.append(
                f"{col_suffix}_list = {_convert_id_list_to_bq_struct(id_list)}"
            )

        if not update_dict and not struct_updates:
            return

        if update_dict:
            query, parameters = build_update_query(
                table=f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}",
                updates=update_dict,
                where_field="cpf",
                where_value=cpf,
            )
            if struct_updates:
                query_parts = query.split("WHERE")
                set_clause = query_parts[0].rstrip()
                set_clause += ",\n        " + ",\n        ".join(struct_updates)
                set_clause += ",\n        updated_at = CURRENT_TIMESTAMP()"
                query = set_clause + "\n    WHERE" + query_parts[1]
            else:
                query_parts = query.split("WHERE")
                set_clause = query_parts[0].rstrip()
                set_clause += ",\n        updated_at = CURRENT_TIMESTAMP()"
                query = set_clause + "\n    WHERE" + query_parts[1]
        else:
            all_updates = struct_updates + ["updated_at = CURRENT_TIMESTAMP()"]
            query = (
                f"UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}` "
                f"SET {', '.join(all_updates)} WHERE cpf = @cpf"
            )
            parameters = [bigquery.ScalarQueryParameter("cpf", "STRING", cpf)]

        execute_query(query, parameters)
        logger.info("Usuario atualizado")

    async def insert_user(
        self,
        cpf: str,
        fields: dict[str, Any],
        id_lists: dict[str, list[IdWithName] | None],
        created_by: str,
    ) -> None:
        id_cras_sql = _convert_id_list_to_bq_struct(id_lists.get("id_cras_list"))
        id_escola_sql = _convert_id_list_to_bq_struct(id_lists.get("id_escola_list"))
        id_cre_sql = _convert_id_list_to_bq_struct(id_lists.get("id_cre_list"))
        id_ap_sql = _convert_id_list_to_bq_struct(id_lists.get("id_ap_list"))
        id_cas_sql = _convert_id_list_to_bq_struct(id_lists.get("id_cas_list"))
        id_clinica_sql = _convert_id_list_to_bq_struct(id_lists.get("id_clinica_familia_list"))
        id_equipe_sql = _convert_id_list_to_bq_struct(id_lists.get("id_equipe_familia_list"))

        secretaria_acesso = fields.get("secretaria_acesso")
        secretaria_acesso_value = None if secretaria_acesso == "NULL" or secretaria_acesso is None else secretaria_acesso

        query = f"""
        INSERT INTO `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
        (cpf, email, nome, ocupacao, secretaria, is_admin, is_super_admin, permission,
         id_cras_list, id_escola_list, id_cre_list, id_ap_list, id_cas_list, id_clinica_familia_list, id_equipe_familia_list,
         secretaria_acesso, created_by, active, notes, created_at)
        VALUES (@cpf, @email, @nome, @ocupacao, @secretaria, @is_admin, @is_super_admin, @permission,
         {id_cras_sql},
         {id_escola_sql},
         {id_cre_sql},
         {id_ap_sql},
         {id_cas_sql},
         {id_clinica_sql},
         {id_equipe_sql},
         @secretaria_acesso, @created_by, @active, @notes, CURRENT_TIMESTAMP())
        """

        parameters = [
            bigquery.ScalarQueryParameter("cpf", "STRING", cpf),
            bigquery.ScalarQueryParameter("email", "STRING", fields.get("email")),
            bigquery.ScalarQueryParameter("nome", "STRING", fields.get("nome")),
            bigquery.ScalarQueryParameter("ocupacao", "STRING", fields.get("ocupacao")),
            bigquery.ScalarQueryParameter("secretaria", "STRING", fields.get("secretaria")),
            bigquery.ScalarQueryParameter("is_admin", "BOOL", fields.get("is_admin", False)),
            bigquery.ScalarQueryParameter("is_super_admin", "BOOL", fields.get("is_super_admin", False)),
            bigquery.ScalarQueryParameter("permission", "STRING", fields.get("permission", "user")),
            bigquery.ScalarQueryParameter("secretaria_acesso", "STRING", secretaria_acesso_value),
            bigquery.ScalarQueryParameter("created_by", "STRING", created_by),
            bigquery.ScalarQueryParameter("active", "BOOL", fields.get("active", True)),
            bigquery.ScalarQueryParameter("notes", "STRING", fields.get("notes")),
        ]

        execute_query(query, parameters)
        logger.info("Usuario criado")

    async def soft_delete_user(self, cpf: str, updated_by: str) -> None:
        query = f"""
        UPDATE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}`
        SET active = @active, updated_by = @updated_by, updated_at = CURRENT_TIMESTAMP()
        WHERE cpf = @cpf
        """
        parameters = [
            bigquery.ScalarQueryParameter("active", "BOOL", False),
            bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
            bigquery.ScalarQueryParameter("cpf", "STRING", cpf),
        ]
        execute_query(query, parameters)
        logger.info("Usuario marcado como inativo")

    async def batch_merge_permissions(
        self,
        valid_users: list[dict[str, Any]],
        is_admin: bool,
        permission: str,
        id_lists: dict[str, list[IdWithName] | None],
        secretaria_acesso: str | None,
        updated_by: str,
    ) -> None:
        id_cras_sql = _convert_id_list_to_bq_struct(id_lists.get("id_cras_list"))
        id_escola_sql = _convert_id_list_to_bq_struct(id_lists.get("id_escola_list"))
        id_cre_sql = _convert_id_list_to_bq_struct(id_lists.get("id_cre_list"))
        id_ap_sql = _convert_id_list_to_bq_struct(id_lists.get("id_ap_list"))
        id_cas_sql = _convert_id_list_to_bq_struct(id_lists.get("id_cas_list"))
        id_clinica_sql = _convert_id_list_to_bq_struct(id_lists.get("id_clinica_familia_list"))
        id_equipe_familia_sql = _convert_id_list_to_bq_struct(id_lists.get("id_equipe_familia_list"))

        if not secretaria_acesso or secretaria_acesso == "NULL":
            secretaria_acesso_sql = "NULL"
        else:
            secretaria_acesso_sql = f"'{secretaria_acesso}'"

        source_rows = [
            f"SELECT '{u['cpf']}' as cpf, {u['nome']} as nome, {u['email']} as email, {u['ocupacao']} as ocupacao, {u['secretaria']} as secretaria"
            for u in valid_users
        ]
        source_query = " UNION ALL ".join(source_rows)

        merge_query = f"""
        MERGE `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID_DATA_ACCESS}` AS T
        USING ({source_query}) AS S
        ON T.cpf = S.cpf
        WHEN MATCHED THEN
            UPDATE SET
                is_admin = {str(is_admin).upper()},
                permission = '{permission}',
                id_cras_list = {id_cras_sql},
                id_escola_list = {id_escola_sql},
                id_cre_list = {id_cre_sql},
                id_ap_list = {id_ap_sql},
                id_cas_list = {id_cas_sql},
                id_clinica_familia_list = {id_clinica_sql},
                id_equipe_familia_list = {id_equipe_familia_sql},
                secretaria_acesso = {secretaria_acesso_sql},
                nome = COALESCE(S.nome, T.nome),
                email = COALESCE(S.email, T.email),
                ocupacao = COALESCE(S.ocupacao, T.ocupacao),
                secretaria = COALESCE(S.secretaria, T.secretaria),
                updated_by = '{updated_by}',
                updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
            INSERT (cpf, nome, email, ocupacao, secretaria, is_admin, is_super_admin, permission,
                    id_cras_list, id_escola_list, id_cre_list, id_ap_list, id_cas_list, id_clinica_familia_list, id_equipe_familia_list,
                    secretaria_acesso, notes, active, created_at, updated_at, created_by, updated_by)
            VALUES (S.cpf, S.nome, S.email, S.ocupacao, S.secretaria, {str(is_admin).upper()},
                    FALSE, '{permission}',
                    {id_cras_sql}, {id_escola_sql}, {id_cre_sql}, {id_ap_sql}, {id_cas_sql}, {id_clinica_sql}, {id_equipe_familia_sql},
                    {secretaria_acesso_sql}, NULL, TRUE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(),
                    '{updated_by}', '{updated_by}')
        """

        logger.info(f"Executando MERGE para {len(valid_users)} usuarios...")
        execute_query(merge_query)
        logger.info("MERGE executado com sucesso")

    async def refresh_cache(self) -> None:
        refresh_governance_cache()
