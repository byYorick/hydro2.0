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

# Функция для запуска одного сценария
run_scenario() {
    local scenario=$1
    local scenario_path="scenarios/${scenario}.yaml"
    
    if [ ! -f "$scenario_path" ]; then
        log_error "Сценарий не найден: $scenario_path"
        return 1
    fi
    
    log_info "Запуск сценария: $scenario"
    
    # Определяем Python интерпретатор
    local PYTHON_BIN="python3"
    if [ -d "$PROJECT_ROOT/.venv" ] && [ -f "$PROJECT_ROOT/.venv/bin/python3" ]; then
        PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
    else
        # Создаем venv если его нет
        if [ ! -d "$PROJECT_ROOT/.venv" ]; then
            log_info "Создание venv и установка зависимостей..."
            python3 -m venv "$PROJECT_ROOT/.venv"
            "$PROJECT_ROOT/.venv/bin/pip" install -q -r "$E2E_DIR/requirements.txt"
        fi
        PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
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
            # Получаем токен для API
            log_info "Получение API токена..."
            LOGIN_RESPONSE=$(curl -sS -X POST "$LARAVEL_URL/api/auth/login" \
                -H "Accept: application/json" \
                -H "Content-Type: application/json" \
                -d '{"email":"e2e@example.com","password":"e2e"}')
            
            E2E_TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import json,sys; print((json.load(sys.stdin).get('data') or {}).get('token',''))")
            
            if [ -z "$E2E_TOKEN" ]; then
                log_error "Не удалось получить API токен. Ответ: $LOGIN_RESPONSE"
                exit 1
            fi
            
            export LARAVEL_API_TOKEN="$E2E_TOKEN"
            export DATABASE_URL="postgresql://${DB_USERNAME}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_DATABASE}"
            export DB_HOST DB_PORT DB_DATABASE DB_USERNAME DB_PASSWORD
            
            log_info "API токен получен ✓"
            
            # Запуск обязательных сценариев
            SCENARIOS=(
                "E01_bootstrap"
                "E02_command_happy"
                "E03_duplicate_cmd_response"
                "E04_error_alert"
                "E05_unassigned_attach"
                "E06_laravel_down_queue_recovery"
                "E07_ws_reconnect_snapshot_replay"
            )
            
            log_info "Запуск обязательных E2E сценариев..."
            
            PASSED=0
            FAILED=0
            FAILED_SCENARIOS=()
            
            for scenario in "${SCENARIOS[@]}"; do
                if run_scenario "$scenario"; then
                    PASSED=$((PASSED+1))
                else
                    FAILED=$((FAILED+1))
                    FAILED_SCENARIOS+=("$scenario")
                fi
            done
            
            # Итоговый отчет
            echo ""
            log_info "=== Итоговый отчет ==="
            log_info "Пройдено: $PASSED/${#SCENARIOS[@]}"
            log_info "Провалено: $FAILED/${#SCENARIOS[@]}"
            
            if [ $FAILED -gt 0 ]; then
                log_error "Проваленные сценарии:"
                for scenario in "${FAILED_SCENARIOS[@]}"; do
                    log_error "  - $scenario"
                done
                log_info "Отчеты доступны в: $E2E_DIR/reports/"
                exit 1
            else
                log_info "✓ Все сценарии прошли успешно!"
                log_info "Отчеты доступны в: $E2E_DIR/reports/"
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
