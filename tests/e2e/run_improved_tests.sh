#!/bin/bash
# Улучшенный скрипт запуска E2E тестов

set -e

echo "🚀 Запуск улучшенных E2E тестов..."

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
    local max_attempts=3
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        echo "📋 Запуск $test_name (попытка $attempt/$max_attempts)"

        if python3 -m runner.e2e_runner $test_name; then
            echo "✅ $test_name прошел успешно"
            return 0
        else
            echo "❌ $test_name не прошел (попытка $attempt)"
            if [ $attempt -lt $max_attempts ]; then
                echo "⏳ Ждем 5 секунд перед следующей попыткой..."
                sleep 5
            fi
        fi

        ((attempt++))
    done

    echo "💥 $test_name не прошел после $max_attempts попыток"
    return 1
}

# Запуск тестов по категориям с улучшенной последовательностью

echo "=== CORE ТЕСТЫ ==="
run_test_with_retry "scenarios/core/E01_bootstrap.yaml"
run_test_with_retry "scenarios/core/E02_auth_ws_api.yaml"

echo "=== COMMANDS ТЕСТЫ (исправлены 503 ошибки) ==="
run_test_with_retry "scenarios/commands/E10_command_happy.yaml"
run_test_with_retry "scenarios/commands/E11_command_failed.yaml"
run_test_with_retry "scenarios/commands/E13_command_duplicate_response.yaml"
run_test_with_retry "scenarios/commands/E14_command_response_before_sent.yaml"

echo "=== GROW CYCLE ТЕСТЫ ==="
run_test_with_retry "scenarios/grow_cycle/E50_create_cycle_planned.yaml"
run_test_with_retry "scenarios/grow_cycle/E51_start_cycle_running.yaml"
run_test_with_retry "scenarios/grow_cycle/E52_stage_progress_timeline.yaml"
run_test_with_retry "scenarios/grow_cycle/E53_manual_advance_stage.yaml"
run_test_with_retry "scenarios/grow_cycle/E54_pause_resume_harvest.yaml"

echo "=== INFRASTRUCTURE ТЕСТЫ ==="
run_test_with_retry "scenarios/infrastructure/E40_zone_readiness_fail.yaml"
run_test_with_retry "scenarios/infrastructure/E41_zone_readiness_warn_start_anyway.yaml"
run_test_with_retry "scenarios/infrastructure/E42_bindings_role_resolution.yaml"

echo "=== ALERTS ТЕСТЫ (увеличены таймауты) ==="
run_test_with_retry "scenarios/alerts/E20_error_to_alert_realtime.yaml"
run_test_with_retry "scenarios/alerts/E21_alert_dedup_count.yaml"
run_test_with_retry "scenarios/alerts/E22_unassigned_error_capture.yaml"
run_test_with_retry "scenarios/alerts/E24_laravel_down_pending_alerts.yaml"
run_test_with_retry "scenarios/alerts/E25_dlq_replay.yaml"

echo "=== AUTOMATION ENGINE ТЕСТЫ (AE2-Lite compatible) ==="
run_test_with_retry "scenarios/automation_engine/E61_fail_closed_corrections.yaml"
run_test_with_retry "scenarios/automation_engine/E64_effective_targets_only.yaml"
run_test_with_retry "scenarios/automation_engine/E65_phase_transition_api.yaml"
run_test_with_retry "scenarios/automation_engine/E74_node_zone_mismatch_guard.yaml"

echo "=== SCHEDULER ТЕСТЫ ==="
run_test_with_retry "scenarios/scheduler/E93_start_cycle_intent_executor_path.yaml"

echo "=== SNAPSHOT ТЕСТЫ ==="
run_test_with_retry "scenarios/snapshot/E30_snapshot_contains_last_event_id.yaml"
run_test_with_retry "scenarios/snapshot/E31_reconnect_replay_gap.yaml"

echo "=== CHAOS ТЕСТЫ ==="
run_test_with_retry "scenarios/chaos/E70_mqtt_down_recovery.yaml"
run_test_with_retry "scenarios/chaos/E71_db_flaky.yaml"

echo "🎉 Все тесты завершены!"

# Опционально: запуск браузерных тестов
echo "=== БРАУЗЕРНЫЕ ТЕСТЫ ==="
echo "Запустить браузерные тесты? (y/N)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Запуск браузерных тестов..."
    cd backend/laravel
    npm run e2e:browser
fi
