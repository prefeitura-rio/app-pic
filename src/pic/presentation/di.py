import asyncio

from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.ports.dashboard_repository import IDashboardRepository
from src.pic.application.ports.debug_repository import IDebugRepository
from src.pic.application.ports.geospatial_repository import IGeospatialRepository
from src.pic.application.ports.participant_read_repository import (
    ParticipantRepository,
)
from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.application.use_cases.admin_batch import (
    BatchImportUsersUseCase,
    BatchUpdatePermissionsUseCase,
)
from src.pic.application.use_cases.admin_read import (
    GetAvailableIdsUseCase,
    GetCurrentUserUseCase,
)
from src.pic.application.use_cases.admin_write import (
    DeleteUserUseCase,
    ListUsersUseCase,
    UpsertUserUseCase,
)
from src.pic.application.use_cases.export_participants import ExportParticipantsUseCase
from src.pic.application.use_cases.get_dashboard import GetDashboardUseCase
from src.pic.application.use_cases.get_debug_participant import (
    GetDebugParticipantUseCase,
)
from src.pic.application.use_cases.get_filter_options import (
    GetFilterOptionsUseCase,
)
from src.pic.application.use_cases.get_geospatial_filter_vocabulary import (
    GetGeospatialFilterVocabularyUseCase,
)
from src.pic.application.use_cases.get_geospatial_layers import (
    GetGeospatialLayersUseCase,
)
from src.pic.application.use_cases.get_participant_detail import (
    GetParticipantDetailUseCase,
)
from src.pic.application.use_cases.list_participants import ListParticipantsUseCase
from src.pic.infrastructure.postgrest_client.client import get_postgrest_client
from src.pic.infrastructure.redis_client import get_redis_client
from src.pic.infrastructure.repositories.bigquery_debug import (
    BigQueryDebugRepository,
)
from src.pic.infrastructure.repositories.bigquery_geospatial import (
    BigQueryGeospatialRepository,
)
from src.pic.infrastructure.repositories.bigquery_participant import (
    BigQueryParticipantRepository,
)
from src.pic.infrastructure.repositories.hybrid_admin import (
    HybridAdminRepository,
)
from src.pic.infrastructure.repositories.postgrest_dashboard_repository import (
    PostgrestDashboardRepository,
)
from src.pic.infrastructure.repositories.postgrest_participant_repository import (
    PostgrestParticipantRepository,
)


def get_participant_repo() -> IParticipantRepository:
    """BigQuery-backed repo, still used by the CSV export only."""
    return BigQueryParticipantRepository()


async def get_participant_read_repo() -> ParticipantRepository:
    """PostgREST-backed repo for participant list/detail (data-proxy).

    Redis is used to cache the participant list per user (cpf); when Redis is
    unavailable the repository still works without caching.
    """
    postgrest_client, redis_client = await asyncio.gather(
        get_postgrest_client(),
        get_redis_client(),
    )
    return PostgrestParticipantRepository(
        postgrest_client, redis_client=redis_client
    )


async def get_dashboard_repo() -> IDashboardRepository:
    """PostgREST-backed dashboard repository (V2 hexagonal).

    Both the PostgREST and Redis clients are lazy singletons; the first call
    creates them, subsequent calls reuse the same instance.  If Redis is
    unavailable (URL missing, connection error) ``get_redis_client`` returns
    ``None`` and caching is silently disabled — the request still succeeds.
    """
    postgrest_client, redis_client = await asyncio.gather(
        get_postgrest_client(),
        get_redis_client(),
    )
    return PostgrestDashboardRepository(postgrest_client, redis_client=redis_client)


def get_admin_repo() -> IAdminRepository:
    return HybridAdminRepository()


def get_geospatial_repo() -> IGeospatialRepository:
    return BigQueryGeospatialRepository()


def get_debug_repo() -> IDebugRepository:
    return BigQueryDebugRepository()


async def get_list_participants_use_case() -> ListParticipantsUseCase:
    return ListParticipantsUseCase(repository=await get_participant_read_repo())


async def get_participant_detail_use_case() -> GetParticipantDetailUseCase:
    return GetParticipantDetailUseCase(repository=await get_participant_read_repo())


async def get_filter_options_use_case() -> GetFilterOptionsUseCase:
    return GetFilterOptionsUseCase(repository=await get_participant_read_repo())


async def get_dashboard_use_case() -> GetDashboardUseCase:
    return GetDashboardUseCase(repository=await get_dashboard_repo())


def get_export_participants_use_case() -> ExportParticipantsUseCase:
    return ExportParticipantsUseCase(repository=get_participant_repo())


def get_geospatial_layers_use_case() -> GetGeospatialLayersUseCase:
    return GetGeospatialLayersUseCase(repository=get_geospatial_repo())


def get_geospatial_filter_vocabulary_use_case() -> GetGeospatialFilterVocabularyUseCase:
    return GetGeospatialFilterVocabularyUseCase(repository=get_geospatial_repo())


def get_debug_participant_use_case() -> GetDebugParticipantUseCase:
    return GetDebugParticipantUseCase(repository=get_debug_repo())


def get_current_user_use_case() -> GetCurrentUserUseCase:
    return GetCurrentUserUseCase(repository=get_admin_repo())


def get_available_ids_use_case() -> GetAvailableIdsUseCase:
    return GetAvailableIdsUseCase(repository=get_admin_repo())


def get_list_users_use_case() -> ListUsersUseCase:
    return ListUsersUseCase(repository=get_admin_repo())


def get_upsert_user_use_case() -> UpsertUserUseCase:
    return UpsertUserUseCase(repository=get_admin_repo())


def get_delete_user_use_case() -> DeleteUserUseCase:
    return DeleteUserUseCase(repository=get_admin_repo())


def get_batch_import_users_use_case() -> BatchImportUsersUseCase:
    return BatchImportUsersUseCase(repository=get_admin_repo())


def get_batch_update_permissions_use_case() -> BatchUpdatePermissionsUseCase:
    return BatchUpdatePermissionsUseCase(repository=get_admin_repo())
