"""Idempotent demonstration data seed script for ScheduleService.

Usage:
    poetry run python -m scripts.seed_demo_data
"""

import asyncio
from dataclasses import dataclass
from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.config import get_settings
from schedule_service.core.database import Base, create_engine_and_sessionmaker
from schedule_service.models.classroom import Classroom
from schedule_service.models.group import Group
from schedule_service.models.lesson import Lesson, LessonType, WeekParity
from schedule_service.models.subject import Subject
from schedule_service.models.teacher import Teacher
from schedule_service.models.time_slot import TimeSlot
from schedule_service.services.conflict_service import ScheduleValidationService


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Summary counts of entities present after running the demo seed."""

    groups: int
    teachers: int
    classrooms: int
    subjects: int
    time_slots: int
    lessons: int


DEMO_GROUPS: list[dict[str, Any]] = [
    {
        "name": "Б05-401",
        "faculty": "ФПМИ",
        "course_number": 1,
        "student_count": 28,
        "is_active": True,
    },
    {
        "name": "Б05-301",
        "faculty": "ФПМИ",
        "course_number": 2,
        "student_count": 26,
        "is_active": True,
    },
    {
        "name": "Б01-202",
        "faculty": "ФРКТ",
        "course_number": 3,
        "student_count": 24,
        "is_active": True,
    },
    {
        "name": "Б02-105",
        "faculty": "ЛФИ",
        "course_number": 4,
        "student_count": 22,
        "is_active": True,
    },
    {
        "name": "Б06-302",
        "faculty": "ФБМФ",
        "course_number": 2,
        "student_count": 25,
        "is_active": True,
    },
]

DEMO_TEACHERS: list[dict[str, Any]] = [
    {
        "full_name": "Иванов Сергей Петрович",
        "email": "s.ivanov@phystech.edu",
        "department": "Кафедра высшей математики",
        "position": "Профессор",
        "is_active": True,
    },
    {
        "full_name": "Смирнова Елена Викторовна",
        "email": "e.smirnova@phystech.edu",
        "department": "Кафедра алгоритмов и технологий программирования",
        "position": "Доцент",
        "is_active": True,
    },
    {
        "full_name": "Кузнецов Андрей Николаевич",
        "email": "a.kuznetsov@phystech.edu",
        "department": "Кафедра общей физики",
        "position": "Профессор",
        "is_active": True,
    },
    {
        "full_name": "Попова Ольга Александровна",
        "email": "o.popova@phystech.edu",
        "department": "Кафедра дискретной математики",
        "position": "Доцент",
        "is_active": True,
    },
    {
        "full_name": "Соколов Дмитрий Игоревич",
        "email": "d.sokolov@phystech.edu",
        "department": "Кафедра системного программирования",
        "position": "Старший преподаватель",
        "is_active": True,
    },
    {
        "full_name": "Волкова Наталья Сергеевна",
        "email": "n.volkova@phystech.edu",
        "department": "Кафедра анализа данных",
        "position": "Доцент",
        "is_active": True,
    },
    {
        "full_name": "Морозов Павел Владимирович",
        "email": "p.morozov@phystech.edu",
        "department": "Кафедра биоинформатики",
        "position": "Профессор",
        "is_active": True,
    },
    {
        "full_name": "Лебедев Артём Олегович",
        "email": "a.lebedev@phystech.edu",
        "department": "Кафедра иностранных языков",
        "position": "Старший преподаватель",
        "is_active": True,
    },
]

DEMO_CLASSROOMS: list[dict[str, Any]] = [
    {
        "building": "Главный корпус",
        "room_number": "115",
        "capacity": 150,
        "has_projector": True,
        "has_computers": False,
        "is_active": True,
    },
    {
        "building": "Главный корпус",
        "room_number": "202",
        "capacity": 120,
        "has_projector": True,
        "has_computers": False,
        "is_active": True,
    },
    {
        "building": "Главный корпус",
        "room_number": "430",
        "capacity": 40,
        "has_projector": True,
        "has_computers": False,
        "is_active": True,
    },
    {
        "building": "УЛК",
        "room_number": "312",
        "capacity": 35,
        "has_projector": True,
        "has_computers": False,
        "is_active": True,
    },
    {
        "building": "УЛК",
        "room_number": "314",
        "capacity": 35,
        "has_projector": False,
        "has_computers": False,
        "is_active": True,
    },
    {
        "building": "УЛК",
        "room_number": "418",
        "capacity": 30,
        "has_projector": True,
        "has_computers": True,
        "is_active": True,
    },
    {
        "building": "УЛК",
        "room_number": "420",
        "capacity": 30,
        "has_projector": True,
        "has_computers": True,
        "is_active": True,
    },
    {
        "building": "Арктика",
        "room_number": "210",
        "capacity": 32,
        "has_projector": True,
        "has_computers": True,
        "is_active": True,
    },
    {
        "building": "Цифра",
        "room_number": "101",
        "capacity": 80,
        "has_projector": True,
        "has_computers": True,
        "is_active": True,
    },
    {
        "building": "КПМ",
        "room_number": "505",
        "capacity": 30,
        "has_projector": True,
        "has_computers": False,
        "is_active": True,
    },
]

DEMO_SUBJECTS: list[dict[str, str]] = [
    {
        "name": "Математический анализ",
        "code": "MATH-101",
        "description": "Дифференциальное и интегральное исчисление",
    },
    {
        "name": "Линейная алгебра и геометрия",
        "code": "MATH-102",
        "description": "Векторные пространства, матрицы и линейные операторы",
    },
    {
        "name": "Алгоритмы и структуры данных",
        "code": "CS-101",
        "description": "Базовые алгоритмы, деревья поиска и алгоритмы на графах",
    },
    {
        "name": "Общая физика: Механика и термодинамика",
        "code": "PHYS-101",
        "description": "Классическая механика и молекулярная физика",
    },
    {
        "name": "Дискретная математика",
        "code": "MATH-201",
        "description": "Комбинаторика, теория графов и булевы функции",
    },
    {
        "name": "Архитектура компьютеров и операционные системы",
        "code": "CS-201",
        "description": "Устройство процессоров, память, ядро ОС и системные вызовы",
    },
    {
        "name": "Базы данных и SQL",
        "code": "CS-202",
        "description": "Проектирование реляционных БД, транзакции и индексы",
    },
    {
        "name": "Теория вероятностей и математическая статистика",
        "code": "MATH-202",
        "description": "Случайные величины, предельные теоремы и проверка гипотез",
    },
    {
        "name": "Машинное обучение",
        "code": "AI-301",
        "description": "Линейные модели, градиентный бустинг и глубокое обучение",
    },
    {
        "name": "Процесс разработки и DevOps",
        "code": "SE-301",
        "description": "Модели ветвления, CI/CD, контейнеризация и эксплуатация сервисов",
    },
    {
        "name": "Молекулярная биология и биоинформатика",
        "code": "BIO-201",
        "description": "Анализ последовательностей ДНК/РНК и структурная биоинформатика",
    },
    {
        "name": "Английский язык для академических целей",
        "code": "LANG-101",
        "description": "Научная коммуникация, презентации и академическое письмо",
    },
]

BELL_SCHEDULE_SLOTS: list[tuple[int, time, time]] = [
    (1, time(9, 0), time(10, 25)),
    (2, time(10, 45), time(12, 10)),
    (3, time(12, 20), time(13, 45)),
    (4, time(13, 55), time(15, 20)),
    (5, time(15, 30), time(16, 55)),
    (6, time(17, 5), time(18, 30)),
]

# Tuple schema:
# (group_name, subject_code, teacher_email, (building, room_number),
#  (day_of_week, slot_number), lesson_type, parity)
DEMO_LESSONS_PLAN: list[
    tuple[str, str, str, tuple[str, str], tuple[int, int], LessonType, WeekParity]
] = [
    # Понедельник (day=1)
    (
        "Б05-401",
        "MATH-101",
        "s.ivanov@phystech.edu",
        ("Главный корпус", "115"),
        (1, 1),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    (
        "Б05-401",
        "CS-101",
        "e.smirnova@phystech.edu",
        ("УЛК", "418"),
        (1, 2),
        LessonType.LAB,
        WeekParity.ALWAYS,
    ),
    (
        "Б05-301",
        "MATH-201",
        "o.popova@phystech.edu",
        ("УЛК", "312"),
        (1, 1),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    (
        "Б05-301",
        "CS-201",
        "d.sokolov@phystech.edu",
        ("Цифра", "101"),
        (1, 2),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    # Вторник (day=2)
    (
        "Б05-401",
        "MATH-102",
        "s.ivanov@phystech.edu",
        ("УЛК", "312"),
        (2, 1),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    (
        "Б05-401",
        "PHYS-101",
        "a.kuznetsov@phystech.edu",
        ("Главный корпус", "202"),
        (2, 2),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    (
        "Б01-202",
        "AI-301",
        "n.volkova@phystech.edu",
        ("Цифра", "101"),
        (2, 1),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    (
        "Б01-202",
        "SE-301",
        "d.sokolov@phystech.edu",
        ("УЛК", "420"),
        (2, 2),
        LessonType.LAB,
        WeekParity.ODD_WEEK,
    ),
    (
        "Б01-202",
        "CS-202",
        "e.smirnova@phystech.edu",
        ("УЛК", "420"),
        (2, 2),
        LessonType.LAB,
        WeekParity.EVEN_WEEK,
    ),
    # Среда (day=3)
    (
        "Б05-301",
        "MATH-202",
        "o.popova@phystech.edu",
        ("Главный корпус", "115"),
        (3, 1),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    (
        "Б05-301",
        "CS-202",
        "e.smirnova@phystech.edu",
        ("УЛК", "418"),
        (3, 2),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    (
        "Б06-302",
        "BIO-201",
        "p.morozov@phystech.edu",
        ("Арктика", "210"),
        (3, 1),
        LessonType.LAB,
        WeekParity.ALWAYS,
    ),
    (
        "Б06-302",
        "LANG-101",
        "a.lebedev@phystech.edu",
        ("КПМ", "505"),
        (3, 2),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    # Четверг (day=4)
    (
        "Б02-105",
        "SE-301",
        "d.sokolov@phystech.edu",
        ("Цифра", "101"),
        (4, 1),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    (
        "Б02-105",
        "AI-301",
        "n.volkova@phystech.edu",
        ("УЛК", "418"),
        (4, 2),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    (
        "Б05-401",
        "LANG-101",
        "a.lebedev@phystech.edu",
        ("КПМ", "505"),
        (4, 3),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    # Пятница (day=5)
    (
        "Б01-202",
        "MATH-202",
        "o.popova@phystech.edu",
        ("Главный корпус", "430"),
        (5, 1),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
    (
        "Б06-302",
        "PHYS-101",
        "a.kuznetsov@phystech.edu",
        ("Главный корпус", "202"),
        (5, 2),
        LessonType.LECTURE,
        WeekParity.ALWAYS,
    ),
    # Суббота (day=6)
    (
        "Б02-105",
        "BIO-201",
        "p.morozov@phystech.edu",
        ("Арктика", "210"),
        (6, 1),
        LessonType.SEMINAR,
        WeekParity.ODD_WEEK,
    ),
    (
        "Б05-301",
        "CS-201",
        "d.sokolov@phystech.edu",
        ("УЛК", "314"),
        (6, 2),
        LessonType.SEMINAR,
        WeekParity.ALWAYS,
    ),
]


async def seed_demo_data(session: AsyncSession) -> SeedSummary:
    """Idempotently populate the database with demo reference data and weekly schedule."""
    # 1. Seed Academic Groups (5)
    groups_by_name: dict[str, Group] = {}
    for g_data in DEMO_GROUPS:
        group_res = await session.execute(select(Group).where(Group.name == g_data["name"]))
        group = group_res.scalar_one_or_none()
        if group is None:
            group = Group(**g_data)
            session.add(group)
            await session.flush()
        groups_by_name[group.name] = group

    # 2. Seed Teachers (8)
    teachers_by_email: dict[str, Teacher] = {}
    for t_data in DEMO_TEACHERS:
        teacher_res = await session.execute(select(Teacher).where(Teacher.email == t_data["email"]))
        teacher = teacher_res.scalar_one_or_none()
        if teacher is None:
            teacher = Teacher(**t_data)
            session.add(teacher)
            await session.flush()
        teachers_by_email[teacher.email] = teacher

    # 3. Seed Classrooms (10)
    classrooms_by_key: dict[tuple[str, str], Classroom] = {}
    for c_data in DEMO_CLASSROOMS:
        classroom_res = await session.execute(
            select(Classroom).where(
                Classroom.building == c_data["building"],
                Classroom.room_number == c_data["room_number"],
            )
        )
        classroom = classroom_res.scalar_one_or_none()
        if classroom is None:
            classroom = Classroom(**c_data)
            session.add(classroom)
            await session.flush()
        classrooms_by_key[(classroom.building, classroom.room_number)] = classroom

    # 4. Seed Subjects (12)
    subjects_by_code: dict[str, Subject] = {}
    for s_data in DEMO_SUBJECTS:
        subject_res = await session.execute(select(Subject).where(Subject.code == s_data["code"]))
        subject = subject_res.scalar_one_or_none()
        if subject is None:
            subject = Subject(**s_data)
            session.add(subject)
            await session.flush()
        if subject.code is not None:
            subjects_by_code[subject.code] = subject

    # 5. Seed TimeSlots (6 slots * 6 days Mon..Sat = 36)
    slots_by_key: dict[tuple[int, int], TimeSlot] = {}
    for day_of_week in range(1, 7):
        for slot_number, start_t, end_t in BELL_SCHEDULE_SLOTS:
            slot_res = await session.execute(
                select(TimeSlot).where(
                    TimeSlot.day_of_week == day_of_week,
                    TimeSlot.slot_number == slot_number,
                )
            )
            slot = slot_res.scalar_one_or_none()
            if slot is None:
                slot = TimeSlot(
                    day_of_week=day_of_week,
                    slot_number=slot_number,
                    start_time=start_t,
                    end_time=end_t,
                )
                session.add(slot)
                await session.flush()
            slots_by_key[(day_of_week, slot_number)] = slot

    # 6. Seed conflict-free Lessons
    lessons_count = 0
    for (
        group_name,
        subject_code,
        teacher_email,
        room_key,
        slot_key,
        lesson_type,
        parity,
    ) in DEMO_LESSONS_PLAN:
        group = groups_by_name[group_name]
        subject = subjects_by_code[subject_code]
        teacher = teachers_by_email[teacher_email]
        classroom = classrooms_by_key[room_key]
        slot = slots_by_key[slot_key]

        existing_lesson = await session.execute(
            select(Lesson).where(
                Lesson.group_id == group.id,
                Lesson.time_slot_id == slot.id,
                Lesson.parity == parity,
                Lesson.specific_date.is_(None),
            )
        )
        if existing_lesson.scalar_one_or_none() is None:
            lesson = Lesson(
                subject_id=subject.id,
                teacher_id=teacher.id,
                group_id=group.id,
                classroom_id=classroom.id,
                time_slot_id=slot.id,
                lesson_type=lesson_type,
                parity=parity,
                specific_date=None,
            )
            await ScheduleValidationService.validate_lesson(session, lesson)
            session.add(lesson)
            await session.flush()
        lessons_count += 1

    await session.commit()

    return SeedSummary(
        groups=len(groups_by_name),
        teachers=len(teachers_by_email),
        classrooms=len(classrooms_by_key),
        subjects=len(subjects_by_code),
        time_slots=len(slots_by_key),
        lessons=lessons_count,
    )


async def run_seed(database_url: str | None = None) -> SeedSummary:
    """Connect to the target database, ensure schema exists, and run seed_demo_data."""
    url = database_url or get_settings().database_url
    engine, session_maker = create_engine_and_sessionmaker(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=[
                        Group.__table__,  # type: ignore[list-item]
                        Teacher.__table__,  # type: ignore[list-item]
                        Classroom.__table__,  # type: ignore[list-item]
                        Subject.__table__,  # type: ignore[list-item]
                        TimeSlot.__table__,  # type: ignore[list-item]
                        Lesson.__table__,  # type: ignore[list-item]
                    ],
                )
            )

        async with session_maker() as session:
            return await seed_demo_data(session)
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entry point for `python -m scripts.seed_demo_data`."""
    summary = asyncio.run(run_seed())
    print(
        "Demo data seeded successfully: "
        f"{summary.groups} groups, "
        f"{summary.teachers} teachers, "
        f"{summary.classrooms} classrooms, "
        f"{summary.subjects} subjects, "
        f"{summary.time_slots} time slots, "
        f"{summary.lessons} lessons."
    )


if __name__ == "__main__":
    main()
