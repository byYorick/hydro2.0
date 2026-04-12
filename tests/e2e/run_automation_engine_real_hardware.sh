#!/usr/bin/env bash
# Run E2E scenarios against a real test node (no node-sim control)

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
: "${TEST_NODE_UID:=auto}"
: "${TEST_WORKFLOW_NODE_UID:=auto}"
: "${TEST_PH_NODE_UID:=auto}"
: "${TEST_EC_NODE_UID:=auto}"
: "${TEST_SOIL_NODE_UID:=auto}"
: "${TEST_NODE_HW_ID:=auto}"
: "${REAL_HW_USE_NODE_SIM_SESSION:=0}"
: "${REAL_HW_REBOOT_CMD:=restart}"
: "${MQTT_LIVE_SCAN_SEC:=25}"
: "${MQTT_TEMP_WAIT_SEC:=180}"
: "${NODE_RECREATE_WAIT_SEC:=240}"
: "${E2E_NODE_UID_REGEX:=^nd-test-}"
: "${BIND_DISCOVERY_SCAN_SEC:=20}"
: "${STRICT_SERVICE_LOG_SCAN:=0}"
: "${SERVICE_LOG_INCLUDE_REGEX:= - (ERROR|CRITICAL) - |testing\\.ERROR:|Traceback|Exception}"
: "${SERVICE_LOG_EXCLUDE_REGEX:=connect_tcp.started| 0 failed|GET /api/health |SQLSTATE\\[40001\\].*nodes_register_hwid_zone_unique|Scheduler task execution finished|testing\\.ERROR: SQLSTATE\\[40001\\]: Serialization failure|url\":\"http://laravel/api/nodes/register\".*SQLSTATE\\[40001\\]}"

export E2E_REAL_HARDWARE=1
export REAL_HW_USE_NODE_SIM_SESSION=0
export TEST_NODE_GH_UID TEST_NODE_ZONE_UID TEST_NODE_UID TEST_WORKFLOW_NODE_UID TEST_PH_NODE_UID TEST_EC_NODE_UID TEST_SOIL_NODE_UID TEST_NODE_HW_ID
LARAVEL_URL="${LARAVEL_URL:-http://localhost:8081}"
AUTOMATION_ENGINE_URL="${AUTOMATION_ENGINE_URL:-http://localhost:9505}"
HISTORY_LOGGER_URL="${HISTORY_LOGGER_URL:-http://localhost:${HISTORY_LOGGER_PORT:-9302}}"
HISTORY_LOGGER_TOKEN="${HISTORY_LOGGER_API_TOKEN:-${PY_INGEST_TOKEN:-dev-token-12345}}"
SCENARIO_SET="${SCENARIO_SET:-full}"
LIST_ONLY=0
SCENARIOS=()

is_auto_uid() {
  local uid="${1:-}"
  [ -z "$uid" ] || [ "$uid" = "auto" ]
}

uid_matches_discovery_filter() {
  local uid="${1:-}"
  local regex="${E2E_NODE_UID_REGEX:-}"
  if [ -z "$uid" ]; then
    return 1
  fi
  if [ -z "$regex" ]; then
    return 0
  fi
  printf '%s\n' "$uid" | rg -qx "$regex"
}

uid_in_list() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

first_uid_matching_pattern() {
  local regex="$1"
  shift
  local uid
  for uid in "$@"; do
    if printf '%s\n' "$uid" | rg -q "$regex"; then
      printf '%s\n' "$uid"
      return 0
    fi
  done
  return 1
}

sync_automation_engine_env() {
  local url host_port parsed_host parsed_port

  url="${AUTOMATION_ENGINE_URL#http://}"
  url="${url#https://}"
  host_port="${url%%/*}"
  parsed_host="${host_port%%:*}"
  parsed_port="${host_port##*:}"

  if [ -z "${AUTOMATION_ENGINE_HOST:-}" ]; then
    AUTOMATION_ENGINE_HOST="${parsed_host:-localhost}"
  fi

  if [ -z "${AUTOMATION_ENGINE_API_PORT:-}" ]; then
    if [ "$parsed_port" = "$host_port" ]; then
      AUTOMATION_ENGINE_API_PORT=9505
    else
      AUTOMATION_ENGINE_API_PORT="$parsed_port"
    fi
  fi
}

sync_automation_engine_env
export AUTOMATION_ENGINE_HOST AUTOMATION_ENGINE_API_PORT

SERVICES=(automation-engine history-logger laravel mqtt-bridge digital-twin)
AUTOMATION_SCENARIOS=(
  "scenarios/automation_engine/E61_fail_closed_corrections.yaml"
  "scenarios/automation_engine/E64_effective_targets_only.yaml"
  "scenarios/automation_engine/E65_phase_transition_api.yaml"
  "scenarios/automation_engine/E66_full_prod_path_zone_recipe_bind_and_run.yaml"
  "scenarios/automation_engine/E67_nutrition_strict_contract.yaml"
  "scenarios/automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml"
  "scenarios/automation_engine/E74_node_zone_mismatch_guard.yaml"
  "scenarios/automation_engine/E80_ph_pid_ki_convergence.yaml"
  "scenarios/automation_engine/E81_ec_correction_partial_calibration.yaml"
)
WORKFLOW_SCENARIOS=(
  "scenarios/workflow/E83_clean_water_fill.yaml"
  "scenarios/workflow/E84_solution_preparation.yaml"
  "scenarios/workflow/E85_recirculation_targets.yaml"
  "scenarios/workflow/E86_ec_ph_correction.yaml"
  "scenarios/workflow/E87_ec_ph_correction_during_fill.yaml"
  "scenarios/workflow/E88_config_report_soft_deactivate_channels.yaml"
  "scenarios/workflow/E89_correction_state_machine_and_duration_aware.yaml"
  "scenarios/workflow/E94_startup_to_ready_smoke.yaml"
)
AE3LITE_SCENARIOS=(
  "scenarios/ae3lite/E100_ae3_two_tank_realhw_smoke.yaml"
  "scenarios/ae3lite/E101_ae3_two_tank_realhw_ready_during_fill.yaml"
  "scenarios/ae3lite/E101_ae3_two_tank_realhw_setup_ready.yaml"
  "scenarios/ae3lite/E102_ae3_recirculation_retry_limit_alert_reset_realhw.yaml"
  "scenarios/ae3lite/E102_ae3_two_tank_realhw_ready_during_recirculation.yaml"
  "scenarios/ae3lite/E103_ae3_recirculation_retry_limit_alert_resolve_ready_realhw.yaml"
  "scenarios/ae3lite/E104_ae3_two_tank_realhw_hot_reload_correction_config.yaml"
  "scenarios/ae3lite/E105_ae3_two_tank_fail_closed_missing_command_plan_realhw.yaml"
  "scenarios/ae3lite/E106_ae3_two_tank_realhw_piggyback_ec_ph_cycle.yaml"
  "scenarios/ae3lite/E112_ae3_per_phase_ec_target_realhw.yaml"
)
SMART_IRRIGATION_SCENARIOS=(
  "scenarios/ae3lite/E107_ae3_irrigation_runtime_test_node.yaml"
  "scenarios/ae3lite/E108_ae3_irrigation_inline_correction_contract.yaml"
  "scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml"
)
INLINE_IRRIGATION_SCENARIOS=(
  "scenarios/ae3lite/E108_ae3_irrigation_inline_correction_contract.yaml"
  "scenarios/ae3lite/E109_ae3_irrigation_inline_correction_test_node.yaml"
)
CALIBRATION_SCENARIOS=(
  "scenarios/calibration/E110_sensor_calibration_realhw_create_cancel.yaml"
  "scenarios/calibration/E111_sensor_calibration_realhw_unsupported_command.yaml"
)

usage() {
  cat <<'EOF'
Usage:
  tests/e2e/run_automation_engine_real_hardware.sh [--set automation|workflow|ae3lite|smart_irrigation|inline_irrigation|calibration|full] [--list]

Env:
  SCENARIO_SET=automation|workflow|ae3lite|smart_irrigation|inline_irrigation|calibration|full   # default: full
  TEST_NODE_UID/TEST_WORKFLOW_NODE_UID/TEST_PH_NODE_UID/TEST_EC_NODE_UID/TEST_SOIL_NODE_UID=auto|<uid>
  REAL_HW_REBOOT_CMD=restart|reboot       # default: restart
  E2E_NODE_UID_REGEX=<regex>              # default: ^nd-test-
  E2E_SCENARIO_INCLUDE_REGEX=<regex>      # optional include filter
  E2E_SCENARIO_EXCLUDE_REGEX=<regex>      # optional exclude filter
EOF
}

collect_full_scenarios() {
  printf '%s\n' \
    "${AUTOMATION_SCENARIOS[@]}" \
    "${WORKFLOW_SCENARIOS[@]}" \
    "${AE3LITE_SCENARIOS[@]}" \
    "${SMART_IRRIGATION_SCENARIOS[@]}" \
    "${CALIBRATION_SCENARIOS[@]}" \
    | LC_ALL=C sort -u
}

