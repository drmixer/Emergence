#!/usr/bin/env sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

case "${PORT}" in
  ''|*[!0-9]*)
    echo "[startup] WARN: PORT='${PORT}' is not numeric; defaulting to 8080"
    PORT=8080
    ;;
esac

WORKER_MODE_RAW="${WORKER_MODE:-false}"
WORKER_MODE_NORM="$(printf '%s' "${WORKER_MODE_RAW}" | tr '[:upper:]' '[:lower:]')"

echo "[startup] emergence-backend starting"
echo "[startup] python=$(python -V 2>&1)"
echo "[startup] host=${HOST} port=${PORT}"
echo "[startup] worker_mode=${WORKER_MODE_NORM}"

case "${WORKER_MODE_NORM}" in
  1|true|yes|on)
    echo "[startup] launching worker process"
    exec python worker.py
    ;;
esac

exec python -m uvicorn app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --timeout-keep-alive 75
