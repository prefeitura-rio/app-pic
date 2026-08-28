from typing import Any

from src.pic.application.ports.dashboard_repository import IDashboardRepository
from src.pic.domain.models.dashboard import Dashboard
from src.pic.infrastructure.dashboard.factory import _create_empty_dashboard


class DashboardOutput:
    def __init__(self, data: Dashboard, can_view_dashboard: bool = True):
        self.data = data
        self.can_view_dashboard = can_view_dashboard


class GetDashboardUseCase:
    def __init__(self, repository: IDashboardRepository):
        self._repository = repository

    async def execute(
        self,
        permissions: Any,
        user_token: str | None = None,
        grupo: str | None = None,
        cohort: str | None = None,
        status: str | None = None,
        secretaria: str | None = None,
        subprefeitura: str | None = None,
        regiao_administrativa: str | None = None,
        bairro: str | None = None,
        cre: str | None = None,
        ap: str | None = None,
        cas: str | None = None,
        cras: str | None = None,
        escola: str | None = None,
        unidade_saude: str | None = None,
        equipe_saude: str | None = None,
        has_bolsa_familia: bool | None = None,
        bypass_cache: bool = False,
    ) -> DashboardOutput:
        if permissions and permissions.secretaria_acesso != "TODOS":
            return DashboardOutput(
                data=_create_empty_dashboard(),
                can_view_dashboard=False,
            )

        filters = self._build_filters_dict(
            grupo=grupo,
            cohort=cohort,
            status=status,
            subprefeitura=subprefeitura,
            regiao_administrativa=regiao_administrativa,
            bairro=bairro,
            cre=cre,
            ap=ap,
            cas=cas,
            cras=cras,
            escola=escola,
            unidade_saude=unidade_saude,
            equipe_saude=equipe_saude,
            has_bolsa_familia=has_bolsa_familia,
        )

        dashboard = await self._repository.get_dashboard_metrics(
            filters=filters,
            user_token=user_token,
            secretaria=secretaria,
            user_id=permissions.cpf if permissions else None,
            bypass_cache=bypass_cache,
        )

        return DashboardOutput(data=dashboard)

    @staticmethod
    def _parse_multi_select(value: str | None) -> str | list[str] | None:
        if not value:
            return None
        if "|" in value:
            return [v.strip() for v in value.split("|") if v.strip()]
        return value

    @classmethod
    def _build_filters_dict(
        cls,
        grupo: str | None = None,
        cohort: str | None = None,
        status: str | None = None,
        subprefeitura: str | None = None,
        regiao_administrativa: str | None = None,
        bairro: str | None = None,
        cre: str | None = None,
        ap: str | None = None,
        cas: str | None = None,
        cras: str | None = None,
        escola: str | None = None,
        unidade_saude: str | None = None,
        equipe_saude: str | None = None,
        has_bolsa_familia: bool | None = None,
    ) -> dict[str, object]:
        filters: dict[str, object] = {}
        if grupo:
            filters["pic_grupo"] = cls._parse_multi_select(grupo)
        if cohort:
            filters["pic_cohort"] = cls._parse_multi_select(cohort)
        if status:
            filters["pic_status"] = cls._parse_multi_select(status)
        if subprefeitura:
            filters["subprefeitura"] = cls._parse_multi_select(subprefeitura)
        if regiao_administrativa:
            filters["regiao_administrativa"] = cls._parse_multi_select(regiao_administrativa)
        if bairro:
            filters["bairro"] = cls._parse_multi_select(bairro)
        if cre:
            filters["id_cre"] = cls._parse_multi_select(cre)
        if ap:
            filters["id_ap"] = cls._parse_multi_select(ap)
        if cas:
            filters["id_cas"] = cls._parse_multi_select(cas)
        if cras:
            filters["id_cras"] = cls._parse_multi_select(cras)
        if escola:
            filters["id_escola"] = cls._parse_multi_select(escola)
        if unidade_saude:
            filters["id_clinica_familia"] = cls._parse_multi_select(unidade_saude)
        if equipe_saude:
            filters["id_equipe_familia"] = cls._parse_multi_select(equipe_saude)
        if has_bolsa_familia is not None:
            filters["has_bolsa_familia"] = has_bolsa_familia
        return filters
