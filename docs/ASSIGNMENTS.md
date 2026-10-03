# Распределение задач MVP между участниками команды

**Проект:** [Сервис планирования расписаний (BiGithubFlow2026)](https://github.com/akhtyamovpavel/BiGithubFlow2026)  
**Модель процесса:** GitHub Flow  
**Команда:**
- **Team Lead** (Архитектура, Инфраструктура, База данных, CI/CD, Сквозная валидация)
- **Ваня** (Backend-разработчик: Модели данных справочников, Схемы, CRUD API)
- **Коля** (Backend-разработчик: Расписание, Алгоритмы детекции коллизий, Просмотр и Экспорт)

---

## 1. Сводная матрица распределения задач (20 задач)

| Исполнитель | Количество задач | Номера Issues на GitHub | Фокус работы |
|---|---|---|---|
| **Team Lead** | 7 | [#1](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/1), [#2](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/2), [#3](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/3), [#4](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/4), [#5](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/5), [#13](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/13), [#20](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/20) | Каркас проекта, CI/CD, сессия БД/Alembic, фасад валидации коллизий, сид-данные |
| **Ваня** | 6 | [#6](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/6), [#7](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/7), [#8](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/8), [#9](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/9), [#14](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/14), [#15](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/15) | Базовые сущности (Группы, Преподаватели, Аудитории, Слоты) и их REST CRUD API |
| **Коля** | 7 | [#10](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/10), [#11](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/11), [#12](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/12), [#16](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/16), [#17](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/17), [#18](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/18), [#19](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/19) | Модель занятий, движок детекции накладок, выборка расписания, свободные залы, .ics |

---

## 2. Детальный план по исполнителям

### 👔 Team Lead (7 задач)
*Зона ответственности: архитектура, общие контракты, качество и инфраструктура разработки.*

1. **[#1 [INFRA] Инициализация проекта, Poetry/uv и модуля конфигурации](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/1)**
   - Ветка: `feature/issue-1-project-setup`
   - Результат: скелет `src/schedule_service`, `Settings` через `pydantic-settings`, эндпоинт `/health`.
2. **[#2 [INFRA] Настройка линтинга, форматирования и pre-commit (Ruff, mypy)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/2)**
   - Ветка: `feature/issue-2-linters-precommit`
   - Результат: правила Ruff, строгий mypy, хуки pre-commit для всей команды.
3. **[#3 [CI/CD] Настройка GitHub Actions CI пайплайна](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/3)**
   - Ветка: `feature/issue-3-github-actions-ci`
   - Результат: workflow на GitHub Actions (lint + mypy + pytest на каждый PR).
4. **[#4 [INFRA] Контейнеризация сервиса (Dockerfile и docker-compose)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/4)**
   - Ветка: `feature/issue-4-docker-setup`
   - Результат: multi-stage Dockerfile, PostgreSQL 16 в `docker-compose.yml`.
5. **[#5 [CORE] Подключение к БД через SQLAlchemy 2.0 (asyncio) и настройка Alembic](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/5)**
   - Ветка: `feature/issue-5-db-and-alembic`
   - Результат: `async_sessionmaker`, базовый класс `Base`, асинхронный `alembic/env.py`.
6. **[#13 [LOGIC] Детекция коллизий: занятость группы и фасад валидации расписания](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/13)**
   - Ветка: `feature/issue-13-group-conflict-and-facade`
   - Результат: проверка занятости группы и объединение алгоритмов Вани и Коли в единый фасад `ScheduleValidationService`.
7. **[#20 [DATA] Скрипт генерации демонстрационных данных (Seed fixtures)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/20)**
   - Ветка: `feature/issue-20-demo-seed-data`
   - Результат: идемпотентный скрипт создания тестовых сущностей и неконфликтного расписания для демо.

---

### 👨‍💻 Ваня (6 задач)
*Зона ответственности: нормализованные справочники и их REST API.*

1. **[#6 [MODEL] Справочник академических групп (модель Group, Pydantic-схемы)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/6)**
   - Ветка: `feature/issue-6-group-model`
   - Результат: модель `Group` (id, name, course, student_count), схемы валидации, миграция.
2. **[#7 [MODEL] Справочник преподавателей (модель Teacher, Pydantic-схемы)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/7)**
   - Ветка: `feature/issue-7-teacher-model`
   - Результат: модель `Teacher` (id, full_name, email, department), валидация email, миграция.
3. **[#8 [MODEL] Справочник аудиторий (модель Classroom, Pydantic-схемы)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/8)**
   - Ветка: `feature/issue-8-classroom-model`
   - Результат: модель `Classroom` (корпус, номер, вместимость, проектор), ограничение уникальности.
4. **[#9 [MODEL] Справочники дисциплин и временных слотов (Subject, TimeSlot)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/9)**
   - Ветка: `feature/issue-9-subject-timeslot-models`
   - Результат: модели `Subject` и `TimeSlot` (сетка 1..7 пар по дням недели).
5. **[#14 [API] CRUD эндпоинты для академических групп и преподавателей](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/14)**
   - Ветка: `feature/issue-14-groups-teachers-api`
   - Результат: роутеры `/api/v1/groups` и `/api/v1/teachers` с пагинацией, фильтрацией и тестами на `httpx`.
6. **[#15 [API] CRUD эндпоинты для аудиторий, предметов и слотов](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/15)**
   - Ветка: `feature/issue-15-classrooms-subjects-slots-api`
   - Результат: роутеры `/api/v1/classrooms`, `/api/v1/subjects`, `/api/v1/time-slots` с фильтрами по вместимости и оборудованию.

---

### 👨‍💻 Коля (7 задач)
*Зона ответственности: расписание, логика проверки накладок, пользовательские выборки и экспорт.*

1. **[#10 [MODEL] Модель занятия в расписании (Lesson / ScheduleEvent)](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/10)**
   - Ветка: `feature/issue-10-lesson-model`
   - Результат: связующая модель `Lesson` (FK на группу, преподавателя, аудиторию, предмет, слот; тип недели).
2. **[#11 [LOGIC] Детекция коллизий: проверка занятости преподавателя](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/11)**
   - Ветка: `feature/issue-11-teacher-conflict-check`
   - Результат: функция проверки пересечений занятий преподавателя с учетом четности недели.
3. **[#12 [LOGIC] Детекция коллизий: проверка занятости аудитории и вместимости](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/12)**
   - Ветка: `feature/issue-12-classroom-conflict-check`
   - Результат: проверка занятости аудитории в слот и контроль правила `capacity >= student_count`.
4. **[#16 [API] REST API управления занятиями (Lesson CRUD) с валидацией коллизий](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/16)**
   - Ветка: `feature/issue-16-lessons-crud-api`
   - Результат: роутер `/api/v1/lessons` с возвратом HTTP 409 Conflict при обнаружении накладок.
5. **[#17 [API] Эндпоинты просмотра расписания для группы и преподавателя](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/17)**
   - Ветка: `feature/issue-17-schedule-view-endpoints`
   - Результат: `GET /schedule/group/{id}` и `GET /schedule/teacher/{id}` с группировкой по дням и слотам.
6. **[#18 [API] Поиск свободных аудиторий на заданный слот](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/18)**
   - Ветка: `feature/issue-18-available-classrooms-search`
   - Результат: поиск незанятых аудиторий заданной вместимости для диспетчера.
7. **[#19 [EXPORT] Экспорт расписания в формат iCalendar (.ics) и CSV](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/19)**
   - Ветка: `feature/issue-19-calendar-export`
   - Результат: генерация файлов `.ics` (RFC 5545) и `.csv` для импорта в календари на смартфонах.

---

## 3. Очередь интеграции и параллельная разработка (GitHub Flow)

```
Этап 1 (Фундамент):
  Team Lead: #1 (Setup) -> #2 (Linters) -> #3 (CI) -> #4 (Docker) -> #5 (DB Base)
                 │
                 ▼ (main обновлен, база готова)
Этап 2 (Параллельная разработка моделей и логики):
  ┌──────────────────────────────┬──────────────────────────────┐
  │ Ваня:                        │ Коля:                        │
  │ #6 (Group)                   │ #10 (Lesson Model)           │
  │ #7 (Teacher)                 │ #11 (Teacher Conflict)       │
  │ #8 (Classroom)               │ #12 (Classroom Conflict)     │
  │ #9 (Subject & Slots)         │                              │
  └──────────────────────────────┴──────────────────────────────┘
                 │
                 ▼
  Team Lead: #13 (Фасад валидации коллизий объединяет логику)
                 │
                 ▼
Этап 3 (Параллельная разработка API):
  ┌──────────────────────────────┬──────────────────────────────┐
  │ Ваня:                        │ Коля:                        │
  │ #14 (Groups & Teachers API)  │ #16 (Lesson CRUD + 409)      │
  │ #15 (Classrooms & Slots API) │ #17 (Schedule View)          │
  │                              │ #18 (Free Classrooms)        │
  │                              │ #19 (iCal / CSV Export)      │
  └──────────────────────────────┴──────────────────────────────┘
                 │
                 ▼
Этап 4 (Приёмка и демонстрация):
  Team Lead: #20 (Seed Demo Data) + Прогон сквозных тестов + Релиз MVP v0.1.0
```

---

## 4. Регламент Code Review для команды
1. **Каждый PR проверяется коллегой:**
   - ПР Вани смотрит Коля или Team Lead.
   - ПР Коли смотрит Ваня или Team Lead.
   - ПР Team Lead смотрят Ваня и Коля.
2. **Слияние разрешено только если:**
   - Все проверки GitHub Actions CI зелёные.
   - Получен хотя бы один аппрув (`Approved`).
   - Отсутствуют неразрешенные комментарии (`Unresolved conversations`).
