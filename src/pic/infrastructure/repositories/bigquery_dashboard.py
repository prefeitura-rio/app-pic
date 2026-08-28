from src.api.v1.queries import DASHBOARD_TABLE_QUERY
from src.pic.application.ports.dashboard_repository import IDashboardRepository
from src.pic.domain.models.dashboard import Dashboard
from src.pic.infrastructure.dashboard.compute import _calculate_dashboard_metrics
from src.pic.infrastructure.dashboard.config import DASHBOARD_FILTER_OPTIONS_CONFIG
from src.pic.infrastructure.dashboard.factory import _create_empty_dashboard
from src.utils.data_manager import DataManager
from src.utils.log import logger


class BigQueryDashboardRepository(IDashboardRepository):
    async def get_dashboard_metrics(
        self,
        filters: dict[str, object],
        user_token: str | None = None,
        secretaria: str | None = None,
        user_id: str | None = None,
        bypass_cache: bool = False,
    ) -> Dashboard:
        try:
            df, _, _ = await DataManager.fetch_filter_paginate(
                query=DASHBOARD_TABLE_QUERY,
                filters_dict=filters,
                page=1,
                page_size=None,
                filter_columns_config=DASHBOARD_FILTER_OPTIONS_CONFIG,
                user_permissions=None,
                bypass_cache=bypass_cache,
            )
        except Exception as e:
            logger.error(f"Error fetching dashboard data: {e}", exc_info=True)
            raise

        if df.is_empty():
            return _create_empty_dashboard()

        return _calculate_dashboard_metrics(df, filtro_secretaria=secretaria)
