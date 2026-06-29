#!/usr/bin/env bash
# Стресс-тест зоны на реальной test_node: fault injection + мониторинг
# Использование:
#   ZONE_ID=6 ./tools/testing/stress_test_zone.sh
#   FAULT_DURATION_S=20 LOG_DIR=/tmp/my_stress ./tools/testing/stress_test_zone.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/backend/docker-compose.dev.yml"

ZONE_ID="${ZONE_ID:-6}"
LARAVEL_URL="${LARAVEL_URL:-http://localhost:8080}"
AE_URL="${AE_URL:-http://localhost:9405}"
LOG_DIR="${LOG_DIR:-/tmp/hydro_stress_$(date +%Y%m%d_%H%M%S)}"
FAULT_DURATION_S="${FAULT_DURATION_S:-25}"
STOP_NODE_SIM="${STOP_NODE_SIM:-1}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

mkdir -p "$LOG_DIR"

log() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
pass() { echo -e "${GREEN}PASS${NC} $*"; }
fail() { echo -e "${RED}FAIL${NC} $*"; }
warn() { echo -e "${YELLOW}WARN${NC} $*"; }

dc() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

ensure_token() {
  if [[ -n "${TOKEN:-}" ]]; then
    return 0
  fi
  log "Создаём Sanctum token (agronomist@example.com)..."
  TOKEN="$(dc exec -T laravel php artisan tinker --execute='$u=\App\Models\User::where("email","agronomist@example.com")->first(); echo $u?->createToken("stress-test")->plainTextToken;' | tr -d '\r')"
  if [[ -z "$TOKEN" ]]; then
    fail "Не удалось получить API token"
    exit 1
  fi
}

api_get() {
  local path="$1"
  curl -s --max-time 8 -H "Authorization: Bearer $TOKEN" -H 'Accept: application/json' \
    "${LARAVEL_URL}${path}"
}

api_post() {
  local path="$1"
  local payload="${2:-{}}"
  curl -s --max-time 12 -X POST -H "Authorization: Bearer $TOKEN" -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    -d "$payload" "${LARAVEL_URL}${path}"
}

curl_json() {
  local url="$1"
  curl -s --max-time 8 "$url" 2>/dev/null || echo 'null'
}

zone_summary() {
  api_get "/api/zones/${ZONE_ID}/state" | jq -c '{
    workflow_phase,
    current_stage,
    task_status: .observability.runtime.task_status,
    task_id: .observability.runtime.task_id,
    overall_health: .observability.overall_health,
    failed: .state_details.failed,
    error: .state_details.error_code,
    hang_hints: [.observability.hang_hints[]?.code]
  }' 2>/dev/null || echo '{}'
}

snapshot() {
  local label="$1"
  local file="$LOG_DIR/${label}.json"
  log "Snapshot: $label"
  jq -n \
    --arg ts "$(date -Iseconds)" \
    --arg label "$label" \
    --argjson zone_state "$(api_get "/api/zones/${ZONE_ID}/state" 2>/dev/null | jq -c . 2>/dev/null || echo 'null')" \
    --argjson ae_state "$(curl_json "${AE_URL}/zones/${ZONE_ID}/state" | jq -c . 2>/dev/null || echo 'null')" \
    --arg hl_health "$(curl_json http://localhost:9300/health)" \
    --arg ae_health "$(curl_json ${AE_URL}/health/ready)" \
    --arg mqtt_sample "$(timeout 3 mosquitto_sub -h localhost -p 1883 -t "hydro/gh-temp/zn-temp/nd-test-irrig-1/status" -C 1 -W 3 2>/dev/null || echo 'no_mqtt')" \
    '{ts: $ts, label: $label, zone_state: $zone_state, ae_state: $ae_state, hl_health: ($hl_health|fromjson?), ae_health: ($ae_health|fromjson?), mqtt_irrig_status: $mqtt_sample}' \
    > "$file" 2>/dev/null || true
  zone_summary | tee -a "$LOG_DIR/timeline.log"
}

db_query() {
  psql "postgresql://hydro:hydro@localhost:5432/hydro_dev" -t -A -c "$1" 2>/dev/null
}

wait_seconds() {
  local secs="$1"
  local msg="${2:-ожидание}"
  log "$msg (${secs}s)..."
  sleep "$secs"
}

inject_fault() {
  local service="$1"
  local action="${2:-stop}"
  log "Fault inject: $action $service"
  dc "$action" "$service" 2>/dev/null || warn "Не удалось $action $service"
}

