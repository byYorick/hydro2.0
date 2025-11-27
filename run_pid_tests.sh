#!/bin/bash
# Скрипт для запуска тестов PID функциональности в Docker контейнерах

set -e

echo "=== Запуск тестов PID конфигурации в Docker ==="
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Определяем корневую директорию проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

# Проверяем, запущены ли контейнеры
if ! docker-compose -f docker-compose.dev.yml ps | grep -q "Up"; then
    echo -e "${YELLOW}⚠ Контейнеры не запущены. Запускаю...${NC}"
    docker-compose -f docker-compose.dev.yml up -d db
    sleep 5
fi

# Функция для запуска PHP тестов
run_php_tests() {
    echo -e "${BLUE}=== PHP тесты (Laravel) ===${NC}"
    
    # Проверяем, запущен ли контейнер laravel
    if ! docker-compose -f docker-compose.dev.yml ps laravel 2>/dev/null | grep -q "Up"; then
        echo -e "${YELLOW}⚠ Контейнер laravel не запущен. Запускаю...${NC}"
        docker-compose -f docker-compose.dev.yml up -d laravel
        sleep 10
    fi
    
    echo "Запуск PHP unit тестов..."
    docker-compose -f docker-compose.dev.yml exec -T laravel php artisan test --filter=ZonePidConfig
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ PHP тесты пройдены${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ PHP тесты завершились с ошибками${NC}"
        echo ""
        return 1
    fi
}

# Функция для запуска Python тестов
run_python_tests() {
    echo -e "${BLUE}=== Python тесты (automation-engine) ===${NC}"
    
    echo "Запуск Python тестов..."
    COMPOSE_PROFILES=tests docker-compose -f docker-compose.dev.yml run --rm pid-tests
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ Python тесты пройдены${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ Python тесты завершились с ошибками${NC}"
        echo ""
        return 1
    fi
}

# Функция для запуска E2E тестов
run_e2e_tests() {
    echo -e "${BLUE}=== E2E тесты (Playwright) ===${NC}"
    
    if ! docker-compose -f docker-compose.dev.yml ps laravel 2>/dev/null | grep -q "Up"; then
        echo -e "${YELLOW}⚠ Контейнер laravel не запущен${NC}"
        return 1
    fi
    
    echo "Запуск E2E тестов..."
    docker-compose -f docker-compose.dev.yml exec -T laravel npx playwright test tests/E2E/pid-config.spec.ts
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ E2E тесты пройдены${NC}"
        echo ""
        return 0
    else
        echo -e "${YELLOW}⚠ E2E тесты требуют настройки Playwright или завершились с ошибками${NC}"
        echo ""
        return 1
    fi
}

# Главное меню
show_menu() {
    echo "Выберите тесты для запуска:"
    echo "  1) PHP тесты (Laravel)"
    echo "  2) Python тесты (automation-engine)"
    echo "  3) E2E тесты (Playwright)"
    echo "  4) Все тесты"
    echo "  5) Выход"
    echo ""
    read -p "Ваш выбор [1-5]: " choice
    
    case $choice in
        1)
            run_php_tests
            ;;
        2)
            run_python_tests
            ;;
        3)
            run_e2e_tests
            ;;
        4)
            run_php_tests
            run_python_tests
            run_e2e_tests
            ;;
        5)
            exit 0
            ;;
        *)
            echo -e "${RED}Неверный выбор${NC}"
            exit 1
            ;;
    esac
}

# Если передан аргумент, используем его
if [ "$1" = "php" ]; then
    run_php_tests
elif [ "$1" = "python" ]; then
    run_python_tests
elif [ "$1" = "e2e" ]; then
    run_e2e_tests
elif [ "$1" = "all" ]; then
    run_php_tests
    run_python_tests
    run_e2e_tests
    echo -e "${GREEN}=== Все тесты завершены ===${NC}"
elif [ -z "$1" ]; then
    # Интерактивное меню
    show_menu
else
    echo -e "${RED}Неизвестный аргумент: $1${NC}"
    echo "Использование: $0 [php|python|e2e|all]"
    exit 1
fi

