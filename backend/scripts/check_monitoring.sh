#!/bin/bash

# Скрипт проверки работоспособности мониторинга
# Использование: ./check_monitoring.sh

set -e

echo "=== Проверка мониторинга hydro2.0 ==="
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция проверки HTTP endpoint
check_endpoint() {
    local name=$1
    local url=$2
    local expected_status=${3:-200}
    
    echo -n "Проверка $name... "
    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    
    if [ "$response" = "$expected_status" ]; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC} (HTTP $response)"
        return 1
    fi
}

# Функция проверки доступности сервиса
check_service() {
    local name=$1
    local host=$2
    local port=$3
    
    echo -n "Проверка $name ($host:$port)... "
    if timeout 2 bash -c "echo > /dev/tcp/$host/$port" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        return 1
    fi
}

ERRORS=0

# Проверка Prometheus
echo "--- Prometheus ---"
check_endpoint "Prometheus UI" "http://localhost:9090" || ERRORS=$((ERRORS + 1))
check_endpoint "Prometheus metrics" "http://localhost:9090/metrics" || ERRORS=$((ERRORS + 1))
check_endpoint "Prometheus targets" "http://localhost:9090/api/v1/targets" || ERRORS=$((ERRORS + 1))
echo ""

# Проверка Alertmanager
echo "--- Alertmanager ---"
check_endpoint "Alertmanager UI" "http://localhost:9093" || ERRORS=$((ERRORS + 1))
check_endpoint "Alertmanager status" "http://localhost:9093/api/v2/status" || ERRORS=$((ERRORS + 1))
echo ""

# Проверка Grafana
echo "--- Grafana ---"
check_endpoint "Grafana UI" "http://localhost:3000" || ERRORS=$((ERRORS + 1))
check_endpoint "Grafana API health" "http://localhost:3000/api/health" || ERRORS=$((ERRORS + 1))
echo ""

# Проверка Python сервисов (метрики)
echo "--- Python Services Metrics ---"
check_endpoint "Automation Engine metrics" "http://localhost:9401/metrics" || ERRORS=$((ERRORS + 1))
check_endpoint "Scheduler metrics" "http://localhost:9402/metrics" || ERRORS=$((ERRORS + 1))
check_endpoint "MQTT Bridge metrics" "http://localhost:9000/metrics" || echo -e "${YELLOW}WARNING: MQTT Bridge metrics may not be available${NC}"
echo ""

# Проверка PostgreSQL
echo "--- PostgreSQL ---"
check_service "PostgreSQL" "localhost" "5432" || ERRORS=$((ERRORS + 1))
echo ""

# Итоги
echo "=== Итоги ==="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}Все проверки пройдены успешно!${NC}"
    exit 0
else
    echo -e "${RED}Обнаружено ошибок: $ERRORS${NC}"
    echo "Проверьте логи сервисов: docker-compose logs"
    exit 1
fi

