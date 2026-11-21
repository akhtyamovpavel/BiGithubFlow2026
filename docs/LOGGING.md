# Централизованный сбор логов (Loki + Promtail + Grafana)

Инфраструктура сбора и поиска логов контейнеров `ScheduleService` (**FastAPI**, **Nginx**, **PostgreSQL**) построена на базе **Promtail → Grafana Loki → Grafana** и подключается поверх базового или production Docker Compose через оверлей [`docker-compose.observability.yml`](../docker-compose.observability.yml).

---

## 1. Архитектура и постоянное хранение

```text
┌────────────────┐  ┌────────────────┐  ┌──────────────────┐
│  app (FastAPI) │  │ frontend(Nginx)│  │ postgres (PG 16) │
└───────┬────────┘  └───────┬────────┘  └────────┬─────────┘
        │ Docker json-file (stdout/stderr, rotation 10m x 3)
        ▼
┌──────────────────────────────────────────────────────────┐
│ Promtail (docker_sd_configs, /var/run/docker.sock:ro)    │
│ • нормализует service (app / nginx / postgres) и level   │
│ • извлекает request_id в Loki structured_metadata        │
│ • маскирует секреты (Authorization, password, token)     │
│ • хранит позиции чтения в volume: promtail_positions     │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP push (внутренняя сеть Docker)
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Loki 3.4 (TSDB v13, retention 168h / 7 дней)             │
│ • не публикует порт наружу (только внутренняя сеть)      │
│ • постоянное хранилище в volume: loki_data (/loki)       │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP query (внутренняя сеть Docker)
                           ▼
┌──────────────────────────────────────────────────────────┐
│ Grafana 11.5 (общий экземпляр для логов и метрик #50)    │
│ • слушает только 127.0.0.1:3000 по умолчанию             │
│ • анонимный доступ и саморегистрация отключены           │
│ • авто-provisioning datasource Loki и дашборда логов     │
│ • постоянное хранилище в volume: grafana_data            │
└──────────────────────────────────────────────────────────┘
```

### Файлы конфигурации

| Файл | Назначение |
|---|---|
| [`docker-compose.observability.yml`](../docker-compose.observability.yml) | Оверлей Compose: добавляет метки/ротацию логов на `app`, `frontend`, `postgres` и поднимает `loki`, `promtail`, `grafana` с named volumes (`loki_data`, `promtail_positions`, `grafana_data`). |
| [`observability/loki/loki-config.yml`](../observability/loki/loki-config.yml) | Конфигурация Loki 3.x: TSDB v13, локальное хранение в `/loki`, retention `168h` (7 дней), `allow_structured_metadata: true`. |
| [`observability/promtail/promtail-config.yml`](../observability/promtail/promtail-config.yml) | Сборщик Promtail: автообнаружение контейнеров через `docker_sd_configs`, нормализация меток `service` и `level`, извлечение `request_id` в structured metadata, защитная маскировка секретов. |
| [`observability/grafana/provisioning/datasources/loki.yml`](../observability/grafana/provisioning/datasources/loki.yml) | Автоматическое подключение datasource `Loki` (`uid: loki`) с derived field `RequestID` для перехода по `request_id`. |
| [`observability/grafana/provisioning/dashboards/dashboards.yml`](../observability/grafana/provisioning/dashboards/dashboards.yml) | Общий провайдер дашбордов Grafana из `/var/lib/grafana/dashboards` (папка `ScheduleService`). |
| [`observability/grafana/dashboards/logs.json`](../observability/grafana/dashboards/logs.json) | Дашборд `ScheduleService — Logs & Request Tracing` (`uid: schedule-service-logs`) с фильтрами `service`, `level`, `request_id`, `search`. |

---

## 2. Запуск стека

### Локальный запуск (разработка и проверка)

```bash
# Опционально задайте учётные данные Grafana в .env (см. .env.example)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
```

Проверьте готовность сервисов:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml ps
```

Откройте Grafana в браузере: `http://127.0.0.1:3000` (логин/пароль из `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`, по умолчанию `admin` / `change-me-in-prod`).

### Запуск в production

```bash
# В .env обязательно задайте надёжный GRAFANA_ADMIN_PASSWORD
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml up -d
```

Для доступа к Grafana на удалённом сервере без публикации порта наружу используйте SSH-туннель:

```bash
ssh -N -L 3000:127.0.0.1:3000 root@execed.tech
```

После этого Grafana доступна локально на `http://127.0.0.1:3000`.

---

## 3. Ограничение доступа и безопасность

1. **Loki и Promtail изолированы во внутренней сети Docker**: порты `3100` (Loki) и `9080` (Promtail) не публикуются на хост (`ports` не заданы, используется только `expose`), поэтому прямой неавторизованный доступ к API логов извне невозможен.
2. **Grafana привязана к loopback (`127.0.0.1`)**: переменная `GRAFANA_BIND_HOST` по умолчанию равна `127.0.0.1`, что исключает случайную публикацию интерфейса логов на публичном интерфейсе сервера.
3. **Отключён анонимный доступ и регистрация**:
   - `GF_AUTH_ANONYMOUS_ENABLED=false`
   - `GF_USERS_ALLOW_SIGN_UP=false`
   - `GF_USERS_ALLOW_ORG_CREATE=false`
   - Пароль администратора передаётся через `GRAFANA_ADMIN_PASSWORD` в `.env` (в production необходимо заменить значение по умолчанию).
