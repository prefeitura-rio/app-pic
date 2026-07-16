from src.pic.application.ports.participant_repository import IParticipantRepository
from src.pic.application.use_cases.get_filter_vocabulary import (
    GetFilterVocabularyUseCase,
)
from src.pic.application.use_cases.get_participant_detail import (
    GetParticipantDetailUseCase,
)
from src.pic.application.use_cases.list_participants import ListParticipantsUseCase
from src.pic.infrastructure.repositories.bigquery_participant import (
    BigQueryParticipantRepository,
)


def get_participant_repo() -> IParticipantRepository:
    return BigQueryParticipantRepository()


def get_list_participants_use_case() -> ListParticipantsUseCase:
    return ListParticipantsUseCase(repository=get_participant_repo())


def get_participant_detail_use_case() -> GetParticipantDetailUseCase:
    return GetParticipantDetailUseCase(repository=get_participant_repo())


def get_filter_vocabulary_use_case() -> GetFilterVocabularyUseCase:
    return GetFilterVocabularyUseCase(repository=get_participant_repo())
