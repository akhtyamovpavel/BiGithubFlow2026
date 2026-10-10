"""API v1 master router aggregating resource endpoints."""

from fastapi import APIRouter

from schedule_service.api.v1.groups import router as groups_router
from schedule_service.api.v1.teachers import router as teachers_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(
    groups_router,
    prefix="/groups",
    tags=["Groups"],
)
api_v1_router.include_router(
    teachers_router,
    prefix="/teachers",
    tags=["Teachers"],
)