_scenario_line_matches_re() {
  local line="$1"
  local re="$2"
  if command -v rg >/dev/null 2>&1; then
    printf '%s\n' "$line" | rg -q "$re"
  else
    printf '%s\n' "$line" | grep -Eq "$re"
  fi
}

apply_scenario_filters() {
  local include_re="${E2E_SCENARIO_INCLUDE_REGEX:-}"
  local exclude_re="${E2E_SCENARIO_EXCLUDE_REGEX:-}"
  local filtered=()
  local item

  for item in "${SCENARIOS[@]}"; do
    if [ -n "$include_re" ] && ! _scenario_line_matches_re "$item" "$include_re"; then
      continue
    fi
    if [ -n "$exclude_re" ] && _scenario_line_matches_re "$item" "$exclude_re"; then
      continue
    fi
    filtered+=("$item")
  done
  SCENARIOS=("${filtered[@]}")
}

resolve_scenarios() {
  case "$SCENARIO_SET" in
    automation)
      SCENARIOS=("${AUTOMATION_SCENARIOS[@]}")
      ;;
    workflow)
      SCENARIOS=("${WORKFLOW_SCENARIOS[@]}")
      ;;
    ae3lite)
      SCENARIOS=("${AE3LITE_SCENARIOS[@]}")
      ;;
    smart_irrigation)
      SCENARIOS=("${SMART_IRRIGATION_SCENARIOS[@]}")
      ;;
    inline_irrigation)
      SCENARIOS=("${INLINE_IRRIGATION_SCENARIOS[@]}")
      ;;
    calibration)
      SCENARIOS=("${CALIBRATION_SCENARIOS[@]}")
      ;;
    full)
      mapfile -t SCENARIOS < <(collect_full_scenarios)
      ;;
    *)
      echo "❌ Неизвестный SCENARIO_SET: $SCENARIO_SET"
      usage
      exit 1
      ;;
  esac

  apply_scenario_filters

  if [ "${#SCENARIOS[@]}" -eq 0 ]; then
    echo "❌ Список сценариев пуст (set=$SCENARIO_SET)"
    exit 1
  fi

  local missing=0
  local scenario
  for scenario in "${SCENARIOS[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$scenario" ]; then
      echo "❌ Сценарий не найден: $scenario"
      missing=1
    fi
  done
  if [ "$missing" -ne 0 ]; then
    exit 1
  fi
}

for arg in "$@"; do
  case "$arg" in
    --set=*)
      SCENARIO_SET="${arg#--set=}"
      ;;
    --set)
      echo "❌ Используйте формат --set=<automation|workflow|ae3lite|smart_irrigation|inline_irrigation|calibration|full>"
      exit 1
      ;;
    --list)
      LIST_ONLY=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Неизвестный аргумент: $arg"
      usage
      exit 1
      ;;
  esac
done

resolve_scenarios

if [ "$LIST_ONLY" -eq 1 ]; then
  echo "📋 Scenario set: $SCENARIO_SET"
  printf '%s\n' "${SCENARIOS[@]}"
  exit 0
fi

