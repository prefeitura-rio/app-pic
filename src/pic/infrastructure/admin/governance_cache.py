from src.api.v1.queries import GOVERNANCE_TABLE_QUERY
from src.utils.cache_manager import query_cache
from src.utils.log import logger


def refresh_governance_cache():
    query_cache.delete(GOVERNANCE_TABLE_QUERY)
    logger.info("Governance cache invalidated (lazy refresh)")
