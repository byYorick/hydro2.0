#!/bin/bash
# E2E Core Test Runner Script
# Запускает быстрый набор критичных E2E сценариев (CORE + COMMANDS + ALERTS + SNAPSHOT + INFRA)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
E2E_DIR="$PROJECT_ROOT/tests/e2e"

cd "$E2E_DIR"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Загрузка переменных окружения
if [ -f .env.e2e ]; then
    log_info "Загружаем переменные из .env.e2e"
    export $(cat .env.e2e | grep -v '^#' | xargs)
elif [ -f .env.e2e.example ]; then
    log_warn ".env.e2e не найден, используем .env.e2e.example"
    export $(cat .env.e2e.example | grep -v '^#' | xargs)
fi

# Установка значений по умолчанию
export LARAVEL_URL=${LARAVEL_URL:-http://localhost:8081}
export MQTT_HOST=${MQTT_HOST:-localhost}
export MQTT_PORT=${MQTT_PORT:-1884}
export DB_HOST=${DB_HOST:-127.0.0.1}
export DB_PORT=${DB_PORT:-5433}
export DB_DATABASE=${DB_DATABASE:-hydro_e2e}
export DB_USERNAME=${DB_USERNAME:-hydro}
export DB_PASSWORD=${DB_PASSWORD:-hydro_e2e}
export WS_URL=${WS_URL:-ws://localhost:6002/app/local}

# Функция для запуска одного сценария
run_scenario() {
    local scenario=$1
    local scenario_path="$scenario"
    
    if [ ! -f "scenarios/$scenario_path.yaml" ]; then
        log_error "Сценарий не найден: scenarios/$scenario_path.yaml"
        return 1
    fi
    
    log_info "Запуск сценария: $scenario"
    
    # Определяем Python интерпретатор
    local PYTHON_BIN="python3"
    if [ -d "$E2E_DIR/venv" ] && [ -f "$E2E_DIR/venv/bin/python3" ]; then
        PYTHON_BIN="$E2E_DIR/venv/bin/python3"
    elif [ -d "$PROJECT_ROOT/.venv" ] && [ -f "$PROJECT_ROOT/.venv/bin/python3" ]; then
        PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
    fi
    
    # Запуск сценария
    cd "$E2E_DIR"
    "$PYTHON_BIN" -m runner.e2e_runner "scenarios/$scenario_path.yaml" || {
        log_error "Сценарий $scenario завершился с ошибкой"
        return 1
    }
    
    log_info "✓ Сценарий $scenario завершен успешно"
    return 0
}

# Главная функция
main() {
    log_info "=== E2E Core Test Runner ==="
    log_info "Быстрая проверка критичных инвариантов"
    log_info ""
    
    export DATABASE_URL="postgresql://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_DATABASE}"
    export DB_HOST DB_PORT DB_DATABASE DB_USERNAME DB_PASSWORD
    export WS_URL="${WS_URL:-ws://localhost:6002/app/local}"
    
    # CORE набор: core/, commands/, alerts/, snapshot/, infrastructure/
    SCENARIOS=(
        # CORE
        "core/E01_bootstrap"
        "core/E02_auth_ws_api"
        
        # COMMANDS
        "commands/E10_command_happy"
        "commands/E11_command_failed"
        "commands/E12_command_timeout"
        "commands/E13_command_duplicate_response"
        "commands/E14_command_response_before_sent"
        
        # ALERTS
        "alerts/E20_error_to_alert_realtime"
        "alerts/E21_alert_dedup_count"
        "alerts/E22_unassigned_error_capture"
        "alerts/E23_unassigned_attach_on_registry"
        "alerts/E24_laravel_down_pending_alerts"
        "alerts/E25_dlq_replay"
        
        # SNAPSHOT
        "snapshot/E30_snapshot_contains_last_event_id"
        "snapshot/E31_reconnect_replay_gap"
        "snapshot/E32_out_of_order_guard"
        
        # INFRASTRUCTURE
        "infrastructure/E40_zone_readiness_fail"
        "infrastructure/E41_zone_readiness_warn_start_anyway"
        "infrastructure/E42_bindings_role_resolution"
    )
    
    log_info "Запуск CORE набора тестов (${#SCENARIOS[@]} сценариев)..."
    echo ""
    
    PASSED=0
    FAILED=0
    FAILED_SCENARIOS=()
    SCENARIO_RESULTS=()
    
    for scenario in "${SCENARIOS[@]}"; do
        log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        log_info "Запуск: $scenario"
        
        if run_scenario "$scenario"; then
            PASSED=$((PASSED+1))
            SCENARIO_RESULTS+=("$scenario:PASS")
            log_info "✓ PASS: $scenario"
        else
            FAILED=$((FAILED+1))
            FAILED_SCENARIOS+=("$scenario")
            SCENARIO_RESULTS+=("$scenario:FAIL")
            log_error "✗ FAIL: $scenario"
        fi
    done
    
    # Итоговый отчет
    echo ""
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "=== ИТОГОВЫЙ ОТЧЕТ ==="
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    log_info "Summary:"
    for result in "${SCENARIO_RESULTS[@]}"; do
        scenario_name=$(echo "$result" | cut -d: -f1)
        status=$(echo "$result" | cut -d: -f2)
        if [ "$status" = "PASS" ]; then
            echo -e "  ${GREEN}✓ PASS${NC}: $scenario_name"
        else
            echo -e "  ${RED}✗ FAIL${NC}: $scenario_name"
        fi
    done
    echo ""
    
    log_info "Статистика:"
    log_info "  Пройдено: $PASSED/${#SCENARIOS[@]}"
    if [ $FAILED -gt 0 ]; then
        log_error "  Провалено: $FAILED/${#SCENARIOS[@]}"
    else
        log_info "  Провалено: $FAILED/${#SCENARIOS[@]}"
    fi
    echo ""
    
    # Пути к отчётам
    REPORTS_DIR="$E2E_DIR/reports"
    log_info "Отчёты:"
    JUNIT_XML="$REPORTS_DIR/junit.xml"
    TIMELINE_JSON="$REPORTS_DIR/timeline.json"
    if [ -f "$JUNIT_XML" ]; then
        log_info "  JUnit XML: $JUNIT_XML"
    fi
    if [ -f "$TIMELINE_JSON" ]; then
        log_info "  Timeline JSON: $TIMELINE_JSON"
    fi
    echo ""
    
    if [ $FAILED -gt 0 ]; then
        log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        log_error "✗ CORE набор завершен с ошибками"
        log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        exit 1
    else
        log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        log_info "✓ Все CORE сценарии прошли успешно!"
        log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        exit 0
    fi
}

main "$@"


