# Метрики Prometheus FastAPI (`GET /metrics`)

Приложение `ScheduleService` экспортирует HTTP-метрики (RED) и бизнес-метрики расписания в текстовом формате Prometheus (`text/plain; version=0.0.4; charset=utf-8`) на эндпоинте **`GET /metrics`**.

Эндпоинт `/metrics` доступен без пользовательской авторизации (аналогично `/health/ready`) для сбора Prometheus внутри сети Docker Compose (`http://app:8000/metrics`).

---

## 1. Реестр метрик и меток

| Метрика | Тип | Метки (ограниченная кардинальность) | Описание |
|---|---|---|---|
| `http_requests_total` | `Counter` | `method`, `route`, `status_code`, `status_class` | Общее число HTTP-запросов, обработанных FastAPI |
| `http_request_duration_seconds` | `Histogram` | `method`, `route` (корзины: `0.005..10.0` с, включая `0.5` с) | Длительность обработки HTTP-запросов в секундах |
| `schedule_lessons_created_total` | `Counter` | `lesson_type` (`LECTURE`, `SEMINAR`, `LAB`) | Количество успешно созданных занятий |
| `schedule_conflicts_detected_total` | `Counter` | `conflict_type` (`TEACHER_BUSY`, `CLASSROOM_BUSY`, `GROUP_BUSY`, `CAPACITY_EXCEEDED`, `OCCURRENCE_EXCEPTION`, `INTEGRITY_ERROR`) | Количество зафиксированных конфликтов расписания |
| `schedule_exports_total` | `Counter` | `format` (`ics`, `csv`), `target` (`group`, `teacher`) | Количество выполненных экспортов расписания |
| `schedule_db_entities_count` | `Gauge` | `entity` (`groups`, `teachers`, `classrooms`, `subjects`, `time_slots`, `lessons`) | Текущее количество сущностей в БД (обновляется при сборе `/metrics`) |

---

## 2. Ограничение кардинальности и приватность

- **Нет персональных данных (PII):** имена, email, логины, пароли и токены никогда не попадают в метки.
- **Нет `request_id`:** идентификатор запроса используется только в логах (`docs/LOGGING.md`), но не в метках Prometheus.
- **Нормализация `route`:** используется шаблон маршрута FastAPI (например, `/api/v1/lessons/{lesson_id}`), а неизвестные пути (404) группируются под `route="unmatched"`.
- **Фиксированные enum-метки:** значения `method`, `status_class` (`2xx`/`3xx`/`4xx`/`5xx`/`other`), `lesson_type`, `conflict_type`, `format`, `target` и `entity` валидируются по закрытым спискам.

---

## 3. Запросы PromQL для дашборда и алертов (#50)

```promql
# Общий RPS по приложению
sum(rate(http_requests_total[5m]))

# Доля 5xx-ошибок (алерт > 5%)
sum(rate(http_requests_total{status_class="5xx"}[5m]))
/
clamp_min(sum(rate(http_requests_total[5m])), 1e-9)

# Перцентили длительности p50 / p95 / p99 (алерт p95 > 0.5 c)
histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Бизнес-метрики
sum by (lesson_type) (increase(schedule_lessons_created_total[1h]))
sum by (conflict_type) (increase(schedule_conflicts_detected_total[1h]))
sum by (format, target) (increase(schedule_exports_total[1h]))
schedule_db_entities_count
```
