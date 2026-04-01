#!/bin/bash
# Точечный launcher для smart-irrigation E2E pipeline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
E2E_DIR="$PROJECT_ROOT/tests/e2e"

if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "❌ Не найден docker compose или docker-compose"
  exit 1
fi

export HYDRO_SEED_PROFILE="${HYDRO_SEED_PROFILE:-smart-irrigation}"
export LARAVEL_URL="${LARAVEL_URL:-http://localhost:8081}"
export MQTT_HOST="${MQTT_HOST:-localhost}"
export MQTT_PORT="${MQTT_PORT:-1884}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5433}"
export DB_DATABASE="${DB_DATABASE:-hydro_e2e}"
export DB_USERNAME="${DB_USERNAME:-hydro}"
export DB_PASSWORD="${DB_PASSWORD:-hydro_e2e}"
export WS_URL="${WS_URL:-ws://localhost:6002/app/local}"

echo "🧪 Smart irrigation E2E launcher"
echo "  - HYDRO_SEED_PROFILE=${HYDRO_SEED_PROFILE}"

"${DOCKER_COMPOSE[@]}" -f "$E2E_DIR/docker-compose.e2e.yml" down -v --remove-orphans >/dev/null 2>&1 || true
"${DOCKER_COMPOSE[@]}" -f "$E2E_DIR/docker-compose.e2e.yml" up -d --build

cd "$E2E_DIR"
if [ ! -d "$E2E_DIR/venv" ]; then
  python3 -m venv "$E2E_DIR/venv"
fi

PYTHON_BIN="$E2E_DIR/venv/bin/python3"
PIP_BIN="$E2E_DIR/venv/bin/pip"

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import yaml  # noqa: F401
import httpx  # noqa: F401
import websockets  # noqa: F401
import tenacity  # noqa: F401
import psycopg  # noqa: F401
PY
then
  "$PIP_BIN" install -q -r "$E2E_DIR/requirements.txt"
fi

PYTHONPATH="$E2E_DIR" "$PYTHON_BIN" -m runner.suite \
  "scenarios/ae3lite/E108_ae3_irrigation_inline_correction_contract.yaml" \
  "scenarios/ae3lite/E107_ae3_start_irrigation_api_smoke.yaml" \
  "scenarios/ae3lite/E109_ae3_irrigation_inline_correction_node_sim.yaml"