scan_logs_since_epoch() {
  local start_epoch="$1"
  local since_iso
  since_iso="$(date -u -d "@${start_epoch}" +"%Y-%m-%dT%H:%M:%SZ")"

  local found=0
  for svc in "${SERVICES[@]}"; do
    local raw out
    raw="$("${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" logs --since "$since_iso" "$svc" 2>/dev/null || true)"
    out="$(printf '%s\n' "$raw" | rg -n "$SERVICE_LOG_INCLUDE_REGEX" -S || true)"
    if [ -n "$out" ] && [ -n "${SERVICE_LOG_EXCLUDE_REGEX:-}" ]; then
      out="$(printf '%s\n' "$out" | rg -v "$SERVICE_LOG_EXCLUDE_REGEX" -S || true)"
    fi
    if [ -n "$out" ]; then
      found=1
      echo "\n❌ Найдены ошибки в логах сервиса $svc:"
      echo "$out"
    fi
  done

  if [ "$found" -eq 0 ]; then
    return 0
  fi

  if [ "$STRICT_SERVICE_LOG_SCAN" = "1" ]; then
    return 1
  fi

  echo "⚠️ В логах сервисов есть ERROR/CRITICAL, но STRICT_SERVICE_LOG_SCAN=0, продолжаю."
  return 0
}

db_query_line() {
  local sql="$1"
  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T \
    -e PGOPTIONS='-c client_min_messages=warning' \
    postgres \
    psql -qX -U "${POSTGRES_USER:-hydro}" -d "${POSTGRES_DB:-hydro_e2e}" -AtF '|' -c "$sql"
}

scenario_db_metrics_since_epoch() {
  local start_epoch="$1"
  local zone_id
  local zone_ids=()

  while IFS= read -r zone_id; do
    [ -z "$zone_id" ] && continue
    zone_ids+=("$zone_id")
  done < <(db_query_line "
    SELECT DISTINCT zone_id::text
    FROM (
      SELECT zone_id
      FROM zone_events
      WHERE created_at >= to_timestamp(${start_epoch})
        AND zone_id IS NOT NULL
      UNION
      SELECT zone_id
      FROM commands
      WHERE created_at >= to_timestamp(${start_epoch})
        AND zone_id IS NOT NULL
    ) AS touched
    ORDER BY zone_id;
  " || true)

  if [ "${#zone_ids[@]}" -eq 0 ]; then
    echo "⚠️ DB metrics: не найдено zone activity в окне сценария (возможен cleanup с удалением временной зоны)"
    return 0
  fi

  for zid in "${zone_ids[@]}"; do
    echo "📊 DB metrics (scenario window, zone_id=${zid}):"
    db_query_line "
      SELECT 'zone_events_error_like_window=' || COUNT(*)
      FROM zone_events
      WHERE zone_id = ${zid}
        AND created_at >= to_timestamp(${start_epoch})
        AND (type ILIKE '%ERROR%' OR payload_json::text ILIKE '%error%');

      SELECT 'fixed_timeout_reason_window=' || COUNT(*)
      FROM zone_events
      WHERE zone_id = ${zid}
        AND type = 'CORRECTION_COMMAND_ATTEMPT_FAILED'
        AND COALESCE(payload_json->>'reason','') = 'ack_done_timeout_5s'
        AND created_at >= to_timestamp(${start_epoch});

      SELECT 'schedule_finished_failed_window=' || COUNT(*)
      FROM zone_events
      WHERE zone_id = ${zid}
        AND type = 'SCHEDULE_TASK_EXECUTION_FINISHED'
        AND COALESCE(payload_json->'result'->>'success','false') = 'false'
        AND created_at >= to_timestamp(${start_epoch});

      SELECT 'command_failed_window=' || COUNT(*)
      FROM zone_events
      WHERE zone_id = ${zid}
        AND type = 'COMMAND_FAILED'
        AND created_at >= to_timestamp(${start_epoch});

      SELECT 'runtime_event_counts_window=' || COALESCE(
        (
          SELECT string_agg(type || ':' || cnt, ',' ORDER BY type)
          FROM (
            SELECT type, COUNT(*)::int AS cnt
            FROM zone_events
            WHERE zone_id = ${zid}
              AND created_at >= to_timestamp(${start_epoch})
              AND type IN (
                'IRRIGATION_DECISION_SNAPSHOT_LOCKED',
                'IRRIGATION_CORRECTION_STARTED',
                'CORRECTION_DECISION_MADE',
                'EC_DOSING',
                'PH_CORRECTED',
                'IRR_STATE_SNAPSHOT'
              )
            GROUP BY type
          ) AS runtime_counts
        ),
        'none'
      );

      SELECT 'runtime_event_schema_version_missing_window=' || COUNT(*)
      FROM zone_events
      WHERE zone_id = ${zid}
        AND created_at >= to_timestamp(${start_epoch})
        AND type IN (
          'IRRIGATION_DECISION_SNAPSHOT_LOCKED',
          'IRRIGATION_CORRECTION_STARTED',
          'CORRECTION_DECISION_MADE',
          'EC_DOSING',
          'PH_CORRECTED'
        )
        AND NULLIF(COALESCE(COALESCE(details, payload_json)->>'event_schema_version', ''), '') IS NULL;

      SELECT 'runtime_event_schema_versions_window=' || COALESCE(
        (
          SELECT string_agg(version, ',' ORDER BY version)
          FROM (
            SELECT DISTINCT NULLIF(COALESCE(COALESCE(details, payload_json)->>'event_schema_version', ''), '') AS version
            FROM zone_events
            WHERE zone_id = ${zid}
              AND created_at >= to_timestamp(${start_epoch})
              AND type IN (
                'IRRIGATION_DECISION_SNAPSHOT_LOCKED',
                'IRRIGATION_CORRECTION_STARTED',
                'CORRECTION_DECISION_MADE',
                'EC_DOSING',
                'PH_CORRECTED'
              )
          ) AS versions
          WHERE version IS NOT NULL
        ),
        'none'
      );

      SELECT 'irrigation_snapshot_causality_gaps_window=' || COUNT(*)
      FROM zone_events
      WHERE zone_id = ${zid}
        AND created_at >= to_timestamp(${start_epoch})
        AND type IN (
          'IRRIGATION_CORRECTION_STARTED',
          'CORRECTION_DECISION_MADE',
          'EC_DOSING',
          'PH_CORRECTED'
        )
        AND COALESCE(COALESCE(details, payload_json)->>'workflow_phase', '') IN ('irrigating', 'irrig_recirc')
        AND NULLIF(COALESCE(COALESCE(details, payload_json)->>'snapshot_event_id', ''), '') IS NULL;

      SELECT 'alerts_new_window=' || COUNT(*)
      FROM alerts
      WHERE zone_id = ${zid}
        AND created_at >= to_timestamp(${start_epoch});

      SELECT 'alerts_new_codes_window=' || COALESCE(
        (
          SELECT string_agg(code || ':' || cnt, ',' ORDER BY code)
          FROM (
            SELECT COALESCE(code, 'unknown') AS code, COUNT(*)::int AS cnt
            FROM alerts
            WHERE zone_id = ${zid}
              AND created_at >= to_timestamp(${start_epoch})
            GROUP BY COALESCE(code, 'unknown')
          ) AS alert_codes
        ),
        'none'
      );
    " || true
  done

  db_query_line "
    SELECT 'alerts_open_total=' || COUNT(*)
    FROM alerts
    WHERE (UPPER(COALESCE(status, '')) = 'ACTIVE'
       OR LOWER(COALESCE(status, '')) = 'open')
      AND LOWER(COALESCE(severity, '')) <> 'info';

    SELECT 'alerts_info_total=' || COUNT(*)
    FROM alerts
    WHERE (UPPER(COALESCE(status, '')) = 'ACTIVE'
       OR LOWER(COALESCE(status, '')) = 'open')
      AND LOWER(COALESCE(severity, '')) = 'info';

    SELECT 'alerts_open_codes_total=' || COALESCE(
      (
        SELECT string_agg(code || ':' || cnt, ',' ORDER BY code)
        FROM (
          SELECT COALESCE(code, 'unknown') AS code, COUNT(*)::int AS cnt
          FROM alerts
          WHERE (UPPER(COALESCE(status, '')) = 'ACTIVE'
             OR LOWER(COALESCE(status, '')) = 'open')
            AND LOWER(COALESCE(severity, '')) <> 'info'
          GROUP BY COALESCE(code, 'unknown')
        ) AS open_codes
      ),
      'none'
    );
  " || true
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
paths = ["/api/system/health"]
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

wait_automation_engine_ready() {
  local timeout="${1:-120}"
  local started_at
  started_at="$(date +%s)"
  while true; do
    if "$PYTHON_BIN" - <<'PY' "$AUTOMATION_ENGINE_URL" >/dev/null 2>&1
import sys
import httpx

base = sys.argv[1].rstrip("/")
with httpx.Client(timeout=3.0) as c:
    resp = c.get(base + "/health/ready")
if resp.status_code == 200:
    raise SystemExit(0)
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

wait_history_logger_health() {
  local timeout="${1:-120}"
  local started_at
  started_at="$(date +%s)"
  while true; do
    if "$PYTHON_BIN" - <<'PY' "$HISTORY_LOGGER_URL" >/dev/null 2>&1
import sys
import httpx

base = sys.argv[1].rstrip("/")
with httpx.Client(timeout=3.0) as c:
    resp = c.get(base + "/health")
if resp.status_code == 200:
    raise SystemExit(0)
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

verify_rollout_observability_contract() {
  "$PYTHON_BIN" - <<'PY' "$AUTOMATION_ENGINE_URL" "$HISTORY_LOGGER_URL" "$LARAVEL_URL"
from __future__ import annotations

import re
import sys

import httpx


def has_metric_contract(text: str, metric_name: str) -> bool:
    escaped = re.escape(metric_name)
    return re.search(rf"(^# (HELP|TYPE) {escaped}\b|^{escaped}(?:\{{|\s))", text, flags=re.MULTILINE) is not None


targets = [
    {
        "name": "automation-engine",
        "base": sys.argv[1].rstrip("/"),
        "path": "/metrics/",
        "metrics": [
            "ae3_active_tasks",
            "ae3_tick_errors_total",
            "ae3_command_terminal_total",
            "ae3_stage_deadline_exceeded_total",
            "ae3_correction_exhausted_total",
            "ae3_startup_recovery_task_total",
        ],
    },
    {
        "name": "history-logger",
        "base": sys.argv[2].rstrip("/"),
        "path": "/metrics",
        "metrics": [
            "telemetry_queue_size",
            "telemetry_processed_total",
            "telemetry_dropped_total",
            "database_errors_total",
            "node_event_unknown_total",
        ],
    },
    {
        "name": "laravel-scheduler",
        "base": sys.argv[3].rstrip("/"),
        "path": "/api/system/scheduler/metrics",
        "metrics": [
            "laravel_scheduler_dispatches_total",
            "laravel_scheduler_cycle_duration_seconds",
            "laravel_scheduler_active_tasks_count",
        ],
    },
]

with httpx.Client(timeout=10.0) as client:
    for target in targets:
        response = client.get(target["base"] + target["path"])
        response.raise_for_status()
        body = response.text
        missing = [metric for metric in target["metrics"] if not has_metric_contract(body, metric)]
        if missing:
            joined = ", ".join(missing)
            raise SystemExit(f"{target['name']}: missing metrics contract: {joined}")

print("ok")
PY
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

mqtt_publish_json() {
  local topic="$1"
  local payload_json="$2"
  if [ -z "$topic" ] || [ -z "$payload_json" ]; then
    return 1
  fi
  if ! printf '%s' "$payload_json" | "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T mosquitto \
    mosquitto_pub -h localhost -p 1883 -q 1 -t "$topic" -s >/dev/null; then
    return 1
  fi
  return 0
}

collect_live_heartbeat_topics() {
  local out_file="$1"
  local scan_seconds="${2:-20}"
  local raw_file
  local scan_rc
  raw_file="$(mktemp /tmp/e2e_live_topics_raw.XXXXXX)"

  set +e
  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T mosquitto sh -lc \
    "timeout ${scan_seconds}s mosquitto_sub -h localhost -p 1883 -t 'hydro/+/+/+/heartbeat' -v" >"$raw_file" 2>/dev/null
  scan_rc=$?
  set -e

  # docker compose exec may outlive TERM; accept timeout terminal rc variants too.
  if [ "$scan_rc" -ne 0 ] && [ "$scan_rc" -ne 124 ] && [ "$scan_rc" -ne 137 ] && [ "$scan_rc" -ne 143 ]; then
    rm -f "$raw_file"
    echo "❌ Ошибка MQTT scan heartbeat (rc=$scan_rc)"
    return 1
  fi

  awk -v node_re="${E2E_NODE_UID_REGEX}" '
    {
      topic = $1
      n = split(topic, seg, "/")
      if (n == 5 && seg[1] == "hydro" && seg[5] == "heartbeat" && seg[2] != "" && seg[3] != "" && seg[4] != "" && seg[4] ~ node_re) {
        print seg[2] "|" seg[3] "|" seg[4]
      }
    }
  ' "$raw_file" | sort -u > "$out_file"

  rm -f "$raw_file"
  return 0
}

build_temp_reset_config_payload() {
  "$PYTHON_BIN" - <<'PY'
import json
print(json.dumps({"gh_uid": "gh-temp", "zone_uid": "zn-temp"}, separators=(",", ":")))
PY
}

build_mqtt_command_payload() {
  local cmd="$1"
  local cmd_id="${2:-}"
  "$PYTHON_BIN" - <<'PY' "$cmd" "$cmd_id"
import json
import sys
import time
import uuid

cmd = sys.argv[1]
cmd_id = sys.argv[2] or str(uuid.uuid4())
payload = {
    "cmd_id": cmd_id,
    "cmd": cmd,
    "params": {},
    "ts": int(time.time()),
    "sig": "0" * 64,
}
print(json.dumps(payload, separators=(",", ":")))
PY
}

extract_cmd_id_from_payload_json() {
  local payload_json="$1"
  "$PYTHON_BIN" - <<'PY' "$payload_json"
import json
import sys

payload = json.loads(sys.argv[1])
print(str(payload.get("cmd_id") or "").strip())
PY
}

publish_direct_command_and_wait_terminal() {
  local topic="$1"
  local payload_json="$2"
  local timeout_sec="${3:-30}"
  local raw_file cmd_id sub_pid publish_ok=0

  cmd_id="$(extract_cmd_id_from_payload_json "$payload_json" || true)"
  if [ -z "$cmd_id" ]; then
    echo "❌ Не удалось извлечь cmd_id из direct MQTT payload"
    return 1
  fi

  raw_file="$(mktemp /tmp/e2e_direct_command_response.XXXXXX)"
  set +e
  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T mosquitto sh -lc \
    "timeout ${timeout_sec}s mosquitto_sub -h localhost -p 1883 -t 'hydro/+/+/+/+/command_response' -v" >"$raw_file" 2>/dev/null &
  sub_pid=$!
  set -e

  sleep 1
  if mqtt_publish_json "$topic" "$payload_json"; then
    publish_ok=1
  fi

  set +e
  wait "$sub_pid"
  set -e

  if [ "$publish_ok" -ne 1 ]; then
    rm -f "$raw_file"
    echo "❌ Не удалось опубликовать direct MQTT command: topic=$topic cmd_id=$cmd_id"
    return 1
  fi

  local response_summary
  response_summary="$("$PYTHON_BIN" - <<'PY' "$raw_file" "$cmd_id"
import json
import sys

raw_file, expected_cmd_id = sys.argv[1:3]
terminal = {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT"}

with open(raw_file, "r", encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line or " " not in line:
            continue
        topic, payload_raw = line.split(" ", 1)
        try:
            payload = json.loads(payload_raw)
        except Exception:
            continue
        if str(payload.get("cmd_id") or "").strip() != expected_cmd_id:
            continue
        status = str(payload.get("status") or "").strip().upper()
        if status not in terminal:
            continue
        print(f"{status}|{topic}|{json.dumps(payload, separators=(',', ':'))}")
        raise SystemExit(0)

raise SystemExit(1)
PY
  )" || true
  rm -f "$raw_file"

  if [ -z "$response_summary" ]; then
    echo "❌ Не получен terminal command_response для direct MQTT command: topic=$topic cmd_id=$cmd_id"
    return 1
  fi

  local terminal_status response_topic response_payload
  IFS='|' read -r terminal_status response_topic response_payload <<<"$response_summary"
  if [ "$terminal_status" != "DONE" ]; then
    echo "❌ Direct MQTT command завершился неуспешно: topic=$topic cmd_id=$cmd_id status=$terminal_status response=$response_payload"
    return 1
  fi

  echo "✅ Direct MQTT command завершился DONE: topic=$response_topic cmd_id=$cmd_id"
  return 0
}

build_config_switch_payload() {
  local target_gh_uid="$1"
  local target_zone_uid="$2"
  "$PYTHON_BIN" - <<'PY' "$target_gh_uid" "$target_zone_uid"
import json
import sys
gh_uid, zone_uid = sys.argv[1:3]
print(json.dumps({"gh_uid": gh_uid, "zone_uid": zone_uid}, separators=(",", ":")))
PY
}

publish_bind_namespace_nudge() {
  local zone_id="$1"
  local target_gh_uid="$2"
  local target_zone_uid="$3"
  shift 3
  local uid
  local payload
  payload="$(build_config_switch_payload "$target_gh_uid" "$target_zone_uid")"

  for uid in "$@"; do
    local row
    row="$(db_query_line "SELECT COALESCE(zone_id::text,''), COALESCE(pending_zone_id::text,''), COALESCE(config->>'gh_uid',''), COALESCE(config->>'zone_uid','') FROM nodes WHERE uid = '${uid}' LIMIT 1;")"
    if [ -z "$row" ]; then
      continue
    fi

    local current_zone_id current_pending_zone_id current_gh_uid current_zone_uid
    IFS='|' read -r current_zone_id current_pending_zone_id current_gh_uid current_zone_uid <<<"$row"
    local should_nudge=0

    # During bind we may observe both states:
    # 1) pending assignment (zone_id empty, pending_zone_id=target)
    # 2) assigned in DB but still reporting temp namespace (zone_id=target, pending_zone_id empty)
    if [ -z "$current_zone_id" ] && [ "$current_pending_zone_id" = "$zone_id" ]; then
      should_nudge=1
    elif [ "$current_zone_id" = "$zone_id" ] && [ -z "$current_pending_zone_id" ]; then
      should_nudge=1
    fi

    if [ "$should_nudge" -ne 1 ]; then
      continue
    fi
    if [ "$current_gh_uid" = "$target_gh_uid" ] && [ "$current_zone_uid" = "$target_zone_uid" ]; then
      continue
    fi
    if [ -z "$current_gh_uid" ] || [ -z "$current_zone_uid" ]; then
      current_gh_uid="$target_gh_uid"
      current_zone_uid="$target_zone_uid"
    fi

    local topic
    topic="hydro/${current_gh_uid}/${current_zone_uid}/${uid}/config"
    echo "↪ bind-nudge: node=$uid topic=$topic -> ${target_gh_uid}/${target_zone_uid}"
    mqtt_publish_json "$topic" "$payload" || true
  done
}

publish_temp_reset_config_to_live_topics() {
  local topics_file="$1"
  local payload
  local sent_count=0
  payload="$(build_temp_reset_config_payload)"

  while IFS='|' read -r src_gh_uid src_zone_uid src_node_uid; do
    local config_topic
    if [ -z "$src_gh_uid" ] || [ -z "$src_zone_uid" ] || [ -z "$src_node_uid" ]; then
      continue
    fi
    config_topic="hydro/${src_gh_uid}/${src_zone_uid}/${src_node_uid}/config"
    echo "↪ reset config: topic=$config_topic -> gh-temp/zn-temp"
    if ! mqtt_publish_json "$config_topic" "$payload"; then
      echo "❌ Не удалось отправить reset config: topic=$config_topic"
      return 1
    fi
    sent_count=$((sent_count + 1))
  done < "$topics_file"

  if [ "$sent_count" -eq 0 ]; then
    echo "❌ Нет живых heartbeat-топиков для reset config"
    return 1
  fi

  echo "✅ Reset config отправлен в $sent_count topic(s)"
  return 0
}

wait_nodes_in_temp_heartbeat_topics() {
  local expected_topics_file="$1"
  local timeout_sec="${2:-180}"
  local started_at
  local temp_topics_file
  local missing_nodes
  local expected_nodes=()
  local current_nodes=()
  local node
  local missing_count
  local -A seen_nodes=()

  mapfile -t expected_nodes < <(cut -d'|' -f3 "$expected_topics_file" | sed '/^$/d' | sort -u)
  if [ "${#expected_nodes[@]}" -eq 0 ]; then
    echo "❌ Пустой список ожидаемых нод для temp namespace"
    return 1
  fi

  started_at="$(date +%s)"
  temp_topics_file="$(mktemp /tmp/e2e_temp_topics.XXXXXX)"

  while true; do
    collect_live_heartbeat_topics "$temp_topics_file" 12 || true
    mapfile -t current_nodes < <(awk -F'|' '$1=="gh-temp" && $2=="zn-temp" && $3!="" {print $3}' "$temp_topics_file" | sort -u)
    seen_nodes=()
    for node in "${current_nodes[@]}"; do
      seen_nodes["$node"]=1
    done

    missing_nodes=""
    missing_count=0
    for node in "${expected_nodes[@]}"; do
      if [ -z "${seen_nodes[$node]:-}" ]; then
        if [ -z "$missing_nodes" ]; then
          missing_nodes="$node"
        else
          missing_nodes="${missing_nodes},$node"
        fi
        missing_count=$((missing_count + 1))
      fi
    done

    if [ "$missing_count" -eq 0 ]; then
      echo "✅ Все ноды появились в temp heartbeat namespace"
      rm -f "$temp_topics_file"
      return 0
    fi

    if [ $(( "$(date +%s)" - started_at )) -ge "$timeout_sec" ]; then
      echo "❌ Не дождались temp heartbeat namespace за ${timeout_sec}s. missing=${missing_nodes}"
      rm -f "$temp_topics_file"
      return 1
    fi
    sleep 3
  done
}

resolve_reboot_uid_from_topics_file() {
  local expected_topics_file="$1"
  local reboot_uid=""
  local expected_uids=()
  mapfile -t expected_uids < <(cut -d'|' -f3 "$expected_topics_file" | sed '/^$/d' | sort -u)

  if ! is_auto_uid "${TEST_WORKFLOW_NODE_UID:-}" && uid_in_list "$TEST_WORKFLOW_NODE_UID" "${expected_uids[@]}"; then
    reboot_uid="$TEST_WORKFLOW_NODE_UID"
  elif ! is_auto_uid "${TEST_NODE_UID:-}" && uid_in_list "$TEST_NODE_UID" "${expected_uids[@]}"; then
    reboot_uid="$TEST_NODE_UID"
  else
    reboot_uid="$(first_uid_matching_pattern '(^|[-_])irrig([-_]|$)' "${expected_uids[@]}" || true)"
    if [ -z "$reboot_uid" ]; then
      reboot_uid="${expected_uids[0]:-}"
    fi
  fi

  if [ -z "$reboot_uid" ]; then
    return 1
  fi

  printf '%s\n' "$reboot_uid"
  return 0
}

publish_reboot_to_temp_topics() {
  local expected_topics_file="$1"
  local payload
  local reboot_uid=""
  payload="$(build_mqtt_command_payload "$REAL_HW_REBOOT_CMD")"

  if ! reboot_uid="$(resolve_reboot_uid_from_topics_file "$expected_topics_file")"; then
    echo "❌ Нет нод для reboot в temp namespace"
    return 1
  fi

  local reboot_topic
  reboot_topic="hydro/gh-temp/zn-temp/${reboot_uid}/system/command"
  echo "↪ reboot (hardware): topic=$reboot_topic cmd=$REAL_HW_REBOOT_CMD"
  if ! publish_direct_command_and_wait_terminal "$reboot_topic" "$payload" 30; then
    echo "❌ Не удалось завершить reboot в temp topic: node=$reboot_uid"
    return 1
  fi

  echo "✅ Reboot отправлен в 1 temp topic (node=$reboot_uid)"
  return 0
}

publish_reboot_to_live_topics() {
  local topics_file="$1"
  local payload reboot_uid namespace_row reboot_gh_uid reboot_zone_uid reboot_topic
  payload="$(build_mqtt_command_payload "$REAL_HW_REBOOT_CMD")"

  if ! reboot_uid="$(resolve_reboot_uid_from_topics_file "$topics_file")"; then
    echo "❌ Нет нод для reboot в исходном live namespace"
    return 1
  fi

  namespace_row="$(awk -F'|' -v uid="$reboot_uid" '$3==uid {print $1 "|" $2; exit}' "$topics_file")"
  if [ -z "$namespace_row" ]; then
    namespace_row="$(awk -F'|' 'NF >= 3 {print $1 "|" $2; exit}' "$topics_file")"
  fi
  if [ -z "$namespace_row" ]; then
    echo "❌ Не удалось определить namespace для reboot: node=$reboot_uid"
    return 1
  fi
  IFS='|' read -r reboot_gh_uid reboot_zone_uid <<<"$namespace_row"
  if [ -z "$reboot_gh_uid" ] || [ -z "$reboot_zone_uid" ]; then
    echo "❌ Невалидный namespace для reboot: row=$namespace_row node=$reboot_uid"
    return 1
  fi

  reboot_topic="hydro/${reboot_gh_uid}/${reboot_zone_uid}/${reboot_uid}/system/command"
  echo "↪ reboot (live): topic=$reboot_topic cmd=$REAL_HW_REBOOT_CMD"
  if ! publish_direct_command_and_wait_terminal "$reboot_topic" "$payload" 30; then
    echo "❌ Не удалось завершить reboot в live topic: node=$reboot_uid"
    return 1
  fi

  echo "✅ Reboot отправлен в 1 live topic (node=$reboot_uid)"
  return 0
}

wait_nodes_recreated_in_db() {
  local expected_topics_file="$1"
  local timeout_sec="${2:-240}"
  local expected_nodes=()
  local missing_nodes
  local started_at
  local uid
  local zone_uid="${TEST_NODE_ZONE_UID:-}"
  local test_zone_id=""

  mapfile -t expected_nodes < <(cut -d'|' -f3 "$expected_topics_file" | sed '/^$/d' | sort -u)
  if [ "${#expected_nodes[@]}" -eq 0 ]; then
    echo "❌ Пустой список ожидаемых нод для проверки регистрации в БД"
    return 1
  fi

  if [ -n "$zone_uid" ]; then
    test_zone_id="$(db_query_line "SELECT id FROM zones WHERE uid = '${zone_uid}' ORDER BY id DESC LIMIT 1;")" || true
  fi

  started_at="$(date +%s)"
  while true; do
    missing_nodes=""
    for uid in "${expected_nodes[@]}"; do
      local db_row
      db_row="$(db_query_line "
        SELECT id
        FROM nodes
        WHERE uid = '${uid}'
          AND last_seen_at > NOW() - INTERVAL '15 minutes'
          AND (
            (zone_id IS NULL AND lifecycle_state = 'REGISTERED_BACKEND')
            OR (
              '${test_zone_id}' <> ''
              AND zone_id = CAST('${test_zone_id}' AS bigint)
              AND lifecycle_state IN ('ASSIGNED_TO_ZONE', 'ACTIVE')
            )
          )
        ORDER BY last_seen_at DESC NULLS LAST
        LIMIT 1;
      ")"
      if [ -z "$db_row" ]; then
        if [ -z "$missing_nodes" ]; then
          missing_nodes="$uid"
        else
          missing_nodes="${missing_nodes},$uid"
        fi
      fi
    done

    if [ -z "$missing_nodes" ]; then
      echo "✅ Все ноды после reboot снова видны в БД в допустимом lifecycle state"
      return 0
    fi

    if [ $(( "$(date +%s)" - started_at )) -ge "$timeout_sec" ]; then
      echo "❌ Не дождались появления нод в БД после reboot за ${timeout_sec}s. missing=${missing_nodes}"
      db_query_line "SELECT id, uid, hardware_id, zone_id, pending_zone_id, lifecycle_state, status, last_seen_at FROM nodes ORDER BY last_seen_at DESC NULLS LAST LIMIT 20;" || true
      return 1
    fi
    sleep 3
  done
}

build_bind_uids_from_runtime() {
  local out_file="$1"
  local scan_seconds="${2:-20}"
  local scan_file db_file filtered_file explicit_file
  scan_file="$(mktemp /tmp/e2e_bind_scan.XXXXXX)"
  db_file="$(mktemp /tmp/e2e_bind_db.XXXXXX)"
  filtered_file="$(mktemp /tmp/e2e_bind_filtered.XXXXXX)"
  explicit_file="$(mktemp /tmp/e2e_bind_explicit.XXXXXX)"

  collect_live_heartbeat_topics "$scan_file" "$scan_seconds" || true
  cut -d'|' -f3 "$scan_file" | sed '/^$/d' > "${scan_file}.uids"
  db_query_line "SELECT uid FROM nodes WHERE zone_id IS NULL AND last_seen_at > NOW() - INTERVAL '15 minutes' ORDER BY uid;" > "$db_file" || true

  {
    cat "${scan_file}.uids" 2>/dev/null || true
    cat "$db_file" 2>/dev/null || true
  } | sed '/^$/d' | sort -u | while IFS= read -r uid; do
    if uid_matches_discovery_filter "$uid"; then
      printf '%s\n' "$uid"
    fi
  done > "$filtered_file"

  : > "$explicit_file"
  local explicit_uid
  for explicit_uid in "${TEST_NODE_UID:-}" "${TEST_WORKFLOW_NODE_UID:-}" "${TEST_PH_NODE_UID:-}" "${TEST_EC_NODE_UID:-}"; do
    if ! is_auto_uid "$explicit_uid"; then
      printf '%s\n' "$explicit_uid" >> "$explicit_file"
    fi
  done

  {
    cat "$filtered_file" 2>/dev/null || true
    cat "$explicit_file" 2>/dev/null || true
  } | sed '/^$/d' | sort -u > "$out_file"

  rm -f "$scan_file" "${scan_file}.uids" "$db_file" "$filtered_file" "$explicit_file"
  return 0
}

build_ae_publish_payload() {
  local zone_id="$1"
  local node_uid="$2"
  local channel="$3"
  local cmd="$4"
  local params_json="${5:-{}}"
  local cmd_id="$6"
  "$PYTHON_BIN" - <<'PY' "$zone_id" "$node_uid" "$channel" "$cmd" "$params_json" "$cmd_id" "$TEST_NODE_GH_UID"
import json
import sys

zone_id, node_uid, channel, cmd, params_json, cmd_id, gh_uid = sys.argv[1:8]
params = {}
if params_json:
    try:
        parsed = json.loads(params_json)
        if isinstance(parsed, dict):
            params = parsed
    except Exception:
        params = {}
payload = {
    "greenhouse_uid": gh_uid,
    "zone_id": int(zone_id),
    "node_uid": node_uid,
    "channel": channel,
    "cmd": cmd,
    "params": params,
    "cmd_id": cmd_id,
    "source": "e2e_real_hardware",
}
print(json.dumps(payload, separators=(",", ":")))
PY
}

new_cmd_id() {
  "$PYTHON_BIN" - <<'PY'
import uuid
print(str(uuid.uuid4()))
PY
}

assert_ae_publish_ok() {
  local body_file="$1"
  "$PYTHON_BIN" - <<'PY' "$body_file"
import json
import sys

body_file = sys.argv[1]
with open(body_file, "r", encoding="utf-8") as f:
    data = json.loads(f.read() or "{}")
ok = str(data.get("status") or "").strip().lower() == "ok"
command_id = str(((data.get("data") or {}).get("command_id") or "")).strip()
if not ok or not command_id:
    raise SystemExit(1)
PY
}

extract_ae_response_cmd_id() {
  local body_file="$1"
  "$PYTHON_BIN" - <<'PY' "$body_file"
import json
import sys

body_file = sys.argv[1]
with open(body_file, "r", encoding="utf-8") as f:
    data = json.loads(f.read() or "{}")
cmd_id = ((data.get("data") or {}).get("command_id")) or ((data.get("data") or {}).get("cmd_id")) or ""
print(str(cmd_id).strip())
PY
}

wait_command_terminal_status() {
  local cmd_id="$1"
  local timeout="${2:-45}"
  local started_at now_epoch
  started_at="$(date +%s)"

  while true; do
    local status
    status="$(db_query_line "SELECT status FROM commands WHERE cmd_id = '${cmd_id}' ORDER BY created_at DESC LIMIT 1;")"
    if [ -n "$status" ]; then
      case "$status" in
        QUEUED|PENDING|SENT|ACK)
          ;;
        *)
          echo "$status"
          return 0
          ;;
      esac
    fi

    now_epoch="$(date +%s)"
    if [ $(( now_epoch - started_at )) -ge "$timeout" ]; then
      return 1
    fi
    sleep 1
  done
}

ae_publish_command() {
  local zone_id="$1"
  local node_uid="$2"
  local channel="$3"
  local cmd="$4"
  local params_json="${5:-{}}"
  local payload_json publish_code request_cmd_id response_cmd_id terminal_status command_row

  request_cmd_id="$(new_cmd_id)"
  if ! payload_json="$(build_ae_publish_payload "$zone_id" "$node_uid" "$channel" "$cmd" "$params_json" "$request_cmd_id")"; then
    echo "❌ Не удалось собрать payload для history-logger /commands: cmd=$cmd node=$node_uid channel=$channel zone_id=$zone_id"
    return 1
  fi
  if [ -z "$payload_json" ]; then
    echo "❌ Пустой payload для history-logger /commands: cmd=$cmd node=$node_uid channel=$channel zone_id=$zone_id"
    return 1
  fi
  publish_code="$(api_request_code "POST" "$HISTORY_LOGGER_URL/commands" "$payload_json" "$HISTORY_LOGGER_TOKEN" "/tmp/e2e_ae_publish_resp.json")"
  if [ "$publish_code" -lt 200 ] || [ "$publish_code" -ge 300 ]; then
    echo "❌ History-logger /commands вернул HTTP $publish_code: cmd=$cmd node=$node_uid channel=$channel zone_id=$zone_id"
    cat /tmp/e2e_ae_publish_resp.json
    return 1
  fi
  if ! assert_ae_publish_ok "/tmp/e2e_ae_publish_resp.json"; then
    echo "❌ History-logger /commands вернул невалидный ответ: cmd=$cmd node=$node_uid channel=$channel zone_id=$zone_id"
    cat /tmp/e2e_ae_publish_resp.json
    return 1
  fi
  response_cmd_id="$(extract_ae_response_cmd_id "/tmp/e2e_ae_publish_resp.json" || true)"
  if [ -z "$response_cmd_id" ]; then
    response_cmd_id="$request_cmd_id"
  fi

  if ! terminal_status="$(wait_command_terminal_status "$response_cmd_id" 45)"; then
    echo "❌ Не дождались terminal-статуса команды cmd_id=$response_cmd_id (cmd=$cmd node=$node_uid channel=$channel zone_id=$zone_id)"
    db_query_line "SELECT cmd_id, status, created_at, sent_at, ack_at, failed_at, error_message FROM commands WHERE cmd_id = '${response_cmd_id}' ORDER BY created_at DESC LIMIT 1;" || true
    return 1
  fi
  if [ "$terminal_status" != "DONE" ]; then
    command_row="$(db_query_line "SELECT cmd_id, status, COALESCE(error_message, '') FROM commands WHERE cmd_id = '${response_cmd_id}' ORDER BY created_at DESC LIMIT 1;")"
    echo "❌ Команда не завершилась DONE: cmd=$cmd node=$node_uid channel=$channel zone_id=$zone_id status=$terminal_status row=$command_row"
    return 1
  fi
  return 0
}

wait_node_unassigned() {
  local node_id="$1"
  local node_hw_id="$2"
  local timeout="${3:-180}"
  local started_at now_epoch
  started_at="$(date +%s)"

  while true; do
    local row=""
    if [ -n "$node_hw_id" ]; then
      row="$(db_query_line "SELECT id, uid, hardware_id FROM nodes WHERE hardware_id = '${node_hw_id}' AND zone_id IS NULL AND last_seen_at > NOW() - INTERVAL '15 minutes' ORDER BY last_seen_at DESC NULLS LAST LIMIT 1;")"
    fi
    if [ -z "$row" ]; then
      row="$(db_query_line "SELECT id, uid, hardware_id FROM nodes WHERE id = ${node_id} AND zone_id IS NULL AND last_seen_at > NOW() - INTERVAL '15 minutes' LIMIT 1;")"
    fi
    if [ -n "$row" ]; then
      echo "$row"
      return 0
    fi

    now_epoch="$(date +%s)"
    if [ $(( now_epoch - started_at )) -ge "$timeout" ]; then
      return 1
    fi
    sleep 3
  done
}

broadcast_reset_state_for_available_topics() {
  local preferred_zone_id="$1"
  local node_hw_id="$2"
  local primary_uid="$3"
  local rows
  local sent_count=0

  rows="$(db_query_line "SELECT DISTINCT uid, COALESCE(zone_id, 0) FROM nodes WHERE last_seen_at > NOW() - INTERVAL '20 minutes' ORDER BY uid;")"
  if [ -z "$rows" ]; then
    echo "⚠️ Не найден список нод для broadcast reset_state, отправляю только primary uid=$primary_uid"
    if ! ae_publish_command "$preferred_zone_id" "$primary_uid" "system" "reset_state" "{}"; then
      echo "❌ Не удалось отправить reset_state в primary topic для node=$primary_uid zone_id=$preferred_zone_id"
      return 1
    fi
    echo "✅ reset_state отправлен: node=$primary_uid topic=.../$primary_uid/system/command"
    return 0
  fi

  while IFS='|' read -r reset_uid reset_zone_id; do
    if [ -z "$reset_uid" ]; then
      continue
    fi
    if ! uid_matches_discovery_filter "$reset_uid" && [ "$reset_uid" != "$primary_uid" ]; then
      continue
    fi
    if [ -z "$reset_zone_id" ] || [ "$reset_zone_id" = "0" ]; then
      echo "ℹ️ reset_state skip: node=$reset_uid (unassigned, zone_id=0)"
      continue
    fi

    echo "↪ reset_state: node=$reset_uid zone_id=$reset_zone_id topic=.../$reset_uid/system/command"
    if ! ae_publish_command "$reset_zone_id" "$reset_uid" "system" "reset_state" "{}"; then
      echo "❌ Не удалось отправить reset_state: node=$reset_uid zone_id=$reset_zone_id"
      return 1
    fi
    sent_count=$((sent_count + 1))
  done <<< "$rows"

  if [ "$sent_count" -eq 0 ]; then
    if [ -z "$preferred_zone_id" ] || [ "$preferred_zone_id" = "0" ]; then
      echo "ℹ️ reset_state broadcast отложен: нет assigned topic до bind"
      return 2
    fi
    echo "⚠️ Все найденные ноды были unassigned, пробую reset_state для primary uid=$primary_uid zone_id=$preferred_zone_id"
    if ! ae_publish_command "$preferred_zone_id" "$primary_uid" "system" "reset_state" "{}"; then
      echo "❌ Не удалось отправить fallback reset_state в primary topic для node=$primary_uid"
      return 1
    fi
    sent_count=1
  fi

  echo "✅ reset_state broadcast завершен: отправлено в $sent_count topic(s)"
  return 0
}

prepare_real_hardware_node() {
  echo "🔧 Подготовка real hardware ноды для e2e..."
  echo "ℹ️ real-hardware harness работает только с реальной test_node без node-sim"

  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" up -d \
    postgres redis mosquitto history-logger mqtt-bridge automation-engine laravel digital-twin >/dev/null

  # В real-hardware контуре не должно остаться ни одного node-sim publisher
  # с nd-test-* UID, иначе IRR/state ответы от симулятора смешаются с реальной нодой.
  for service in node-sim node-sim-workflow node-sim-test-node node-sim-manager; do
    "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" stop "$service" >/dev/null 2>&1 || true
  done
  echo "ℹ️ Убедился, что real-hardware harness видел только реальную test_node"

  if ! wait_laravel_health 180; then
    echo "❌ Laravel не стал healthy вовремя: $LARAVEL_URL/api/system/health"
    exit 1
  fi
  if ! wait_automation_engine_ready 180; then
    echo "❌ automation-engine не стал ready вовремя: $AUTOMATION_ENGINE_URL/health/ready"
    exit 1
  fi
  if ! wait_history_logger_health 180; then
    echo "❌ history-logger не стал healthy вовремя: $HISTORY_LOGGER_URL/health"
    exit 1
  fi
  if ! verify_rollout_observability_contract; then
    echo "❌ observability contract не сошелся: exporter или метрики не готовы к rollout"
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
  local target_zone_uid target_gh_uid
  target_zone_uid="$zone_uid"
  target_gh_uid="$gh_uid"

  echo "🧹 Удаляю stale AE3 blocking alerts для тестовой зоны..."
  db_query_line "
    DELETE FROM alerts
    WHERE zone_id = ${zone_id}
      AND code IN (
        'biz_zone_correction_config_missing',
        'biz_zone_dosing_calibration_missing',
        'biz_solution_fill_timeout',
        'biz_prepare_recirculation_retry_exhausted',
        'biz_ae3_task_failed',
        'biz_correction_exhausted',
        'biz_irrigation_correction_exhausted',
        'biz_irrigation_decision_skip'
      );
  " >/dev/null

  echo "🧹 Удаляю orphan AE3 alerts от удалённых временных зон..."
  db_query_line "
    DELETE FROM alerts
    WHERE zone_id IS NULL
      AND COALESCE(details->>'zone_validation', '') = 'zone_not_found'
      AND code IN (
        'biz_zone_correction_config_missing',
        'biz_zone_dosing_calibration_missing',
        'biz_solution_fill_timeout',
        'biz_prepare_recirculation_retry_exhausted',
        'biz_ae3_task_failed',
        'biz_correction_exhausted',
        'biz_irrigation_correction_exhausted'
      );
  " >/dev/null

  echo "🧹 Удаляю все ноды из БД перед тестом..."
  db_query_line "TRUNCATE TABLE nodes RESTART IDENTITY CASCADE;" >/dev/null

  local live_topics_file
  live_topics_file="$(mktemp /tmp/e2e_live_topics.XXXXXX)"
  echo "🔍 Сканирую live heartbeat topics (${MQTT_LIVE_SCAN_SEC}s)..."
  if ! collect_live_heartbeat_topics "$live_topics_file" "$MQTT_LIVE_SCAN_SEC"; then
    echo "❌ Ошибка сканирования live heartbeat topics"
    exit 1
  fi
  if [ ! -s "$live_topics_file" ]; then
    echo "❌ Не найдено live heartbeat topics. Проверь, что test_node онлайн и шлет heartbeat."
    exit 1
  fi
  echo "✅ Найдены live topics:"
  cat "$live_topics_file"

  echo "♻️ Пушу reset config во все live topics..."
  if ! publish_temp_reset_config_to_live_topics "$live_topics_file"; then
    echo "❌ Не удалось запушить reset config во все live topics"
    exit 1
  fi

  local temp_namespace_ready=0
  echo "⏳ Жду появления всех нод в temp heartbeat topics..."
  if wait_nodes_in_temp_heartbeat_topics "$live_topics_file" "$MQTT_TEMP_WAIT_SEC"; then
    temp_namespace_ready=1
  else
    echo "⚠️ Temp heartbeat namespace не появился за ${MQTT_TEMP_WAIT_SEC}s; пробую reboot по исходным live topics."
  fi

  if [ "$temp_namespace_ready" -eq 1 ]; then
    echo "🔁 Пушу reboot в temp topics..."
    if ! publish_reboot_to_temp_topics "$live_topics_file"; then
      echo "❌ Не удалось отправить reboot в temp topics"
      exit 1
    fi
  else
    echo "🔁 Temp namespace не подтверждён, пушу reboot в исходный live namespace..."
    if ! publish_reboot_to_live_topics "$live_topics_file"; then
      echo "❌ Не удалось отправить reboot в исходный live namespace"
      exit 1
    fi
  fi

  echo "⏳ Жду регистрации нод в БД как новых после reboot..."
  if ! wait_nodes_recreated_in_db "$live_topics_file" "$NODE_RECREATE_WAIT_SEC"; then
    echo "❌ Ноды не зарегистрировались в БД после reboot"
    exit 1
  fi

  local bind_uids=()
  local bind_uids_file
  bind_uids_file="$(mktemp /tmp/e2e_bind_uids.XXXXXX)"
  build_bind_uids_from_runtime "$bind_uids_file" "$BIND_DISCOVERY_SCAN_SEC"
  mapfile -t bind_uids < <(cat "$bind_uids_file")
  rm -f "$bind_uids_file"

  if [ "${#bind_uids[@]}" -eq 0 ]; then
    mapfile -t bind_uids < <(
      cut -d'|' -f3 "$live_topics_file" | sed '/^$/d' | sort -u | while IFS= read -r uid; do
        if uid_matches_discovery_filter "$uid"; then
          printf '%s\n' "$uid"
        fi
      done
    )
  fi
  if [ "${#bind_uids[@]}" -eq 0 ]; then
    mapfile -t bind_uids < <(cut -d'|' -f3 "$live_topics_file" | sed '/^$/d' | sort -u)
  fi
  if [ "${#bind_uids[@]}" -eq 0 ]; then
    echo "❌ Нет нод для bind после перерегистрации"
    exit 1
  fi

  echo "✅ Кандидаты для bind:"
  printf '%s\n' "${bind_uids[@]}"

  echo "🧩 Привязываю ноды к зоне ${zone_uid}..."
  local uid
  for uid in "${bind_uids[@]}"; do
    local node_row
    node_row="$(db_query_line "SELECT id, uid, hardware_id FROM nodes WHERE uid = '${uid}' AND zone_id IS NULL AND lifecycle_state = 'REGISTERED_BACKEND' ORDER BY last_seen_at DESC NULLS LAST LIMIT 1;")"
    if [ -z "$node_row" ]; then
      echo "❌ Нода для bind не найдена в REGISTERED_BACKEND: uid=$uid"
      exit 1
    fi
    local node_id node_uid node_hw_id
    IFS='|' read -r node_id node_uid node_hw_id <<<"$node_row"

    local assign_code
    assign_code="$(api_request_code "PATCH" "$LARAVEL_URL/api/nodes/$node_id" "{\"zone_id\":$zone_id}" "$token" "/tmp/e2e_node_assign_resp_${uid}.json")"
    if [ "$assign_code" -lt 200 ] || [ "$assign_code" -ge 300 ]; then
      echo "❌ PATCH /api/nodes/$node_id (uid=$uid zone_id=$zone_id) вернул HTTP $assign_code"
      cat "/tmp/e2e_node_assign_resp_${uid}.json"
      exit 1
    fi

    local publish_code
    publish_code="$(api_request_code "POST" "$LARAVEL_URL/api/nodes/$node_id/config/publish" "{}" "$token" "/tmp/e2e_node_publish_resp_${uid}.json")"
    if [ "$publish_code" -lt 200 ] || [ "$publish_code" -ge 300 ]; then
      echo "⚠️ POST /api/nodes/$node_id/config/publish (uid=$uid) вернул HTTP $publish_code (продолжаю)"
    fi
  done

  local confirm_timeout=240
  local confirm_started_at
  local last_nudge_at=0
  confirm_started_at="$(date +%s)"
  echo "⏳ Жду подтверждение binding/config_report для всех нод (до ${confirm_timeout}s)..."
  while true; do
    local missing_bind=""
    local missing_bind_uids=()
    local now_epoch
    for uid in "${bind_uids[@]}"; do
      local confirm_row
      confirm_row="$(db_query_line "SELECT uid FROM nodes WHERE uid = '${uid}' AND zone_id = ${zone_id} AND pending_zone_id IS NULL AND lifecycle_state = 'ASSIGNED_TO_ZONE' AND COALESCE(config->>'gh_uid','') = '${target_gh_uid}' AND COALESCE(config->>'zone_uid','') = '${target_zone_uid}' AND last_seen_at > NOW() - INTERVAL '15 minutes' LIMIT 1;")"
      if [ -z "$confirm_row" ]; then
        missing_bind_uids+=("$uid")
        if [ -z "$missing_bind" ]; then
          missing_bind="$uid"
        else
          missing_bind="${missing_bind},$uid"
        fi
      fi
    done

    if [ -z "$missing_bind" ]; then
      break
    fi

    now_epoch="$(date +%s)"
    if [ $(( now_epoch - last_nudge_at )) -ge 15 ]; then
      publish_bind_namespace_nudge "$zone_id" "$target_gh_uid" "$target_zone_uid" "${missing_bind_uids[@]}"
      last_nudge_at="$now_epoch"
    fi

    if [ $(( now_epoch - confirm_started_at )) -ge "$confirm_timeout" ]; then
      echo "❌ Не дождались binding/config_report для нод: $missing_bind"
      db_query_line "SELECT id, uid, hardware_id, zone_id, pending_zone_id, lifecycle_state, status, last_seen_at FROM nodes ORDER BY uid;" || true
      exit 1
    fi
    sleep 3
  done

  local node_meta_rows
  node_meta_rows="$(db_query_line "SELECT uid, COALESCE(type, ''), COALESCE(hardware_id, '') FROM nodes WHERE zone_id = ${zone_id} AND last_seen_at > NOW() - INTERVAL '15 minutes' ORDER BY uid;")"
  declare -A bound_node_types=()
  declare -A bound_node_hw_ids=()
  while IFS='|' read -r bound_uid bound_type bound_hw_id; do
    if [ -z "$bound_uid" ] || ! uid_in_list "$bound_uid" "${bind_uids[@]}"; then
      continue
    fi
    bound_node_types["$bound_uid"]="$bound_type"
    bound_node_hw_ids["$bound_uid"]="$bound_hw_id"
  done <<< "$node_meta_rows"

  local primary_uid=""
  if ! is_auto_uid "${TEST_NODE_UID:-}" && uid_in_list "$TEST_NODE_UID" "${bind_uids[@]}"; then
    primary_uid="$TEST_NODE_UID"
  elif ! is_auto_uid "${TEST_WORKFLOW_NODE_UID:-}" && uid_in_list "$TEST_WORKFLOW_NODE_UID" "${bind_uids[@]}"; then
    primary_uid="$TEST_WORKFLOW_NODE_UID"
  else
    for uid in "${bind_uids[@]}"; do
      if [ "${bound_node_types[$uid]:-}" = "irrig" ]; then
        primary_uid="$uid"
        break
      fi
    done
    if [ -z "$primary_uid" ]; then
      primary_uid="$(first_uid_matching_pattern '(^|[-_])irrig([-_]|$)' "${bind_uids[@]}" || true)"
    fi
    if [ -z "$primary_uid" ]; then
      primary_uid="${bind_uids[0]}"
    fi
  fi

  local primary_row
  primary_row="$(db_query_line "SELECT n.uid, n.hardware_id, z.uid, g.uid FROM nodes n JOIN zones z ON z.id = n.zone_id JOIN greenhouses g ON g.id = z.greenhouse_id WHERE n.uid = '${primary_uid}' AND n.zone_id = ${zone_id} LIMIT 1;")"
  if [ -z "$primary_row" ]; then
    echo "❌ Не удалось определить primary ноду после bind: uid=$primary_uid"
    exit 1
  fi

  local primary_hw_id
  local workflow_uid="$primary_uid"
  if ! is_auto_uid "${TEST_WORKFLOW_NODE_UID:-}" && uid_in_list "$TEST_WORKFLOW_NODE_UID" "${bind_uids[@]}"; then
    workflow_uid="$TEST_WORKFLOW_NODE_UID"
  fi

  local ph_uid=""
  if ! is_auto_uid "${TEST_PH_NODE_UID:-}" && uid_in_list "$TEST_PH_NODE_UID" "${bind_uids[@]}"; then
    ph_uid="$TEST_PH_NODE_UID"
  else
    for uid in "${bind_uids[@]}"; do
      if [ "${bound_node_types[$uid]:-}" = "ph" ] && [ "$uid" != "$primary_uid" ]; then
        ph_uid="$uid"
        break
      fi
    done
    if [ -z "$ph_uid" ]; then
      ph_uid="$(first_uid_matching_pattern '(^|[-_])ph([-_]|$)|(^|[-_])dosing([-_]|$)' "${bind_uids[@]}" || true)"
    fi
    if [ -z "$ph_uid" ]; then
      for uid in "${bind_uids[@]}"; do
        if [ "$uid" != "$primary_uid" ]; then
          ph_uid="$uid"
          break
        fi
      done
    fi
    if [ -z "$ph_uid" ]; then
      ph_uid="$primary_uid"
    fi
  fi

  local ec_uid=""
  if ! is_auto_uid "${TEST_EC_NODE_UID:-}" && uid_in_list "$TEST_EC_NODE_UID" "${bind_uids[@]}"; then
    ec_uid="$TEST_EC_NODE_UID"
  else
    for uid in "${bind_uids[@]}"; do
      if [ "${bound_node_types[$uid]:-}" = "ec" ] && [ "$uid" != "$primary_uid" ]; then
        ec_uid="$uid"
        break
      fi
    done
    if [ -z "$ec_uid" ]; then
      ec_uid="$(first_uid_matching_pattern '(^|[-_])ec([-_]|$)' "${bind_uids[@]}" || true)"
    fi
    if [ -z "$ec_uid" ]; then
      for uid in "${bind_uids[@]}"; do
        if [ "$uid" != "$primary_uid" ] && [ "$uid" != "$ph_uid" ]; then
          ec_uid="$uid"
          break
        fi
      done
    fi
    if [ -z "$ec_uid" ]; then
      if [ "$ph_uid" != "$primary_uid" ]; then
        ec_uid="$ph_uid"
      else
        ec_uid="$primary_uid"
      fi
    fi
  fi

  local soil_uid=""
  if ! is_auto_uid "${TEST_SOIL_NODE_UID:-}" && uid_in_list "$TEST_SOIL_NODE_UID" "${bind_uids[@]}"; then
    soil_uid="$TEST_SOIL_NODE_UID"
  else
    for uid in "${bind_uids[@]}"; do
      if [ "${bound_node_types[$uid]:-}" = "water_sensor" ] && [ "$uid" != "$primary_uid" ]; then
        soil_uid="$uid"
        break
      fi
    done
    if [ -z "$soil_uid" ]; then
      soil_uid="$(first_uid_matching_pattern '(^|[-_])soil([-_]|$)|(^|[-_])moisture([-_]|$)|(^|[-_])water_sensor([-_]|$)' "${bind_uids[@]}" || true)"
    fi
    if [ -z "$soil_uid" ]; then
      for uid in "${bind_uids[@]}"; do
        if [ "$uid" != "$primary_uid" ] && [ "$uid" != "$ph_uid" ] && [ "$uid" != "$ec_uid" ]; then
          soil_uid="$uid"
          break
        fi
      done
    fi
    if [ -z "$soil_uid" ]; then
      soil_uid="$primary_uid"
    fi
  fi

  IFS='|' read -r TEST_NODE_UID primary_hw_id TEST_NODE_ZONE_UID TEST_NODE_GH_UID <<<"$primary_row"
  TEST_NODE_HW_ID="$primary_hw_id"
  TEST_WORKFLOW_NODE_UID="$workflow_uid"
  TEST_PH_NODE_UID="$ph_uid"
  TEST_EC_NODE_UID="$ec_uid"
  TEST_SOIL_NODE_UID="$soil_uid"
  export TEST_NODE_UID TEST_WORKFLOW_NODE_UID TEST_PH_NODE_UID TEST_EC_NODE_UID TEST_SOIL_NODE_UID TEST_NODE_HW_ID TEST_NODE_ZONE_UID TEST_NODE_GH_UID

  echo "🧹 Удаляю ложные infra alerts после controlled node re-registration..."
  db_query_line "
    DELETE FROM alerts
    WHERE code IN (
      'infra_telemetry_node_not_found',
      'infra_telemetry_sample_dropped_node_not_found'
    );
  " >/dev/null

  echo "✅ Ноды готовы: gh=$TEST_NODE_GH_UID zone=$TEST_NODE_ZONE_UID primary_node=$TEST_NODE_UID ph_node=$TEST_PH_NODE_UID ec_node=$TEST_EC_NODE_UID soil_node=$TEST_SOIL_NODE_UID hw=$TEST_NODE_HW_ID"
  rm -f "$live_topics_file"
  return 0
}

echo "🚀 Запуск E2E на реальном железе (set=$SCENARIO_SET, scenarios=${#SCENARIOS[@]})"
prepare_real_hardware_node
echo "Node: gh=$TEST_NODE_GH_UID zone=$TEST_NODE_ZONE_UID node=$TEST_NODE_UID workflow_node=$TEST_WORKFLOW_NODE_UID ph_node=$TEST_PH_NODE_UID ec_node=$TEST_EC_NODE_UID soil_node=$TEST_SOIL_NODE_UID hw=$TEST_NODE_HW_ID"

for scenario in "${SCENARIOS[@]}"; do
  echo "\n=== $scenario ==="
  started_at="$(date +%s)"
  scenario_log_tmp="$(mktemp /tmp/e2e_realhw_scenario.XXXXXX.log)"

  if ! "$PYTHON_BIN" -m runner.e2e_runner "$scenario" 2>&1 | tee "$scenario_log_tmp"; then
    echo "❌ Сценарий упал: $scenario"
    scan_logs_since_epoch "$started_at" || true
    scenario_db_metrics_since_epoch "$started_at" || true
    rm -f "$scenario_log_tmp"
    exit 1
  fi

  optional_issues="$(rg -c "Optional action .* failed|Optional assertion .* failed|Optional assertion .* skipped" "$scenario_log_tmp" -S || true)"
  if [ -n "$optional_issues" ] && [ "$optional_issues" -gt 0 ]; then
    echo "⚠️ Найдены optional предупреждения: count=${optional_issues}"
    rg -n "Optional action .* failed|Optional assertion .* failed|Optional assertion .* skipped" "$scenario_log_tmp" -S || true
  else
    echo "✅ Optional checks: без предупреждений"
  fi

  if scan_logs_since_epoch "$started_at"; then
    echo "✅ Сценарий прошел, проверка логов завершена"
  else
    echo "❌ Сценарий прошел, но в логах найдены ошибки (STRICT_SERVICE_LOG_SCAN=1)"
    scenario_db_metrics_since_epoch "$started_at" || true
    rm -f "$scenario_log_tmp"
    exit 1
  fi

  scenario_db_metrics_since_epoch "$started_at" || true
  rm -f "$scenario_log_tmp"
done

echo "\n🎉 Все сценарии для real hardware завершены успешно (set=$SCENARIO_SET)"
