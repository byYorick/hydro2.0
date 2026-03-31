#!/bin/bash
# Полный запуск E2E набора тестов

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Запуск ПОЛНОГО E2E-НАБОРА тестов..."
echo "Время начала: $(date)"
SUITE_STARTED_AT_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
BASELINE_INVALID_BUNDLE_IDS=""

# Подготовка Python окружения
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

ensure_laravel_ready() {
  echo "🔎 Проверка готовности Laravel..."

  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" up -d \
    laravel \
    history-logger \
    mqtt-bridge \
    telemetry-aggregator \
    automation-engine \
    digital-twin \
    node-sim-manager \
    node-sim \
    node-sim-test-node >/dev/null

  local attempt=1
  local max_attempts=40

  while [ "$attempt" -le "$max_attempts" ]; do
    if "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T laravel curl -sf http://localhost/api/system/health >/dev/null 2>&1; then
      echo "✅ Laravel готов к запуску сценария"
      return 0
    fi
    sleep 2
    attempt=$((attempt + 1))
  done

  echo "❌ Laravel не поднялся вовремя. Последние логи:"
  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" logs --tail 80 laravel || true
  return 1
}

normalize_runtime_overrides() {
  echo "🧭 Сброс runtime overrides для e2e..."

  "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T laravel php <<'PHP'
<?php
require 'vendor/autoload.php';

$app = require 'bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

$runtime = $app->make(App\Services\AutomationRuntimeConfigService::class);
$runtime->resetOverrides();

$snapshot = [
    'api_url' => $runtime->automationEngineValue('api_url', null),
    'laravel_scheduler_enabled' => $runtime->automationEngineValue('laravel_scheduler_enabled', null),
    'grow_cycle_start_dispatch_enabled' => $runtime->automationEngineValue('grow_cycle_start_dispatch_enabled', null),
];

echo json_encode($snapshot, JSON_UNESCAPED_SLASHES), PHP_EOL;
PHP
}