check_service_up() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
  if [[ "$code" == "200" || "$code" == "204" ]]; then
    pass "$name доступен (HTTP $code)"
    return 0
  fi
  fail "$name недоступен (HTTP $code)"
  return 1
}

trigger_irrigation() {
  log "POST /api/zones/${ZONE_ID}/start-irrigation (force)"
  api_post "/api/zones/${ZONE_ID}/start-irrigation" '{"mode":"force"}' \
    | tee -a "$LOG_DIR/irrigation_triggers.jsonl" | jq -c '{ts: now|todate, status, code, message}' 2>/dev/null || true
}

trigger_state_probe() {
  log "POST state probe на nd-test-irrig-1"
  local irrig_id
  irrig_id="$(db_query "SELECT id FROM nodes WHERE uid='nd-test-irrig-1' AND zone_id=${ZONE_ID} LIMIT 1;")"
  if [[ -n "$irrig_id" ]]; then
    api_post "/api/nodes/${irrig_id}/commands" '{"cmd":"state","channel":"storage_state","params":{}}' \
      | jq -c '{status, command_id: .data.command_id}' 2>/dev/null || true
  fi
}

analyze_weak_points() {
  log "=== Анализ слабых мест ==="
  local report="$LOG_DIR/WEAK_POINTS.md"

  {
    echo "# Stress test — zone ${ZONE_ID} (real test_node)"
    echo ""
    echo "Дата: $(date -Iseconds)"
    echo "Логи: ${LOG_DIR}"
    echo "node-sim-manager: $(docker compose -f "$COMPOSE_FILE" ps node-sim-manager --format '{{.State}}' 2>/dev/null || echo unknown)"
    echo ""

    echo "## Timeline"
    echo '```'
    cat "$LOG_DIR/timeline.log" 2>/dev/null || true
    echo '```'
    echo ""

    echo "### ae_tasks"
    psql "postgresql://hydro:hydro@localhost:5432/hydro_dev" -c \
      "SELECT id, status, task_type, error_code, left(error_message,90) FROM ae_tasks WHERE zone_id=${ZONE_ID} ORDER BY id DESC LIMIT 6;"
    echo ""
    echo "### commands (последние)"
    psql "postgresql://hydro:hydro@localhost:5432/hydro_dev" -c \
      "SELECT c.id, c.cmd, c.status, c.channel, n.uid FROM commands c JOIN nodes n ON n.id=c.node_id WHERE c.zone_id=${ZONE_ID} ORDER BY c.id DESC LIMIT 12;"
    echo ""
    echo "### ACTIVE alerts"
    psql "postgresql://hydro:hydro@localhost:5432/hydro_dev" -c \
      "SELECT code, status, severity, zone_id, created_at FROM alerts WHERE status='ACTIVE' ORDER BY created_at DESC LIMIT 15;"
    echo ""
    echo "### intents"
    psql "postgresql://hydro:hydro@localhost:5432/hydro_dev" -c \
      "SELECT id, intent_type, status, error_code, created_at FROM zone_automation_intents WHERE zone_id=${ZONE_ID} ORDER BY id DESC LIMIT 6;"
    echo ""

    local phase active_task sent_cmds timeout_cmds stuck_sent
    phase="$(api_get "/api/zones/${ZONE_ID}/state" | jq -r '.workflow_phase // "null"' 2>/dev/null)"
    active_task="$(db_query "SELECT count(*) FROM ae_tasks WHERE zone_id=${ZONE_ID} AND status IN ('pending','claimed','running','waiting_command');")"
    sent_cmds="$(db_query "SELECT count(*) FROM commands WHERE zone_id=${ZONE_ID} AND status='SENT' AND created_at > NOW()-INTERVAL '30 minutes';")"
    timeout_cmds="$(db_query "SELECT count(*) FROM commands WHERE zone_id=${ZONE_ID} AND status='TIMEOUT' AND created_at > NOW()-INTERVAL '30 minutes';")"
    stuck_sent="$(db_query "SELECT count(*) FROM commands WHERE zone_id=${ZONE_ID} AND status='SENT' AND created_at < NOW()-INTERVAL '5 minutes';")"

    echo "## Наблюдения"
    echo ""
    if [[ "${stuck_sent:-0}" -gt 0 ]]; then
      echo "- **Зависшие SENT-команды**: ${stuck_sent} команд старше 5 мин в SENT — возможна потеря command_response после сбоя MQTT/HL."
    fi
    if [[ "${timeout_cmds:-0}" -gt 0 ]]; then
      echo "- **TIMEOUT после fault injection**: ${timeout_cmds} команд — ожидаемо при MQTT down, проверить recovery."
    fi
    if [[ "${active_task:-0}" -eq 0 ]] && [[ "$phase" != "ready" && "$phase" != "idle" && "$phase" != "null" ]]; then
      echo "- **Zombie workflow_phase**: phase=${phase}, активных ae_task нет — риск зависания UI."
    fi
    if db_query "SELECT 1 FROM alerts WHERE code='infra_mqtt_down' AND status='ACTIVE' LIMIT 1;" | grep -q 1; then
      echo "- **infra_mqtt_down не auto-resolve** после восстановления брокера."
    fi
    if db_query "SELECT 1 FROM alerts WHERE code IN ('service_down','history_logger_no_progress_with_incoming_traffic') AND status='ACTIVE' LIMIT 1;" | grep -q 1; then
      echo "- **HL/service_down алерты** остались после restart history-logger."
    fi
    if db_query "SELECT 1 FROM ae_tasks WHERE zone_id=${ZONE_ID} AND status='failed' AND created_at > NOW()-INTERVAL '1 hour' LIMIT 1;" | grep -q 1; then
      echo "- **Failed ae_tasks за час стресс-теста** — см. error_code в таблице выше."
    fi
    if db_query "SELECT 1 FROM ae_tasks WHERE zone_id=${ZONE_ID} AND status IN ('running','waiting_command') LIMIT 1;" | grep -q 1; then
      echo "- **Положительно**: активная ae_task сохранилась/восстановилась после части сбоев."
    fi
    echo ""
    echo "## Snapshots"
    ls -1 "$LOG_DIR"/*.json 2>/dev/null | while read -r f; do echo "- $(basename "$f")"; done
  } | tee "$report"

  log "Отчёт: $report"
}

main() {
  log "=== Hydro stress test — zone ${ZONE_ID} (real test_node) ==="
  log "Логи: ${LOG_DIR}"

  if [[ "$STOP_NODE_SIM" == "1" ]]; then
    log "Останавливаем node-sim-manager (только реальная нода)"
    dc stop node-sim-manager 2>/dev/null || true
  fi

  ensure_token
  : > "$LOG_DIR/timeline.log"

  snapshot "00_baseline"
  check_service_up "Laravel" "${LARAVEL_URL}/api/system/health" || true
  check_service_up "AE3" "${AE_URL}/health/ready" || true
  check_service_up "History-Logger" "http://localhost:9300/health" || true
  trigger_state_probe || true

  log "━━━ Фаза 1: MQTT down ${FAULT_DURATION_S}s ━━━"
  inject_fault mqtt stop
  snapshot "01_mqtt_down"
  trigger_irrigation || true
  wait_seconds "$FAULT_DURATION_S" "MQTT down"
  inject_fault mqtt start
  wait_seconds 15 "MQTT recovery"
  snapshot "02_mqtt_recovered"
  trigger_state_probe || true

  log "━━━ Фаза 2: history-logger down ${FAULT_DURATION_S}s ━━━"
  inject_fault history-logger stop
  snapshot "03_hl_down"
  trigger_irrigation || true
  wait_seconds "$FAULT_DURATION_S" "HL down"
  inject_fault history-logger start
  wait_seconds 20 "HL recovery"
  snapshot "04_hl_recovered"
  trigger_state_probe || true

  log "━━━ Фаза 3: automation-engine restart (во время cycle_start) ━━━"
  inject_fault automation-engine restart
  wait_seconds 25 "AE restart"
  snapshot "05_ae_restarted"
  trigger_state_probe || true
  wait_seconds 10 "после AE restart"

  log "━━━ Фаза 4: laravel pause 15s ━━━"
  dc pause laravel 2>/dev/null || warn "pause laravel"
  wait_seconds 15 "Laravel paused"
  dc unpause laravel 2>/dev/null || inject_fault laravel start
  wait_seconds 8 "Laravel recovery"
  snapshot "06_laravel_recovered"

  log "━━━ Фаза 5: scheduler burst + polling load ━━━"
  for _ in $(seq 1 5); do
    dc exec -T laravel php artisan automation:dispatch-schedules 2>/dev/null &
  done
  for _ in $(seq 1 25); do
    api_get "/api/zones/${ZONE_ID}/state" > /dev/null &
  done
  wait
  snapshot "07_load_burst"

  log "━━━ Фаза 6: recovery check (60s) ━━━"
  wait_seconds 30 "наблюдение recovery"
  trigger_state_probe || true
  wait_seconds 30 "финальное наблюдение"
  snapshot "08_final"

  analyze_weak_points
  log "=== Stress test завершён ==="
  log "Артефакты: ${LOG_DIR}"
}

main "$@"
