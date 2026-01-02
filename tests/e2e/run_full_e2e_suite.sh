#!/bin/bash
# Полный запуск E2E набора тестов

set -e

echo "🚀 Запуск ПОЛНОГО E2E-НАБОРА тестов..."
echo "Время начала: $(date)"

# Переменные окружения для стабильности
export E2E_STABLE_RUN=1
export MQTT_HOST=localhost
export MQTT_PORT=1884
export LARAVEL_URL=http://localhost:8081
export WS_URL=ws://localhost:6002/app/local
export AE_TEST_MODE=1

# Функция для запуска тестов с повторными попытками
run_test_with_retry() {
    local test_name=$1
    local max_attempts=2
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        echo "📋 Запуск $test_name (попытка $attempt/$max_attempts)"

        if python3 -m runner.e2e_runner "$test_name" --verbose; then
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
echo "=== AUTOMATION ENGINE ТЕСТЫ ==="
run_test_with_retry "scenarios/automation_engine/E60_climate_control_happy.yaml"
run_test_with_retry "scenarios/automation_engine/E61_fail_closed_corrections.yaml"
run_test_with_retry "scenarios/automation_engine/E62_controller_fault_isolation.yaml"
run_test_with_retry "scenarios/automation_engine/E63_backoff_on_errors.yaml"
run_test_with_retry "scenarios/automation_engine/E64_effective_targets_only.yaml"
run_test_with_retry "scenarios/automation_engine/E65_phase_transition_api.yaml"
run_test_with_retry "scenarios/automation_engine/E66_fail_closed_corrections.yaml"

echo ""
echo "=== SNAPSHOT ТЕСТЫ ==="
run_test_with_retry "scenarios/snapshot/E30_snapshot_contains_last_event_id.yaml"
run_test_with_retry "scenarios/snapshot/E31_reconnect_replay_gap.yaml"

echo ""
echo "=== CHAOS ТЕСТЫ ==="
run_test_with_retry "scenarios/chaos/E70_mqtt_down_recovery.yaml"
run_test_with_retry "scenarios/chaos/E71_db_flaky.yaml"

echo ""
echo "🎉 ПОЛНЫЙ E2E-НАБОР ЗАВЕРШЕН!"
echo "Время окончания: $(date)"

