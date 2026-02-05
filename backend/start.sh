#!/usr/bin/env sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

echo "[startup] emergence-backend starting"
echo "[startup] python=$(python -V 2>&1)"
echo "[startup] host=${HOST} port=${PORT}"

exec python -m uvicorn app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --timeout-keep-alive 75

