"""Services package."""

from schedule_service.services.conflict_service import (
    ClassroomCapacityExceededError,
    ConflictType,
    LessonConflictData,
    ScheduleConflict,
    ScheduleConflictException,
    ScheduleValidationService,
    check_classroom_capacity,
    check_classroom_conflict,
    check_group_conflict,
    check_teacher_conflict,
    overlapping_parities,
    parities_overlap,
    validate_classroom_capacity,
    validate_lesson,
)

__all__ = [
    "ClassroomCapacityExceededError",
    "ConflictType",
    "LessonConflictData",
    "ScheduleConflict",
    "ScheduleConflictException",
    "ScheduleValidationService",
    "check_classroom_capacity",
    "check_classroom_conflict",
    "check_group_conflict",
    "check_teacher_conflict",
    "overlapping_parities",
    "parities_overlap",
    "validate_classroom_capacity",
    "validate_lesson",
]
