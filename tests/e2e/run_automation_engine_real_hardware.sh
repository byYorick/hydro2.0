#!/usr/bin/env bash
# Run automation_engine E2E scenarios against a real test node (no node-sim control)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x "$SCRIPT_DIR/venv/bin/python3" ]; then
  echo "📦 Создаем virtualenv для E2E..."
  python3 -m venv "$SCRIPT_DIR/venv"
fi

PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"
PIP_BIN="$SCRIPT_DIR/venv/bin/pip"

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import yaml  # noqa: F401
import httpx  # noqa: F401
import websockets  # noqa: F401
import tenacity  # noqa: F401
import psycopg  # noqa: F401
PY
then
  echo "📦 Устанавливаем зависимости E2E в virtualenv..."
  "$PIP_BIN" install -r "$SCRIPT_DIR/requirements.txt"
fi

if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "❌ Не найден docker compose или docker-compose"
  exit 1
fi

: "${TEST_NODE_GH_UID:=gh-test-1}"
: "${TEST_NODE_ZONE_UID:=zn-test-1}"
: "${TEST_NODE_UID:=nd-ph-esp32una}"
: "${TEST_NODE_HW_ID:=esp32-test-001}"

export E2E_REAL_HARDWARE=1
export TEST_NODE_GH_UID TEST_NODE_ZONE_UID TEST_NODE_UID TEST_NODE_HW_ID
LARAVEL_URL="${LARAVEL_URL:-http://localhost:8081}"

SERVICES=(automation-engine history-logger laravel mqtt-bridge digital-twin)
SCENARIOS=(
  "scenarios/automation_engine/E60_climate_control_happy.yaml"
  "scenarios/automation_engine/E61_fail_closed_corrections.yaml"
  "scenarios/automation_engine/E62_controller_fault_isolation.yaml"
  "scenarios/automation_engine/E63_backoff_on_errors.yaml"
  "scenarios/automation_engine/E64_effective_targets_only.yaml"
  "scenarios/automation_engine/E65_phase_transition_api.yaml"
  "scenarios/automation_engine/E66_fail_closed_corrections.yaml"
)

