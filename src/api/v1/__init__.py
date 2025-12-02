from fastapi import APIRouter
from src.api.v1.auth import router as auth_router
from src.api.v1.participants import router as participants_router
from src.api.v1.dashboard import router as dashboard_router
from src.api.v1.protocols import router as protocols_router
from src.api.v1.filters import router as filters_router

router = APIRouter(prefix="/v1")
router.include_router(auth_router)
router.include_router(
    participants_router, prefix="/participants", tags=["Participantes"]
)
router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
router.include_router(protocols_router, prefix="/protocols", tags=["Protocolos"])
router.include_router(filters_router, prefix="/filters", tags=["Filtros"])
