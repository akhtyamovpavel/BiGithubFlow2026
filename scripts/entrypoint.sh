#!/bin/sh
set -e

# Run database migrations before starting the application server
echo "Applying database migrations..."
if alembic upgrade head; then
    echo "Database migrations applied successfully."
else
    echo "Warning: Database migrations failed or database is temporarily unavailable."
fi

echo "Starting Uvicorn application server..."
exec uvicorn schedule_service.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