scan_logs_since_epoch() {
  local start_epoch="$1"
  local since_iso
  since_iso="$(date -u -d "@${start_epoch}" +"%Y-%m-%dT%H:%M:%SZ")"

  local found=0
  for svc in "${SERVICES[@]}"; do
    local out
    out="$("${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" logs --since "$since_iso" "$svc" 2>/dev/null | rg -n " - (ERROR|CRITICAL) - |Traceback|Exception" -S || true)"
    if [ -n "$out" ]; then
      found=1
      echo "\n❌ Найдены ошибки в логах сервиса $svc:"
      echo "$out"
    fi
  done

  if [ "$found" -eq 0 ]; then
    return 0
  fi
  return 1
}

db_query_line() {
  local sql="$1"
  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T postgres \
    psql -U "${POSTGRES_USER:-hydro}" -d "${POSTGRES_DB:-hydro_e2e}" -AtF '|' -c "$sql"
}

wait_laravel_health() {
  local timeout="${1:-120}"
  local started_at
  started_at="$(date +%s)"
  while true; do
    if "$PYTHON_BIN" - <<'PY' "$LARAVEL_URL" >/dev/null 2>&1
import sys
import httpx
base = sys.argv[1].rstrip("/")
paths = ["/api/health", "/api/system/health"]
with httpx.Client(timeout=3.0) as c:
    for path in paths:
        try:
            r = c.get(base + path)
            if r.status_code == 200:
                raise SystemExit(0)
        except Exception:
            pass
raise SystemExit(1)
PY
    then
      return 0
    fi
    if [ $(( "$(date +%s)" - started_at )) -ge "$timeout" ]; then
      return 1
    fi
    sleep 2
  done
}

get_auth_token() {
  "$PYTHON_BIN" - <<'PY' "$LARAVEL_URL"
import httpx
import sys
base = sys.argv[1].rstrip("/")
payload = {"email": "e2e@test.local", "role": "agronomist"}
with httpx.Client(timeout=15.0) as c:
    resp = c.post(base + "/api/e2e/auth/token", json=payload)
resp.raise_for_status()
payload = resp.json()
token = ((payload.get("data") or {}).get("token")) or ""
if not token:
    raise SystemExit(1)
print(token)
PY
}

api_request_code() {
  local method="$1"
  local url="$2"
  local payload="$3"
  local token="$4"
  local out_file="$5"
  "$PYTHON_BIN" - <<'PY' "$method" "$url" "$payload" "$token" "$out_file"
import json
import sys
import httpx

method, url, payload_raw, token, out_file = sys.argv[1:6]
payload = json.loads(payload_raw) if payload_raw else {}
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"

with httpx.Client(timeout=20.0) as c:
    resp = c.request(method=method.upper(), url=url, headers=headers, json=payload)

with open(out_file, "w", encoding="utf-8") as f:
    f.write(resp.text)

print(resp.status_code)
PY
}

prepare_real_hardware_node() {
  echo "🔧 Подготовка real hardware ноды для e2e..."

  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" up -d \
    postgres redis mosquitto history-logger mqtt-bridge automation-engine laravel digital-twin >/dev/null

  if ! wait_laravel_health 180; then
    echo "❌ Laravel не стал healthy вовремя: $LARAVEL_URL/api/system/health"
    exit 1
  fi

  echo "🔐 Получаю e2e токен..."
  local token
  if ! token="$(get_auth_token)"; then
    echo "❌ Не удалось получить e2e auth token"
    exit 1
  fi

  echo "📍 Ищу тестовую зону uid=${TEST_NODE_ZONE_UID}..."
  local zone_row
  zone_row="$(db_query_line "SELECT z.id, z.uid, g.uid FROM zones z JOIN greenhouses g ON g.id = z.greenhouse_id WHERE z.uid = '${TEST_NODE_ZONE_UID}' LIMIT 1;")"
  if [ -z "$zone_row" ]; then
    echo "❌ Не найдена тестовая зона uid=${TEST_NODE_ZONE_UID}"
    exit 1
  fi
  local zone_id zone_uid gh_uid
  IFS='|' read -r zone_id zone_uid gh_uid <<<"$zone_row"

  local node_row=""
  if [ -n "${TEST_NODE_HW_ID:-}" ] && [ "${TEST_NODE_HW_ID}" != "auto" ] && [ "${TEST_NODE_HW_ID}" != "esp32-test-001" ]; then
    node_row="$(db_query_line "SELECT id, uid, hardware_id FROM nodes WHERE hardware_id = '${TEST_NODE_HW_ID}' LIMIT 1;")"
  fi

  if [ -z "$node_row" ]; then
    node_row="$(db_query_line "SELECT id, uid, hardware_id FROM nodes WHERE zone_id IS NULL AND lifecycle_state = 'REGISTERED_BACKEND' AND hardware_id IS NOT NULL AND last_seen_at > NOW() - INTERVAL '15 minutes' ORDER BY last_seen_at DESC NULLS LAST LIMIT 1;")"
  fi

  if [ -z "$node_row" ]; then
    echo "❌ Не найдена активная temp/preconfig нода (REGISTERED_BACKEND, zone_id IS NULL, last_seen_at <= 15m)."
    echo "   Подключи железо в preconfig и дождись node_hello/heartbeat."
    exit 1
  fi

  local node_id node_uid node_hw_id
  IFS='|' read -r node_id node_uid node_hw_id <<<"$node_row"
  echo "📡 Найдена нода: id=$node_id uid=$node_uid hw=$node_hw_id"

  echo "🧩 Отправляю assign node->zone через API..."
  local assign_code
  assign_code="$(api_request_code "PATCH" "$LARAVEL_URL/api/nodes/$node_id" "{\"zone_id\":$zone_id}" "$token" "/tmp/e2e_node_assign_resp.json")"
  if [ "$assign_code" -lt 200 ] || [ "$assign_code" -ge 300 ]; then
    echo "❌ PATCH /api/nodes/$node_id (zone_id=$zone_id) вернул HTTP $assign_code"
    cat /tmp/e2e_node_assign_resp.json
    exit 1
  fi

  echo "📤 Запрашиваю публикацию тестового config..."
  local publish_code
  publish_code="$(api_request_code "POST" "$LARAVEL_URL/api/nodes/$node_id/config/publish" "{}" "$token" "/tmp/e2e_node_publish_resp.json")"
  if [ "$publish_code" -lt 200 ] || [ "$publish_code" -ge 300 ]; then
    echo "⚠️ POST /api/nodes/$node_id/config/publish вернул HTTP $publish_code (продолжаю, т.к. publish мог уйти через listener)"
  fi

  local timeout=180
  local started_at
  started_at="$(date +%s)"
  echo "⏳ Жду подтверждение config_report/binding (до ${timeout}s)..."
  while true; do
    local confirm_row
    confirm_row="$(db_query_line "SELECT n.uid, n.hardware_id, z.uid, g.uid FROM nodes n JOIN zones z ON z.id = n.zone_id JOIN greenhouses g ON g.id = z.greenhouse_id WHERE n.id = ${node_id} AND n.zone_id = ${zone_id} AND n.pending_zone_id IS NULL AND n.lifecycle_state = 'ASSIGNED_TO_ZONE' AND n.last_seen_at > NOW() - INTERVAL '15 minutes' LIMIT 1;")"
    if [ -n "$confirm_row" ]; then
      IFS='|' read -r node_uid node_hw_id zone_uid gh_uid <<<"$confirm_row"
      TEST_NODE_UID="$node_uid"
      TEST_NODE_HW_ID="$node_hw_id"
      TEST_NODE_ZONE_UID="$zone_uid"
      TEST_NODE_GH_UID="$gh_uid"
      export TEST_NODE_UID TEST_NODE_HW_ID TEST_NODE_ZONE_UID TEST_NODE_GH_UID
      echo "✅ Нода подтверждена: gh=$TEST_NODE_GH_UID zone=$TEST_NODE_ZONE_UID node=$TEST_NODE_UID hw=$TEST_NODE_HW_ID"
      return 0
    fi

    if [ $(( "$(date +%s)" - started_at )) -ge "$timeout" ]; then
      echo "❌ Не дождались подтверждения binding/config_report за ${timeout}s"
      db_query_line "SELECT id, uid, hardware_id, zone_id, pending_zone_id, lifecycle_state, status, last_seen_at FROM nodes WHERE id = ${node_id};" || true
      return 1
    fi
    sleep 3
  done
}

echo "🚀 Запуск automation_engine e2e на реальном железе"
prepare_real_hardware_node
echo "Node: gh=$TEST_NODE_GH_UID zone=$TEST_NODE_ZONE_UID node=$TEST_NODE_UID hw=$TEST_NODE_HW_ID"

for scenario in "${SCENARIOS[@]}"; do
  echo "\n=== $scenario ==="
  started_at="$(date +%s)"

  if ! "$PYTHON_BIN" -m runner.e2e_runner "$scenario"; then
    echo "❌ Сценарий упал: $scenario"
    scan_logs_since_epoch "$started_at" || true
    exit 1
  fi

  if scan_logs_since_epoch "$started_at"; then
    echo "✅ Сценарий прошел, критических ошибок в логах не обнаружено"
  else
    echo "❌ Сценарий прошел, но в логах найдены ошибки"
    exit 1
  fi

done

echo "\n🎉 Все automation_engine сценарии для real hardware завершены успешно"
