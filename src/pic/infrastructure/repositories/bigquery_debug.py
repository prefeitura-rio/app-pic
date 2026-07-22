import polars as pl

from src.api.v1.queries import DEBUG_ORIGINS_QUERY, PARTICIPANTS_TABLE_QUERY
from src.config import env
from src.pic.application.ports.debug_repository import IDebugRepository
from src.pic.domain.models.debug import DebugParticipantResponse
from src.utils.bigquery import execute_query
from src.utils.data_manager import DataManager
from src.utils.log import logger


class BigQueryDebugRepository(IDebugRepository):
    async def search_participant_debug(
        self,
        search_term: str,
        bypass_cache: bool = False,
    ) -> DebugParticipantResponse:
        logger.info(f"Debug search: '{search_term}' (bypass_cache={bypass_cache})")

        df_listagem, _, _ = await DataManager.get_dataset(
            PARTICIPANTS_TABLE_QUERY,
            bypass_cache=bypass_cache,
        )

        logger.info(f"Loaded {len(df_listagem)} participants from listagem")

        search_lower = search_term.lower()
        df_search_results = df_listagem.filter(
            pl.col("cpf").str.to_lowercase().str.contains(search_lower)
            | pl.col("nome").str.to_lowercase().str.contains(search_lower)
            | pl.col("id_membro_familia").str.to_lowercase().str.contains(search_lower)
        )

        total_found = len(df_search_results)
        logger.info(f"Found {total_found} participants matching '{search_term}'")

        if total_found == 0:
            return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

        df_search_results = df_search_results.head(1)

        cpfs_str = df_search_results.select("cpf").to_series().to_list()

        cpfs_particao = []
        for cpf_str in cpfs_str:
            if cpf_str:
                cpf_int = int(cpf_str.replace(".", "").replace("-", ""))
                cpfs_particao.append(cpf_int)

        if not cpfs_particao:
            logger.warning("No valid CPF found")
            return DebugParticipantResponse(total_found=0, total_returned=0, data=[])

        cpf_list_str = ",".join(str(cpf) for cpf in cpfs_particao)
        debug_query = f"""
        SELECT *
        FROM `{env.BQ_PROJECT_ID}.{env.BQ_DATASET_ID}.{env.BQ_TABLE_ID_PARTICIPANTS_DEBUG}`
        WHERE cpf_particao IN ({cpf_list_str})
        ORDER BY nome ASC
        """

        logger.info("Fetching debug data for cpf_particao using partitioned query")
        df_participants = execute_query(debug_query)

        if len(df_participants) == 0:
            logger.warning("No debug data found for CPFs")
            return DebugParticipantResponse(
                total_found=total_found, total_returned=0, data=[]
            )

        df_filtered = df_participants.head(1)
        logger.info("Found debug data for participant")

        try:
            unique_protocolo_ids = (
                df_filtered.select("protocolos")
                .explode("protocolos")
                .select(pl.col("protocolos").struct.field("protocolo_id"))
                .unique()
                .to_series()
                .to_list()
            )
        except Exception as e:
            logger.warning(f"Error extracting protocolo_id: {e}")
            unique_protocolo_ids = []

        logger.info(f"Extracted {len(unique_protocolo_ids)} unique protocolo_id values")

        df_origins, _, _ = await DataManager.get_dataset(
            DEBUG_ORIGINS_QUERY,
            bypass_cache=bypass_cache,
        )

        if len(unique_protocolo_ids) > 0:
            df_origins_filtered = df_origins.filter(
                pl.col("protocolo_id").is_in(unique_protocolo_ids)
            )
        else:
            df_origins_filtered = pl.DataFrame()

        logger.info(f"Filtered to {len(df_origins_filtered)} origin protocols")

        origins_dict = {}
        regras_negocio_dict = {}

        if len(df_origins_filtered) > 0:
            df_origins_exploded = df_origins_filtered.select(
                ["protocolo_id", "tabelas_fonte", "regras_negocio"]
            ).explode("tabelas_fonte")

            for row in df_origins_exploded.to_dicts():
                tabela_fonte = row.get("tabelas_fonte")
                if tabela_fonte:
                    id_origem = tabela_fonte.get("id_origem")
                    if id_origem:
                        origins_dict[id_origem] = {
                            "tabela_bq": tabela_fonte.get("tabela_bq"),
                            "dbt_model_path": tabela_fonte.get("dbt_model_path"),
                            "dbt_model_type": tabela_fonte.get("dbt_model_type"),
                            "updated_at": tabela_fonte.get("updated_at"),
                            "dados_schema": tabela_fonte.get("dados_schema"),
                        }

            for row in df_origins_filtered.to_dicts():
                protocolo_id = row.get("protocolo_id")
                regras_negocio = row.get("regras_negocio")
                if protocolo_id and regras_negocio:
                    regras_negocio_dict[protocolo_id] = regras_negocio

        result = df_filtered.to_dicts()[0]

        for protocolo in result.get("protocolos", []):
            protocolo_id = protocolo.get("protocolo_id")
            if protocolo_id and protocolo_id in regras_negocio_dict:
                protocolo["regras_negocio"] = regras_negocio_dict[protocolo_id]

            for metadata_item in protocolo.get("metadata", []):
                id_origem = metadata_item.get("id_origem")
                if id_origem and id_origem in origins_dict:
                    metadata_item.update(origins_dict[id_origem])

        logger.info(f"Returning enriched participant data ({total_found} found, returning 1)")

        return DebugParticipantResponse(
            total_found=total_found,
            total_returned=1,
            data=[result],
        )
