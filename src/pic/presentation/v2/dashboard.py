import time

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.v1.dashboard import (
    DASHBOARD_FILTER_OPTIONS_CONFIG,
    _calculate_dashboard_metrics,
    _create_empty_dashboard,
)
from src.api.v1.queries import DASHBOARD_TABLE_QUERY
from src.core.security.jwt import CurrentUserPermissions, verify_jwt
from src.pic.presentation.v2.schemas import DashboardV2Response
from src.utils.data_manager import DataManager
from src.utils.log import logger

router = APIRouter(dependencies=[Depends(verify_jwt)], tags=["Dashboard V2"])


def _parse_multi_select(value: str | None) -> str | list[str] | None:
    if not value:
        return None
    if "|" in value:
        return [v.strip() for v in value.split("|") if v.strip()]
    return value


@router.get(
    "/dashboard",
    summary="Metricas do Dashboard (V2 — sem filtros inline)",
    response_model=DashboardV2Response,
)
async def get_dashboard(
    permissions: CurrentUserPermissions,
    grupo: str | None = Query(None),
    cohort: str | None = Query(None),
    status: str | None = Query(None),
    secretaria: str | None = Query(None),
    subprefeitura: str | None = Query(None),
    regiao_administrativa: str | None = Query(None),
    bairro: str | None = Query(None),
    cre: str | None = Query(None),
    ap: str | None = Query(None),
    cas: str | None = Query(None),
    cras: str | None = Query(None),
    escola: str | None = Query(None),
    unidade_saude: str | None = Query(None),
    equipe_saude: str | None = Query(None),
    has_bolsa_familia: bool | None = Query(None),
    bypass_cache: bool = Query(False),
):
    endpoint_start = time.perf_counter()
    logger.info("V2 dashboard endpoint started")

    if permissions and permissions.secretaria_acesso != "TODOS":
        logger.warning(
            f"Dashboard not available for secretaria_acesso: {permissions.secretaria_acesso}"
        )
        return DashboardV2Response(
            data=_create_empty_dashboard(), can_view_dashboard=False
        )

    filters_dict: dict[str, object] = {}
    if grupo:
        filters_dict["pic_grupo"] = _parse_multi_select(grupo)
    if cohort:
        filters_dict["pic_cohort"] = _parse_multi_select(cohort)
    if status:
        filters_dict["pic_status"] = _parse_multi_select(status)
    if subprefeitura:
        filters_dict["subprefeitura"] = _parse_multi_select(subprefeitura)
    if regiao_administrativa:
        filters_dict["regiao_administrativa"] = _parse_multi_select(regiao_administrativa)
    if bairro:
        filters_dict["bairro"] = _parse_multi_select(bairro)
    if cre:
        filters_dict["id_cre"] = _parse_multi_select(cre)
    if ap:
        filters_dict["id_ap"] = _parse_multi_select(ap)
    if cas:
        filters_dict["id_cas"] = _parse_multi_select(cas)
    if cras:
        filters_dict["id_cras"] = _parse_multi_select(cras)
    if escola:
        filters_dict["id_escola"] = _parse_multi_select(escola)
    if unidade_saude:
        filters_dict["id_clinica_familia"] = _parse_multi_select(unidade_saude)
    if equipe_saude:
        filters_dict["id_equipe_familia"] = _parse_multi_select(equipe_saude)
    if has_bolsa_familia is not None:
        filters_dict["has_bolsa_familia"] = has_bolsa_familia

    try:
        df, _, _ = await DataManager.fetch_filter_paginate(
            query=DASHBOARD_TABLE_QUERY,
            filters_dict=filters_dict,
            page=1,
            page_size=None,
            filter_columns_config=DASHBOARD_FILTER_OPTIONS_CONFIG,
            user_permissions=permissions,
            bypass_cache=bypass_cache,
        )
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if df.is_empty():
        return DashboardV2Response(data=_create_empty_dashboard())

    dashboard_metrics = _calculate_dashboard_metrics(df, filtro_secretaria=secretaria)

    elapsed = time.perf_counter() - endpoint_start
    logger.info(f"V2 dashboard endpoint completed in {elapsed:.3f}s")

    return DashboardV2Response(data=dashboard_metrics)
