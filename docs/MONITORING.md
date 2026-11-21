# Мониторинг: Prometheus, Grafana и оповещения (#50)

Стек метрик разворачивается единым оверлеем [`docker-compose.observability.yml`](../docker-compose.observability.yml) вместе с логами (`#48`) и экспортерами (`#63`).

## 1. Запуск и доступ к Grafana
```bash
# Локальная разработка / тестовое окружение
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

# Production (в .env должны быть заданы POSTGRES_PASSWORD и GRAFANA_ADMIN_PASSWORD)
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml pull
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml up -d
```
- **Grafana:** `http://127.0.0.1:3000` (на сервере через `ssh -N -L 3000:127.0.0.1:3000 root@execed.tech`). Учётные данные задаются в `.env` (`GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`), анонимный доступ и регистрация отключены.
- **Авто-provisioning:** datasource `Prometheus` (`uid: prometheus`) и дашборд **ScheduleService — Service Health & Metrics** (`observability/grafana/dashboards/metrics.json`) загружаются автоматически.
- **Prometheus:** доступен только во внутренней сети `monitoring` (`http://prometheus:9090`), без публикации порта наружу.

## 2. Проверка scrape-таргетов и правил оповещений
```bash
# Проверка валидности конфига и правил
docker compose -f docker-compose.yml -f docker-compose.observability.yml exec -T prometheus \
  promtool check config /etc/prometheus/prometheus.yml

# Проверка, что все 4 таргета (prometheus, schedule-app, postgres-exporter, nginx-exporter) в статусе up
docker compose -f docker-compose.yml -f docker-compose.observability.yml exec -T prometheus \
  wget -qO- http://127.0.0.1:9090/api/v1/targets | grep -o '"health":"[^"]*"'
```

### Воспроизводимая проверка срабатывания и восстановления оповещений
1. Остановите `frontend` (или `nginx-exporter`):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.observability.yml stop frontend
   ```
2. Через 15–75 секунд проверьте переход правила `NginxDown` в `pending` → `firing`:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.observability.yml exec -T prometheus \
     wget -qO- http://127.0.0.1:9090/api/v1/alerts
   ```
3. Восстановите сервис и убедитесь, что алерт исчез через 2–3 цикла оценки (`30–45с`):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.observability.yml start frontend
   ```

## 3. Диагностика отказа и восстановление
| Алерт / симптом | Что проверить | Восстановление |
|---|---|---|
| `ServiceTargetDown` (`schedule-app`) | `docker compose ps`, `curl -i http://localhost:8000/health/ready`, логи `app` в Grafana Loki | Перезапустить `app` (`docker compose restart app`); при падении после релиза — откатить `DOCKER_IMAGE` на предыдущий тег. |
| `PostgreSQLDown` (`pg_up == 0`) | `docker compose logs postgres postgres-exporter`, свободное место на диске (`df -h`), параметры `POSTGRES_*` в `.env` | Перезапустить `postgres` и `postgres-exporter`; проверить целостность тома `postgres_data`. |
| `NginxDown` (`nginx_up == 0`) | `docker compose exec -T frontend nginx -t`, `docker compose logs frontend` | Исправить конфигурацию Nginx и перезапустить `frontend`. |
| `HighHttp5xxErrorRate` (`> 5%` за `5m`, `for: 2m`) | Дашборд логов в Grafana: `{service="app", level="ERROR"}`, трассировка по `request_id` | Устранить причину 500 (БД/миграция/регрессия) или откатить образ `app`. |
| `HighHttpP95Latency` (`p95 > 500ms` за `5m`, `for: 3m`) | Панель `PostgreSQL Connections`, медленные запросы в логах `app` (`duration_ms`) и `nginx` (`upstream_duration_s`) | Проверить блокировки БД, нагрузку и при необходимости перезапустить/масштабировать `app`. |
