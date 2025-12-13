#!/bin/bash
# E2E Test Runner Script
# Запускает все обязательные E2E сценарии и генерирует отчеты

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

# Проверка наличия docker-compose
if ! command -v docker-compose &> /dev/null; then
    log_error "docker-compose не найден. Установите Docker Compose."
    exit 1
fi

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    log_error "python3 не найден. Установите Python 3."
    exit 1
fi

# Загрузка переменных окружения
if [ -f .env.e2e ]; then
    log_info "Загружаем переменные из .env.e2e"
    export $(cat .env.e2e | grep -v '^#' | xargs)
elif [ -f .env.e2e.example ]; then
    log_warn ".env.e2e не найден, используем .env.e2e.example"
    log_warn "Создайте .env.e2e на основе .env.e2e.example для настройки окружения"
    export $(cat .env.e2e.example | grep -v '^#' | xargs)
else
    log_warn "Файл .env.e2e не найден, используем значения по умолчанию"
fi

# Установка значений по умолчанию
export LARAVEL_URL=${LARAVEL_URL:-http://localhost:8081}
export LARAVEL_API_TOKEN=${LARAVEL_API_TOKEN:-dev-token-12345}
export MQTT_HOST=${MQTT_HOST:-localhost}
export MQTT_PORT=${MQTT_PORT:-1884}
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5433}
export DB_DATABASE=${DB_DATABASE:-hydro_e2e}
export DB_USERNAME=${DB_USERNAME:-hydro}
export DB_PASSWORD=${DB_PASSWORD:-hydro_e2e}
export WS_URL=${WS_URL:-ws://localhost:6002}

# Функция для проверки здоровья сервисов
check_services_health() {
    log_info "Проверка здоровья сервисов..."
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        # Проверка Laravel
        if curl -sf "${LARAVEL_URL}/api/system/health" > /dev/null 2>&1; then
            log_info "✓ Laravel готов"
        else
            log_warn "Laravel еще не готов (попытка $((attempt+1))/$max_attempts)"
            sleep 2
            attempt=$((attempt+1))
            continue
        fi
        
        # Проверка PostgreSQL
        if docker-compose -f docker-compose.e2e.yml exec -T postgres pg_isready -U hydro -d hydro_e2e > /dev/null 2>&1; then
            log_info "✓ PostgreSQL готов"
        else
            log_warn "PostgreSQL еще не готов (попытка $((attempt+1))/$max_attempts)"
            sleep 2
            attempt=$((attempt+1))
            continue
        fi
        
        # Проверка Redis
        if docker-compose -f docker-compose.e2e.yml exec -T redis redis-cli ping > /dev/null 2>&1; then
            log_info "✓ Redis готов"
        else
            log_warn "Redis еще не готов (попытка $((attempt+1))/$max_attempts)"
            sleep 2
            attempt=$((attempt+1))
            continue
        fi
        
        # Проверка MQTT
        if docker-compose -f docker-compose.e2e.yml exec -T mosquitto mosquitto_sub -h localhost -p 1883 -t '$SYS/#' -C 1 > /dev/null 2>&1; then
            log_info "✓ MQTT готов"
        else
            log_warn "MQTT еще не готов (попытка $((attempt+1))/$max_attempts)"
            sleep 2
            attempt=$((attempt+1))
            continue
        fi
        
        log_info "Все сервисы готовы!"
        return 0
    done
    
    log_error "Не удалось дождаться готовности всех сервисов"
    return 1
}

# Функция для сбора информации об ошибке
collect_failure_info() {
    local scenario=$1
    local log_dir="$E2E_DIR/reports/${scenario}_failure_logs"
    mkdir -p "$log_dir"
    
    log_warn "  Сохранение логов сервисов для $scenario..."
    docker-compose -f "$E2E_DIR/docker-compose.e2e.yml" logs --tail 100 laravel > "$log_dir/laravel.log" 2>&1 || true
    docker-compose -f "$E2E_DIR/docker-compose.e2e.yml" logs --tail 100 history-logger > "$log_dir/history-logger.log" 2>&1 || true
    docker-compose -f "$E2E_DIR/docker-compose.e2e.yml" logs --tail 100 node-sim > "$log_dir/node-sim.log" 2>&1 || true
    docker-compose -f "$E2E_DIR/docker-compose.e2e.yml" logs --tail 100 mqtt-bridge > "$log_dir/mqtt-bridge.log" 2>&1 || true
    
    # Сбор последних WS и MQTT событий из логов
    log_warn "  Сбор последних WS/MQTT событий..."
    docker-compose -f "$E2E_DIR/docker-compose.e2e.yml" logs --tail 200 history-logger 2>&1 | grep -E "(MQTT|command_response|command_status|COMMAND)" > "$log_dir/mqtt_events.log" || true
    docker-compose -f "$E2E_DIR/docker-compose.e2e.yml" logs --tail 200 laravel 2>&1 | grep -E "(WebSocket|CommandStatusUpdated|AlertCreated|ZoneEvent)" > "$log_dir/ws_events.log" || true
}

# Функция для извлечения информации о последнем упавшем шаге из JUnit XML
extract_failed_step() {
    local junit_file="$E2E_DIR/reports/junit.xml"
    if [ -f "$junit_file" ] && command -v xmllint &> /dev/null; then
        xmllint --xpath "//testcase[@status='failed'][last()]/@name" "$junit_file" 2>/dev/null | sed 's/name="\(.*\)"/\1/' || echo ""
    elif [ -f "$junit_file" ]; then
        grep -oP '(?<=name=")[^"]*(?=".*status="failed")' "$junit_file" | tail -1 || echo ""
    else
        echo ""
    fi
}

# Функция для показа деталей ошибки
show_failure_details() {
    local scenario=$1
    local log_dir="$E2E_DIR/reports/${scenario}_failure_logs"
    
    log_error ""
    log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_error "Детали ошибки: $scenario"
    log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Последний упавший шаг
    local failed_step=$(extract_failed_step)
    if [ -n "$failed_step" ]; then
        log_error "  Упавший шаг: $failed_step"
        log_error ""
    fi
    
    # Пути к логам
    log_error "  Логи сервисов:"
    log_error "    - Laravel: $log_dir/laravel.log"
    log_error "    - History-logger: $log_dir/history-logger.log"
    log_error "    - Node-sim: $log_dir/node-sim.log"
    log_error "    - MQTT-bridge: $log_dir/mqtt-bridge.log"
    log_error ""
    
    # Последние события
    log_error "  Последние события:"
    if [ -f "$log_dir/mqtt_events.log" ] && [ -s "$log_dir/mqtt_events.log" ]; then
        log_warn "    Последние MQTT события (последние 5 строк):"
        tail -5 "$log_dir/mqtt_events.log" | sed 's/^/      /'
    else
        log_warn "    MQTT события не найдены"
    fi
    if [ -f "$log_dir/ws_events.log" ] && [ -s "$log_dir/ws_events.log" ]; then
        log_warn "    Последние WebSocket события (последние 5 строк):"
        tail -5 "$log_dir/ws_events.log" | sed 's/^/      /'
    else
        log_warn "    WebSocket события не найдены"
    fi
    log_error ""
    
    # JUnit XML
    local junit_file="$E2E_DIR/reports/junit.xml"
    if [ -f "$junit_file" ]; then
        log_error "  JUnit XML: $junit_file"
    fi
}

# Функция для запуска одного сценария
run_scenario() {
    local scenario=$1
    local scenario_path="scenarios/${scenario}.yaml"
    
    # Поддержка новой структуры с подпапками (например, core/E01_bootstrap)
    if [[ "$scenario" == *"/"* ]]; then
        scenario_path="scenarios/${scenario}.yaml"
    fi
    
    if [ ! -f "$scenario_path" ]; then
        log_error "Сценарий не найден: $scenario_path"
        return 1
    fi
    
    log_info "Запуск сценария: $scenario"
    
    # Определяем Python интерпретатор
    local PYTHON_BIN="python3"
    # Проверяем venv в E2E директории
    if [ -d "$E2E_DIR/venv" ] && [ -f "$E2E_DIR/venv/bin/python3" ]; then
        PYTHON_BIN="$E2E_DIR/venv/bin/python3"
    elif [ -d "$PROJECT_ROOT/.venv" ] && [ -f "$PROJECT_ROOT/.venv/bin/python3" ]; then
        PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
    else
        # Создаем venv в E2E директории если его нет
        if [ ! -d "$E2E_DIR/venv" ]; then
            log_info "Создание venv и установка зависимостей..."
            python3 -m venv "$E2E_DIR/venv"
            "$E2E_DIR/venv/bin/pip" install -q -r "$E2E_DIR/requirements.txt"
        fi
        PYTHON_BIN="$E2E_DIR/venv/bin/python3"
    fi
    
    # Запуск сценария
    cd "$E2E_DIR"
    "$PYTHON_BIN" -m runner.e2e_runner "$scenario_path" || {
        log_error "Сценарий $scenario завершился с ошибкой"
        return 1
    }
    
    log_info "✓ Сценарий $scenario завершен успешно"
    return 0
}

# Главная функция
main() {
    log_info "=== E2E Test Runner ==="
    log_info "Проект: $PROJECT_ROOT"
    log_info "E2E директория: $E2E_DIR"
    
    # Параметры командной строки
    ACTION="${1:-all}"
    
    case "$ACTION" in
        "up"|"start")
            log_info "Запуск E2E инфраструктуры..."
            docker-compose -f docker-compose.e2e.yml up -d
            log_info "Ожидание готовности сервисов..."
            sleep 10
            check_services_health
            log_info "Инфраструктура запущена. Используйте './tools/testing/run_e2e.sh test' для запуска тестов."
            ;;
        "down"|"stop")
            log_info "Остановка E2E инфраструктуры..."
            docker-compose -f docker-compose.e2e.yml down
            log_info "Инфраструктура остановлена."
            ;;
        "restart")
            log_info "Перезапуск E2E инфраструктуры..."
            docker-compose -f docker-compose.e2e.yml down
            docker-compose -f docker-compose.e2e.yml up -d
            sleep 10
            check_services_health
            ;;
        "test"|"run")
            # AuthClient теперь автоматически получает токен, поэтому LARAVEL_API_TOKEN не требуется
            # Оставляем только для обратной совместимости или если явно указан пользователем
            if [ -n "$LARAVEL_API_TOKEN" ]; then
                log_info "LARAVEL_API_TOKEN установлен, будет использован вместо AuthClient (для обратной совместимости)"
                log_warn "Рекомендуется не устанавливать LARAVEL_API_TOKEN - AuthClient автоматически получит токен"
            else
                log_info "Используется AuthClient для автоматического управления токенами"
                log_info "Токен будет получен автоматически при запуске тестов"
            fi
            # Не устанавливаем LARAVEL_API_TOKEN, чтобы AuthClient работал автоматически
            
            export DATABASE_URL="postgresql://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_DATABASE}"
            export DB_HOST DB_PORT DB_DATABASE DB_USERNAME DB_PASSWORD
            export WS_URL="${WS_URL:-ws://localhost:6002/app/local}"
            
            log_info "Используем API токен: ${LARAVEL_API_TOKEN:0:10}..."
            
            # Запуск всех сценариев кроме CHAOS (core + commands + alerts + snapshot + infra + grow_cycle + automation_engine)
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
                
                # GROW CYCLE
                "grow_cycle/E50_create_cycle_planned"
                "grow_cycle/E51_start_cycle_running"
                "grow_cycle/E52_stage_progress_timeline"
                "grow_cycle/E53_manual_advance_stage"
                "grow_cycle/E54_pause_resume_harvest"
                
                # AUTOMATION ENGINE
                "automation_engine/E60_climate_control_happy"
                "automation_engine/E61_fail_closed_corrections"
                "automation_engine/E62_controller_fault_isolation"
                "automation_engine/E63_backoff_on_errors"
            )
            
            log_info "Запуск полного набора E2E сценариев (${#SCENARIOS[@]} сценариев, без CHAOS)..."
            log_info "Для CHAOS тестов используйте: ./tools/testing/run_e2e_chaos.sh"
            
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
                    
                    # Сбор информации об ошибке
                    log_warn "Сбор информации об ошибке для $scenario..."
                    collect_failure_info "$scenario"
                fi
            done
            
            # Итоговый отчет
            echo ""
            log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_info "=== ИТОГОВЫЙ ОТЧЕТ ==="
            log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            
            # Summary по сценариям
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
            else
                log_warn "  JUnit XML: не найден"
            fi
            if [ -f "$TIMELINE_JSON" ]; then
                log_info "  Timeline JSON: $TIMELINE_JSON"
            else
                log_warn "  Timeline JSON: не найден"
            fi
            log_info "  Директория: $REPORTS_DIR/"
            echo ""
            
            if [ $FAILED -gt 0 ]; then
                log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                log_error "ДЕТАЛИ ОШИБОК:"
                log_error "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                for scenario in "${FAILED_SCENARIOS[@]}"; do
                    show_failure_details "$scenario"
                done
                exit 1
            else
                log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                log_info "✓ Все обязательные сценарии прошли успешно!"
                log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                exit 0
            fi
            ;;
        "all")
            log_info "Полный цикл: запуск инфраструктуры + тесты"
            docker-compose -f docker-compose.e2e.yml up -d
            sleep 10
            if check_services_health; then
                # Передаем управление в test через bash
                bash "$SCRIPT_DIR/run_e2e.sh" test
            else
                log_error "Не удалось запустить инфраструктуру"
                exit 1
            fi
            ;;
        "logs")
            log_info "Просмотр логов..."
            docker-compose -f docker-compose.e2e.yml logs -f "${2:-}"
            ;;
        "clean")
            log_info "Очистка данных E2E..."
            docker-compose -f docker-compose.e2e.yml down -v
            log_info "Данные очищены."
            ;;
        *)
            echo "Использование: $0 {up|down|restart|test|all|logs|clean}"
            echo ""
            echo "Команды:"
            echo "  up       - Запустить E2E инфраструктуру"
            echo "  down     - Остановить E2E инфраструктуру"
            echo "  restart  - Перезапустить E2E инфраструктуру"
            echo "  test     - Запустить E2E тесты (требует запущенной инфраструктуры)"
            echo "  all      - Запустить инфраструктуру и тесты"
            echo "  logs     - Просмотр логов (опционально: имя сервиса)"
            echo "  clean    - Остановить и удалить все данные"
            exit 1
            ;;
    esac
}

main "$@"