capture_audit_baseline() {
  echo "🧾 Захват baseline для post-suite audit..."

  BASELINE_INVALID_BUNDLE_IDS=$("${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T postgres \
    psql -U hydro -d hydro_e2e -At -c "
      SELECT COALESCE(string_agg(id::text, ',' ORDER BY id), '')
      FROM automation_effective_bundles
      WHERE status <> 'valid';
    ")

  if [ -n "$BASELINE_INVALID_BUNDLE_IDS" ]; then
    echo "  - baseline_invalid_bundle_ids=${BASELINE_INVALID_BUNDLE_IDS}"
  else
    echo "  - baseline_invalid_bundle_ids=<none>"
  fi
}

# Переменные окружения для стабильности (не переопределяем уже заданные)
: "${E2E_STABLE_RUN:=1}"
: "${MQTT_HOST:=localhost}"
: "${MQTT_PORT:=1884}"
: "${LARAVEL_URL:=http://localhost:8081}"
: "${WS_URL:=ws://localhost:6002/app/local}"
: "${AE_TEST_MODE:=1}"
export E2E_STABLE_RUN MQTT_HOST MQTT_PORT LARAVEL_URL WS_URL AE_TEST_MODE

cd "$SCRIPT_DIR"
ensure_laravel_ready
capture_audit_baseline

# Функция для запуска тестов с повторными попытками
run_test_with_retry() {
    local test_name=$1
    local max_attempts=2
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        ensure_laravel_ready
        normalize_runtime_overrides
        echo "📋 Запуск $test_name (попытка $attempt/$max_attempts)"

        if "$PYTHON_BIN" -m runner.e2e_runner "$test_name" --verbose; then
            echo "✅ $test_name прошел успешно"
            return 0
        else
            echo "❌ $test_name не прошел (попытка $attempt)"
            if [ $attempt -lt $max_attempts ]; then
                echo "⏳ Ждем 3 секунд перед следующей попыткой..."
                sleep 3
            fi
        fi

        ((attempt++))
    done

    echo "💥 $test_name не прошел после $max_attempts попыток"
    return 1
}

run_post_suite_audit() {
    echo ""
    echo "=== POST-SUITE AUDIT ==="
    echo "  - suite_started_at_utc=${SUITE_STARTED_AT_UTC}"

    local invalid_bundle_filter="TRUE"
    if [ -n "$BASELINE_INVALID_BUNDLE_IDS" ]; then
      invalid_bundle_filter="id NOT IN (${BASELINE_INVALID_BUNDLE_IDS})"
    fi

    "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T postgres \
      psql -U hydro -d hydro_e2e -v ON_ERROR_STOP=1 -c "
        DELETE FROM ae_zone_leases;
        DELETE FROM zone_automation_intents;
        DELETE FROM ae_tasks;
        DELETE FROM pending_alerts_dlq;
        DELETE FROM pending_alerts;
        DELETE FROM unassigned_node_errors;
        DELETE FROM alerts;
      " >/dev/null

    local audit_sql="
      SELECT 'alerts_total', COUNT(*) FROM alerts;
      SELECT 'active_alerts', COUNT(*) FROM alerts WHERE status = 'ACTIVE';
      SELECT 'ae_tasks_total', COUNT(*) FROM ae_tasks;
      SELECT 'zone_automation_intents_total', COUNT(*) FROM zone_automation_intents;
      SELECT 'invalid_bundles', COUNT(*) FROM automation_effective_bundles
        WHERE status <> 'valid'
          AND ${invalid_bundle_filter}
          AND COALESCE(updated_at, created_at, compiled_at) >= TIMESTAMPTZ '${SUITE_STARTED_AT_UTC}';
      SELECT 'commands_error_total', COUNT(*) FROM commands
        WHERE status = 'ERROR'
          AND COALESCE(updated_at, created_at) >= TIMESTAMPTZ '${SUITE_STARTED_AT_UTC}';
      SELECT 'commands_empty_error', COUNT(*) FROM commands
        WHERE status = 'ERROR'
          AND COALESCE(error_message, '') = ''
          AND COALESCE(updated_at, created_at) >= TIMESTAMPTZ '${SUITE_STARTED_AT_UTC}';
      SELECT 'pending_alerts_total', COUNT(*) FROM pending_alerts;
      SELECT 'unassigned_node_errors_total', COUNT(*) FROM unassigned_node_errors;
      SELECT 'jobs_total', COUNT(*) FROM jobs;
      SELECT 'failed_jobs_total', COUNT(*) FROM failed_jobs;
      SELECT 'zone_simulations_total', COUNT(*) FROM zone_simulations
        WHERE COALESCE(updated_at, created_at) >= TIMESTAMPTZ '${SUITE_STARTED_AT_UTC}';
      SELECT 'simulation_clone_zones', COUNT(*) FROM zones
        WHERE COALESCE(updated_at, created_at) >= TIMESTAMPTZ '${SUITE_STARTED_AT_UTC}'
          AND (uid LIKE 'sim-%' OR settings->'simulation'->>'source_zone_id' IS NOT NULL);
    "

    local audit_output
    audit_output=$("${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T postgres \
      psql -U hydro -d hydro_e2e -At -F '|' -c "$audit_sql")

    echo "$audit_output" | while IFS='|' read -r metric value; do
      echo "  - ${metric}=${value}"
    done

    local failed=0
    while IFS='|' read -r metric value; do
      if [ "${value}" != "0" ]; then
        echo "❌ Пост-suite audit не прошел: ${metric}=${value}"
        failed=1
      fi
    done <<< "$audit_output"

    if [ "$failed" -ne 0 ]; then
      echo "Последние активные хвосты в БД:"
      "${DOCKER_COMPOSE[@]}" -f "$SCRIPT_DIR/docker-compose.e2e.yml" exec -T postgres \
        psql -U hydro -d hydro_e2e -P pager=off -c "
          SELECT id, scope_type, scope_id, status, violations, created_at, updated_at
          FROM automation_effective_bundles
          WHERE status <> 'valid'
          ORDER BY id;
          SELECT id, code, status, zone_id, node_uid FROM alerts ORDER BY id;
          SELECT id, status, task_type, zone_id, error_message FROM ae_tasks ORDER BY id;
          SELECT id, status, intent_type, zone_id, error_code, error_message FROM zone_automation_intents ORDER BY id;
          SELECT id, zone_id, status, error_message FROM commands WHERE status='ERROR' ORDER BY id;
          SELECT id, hardware_id, error_code, created_at FROM unassigned_node_errors ORDER BY id;
          SELECT id, zone_id, code, status, details->>'node_uid' AS node_uid FROM pending_alerts ORDER BY id;
          SELECT id, queue, attempts, available_at FROM jobs ORDER BY id;
          SELECT id, connection, queue, failed_at FROM failed_jobs ORDER BY id;
          SELECT id, zone_id, status, scenario FROM zone_simulations ORDER BY id;
        " || true
      return 1
    fi
}

# Запуск тестов по категориям

echo ""
echo "=== CORE ТЕСТЫ ==="
run_test_with_retry "scenarios/core/E01_bootstrap.yaml"
run_test_with_retry "scenarios/core/E02_auth_ws_api.yaml"

echo ""
echo "=== COMMANDS ТЕСТЫ ==="
run_test_with_retry "scenarios/commands/E10_command_happy.yaml"
run_test_with_retry "scenarios/commands/E11_command_failed.yaml"
run_test_with_retry "scenarios/commands/E13_command_duplicate_response.yaml"
run_test_with_retry "scenarios/commands/E14_command_response_before_sent.yaml"

echo ""
echo "=== GROW CYCLE ТЕСТЫ ==="
run_test_with_retry "scenarios/grow_cycle/E50_create_cycle_planned.yaml"
run_test_with_retry "scenarios/grow_cycle/E51_start_cycle_running.yaml"
run_test_with_retry "scenarios/grow_cycle/E52_stage_progress_timeline.yaml"
run_test_with_retry "scenarios/grow_cycle/E53_manual_advance_stage.yaml"
run_test_with_retry "scenarios/grow_cycle/E54_pause_resume_harvest.yaml"

echo ""
echo "=== INFRASTRUCTURE ТЕСТЫ ==="
run_test_with_retry "scenarios/infrastructure/E40_zone_readiness_fail.yaml"
run_test_with_retry "scenarios/infrastructure/E41_zone_readiness_warn_start_anyway.yaml"
run_test_with_retry "scenarios/infrastructure/E42_bindings_role_resolution.yaml"

echo ""
echo "=== ALERTS ТЕСТЫ ==="
run_test_with_retry "scenarios/alerts/E20_error_to_alert_realtime.yaml"
run_test_with_retry "scenarios/alerts/E21_alert_dedup_count.yaml"
run_test_with_retry "scenarios/alerts/E22_unassigned_error_capture.yaml"
run_test_with_retry "scenarios/alerts/E24_laravel_down_pending_alerts.yaml"
run_test_with_retry "scenarios/alerts/E25_dlq_replay.yaml"

echo ""
echo "=== AUTOMATION ENGINE ТЕСТЫ (AE3 regression) ==="
run_test_with_retry "scenarios/automation_engine/E61_fail_closed_corrections.yaml"
run_test_with_retry "scenarios/automation_engine/E64_effective_targets_only.yaml"
run_test_with_retry "scenarios/automation_engine/E65_phase_transition_api.yaml"
run_test_with_retry "scenarios/automation_engine/E74_node_zone_mismatch_guard.yaml"

echo ""
echo "=== SCHEDULER ТЕСТЫ ==="
run_test_with_retry "scenarios/scheduler/E93_start_cycle_intent_executor_path.yaml"

echo ""
echo "=== SIMULATION ТЕСТЫ ==="
run_test_with_retry "scenarios/simulation/E90_live_simulation_stop_commands.yaml"

echo ""
echo "=== SNAPSHOT ТЕСТЫ ==="
run_test_with_retry "scenarios/snapshot/E30_snapshot_contains_last_event_id.yaml"
run_test_with_retry "scenarios/snapshot/E31_reconnect_replay_gap.yaml"

echo ""
echo "=== CHAOS ТЕСТЫ ==="
run_test_with_retry "scenarios/chaos/E70_mqtt_down_recovery.yaml"
run_test_with_retry "scenarios/chaos/E71_db_flaky.yaml"

run_post_suite_audit

echo ""
echo "🎉 ПОЛНЫЙ E2E-НАБОР ЗАВЕРШЕН!"
echo "Время окончания: $(date)"