4. **Изоляция сбора и read-only доступ к Docker socket**: `/var/run/docker.sock` монтируется в режиме `:ro`, а `docker_sd_configs.filters` ограничивает сбор строго контейнерами с меткой `logging=promtail` (`app`, `frontend`, `postgres`), исключая попадание логов сторонних контейнеров на хосте.
5. **Защитная маскировка чувствительных данных**: в pipeline Promtail настроены стадии `replace`, редактирующие значения `Authorization` / `Bearer`, `password`, `secret`, `access_token`, `refresh_token`, `session_id`, `cookie` на `[REDACTED]` на случай непреднамеренного попадания в сырой вывод контейнеров.

---

## 4. Поиск логов и трассировка по `request_id`

После входа в Grafana автоматически открывается дашборд **ScheduleService — Logs & Request Tracing** (папка `ScheduleService`).

### Фильтрация на дашборде
- **Service** (`$service`): `All`, `app`, `nginx`, `postgres`.
- **Level** (`$level`): `All`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
- **Request ID** (`$request_id`): вставьте значение заголовка `X-Request-ID` из ответа API/Nginx — панель **Request Trace (Nginx + FastAPI by request_id)** отобразит связанные записи прокси и бэкенда в хронологическом порядке (`Ascending`).
- **Search** (`$search`): произвольный полнотекстовый фильтр.

### Полезные LogQL-запросы для Grafana Explore

- Все записи конкретного запроса в Nginx и FastAPI (через structured metadata Loki 3.x):
  ```logql
  {service=~"app|nginx"} | request_id = "<request_id>"
  ```
- Полнотекстовый поиск того же `request_id` (работает также для неструктурированных строк):
  ```logql
  {service=~"app|nginx"} |= "<request_id>"
  ```
- Ошибки и предупреждения приложения (включая конфликты `409 Conflict` с уровнем `WARNING`):
  ```logql
  {service="app", level=~"WARNING|ERROR|CRITICAL"}
  ```
- Ошибки PostgreSQL:
  ```logql
  {service="postgres", level=~"WARNING|ERROR|CRITICAL"}
  ```

---

## 5. Проверка сохранности логов после перезапуска

Постоянство хранения обеспечивается именованными Docker volumes `loki_data`, `promtail_positions` и `grafana_data`:

```bash
# Перезапускаем Loki и Grafana без удаления volumes
docker compose -f docker-compose.yml -f docker-compose.observability.yml restart loki grafana
```

После перезапуска ранее записанные логи остаются доступны в Grafana, а datasource `Loki` и дашборд `ScheduleService — Logs & Request Tracing` загружаются автоматически из файлов provisioning без ручной настройки.

---

## 6. Контракт интеграции со смежными задачами

- **FastAPI JSON-логи (#47)** и **Nginx JSON-логи (#61)**:
  - Promtail ожидает JSON-строки с полями `request_id` (или `x_request_id`) и `level` (`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`), а при отсутствии явного `level` в access-логе Nginx автоматически вычисляет уровень из HTTP-кода `status` (`5xx` → `ERROR`, `4xx` → `WARNING`, иначе `INFO`).
  - Для неструктурированных строк PostgreSQL, ошибок Nginx и Uvicorn работают резервные регулярные выражения, нормализующие уровень в единый набор `DEBUG|INFO|WARNING|ERROR|CRITICAL`.
- **Общий экземпляр Grafana с задачей мониторинга (#50)**:
  - `observability/grafana/provisioning/datasources/` загружает каждый файл datasource отдельно (`loki.yml` принадлежит #48; задача #50 добавляет рядом `prometheus.yml` без конфликта).
  - `observability/grafana/provisioning/dashboards/dashboards.yml` автоматически подхватывает все JSON-дашборды из `observability/grafana/dashboards/` (`logs.json` принадлежит #48; задача #50 добавляет рядом `metrics.json`).

---

## 7. JSON-логи Nginx и сквозной проброс `X-Request-ID` (#61)

В [`frontend/nginx.conf.template`](../frontend/nginx.conf.template) настроен формат `json_access` (`escape=json`) и безопасный проброс `X-Request-ID`:
- Входящий `X-Request-ID` принимается только по шаблону `^[A-Za-z0-9._-]{1,128}$` (совпадает с валидацией FastAPI); при отсутствии или некорректном значении подставляется сгенерированный Nginx `$request_id`.
- Идентификатор передаётся в FastAPI (`proxy_set_header X-Request-ID $resolved_request_id`), а дублирование заголовка ответа исключено через `proxy_hide_header X-Request-ID` + единый `add_header X-Request-ID $resolved_request_id always` (включая ошибки прокси `502`/`504` и `404`).
- В access-лог пишутся `timestamp`, `service`, `request_id`, `method`, `uri` (без query string, чтобы не раскрывать токены/пароли), `status`, `duration_s`, `upstream_duration_s`, `bytes_sent`, `remote_addr`.

### Проверка в Docker Compose
```bash
# 1. Валидация конфигурации Nginx
docker compose exec -T frontend nginx -t

# 2. Запрос через Nginx: ровно один X-Request-ID, совпадает в ответе, логах Nginx и FastAPI
RID="trace-demo-001"
curl -sD - -o /dev/null -H "X-Request-ID: ${RID}" http://localhost:8080/health/ready | grep -i '^x-request-id:'
docker compose logs --tail=20 frontend | grep "${RID}"
docker compose logs --tail=20 app | grep "${RID}"

# 3. Невалидный X-Request-ID заменяется безопасным идентификатором, а при 502 заголовок сохраняется
curl -sD - -o /dev/null -H 'X-Request-ID: bad value!' http://localhost:8080/health/ready | grep -i '^x-request-id:'
```
