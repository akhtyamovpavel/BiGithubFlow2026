# MVP Сервиса планирования учебного расписания (Schedule Planning Service)

**Репозиторий проекта:** [akhtyamovpavel/BiGithubFlow2026](https://github.com/akhtyamovpavel/BiGithubFlow2026)  
**Модель ветвления:** GitHub Flow (короткоживущие ветки `feature/*`, PR в `main`, автоматический CI, обязательный Code Review).

---

## 1. Концепция и цели MVP

### 1.1. Проблема
Составление и ведение расписания занятий в учебных заведениях сопряжено с высокой вероятностью накладок (коллизий):
- Один преподаватель может быть случайно назначен на два занятия одновременно.
- Несколько групп или преподавателей могут претендовать на одну и ту же аудиторию.
- Вместимость аудитории может оказаться меньше фактической численности академической группы.
- Студенты и преподаватели не имеют удобного программного интерфейса для получения своего расписания и его интеграции в персональные календари.

### 1.2. Цель MVP
Разработать легковесный, надежный backend-сервис на **Python 3.12+ (FastAPI + SQLAlchemy 2.0)**, который:
1. Обеспечивает ведение базовых справочников (группы, преподаватели, аудитории, предметы, временные слоты).
2. Позволяет составлять расписание с автоматическим контролем и блокировкой коллизий (Conflict Detection Engine).
3. Предоставляет REST API для просмотра расписания по группам, преподавателям и свободным аудиториям.
4. Позволяет экспортировать расписание в стандартный формат iCalendar (`.ics`) и CSV.

---

## 2. Архитектура и стек технологий

```
┌─────────────────────────────────────────────────────────────┐
│                       Клиенты сервиса                       │
│  (Студенты, Преподаватели, Диспетчер / Календари Google/Apple)│
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON / .ics
┌──────────────────────────────▼──────────────────────────────┐
│                    FastAPI REST API Layer                   │
│   /api/v1/groups, /teachers, /classrooms, /lessons, /schedule│
└──────────────────────────────┬──────────────────────────────┘
                               │ Pydantic v2 DTO
┌──────────────────────────────▼──────────────────────────────┐
│                    Business Logic Layer                     │
│  - ScheduleValidationService (Conflict Detection Engine)    │
│  - CalendarExportService (RFC 5545 iCalendar / CSV)         │
└──────────────────────────────┬──────────────────────────────┘
                               │ SQLAlchemy 2.0 (Async Session)
┌──────────────────────────────▼──────────────────────────────┐
│                   Data Access & Storage                     │
│   PostgreSQL 16 (Production) / SQLite + aiosqlite (Тесты)   │
│   Миграции: Alembic                                         │
└─────────────────────────────────────────────────────────────┘
```

- **Язык**: Python 3.12+
- **Web-фреймворк**: FastAPI (асинхронный, автоматическая интерактивная документация Swagger/OpenAPI)
- **Валидация и DTO**: Pydantic v2 + Pydantic-Settings
- **ORM / База данных**: SQLAlchemy 2.0 (asyncio) + PostgreSQL 16 (в docker-compose) / SQLite для быстрых unit-тестов
- **Миграции**: Alembic
- **Тестирование**: pytest, pytest-asyncio, httpx
- **Качество кода**: Ruff (linter + formatter), mypy (строгая статическая типизация), pre-commit
- **CI/CD**: GitHub Actions (линтер, проверка типов, прогон всех тестов на каждый PR)
- **Контейнеризация**: Dockerfile, docker-compose.yml

---

## 3. Модель данных (Сущности MVP)

1. **Group (Академическая группа)**:
   - `id`: Integer (PK)
   - `name`: String (уникальный шифр группы, например "Б05-201")
   - `faculty`: String (факультет/направление)
   - `course_number`: Integer (1..6)
   - `student_count`: Integer (> 0)
   - `is_active`: Boolean

2. **Teacher (Преподаватель)**:
   - `id`: Integer (PK)
   - `full_name`: String (ФИО)
   - `email`: String (уникальный)
   - `department`: String (кафедра)
   - `position`: String (должность)
   - `is_active`: Boolean

3. **Classroom (Аудиторный фонд)**:
   - `id`: Integer (PK)
   - `building`: String (корпус)
   - `room_number`: String (номер аудитории)
   - `capacity`: Integer (> 0, вместимость)
   - `has_projector`: Boolean
   - `has_computers`: Boolean
   - `is_active`: Boolean
   - *Уникальность*: `(building, room_number)`

4. **Subject (Учебная дисциплина)**:
   - `id`: Integer (PK)
   - `name`: String (название предмета)
   - `code`: String (код курса)
   - `description`: String

5. **TimeSlot (Сетка звонков / Временной слот)**:
   - `id`: Integer (PK)
   - `slot_number`: Integer (номер пары: 1..7)
   - `start_time`: Time (например, 09:00)
   - `end_time`: Time (например, 10:30)
   - `day_of_week`: Integer (1 = Пн ... 7 = Вс)
   - *Условие*: `end_time > start_time`

6. **Lesson (Занятие в расписании)**:
   - `id`: Integer (PK)
   - `subject_id`: FK -> Subject
   - `teacher_id`: FK -> Teacher
   - `group_id`: FK -> Group
   - `classroom_id`: FK -> Classroom
   - `time_slot_id`: FK -> TimeSlot
   - `lesson_type`: Enum (LECTURE, SEMINAR, LAB)
   - `parity`: Enum (ALWAYS, ODD_WEEK, EVEN_WEEK)
   - `specific_date`: Optional[Date] (для разовых пар)

---

## 4. Ядро бизнес-логики: Conflict Detection Engine

Перед созданием (`POST /lessons`) или изменением (`PUT /lessons/{id}`) занятия вызывается сервис валидации коллизий:
1. **Преподаватель**: не может проводить другое занятие в данный слот и дату/четность.
2. **Аудитория**: не может быть занята другим занятием в данный слот и дату/четность.
3. **Группа**: не может находиться на другом занятии в данный слот.
4. **Вместимость**: `classroom.capacity >= group.student_count`.
При наличии коллизий API возвращает **HTTP 409 Conflict** с детализированным списком нарушений.
