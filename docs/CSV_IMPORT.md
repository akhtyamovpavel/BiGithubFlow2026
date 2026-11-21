# Импорт расписания из CSV (API-контракт и шаблон)

Модуль массового импорта расписания позволяет администраторам и диспетчерам загрузить CSV-файл, получить построчный предпросмотр с проверкой справочников и коллизий, а затем сохранить весь пакет занятий атомарно в одной транзакции.

## 1. Доступ и ограничения

- **Роли:** только `admin` и `dispatcher` (роль `reader` получает `403 Forbidden`, анонимный запрос — `401 Unauthorized` на всех эндпоинтах, включая скачивание шаблона).
- **Максимальный размер файла:** `1 MiB` (`1 048 576` байт) — при превышении возвращается `413 Payload Too Large`.
- **Максимум строк данных:** `500` непустых строк — при превышении возвращается `422 Unprocessable Entity`.
- **Кодировка и формат:** UTF-8 (поддерживается UTF-8 с BOM), разделитель `,`, автосоздание справочников не выполняется.

## 2. Формат CSV-шаблона

Заголовок (строка `1`), данные начинаются со строки `2`:

```csv
group_name,teacher_email,subject_code,classroom_building,classroom_room,day_of_week,slot_number,lesson_type,parity,specific_date
Б05-401,s.ivanov@phystech.edu,MATH-101,Главный корпус,115,1,1,LECTURE,ALWAYS,
```

| Колонка | Обязательна | Описание и привязка к справочнику |
|---|---|---|
| `group_name` | да | Уникальное имя существующей академической группы (`groups.name`). |
| `teacher_email` | да | Email существующего преподавателя (`teachers.email`, без учёта регистра). |
| `subject_code` | да | Код существующего предмета (`subjects.code`) или однозначное название (`subjects.name`). |
| `classroom_building` | да | Корпус существующей аудитории (`classrooms.building`). |
| `classroom_room` | да | Номер существующей аудитории (`classrooms.room_number`). |
| `day_of_week` | да | День недели (`1` = Пн … `7` = Вс), ищется в `time_slots`. |
| `slot_number` | да | Номер пары (`1..7`), ищется в `time_slots` по `(day_of_week, slot_number)`. |
| `lesson_type` | да | `LECTURE`, `SEMINAR` или `LAB`. |
| `parity` | нет | `ALWAYS` (по умолчанию), `ODD_WEEK` или `EVEN_WEEK`. |
| `specific_date` | нет | Разовая дата в формате `YYYY-MM-DD`; день недели даты обязан совпадать с `day_of_week`. |

## 3. Эндпоинты API

| Метод и путь | Назначение | Коды ответа |
|---|---|---|
| `GET /api/v1/schedule/import/template` | Скачать CSV-шаблон (`schedule_import_template.csv`). | `200`, `401`, `403` |
| `POST /api/v1/schedule/import/preview` | Загрузить CSV (`multipart/form-data`, поле `file`, опциональный заголовок `Idempotency-Key`), выполнить валидацию и получить `batch_id`. | `200`, `401`, `403`, `409`, `413`, `422` |
| `GET /api/v1/schedule/import/{batch_id}` | Проверить актуальный статус и результат пакета (безопасно после потери соединения). | `200`, `401`, `403`, `404` |
| `POST /api/v1/schedule/import/{batch_id}/confirm` | Повторно проверить пакет под блокировкой расписания и атомарно сохранить все занятия одной транзакцией. | `200`, `401`, `403`, `404`, `409` |

## 4. Формат ответа и ошибок

Эндпоинты `preview`, `GET /{batch_id}` и `confirm` возвращают единую структуру `CsvImportBatchResponse`:

- `batch_id`, `status` (`preview` | `committed` | `failed`), `can_commit`, `already_committed`, `content_hash`
- `total_rows`, `valid_rows`, `error_rows`, `created_count`, `created_lesson_ids`
- `rows`: список строк с распарсенными полями, найденными ID справочников и локальными `errors`
- `errors`: плоский список ошибок вида `{"row": 2, "field": "teacher_email", "code": "UNKNOWN_TEACHER", "message": "..."}`

Проверяются:
1. Корректность типов, перечислений и дат (`specific_date` + совпадение дня недели).
2. Существование всех справочников и вместимость аудитории (`CAPACITY_EXCEEDED`).
3. Коллизии внутри самого CSV-файла (`FILE_TEACHER_CONFLICT`, `FILE_CLASSROOM_CONFLICT`, `FILE_GROUP_CONFLICT`).
4. Коллизии с существующими занятиями в БД (`TEACHER_BUSY`, `CLASSROOM_BUSY`, `GROUP_BUSY`, `CAPACITY_EXCEEDED`).

## 5. Идемпотентность и восстановление после потери соединения

- **Повторная загрузка:** при передаче `Idempotency-Key` с тем же файлом возвращается тот же `batch_id` (с другим файлом — `409 Conflict`). Повторная загрузка уже применённого CSV (по `content_hash`) возвращает применённый пакет (`status: "committed"`, `already_committed: true`) без дублирования занятий.
- **Повторное подтверждение:** повторный `POST /{batch_id}/confirm` для уже применённого пакета возвращает `200 OK` с `already_committed: true` и исходными `created_lesson_ids`, не создавая дубликатов.
- **Потеря соединения при confirm:** клиент может безопасно вызвать `GET /api/v1/schedule/import/{batch_id}` или повторить `POST /api/v1/schedule/import/{batch_id}/confirm`, чтобы узнать итоговый статус пакета.
- **Изменение БД после предпросмотра:** `confirm` всегда повторяет полную проверку под `lock_schedule`; при появлении новой коллизии или удалении справочника возвращается `409 Conflict` со свежим списком `errors`, а БД остаётся неизменной.
