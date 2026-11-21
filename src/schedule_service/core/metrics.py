"""Prometheus metrics definitions and recording helpers for ScheduleService."""

from __future__ import annotations

from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot

METRICS_REGISTRY = CollectorRegistry(auto_describe=True)

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_ALLOWED_LESSON_TYPES = ("LECTURE", "SEMINAR", "LAB")
_ALLOWED_CONFLICT_TYPES = (
    "TEACHER_BUSY",
    "CLASSROOM_BUSY",
    "GROUP_BUSY",
    "CAPACITY_EXCEEDED",
    "OCCURRENCE_EXCEPTION",
    "INTEGRITY_ERROR",
)
_ALLOWED_EXPORT_FORMATS = ("ics", "csv")
_ALLOWED_EXPORT_TARGETS = ("group", "teacher")

_ENTITY_MODELS: tuple[tuple[str, type[Any]], ...] = (
    ("groups", Group),
    ("teachers", Teacher),
    ("classrooms", Classroom),
    ("subjects", Subject),
    ("time_slots", TimeSlot),
    ("lessons", Lesson),
)

HTTP_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests handled by FastAPI",
    ("method", "route", "status_code", "status_class"),
    registry=METRICS_REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
    buckets=HTTP_DURATION_BUCKETS,
    registry=METRICS_REGISTRY,
)

SCHEDULE_LESSONS_CREATED_TOTAL = Counter(
    "schedule_lessons_created_total",
    "Total number of scheduled lessons created",
    ("lesson_type",),
    registry=METRICS_REGISTRY,
)

SCHEDULE_CONFLICTS_DETECTED_TOTAL = Counter(
    "schedule_conflicts_detected_total",
    "Total number of schedule conflicts detected",
    ("conflict_type",),
    registry=METRICS_REGISTRY,
)

SCHEDULE_EXPORTS_TOTAL = Counter(
    "schedule_exports_total",
    "Total number of schedule exports completed",
    ("format", "target"),
    registry=METRICS_REGISTRY,
)

SCHEDULE_DB_ENTITIES_COUNT = Gauge(
    "schedule_db_entities_count",
    "Current number of domain entities stored in the database",
    ("entity",),
    registry=METRICS_REGISTRY,
)


def _initialize_known_series() -> None:
    """Pre-register bounded enum series at 0 for consistent PromQL rate/increase queries."""
    for lesson_type in _ALLOWED_LESSON_TYPES:
        SCHEDULE_LESSONS_CREATED_TOTAL.labels(lesson_type=lesson_type)
    for conflict_type in _ALLOWED_CONFLICT_TYPES[:4]:
        SCHEDULE_CONFLICTS_DETECTED_TOTAL.labels(conflict_type=conflict_type)
    for export_format in _ALLOWED_EXPORT_FORMATS:
        for target in _ALLOWED_EXPORT_TARGETS:
            SCHEDULE_EXPORTS_TOTAL.labels(format=export_format, target=target)
    for entity_name, _ in _ENTITY_MODELS:
        SCHEDULE_DB_ENTITIES_COUNT.labels(entity=entity_name).set(0)


_initialize_known_series()


def _normalize_method(method: str) -> str:
    upper = method.upper()
    return upper if upper in _ALLOWED_METHODS else "OTHER"


def _status_class(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "2xx"
    if 300 <= status_code < 400:
        return "3xx"
    if 400 <= status_code < 500:
        return "4xx"
    if 500 <= status_code < 600:
        return "5xx"
    return "other"


def record_http_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record HTTP request counter and duration histogram with bounded labels."""
    normalized_method = _normalize_method(method)
    bounded_route = route if route else "unmatched"
    HTTP_REQUESTS_TOTAL.labels(
        method=normalized_method,
        route=bounded_route,
        status_code=str(status_code),
        status_class=_status_class(status_code),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=normalized_method,
        route=bounded_route,
    ).observe(max(duration_seconds, 0.0))


def record_lesson_created(lesson_type: str) -> None:
    """Increment lesson creation counter for a bounded lesson_type enum value."""
    normalized = lesson_type.upper()
    label = normalized if normalized in _ALLOWED_LESSON_TYPES else "OTHER"
    SCHEDULE_LESSONS_CREATED_TOTAL.labels(lesson_type=label).inc()


def record_conflict_detected(conflict_type: str, count: int = 1) -> None:
    """Increment schedule conflict counter for a bounded conflict_type enum value."""
    normalized = conflict_type.upper()
    label = normalized if normalized in _ALLOWED_CONFLICT_TYPES else "OTHER"
    SCHEDULE_CONFLICTS_DETECTED_TOTAL.labels(conflict_type=label).inc(count)


def record_schedule_export(export_format: str, target: str) -> None:
    """Increment schedule export counter for bounded format and target labels."""
    fmt = export_format.lower()
    tgt = target.lower()
    if fmt not in _ALLOWED_EXPORT_FORMATS:
        fmt = "other"
    if tgt not in _ALLOWED_EXPORT_TARGETS:
        tgt = "other"
    SCHEDULE_EXPORTS_TOTAL.labels(format=fmt, target=tgt).inc()


async def refresh_db_entity_counts(session: AsyncSession) -> dict[str, int]:
    """Query current row counts for core domain tables and update Prometheus gauges."""
    counts: dict[str, int] = {}
    for entity_name, model in _ENTITY_MODELS:
        total = await session.scalar(select(func.count()).select_from(model))
        value = int(total or 0)
        SCHEDULE_DB_ENTITIES_COUNT.labels(entity=entity_name).set(value)
        counts[entity_name] = value
    return counts


def render_metrics() -> tuple[bytes, str]:
    """Serialize all registered Prometheus metrics in text exposition format."""
    return generate_latest(METRICS_REGISTRY), CONTENT_TYPE_LATEST
