# Бэклог задач MVP (20 задач для реализации в Python)

Все задачи созданы в репозитории [akhtyamovpavel/BiGithubFlow2026/issues](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues) и готовы к взятию в работу по процессу **GitHub Flow**.

---

### Правила работы по GitHub Flow для команды:
1. Каждый разработчик (Ваня, Коля, Вася) выбирает задачу из бэклога и назначает её на себя.
2. От актуальной ветки `main` создается ветка: `git checkout -b feature/issue-<номер>-<краткое-имя>`.
3. Разработка ведется локально с соблюдением требований линтеров (`ruff`, `mypy`) и написанием тестов (`pytest`).
4. Изменения пушатся в GitHub: `git push -u origin feature/...`.
5. Открывается Pull Request в `main` со ссылкой на задачу (например, `Closes #1`).
6. GitHub Actions CI автоматически запускает линтеры и тесты.
7. Проводится Code Review минимум одним коллегой.
8. После аппрува и успешного CI выполняется слияние (Squash and merge или Rebase) в `main`, ветка удаляется.

---

## Реестр 20 задач MVP

| № | Issue | Модуль / Метка | Название задачи | Описание и результат |
|---|---|---|---|---|
| 1 | [#1](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/1) | `infra`, `mvp` | [INFRA] Инициализация проекта, Poetry/uv и модуля конфигурации | Скелет сервиса, pyproject.toml, Pydantic-Settings, `/health` эндпоинт. |
| 2 | [#2](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/2) | `infra`, `mvp` | [INFRA] Настройка линтинга, форматирования и pre-commit (Ruff, mypy) | Конфигурация Ruff, mypy (strict), pre-commit хуки. |
| 3 | [#3](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/3) | `infra`, `mvp` | [CI/CD] Настройка GitHub Actions CI пайплайна | Автоматический прогон линтеров и pytest на каждый PR. |
| 4 | [#4](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/4) | `infra`, `mvp` | [INFRA] Контейнеризация сервиса (Dockerfile и docker-compose) | Multi-stage Dockerfile, PostgreSQL 16 в docker-compose. |
| 5 | [#5](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/5) | `models`, `mvp` | [CORE] Подключение к БД через SQLAlchemy 2.0 (asyncio) и настройка Alembic | Async engine, sessionmaker, базовая модель `Base`, асинхронный Alembic. |
| 6 | [#6](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/6) | `models`, `mvp` | [MODEL] Справочник академических групп (модель Group, Pydantic-схемы) | Модель группы, валидация численности, Pydantic-схемы, миграция. |
| 7 | [#7](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/7) | `models`, `mvp` | [MODEL] Справочник преподавателей (модель Teacher, Pydantic-схемы) | Модель преподавателя (ФИО, уникальный email, кафедра), схемы, миграция. |
| 8 | [#8](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/8) | `models`, `mvp` | [MODEL] Справочник аудиторий (модель Classroom, Pydantic-схемы) | Модель аудитории (корпус, номер, вместимость, проектор), схемы, миграция. |
| 9 | [#9](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/9) | `models`, `mvp` | [MODEL] Справочники дисциплин и временных слотов (Subject, TimeSlot) | Модели предметов и сетки звонков (1..7 пары, дни недели), схемы. |
| 10 | [#10](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/10) | `models`, `mvp` | [MODEL] Модель занятия в расписании (Lesson / ScheduleEvent) | Центральная модель занятия с FK на все справочники, тип недели, миграция. |
| 11 | [#11](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/11) | `logic`, `mvp` | [LOGIC] Детекция коллизий: проверка занятости преподавателя | Алгоритм проверки занятости преподавателя в слот с учетом четности недели. |
| 12 | [#12](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/12) | `logic`, `mvp` | [LOGIC] Детекция коллизий: проверка занятости аудитории и вместимости | Проверка занятости кабинета и соответствия вместимости размеру группы. |
| 13 | [#13](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/13) | `logic`, `mvp` | [LOGIC] Детекция коллизий: занятость группы и фасад валидации расписания | Проверка занятости группы и единый фасад валидации занятия перед сохранением. |
| 14 | [#14](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/14) | `api`, `mvp` | [API] CRUD эндпоинты для академических групп и преподавателей | Роутеры `/api/v1/groups` и `/api/v1/teachers` с пагинацией и фильтрами. |
| 15 | [#15](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/15) | `api`, `mvp` | [API] CRUD эндпоинты для аудиторий, предметов и слотов | Роутеры `/api/v1/classrooms`, `/api/v1/subjects`, `/api/v1/time-slots`. |
| 16 | [#16](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/16) | `api`, `mvp` | [API] REST API управления занятиями (Lesson CRUD) с валидацией коллизий | Эндпоинты создания и редактирования пар с возвратом HTTP 409 при накладках. |
| 17 | [#17](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/17) | `api`, `mvp` | [API] Эндпоинты просмотра расписания для группы и преподавателя | Структурированное расписание на неделю по дням и слотам. |
| 18 | [#18](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/18) | `api`, `mvp` | [API] Поиск свободных аудиторий на заданный слот | Поиск доступных аудиторий заданной вместимости для переноса занятий. |
| 19 | [#19](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/19) | `export`, `mvp` | [EXPORT] Экспорт расписания в формат iCalendar (.ics) и CSV | Выгрузка в календарные форматы (RFC 5545) для Google/Apple Calendar. |
| 20 | [#20](https://github.com/akhtyamovpavel/BiGithubFlow2026/issues/20) | `infra`, `mvp` | [DATA] Скрипт генерации демонстрационных данных (Seed fixtures) | Идемпотентный скрипт создания тестовых групп, преподавателей, аудиторий и пар. |
