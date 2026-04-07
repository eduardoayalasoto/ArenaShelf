#!/bin/bash
set -e

echo "[startup] Running migrations..."
python manage.py migrate --noinput

echo "[startup] Collecting static files..."
python manage.py collectstatic --noinput

echo "[startup] Starting library worker in background..."
python manage.py run_library_worker &
WORKER_PID=$!
echo "[startup] Worker PID: $WORKER_PID"

echo "[startup] Starting gunicorn..."
exec gunicorn bookshelf.wsgi:application --bind 0.0.0.0:$PORT
