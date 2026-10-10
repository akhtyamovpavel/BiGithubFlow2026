# Руководство по развертыванию сервиса на сервере (Production Deployment)

Сервис расписаний (`ScheduleService`) упаковывается в Docker-образ и публикуется в **GitHub Container Registry (GHCR)**. Развертывание на боевом сервере выполняется с помощью **Docker Compose**.

---

## 1. Архитектура доставки и запуска

```
GitHub Repository (main / tags)
          │
          ▼ GitHub Actions (.github/workflows/publish-docker.yml)
GitHub Container Registry (ghcr.io/akhtyamovpavel/bigithubflow2026:tag)
          │
          ▼ docker compose -f docker-compose.prod.yml pull
   Target Linux Server (Docker Engine + Docker Compose)
   ┌──────────────────────────────────────────────────────────┐
   │  ┌──────────────────────┐      ┌──────────────────────┐  │
   │  │   schedule_postgres  │      │     schedule_app     │  │
   │  │    (PostgreSQL 16)   │◄────►│ (FastAPI + Alembic)  │  │
   │  │     :5432 (internal) │      │      :8000 (HTTP)    │  │
   │  └──────────────────────┘      └──────────────────────┘  │
   └──────────────────────────────────────────────────────────┘
```

При старте контейнера `schedule_app` скрипт `entrypoint.sh` автоматически накатывает свежие миграции базы данных (`alembic upgrade head`), после чего запускается сервер Uvicorn.

---

## 2. Подготовка сервера

### Требования к серверу:
- ОС: Ubuntu 22.04+ / Debian 12+
- Установленные пакеты: `docker` и `docker compose` (v2+)
- Открытые порты в фаерволе: `80`, `443` (для веба) и `22` (для SSH).

### Шаги на сервере:
1. Создайте рабочую директорию приложения:
   ```bash
   mkdir -p /opt/schedule-service
   cd /opt/schedule-service
   ```

2. Скопируйте файл [`docker-compose.prod.yml`](../docker-compose.prod.yml) на сервер в каталог `/opt/schedule-service/`.

3. Создайте боевой конфигурационный файл `.env`:
   ```bash
   cat << 'EOF' > .env
   # Application Configuration
   PORT=8000
   DOCKER_IMAGE=ghcr.io/akhtyamovpavel/bigithubflow2026:latest

   # PostgreSQL Credentials (замените пароль на безопасный)
   POSTGRES_USER=schedule_user
   POSTGRES_PASSWORD=super_secure_production_password_123!
   POSTGRES_DB=schedule_prod
   EOF
   chmod 600 .env
   ```

4. *(Если образ приватный)* Авторизуйтесь в GitHub Container Registry с помощью GitHub Personal Access Token (PAT) с правами `read:packages`:
   ```bash
   echo "<YOUR_GITHUB_PAT>" | docker login ghcr.io -u "<YOUR_GITHUB_USERNAME>" --password-stdin
   ```

---

## 3. Первый запуск сервиса

Выполните загрузку образов и старт контейнеров:
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Проверка работоспособности:
1. Проверьте статус контейнеров и healthcheck:
   ```bash
   docker compose -f docker-compose.prod.yml ps
   ```
   Оба контейнера (`schedule_postgres` и `schedule_app`) должны перейти в статус `healthy`.

2. Проверьте логи автоматического применения миграций:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f app
   ```

3. Проверьте эндпоинты здоровья сервиса:
   ```bash
   # Liveness (процесс запущен)
   curl -i http://localhost:8000/health/live

   # Readiness (база данных доступна и подключена)
   curl -i http://localhost:8000/health/ready
   ```

---

## 4. Обновление версии на сервере

Для обновления приложения на новую версию (например, `v0.1.1`):
```bash
# Укажите желаемый тег образа
export DOCKER_IMAGE=ghcr.io/akhtyamovpavel/bigithubflow2026:v0.1.1

# Подтяните обновленный образ и перезапустите app
docker compose -f docker-compose.prod.yml pull app
docker compose -f docker-compose.prod.yml up -d app
```

Alembic автоматически применит новые миграции схемы БД во время старта обновленного контейнера.
