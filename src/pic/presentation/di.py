from src.pic.application.ports.admin_repository import IAdminRepository
from src.pic.application.ports.dashboard_repository import IDashboardRepository
from src.pic.application.ports.debug_repository import IDebugRepository
from src.pic.application.ports.geospatial_repository import IGeospatialRepository
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
from src.pic.application.use_cases.get_dashboard import GetDashboardUseCase
from src.pic.application.use_cases.get_debug_participant import (
    GetDebugParticipantUseCase,
)
from src.pic.application.use_cases.get_filter_vocabulary import (
    GetFilterVocabularyUseCase,
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
from src.pic.infrastructure.repositories.bigquery_admin import (
    BigQueryAdminRepository,
)
from src.pic.infrastructure.repositories.bigquery_dashboard import (
    BigQueryDashboardRepository,
)
from src.pic.infrastructure.repositories.bigquery_debug import (
    BigQueryDebugRepository,
)
from src.pic.infrastructure.repositories.bigquery_geospatial import (
    BigQueryGeospatialRepository,
)
from src.pic.infrastructure.repositories.bigquery_participant import (
    BigQueryParticipantRepository,
)


def get_participant_repo() -> IParticipantRepository:
    return BigQueryParticipantRepository()


def get_dashboard_repo() -> IDashboardRepository:
    return BigQueryDashboardRepository()


def get_admin_repo() -> IAdminRepository:
    return BigQueryAdminRepository()


def get_geospatial_repo() -> IGeospatialRepository:
    return BigQueryGeospatialRepository()


def get_debug_repo() -> IDebugRepository:
    return BigQueryDebugRepository()


def get_list_participants_use_case() -> ListParticipantsUseCase:
    return ListParticipantsUseCase(repository=get_participant_repo())


def get_participant_detail_use_case() -> GetParticipantDetailUseCase:
    return GetParticipantDetailUseCase(repository=get_participant_repo())


def get_filter_vocabulary_use_case() -> GetFilterVocabularyUseCase:
    return GetFilterVocabularyUseCase(repository=get_participant_repo())


def get_dashboard_use_case() -> GetDashboardUseCase:
    return GetDashboardUseCase(repository=get_dashboard_repo())


def get_geospatial_layers_use_case() -> GetGeospatialLayersUseCase:
    return GetGeospatialLayersUseCase(repository=get_geospatial_repo())


def get_geospatial_filter_vocabulary_use_case() -> GetGeospatialFilterVocabularyUseCase:
    return GetGeospatialFilterVocabularyUseCase(repository=get_geospatial_repo())


def get_debug_participant_use_case() -> GetDebugParticipantUseCase:
    return GetDebugParticipantUseCase(repository=get_debug_repo())


def get_current_user_use_case() -> GetCurrentUserUseCase:
    return GetCurrentUserUseCase()


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
