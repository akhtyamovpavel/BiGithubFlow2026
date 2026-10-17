# ScheduleService (`BiGithubFlow2026`) — Agent Guide

Сервис планирования учебного расписания (`ScheduleService`) на **Python 3.12+ (FastAPI + SQLAlchemy 2.0 Async + Alembic + Pydantic v2)** и **React + TypeScript + Vite + shadcn/ui** (`frontend/`). Разрабатывается распределённой командой (Вася, Ваня, Коля, Петя) по модели **GitHub Flow**.

---

## 1. Команды разработки и проверки качества

Все backend-команды выполняются через **Poetry**:

```bash
# Установка зависимостей
poetry install

# Запуск всех тестов
poetry run pytest -v

# Линтинг и форматирование (обязательно перед коммитом)
poetry run ruff check .
poetry run ruff format --check .

# Статическая проверка типов
poetry run mypy src

# Локальный запуск API-сервера
poetry run uvicorn schedule_service.main:app --reload --port 8000

# Применение миграций БД
poetry run alembic upgrade head
```

---

## 2. Архитектура проекта

```text
src/schedule_service/
├── main.py                  # Точка входа FastAPI, lifespan, /health, /health/live, /health/ready, подключение api_v1_router
├── core/
│   ├── config.py            # Настройки приложения (pydantic-settings, DATABASE_URL)
│   └── database.py          # AsyncEngine, AsyncSession, Base (id, created_at, updated_at), get_async_session, check_database_health
├── models/                  # SQLAlchemy 2.0 ORM-модели (Mapped / mapped_column)
│   ├── group.py             # Group (academic_groups, unique name)
│   ├── teacher.py           # Teacher (teachers, unique email)
│   ├── classroom.py         # Classroom (classrooms, unique (building, room_number))
│   ├── subject.py           # Subject (subjects: name, code, description)
│   ├── time_slot.py         # TimeSlot (time_slots: slot_number, start_time, end_time, day_of_week; check end_time > start_time)
│   └── lesson.py            # Lesson (lessons: FK на group, teacher, classroom, subject, time_slot; LessonType, WeekParity, specific_date)
├── schemas/                 # Pydantic v2 схемы (*Base, *Create, *Update, *Read с ConfigDict(from_attributes=True))
├── services/
│   └── conflict_service.py  # Движок детекции коллизий расписания (ConflictType, ScheduleConflict, проверка преподавателя, аудитории, вместимости, группы)
└── api/v1/
    ├── router.py            # Мастер-роутер /api/v1
    ├── groups.py            # CRUD /api/v1/groups
    ├── teachers.py          # CRUD /api/v1/teachers
    ├── classrooms.py        # CRUD /api/v1/classrooms
    ├── subjects.py          # CRUD /api/v1/subjects
    └── time_slots.py        # CRUD /api/v1/time-slots
```

Дополнительные директории:
- `alembic/versions/` — миграции схемы БД (при добавлении новых миграций из параллельных веток проверяй отсутствие двух `head`-ревизий через `poetry run alembic heads`).
- `tests/` — модульные и интеграционные тесты (`pytest` + `pytest-asyncio` + `httpx.AsyncClient` с `ASGITransport` и in-memory `sqlite+aiosqlite:///:memory:`).
- `frontend/` — SPA веб-интерфейс на React 18+, TypeScript, Vite, Tailwind CSS и `shadcn/ui`.
- `docs/` — спецификация (`docs/MVP.md`), бэклог (`docs/TASKS.md`), распределение задач (`docs/ASSIGNMENTS.md`).

---

## 3. Правила кода и конвенции API

1. **Стиль и типизация:**
   - Длина строки: **до 100 символов** (`[tool.ruff] line-length = 100`).
   - Включён `mypy --strict` с плагином `pydantic.mypy`. Все функции и методы в `src/` и новых тестах обязаны иметь полные аннотации типов.
   - В репозитории настроен `pre-commit` (`ruff`, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`).

2. **Конвенции FastAPI роутеров (`src/schedule_service/api/v1/`):**
   - Сессия БД передаётся через `SessionDep = Annotated[AsyncSession, Depends(get_async_session)]`.
   - При создании (`POST /`, статус `201 Created`) и обновлении (`PUT /{id}`, статус `200 OK`) проверяется уникальность бизнес-ключей до `flush()` и перехватывается `IntegrityError` с откатом (`await session.rollback()`) и возвратом **`409 Conflict`**.
   - При отсутствии записи по ID возвращается **`404 Not Found`**.
   - При удалении (`DELETE /{id}`) возвращается **`204 No Content`**.

3. **Правила детекции коллизий (`conflict_service.py`):**
   - Два занятия могут конфликтовать только в одном `time_slot_id`.
   - Пересечение чётности недель (`WeekParity`):
     - `ALWAYS` пересекается с `ALWAYS`, `ODD_WEEK`, `EVEN_WEEK`;
     - `ODD_WEEK` пересекается с `ALWAYS` и `ODD_WEEK`;
     - `EVEN_WEEK` пересекается с `ALWAYS` и `EVEN_WEEK`.
   - Разовые занятия (`specific_date != None`) конфликтуют с регулярными (`specific_date is None`) при совпадении чётности и с разовыми на ту же дату.
   - При проверке на обновление занятия обязательно передавать `exclude_lesson_id`, чтобы занятие не конфликтовало само с собой.

---

## 4. Процесс работы (GitHub Flow) и деплой

1. Перед началом новой задачи:
   ```bash
   git checkout main && git pull origin main
   git checkout -b feature/issue-<id>-<short-slug>
   ```
2. Если в `main` влили параллельную ветку с миграциями Alembic — смержи `main` в свою ветку и убедись, что в `alembic/versions/` линейная цепочка ревизий (один `head`).
3. После прохождения `pytest`, `ruff`, `mypy` пушь ветку и создавай PR через `gh pr create` с `Closes #<id>` в описании.
4. **Production:**
   - Образ публикуется в `ghcr.io/akhtyamovpavel/bigithubflow2026:latest` через GitHub Actions (`.github/workflows/ci.yml` / `publish.yml`).
   - Продакшен развёрнут на `root@execed.tech` в `/opt/schedule-service/docker-compose.prod.yml` за Nginx-прокси на домене **`https://scheduler.execed.tech`** (`/docs`, `/health/ready`, `/api/v1/*`).
