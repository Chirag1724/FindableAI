from fastapi import APIRouter

from .health import router as health_router
from .orgs import router as orgs_router
from .patches import router as patches_router
from .scans import router as scans_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router, tags=["Health"])
api_v1_router.include_router(scans_router, prefix="/scans", tags=["Scans"])
api_v1_router.include_router(patches_router, prefix="/patches", tags=["Patches"])
api_v1_router.include_router(orgs_router, prefix="/orgs", tags=["Organizations"])
