from fastapi import APIRouter

from src.api.v1.admin import router as admin_router
from src.api.v1.auth import router as auth_router
from src.api.v1.dashboard import router as dashboard_router
from src.api.v1.debug import router as debug_router
from src.api.v1.geospatial import router as geospatial_router
from src.api.v1.participants import router as participants_router

router = APIRouter(prefix="/v1")
router.include_router(auth_router)
router.include_router(participants_router)
router.include_router(dashboard_router)
router.include_router(admin_router)
router.include_router(debug_router)
router.include_router(geospatial_router)
