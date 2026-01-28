#!/bin/bash

# Golden Path Regression Suite Runner
# Быстрый локальный прогон базовых инвариантов пайплайна
# Использование: ./tools/regression/run_golden_path.sh

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Пути
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/golden_path.yaml"
PYTHON_SCRIPT="${SCRIPT_DIR}/golden_path_runner.py"

# Переменные окружения (с дефолтами)
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_USER="${MQTT_USER:-}"
MQTT_PASS="${MQTT_PASS:-}"
LARAVEL_URL="${LARAVEL_URL:-http://localhost:8080}"
API_TOKEN="${API_TOKEN:-}"

# Счетчики
PASSED=0
FAILED=0
TOTAL=0

# Функции
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_section() {
    echo -e "\n${CYAN}=== $1 ===${NC}"
}

# Проверка зависимостей
check_dependencies() {
    log_section "Проверка зависимостей"
    
    local deps_ok=true
    
    # Python
    if ! command -v python3 &> /dev/null; then
        log_error "python3 не найден"
        deps_ok=false
    else
        log_success "python3 найден: $(python3 --version)"
    fi
    
    # curl
    if ! command -v curl &> /dev/null; then
        log_error "curl не найден"
        deps_ok=false
    else
        log_success "curl найден: $(curl --version | head -1)"
    fi
    
    # Python библиотеки
    if ! python3 -c "import paho.mqtt.client" 2>/dev/null; then
        log_error "paho-mqtt не установлен. Установите: pip install paho-mqtt"
        deps_ok=false
    else
        log_success "paho-mqtt установлен"
    fi
    
    if ! python3 -c "import yaml" 2>/dev/null; then
        log_error "pyyaml не установлен. Установите: pip install pyyaml"
        deps_ok=false
    else
        log_success "pyyaml установлен"
    fi
    
    if ! python3 -c "import requests" 2>/dev/null; then
        log_error "requests не установлен. Установите: pip install requests"
        deps_ok=false
    else
        log_success "requests установлен"
    fi
    
    if [ "$deps_ok" = false ]; then
        log_error "Не все зависимости установлены"
        exit 1
    fi
}

# Проверка доступности сервисов
check_services() {
    log_section "Проверка доступности сервисов"
    
    # MQTT
    if command -v nc &> /dev/null; then
        if nc -z "${MQTT_HOST}" "${MQTT_PORT}" 2>/dev/null; then
            log_success "MQTT брокер доступен: ${MQTT_HOST}:${MQTT_PORT}"
        else
            log_error "MQTT брокер недоступен: ${MQTT_HOST}:${MQTT_PORT}"
            exit 1
        fi
    else
        log_warning "nc не найден, пропускаем проверку MQTT"
    fi
    
    # Laravel API
    if curl -sf --connect-timeout 2 "${LARAVEL_URL}/api/system/health" > /dev/null 2>&1; then
        log_success "Laravel API доступен: ${LARAVEL_URL}"
    else
        log_error "Laravel API недоступен: ${LARAVEL_URL}"
        log_warning "Убедитесь, что Laravel запущен и доступен"
        exit 1
    fi
}

# Запуск тестов
run_tests() {
    log_section "Запуск Golden Path тестов"
    
    cd "${PROJECT_ROOT}"
    
    # Экспортируем переменные окружения для Python скрипта
    export MQTT_HOST MQTT_PORT MQTT_USER MQTT_PASS
    export LARAVEL_URL API_TOKEN
    
    # Запускаем Python runner
    if python3 "${PYTHON_SCRIPT}" "${CONFIG_FILE}"; then
        log_success "Все тесты пройдены"
        return 0
    else
        log_error "Некоторые тесты провалились"
        return 1
    fi
}

# Главная функция
main() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║     Golden Path Regression Suite Runner (P1)               ║"
    echo "║     Быстрый локальный прогон базовых инвариантов         ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    log_info "Конфигурация:"
    log_info "  MQTT: ${MQTT_HOST}:${MQTT_PORT}"
    log_info "  Laravel: ${LARAVEL_URL}"
    log_info "  Config: ${CONFIG_FILE}"
    echo ""
    
    check_dependencies
    check_services
    
    if run_tests; then
        log_section "Итоги"
        log_success "Все тесты пройдены успешно"
        echo ""
        exit 0
    else
        log_section "Итоги"
        log_error "Некоторые тесты провалились"
        echo ""
        exit 1
    fi
}

# Запуск
main "$@"

