# ==========================================
# Stage 1: Build virtual environment
# ==========================================
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN pip install poetry==${POETRY_VERSION}

WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml poetry.lock README.md ./

# Install production dependencies only (without dev dependencies)
RUN poetry install --without dev --no-root && rm -rf ${POETRY_CACHE_DIR}

# Copy application source code
COPY src/ ./src/

# Install the application itself into the virtual environment
RUN poetry install --without dev && rm -rf ${POETRY_CACHE_DIR}

# ==========================================
# Stage 2: Runtime image
# ==========================================
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

WORKDIR /app

# Create unprivileged user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

# Copy virtual environment and source from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/src /app/src

USER appuser

EXPOSE 8000

CMD ["uvicorn", "schedule_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
