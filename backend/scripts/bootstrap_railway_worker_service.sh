#!/usr/bin/env sh
set -eu

SERVICE_NAME="${1:-worker}"
PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
BACKEND_ROOT="${PROJECT_ROOT}/backend"

echo "[worker-bootstrap] ensuring service variables for '${SERVICE_NAME}'"

railway variable set -s "${SERVICE_NAME}" \
  WORKER_MODE=true \
  SIMULATION_ACTIVE=false \
  ADMIN_ENABLED=false \
  ADMIN_WRITE_ENABLED=false \
  --skip-deploys

railway variable set -s "${SERVICE_NAME}" \
  DATABASE_URL='${{backend.DATABASE_URL}}' \
  REDIS_URL='${{backend.REDIS_URL}}' \
  OPENROUTER_API_KEY='${{backend.OPENROUTER_API_KEY}}' \
  GEMINI_API_KEY='${{backend.GEMINI_API_KEY}}' \
  MISTRAL_API_KEY='${{backend.MISTRAL_API_KEY}}' \
  ENVIRONMENT='${{backend.ENVIRONMENT}}' \
  SECRET_KEY='${{backend.SECRET_KEY}}' \
  FRONTEND_URL='${{backend.FRONTEND_URL}}' \
  USAGE_BUDGET_KEY_PREFIX='${{backend.USAGE_BUDGET_KEY_PREFIX}}' \
  --skip-deploys

echo "[worker-bootstrap] deploying backend artifact to '${SERVICE_NAME}'"
cd "${BACKEND_ROOT}"
railway up -s "${SERVICE_NAME}" -d \
  -m "Deploy dedicated worker service from backend artifact"

echo "[worker-bootstrap] complete"
