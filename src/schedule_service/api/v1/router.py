"""API v1 master router aggregating resource endpoints."""

from fastapi import APIRouter

from schedule_service.api.v1.classrooms import router as classrooms_router
from schedule_service.api.v1.groups import router as groups_router
from schedule_service.api.v1.schedule import router as schedule_router
from schedule_service.api.v1.subjects import router as subjects_router
from schedule_service.api.v1.teachers import router as teachers_router
from schedule_service.api.v1.time_slots import router as time_slots_router

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
api_v1_router.include_router(
    classrooms_router,
    prefix="/classrooms",
    tags=["Classrooms"],
)
api_v1_router.include_router(
    subjects_router,
    prefix="/subjects",
    tags=["Subjects"],
)
api_v1_router.include_router(
    time_slots_router,
    prefix="/time-slots",
    tags=["Time Slots"],
)
api_v1_router.include_router(
    schedule_router,
    prefix="/schedule",
    tags=["Schedule"],
)
