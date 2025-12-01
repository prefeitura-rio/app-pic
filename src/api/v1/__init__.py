from fastapi import APIRouter
from src.api.v1.auth import router as auth_router
from src.api.v1.test_auth import router as test_auth_router


router = APIRouter(prefix="/v1")
router.include_router(auth_router)
router.include_router(test_auth_router, prefix="/auth", tags=["Authentication Test"])
