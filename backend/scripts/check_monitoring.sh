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

WEBHOOK_SECRET="${ALERTMANAGER_WEBHOOK_SECRET:-dev-alertmanager-webhook-secret}"

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
check_endpoint "Prometheus rules" "http://localhost:9090/api/v1/rules" || ERRORS=$((ERRORS + 1))
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

# History Logger health + metrics
echo "--- History Logger ---"
check_endpoint "History Logger /health" "http://localhost:9300/health" || ERRORS=$((ERRORS + 1))
check_endpoint "History Logger :9301/metrics" "http://localhost:9301/metrics" || echo -e "${YELLOW}WARNING: HL metrics on :9301 may be unavailable (fallback /metrics on :9300)${NC}"
check_endpoint "History Logger /metrics" "http://localhost:9300/metrics" || ERRORS=$((ERRORS + 1))
echo ""

# Проверка Python сервисов (метрики)
echo "--- Python Services Metrics ---"
check_endpoint "Automation Engine metrics" "http://localhost:9405/metrics/" || ERRORS=$((ERRORS + 1))
check_endpoint "Laravel scheduler metrics" "http://localhost:8080/api/system/scheduler/metrics" || ERRORS=$((ERRORS + 1))
check_endpoint "MQTT Bridge metrics" "http://localhost:9000/metrics" || echo -e "${YELLOW}WARNING: MQTT Bridge metrics may not be available${NC}"
echo ""

# Exporters
echo "--- Infra Exporters ---"
check_endpoint "Postgres exporter metrics" "http://localhost:9187/metrics" || echo -e "${YELLOW}WARNING: postgres-exporter may be down${NC}"
check_endpoint "Redis exporter metrics" "http://localhost:9121/metrics" || echo -e "${YELLOW}WARNING: redis-exporter may be down${NC}"
check_endpoint "Blackbox exporter metrics" "http://localhost:9115/metrics" || echo -e "${YELLOW}WARNING: blackbox-exporter may be down${NC}"
echo ""

# Firing alerts snapshot
echo "--- Prometheus Alerts ---"
echo -n "Проверка firing alerts (/api/v1/alerts)... "
alerts_json=$(curl -sf "http://localhost:9090/api/v1/alerts" 2>/dev/null || echo "")
if [ -z "$alerts_json" ]; then
    echo -e "${RED}FAILED${NC}"
    ERRORS=$((ERRORS + 1))
else
    firing_count=$(echo "$alerts_json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('alerts',[])))" 2>/dev/null || echo "?")
    echo -e "${GREEN}OK${NC} (firing: ${firing_count})"
fi
echo ""

# Alertmanager → Laravel webhook (smoke)
echo "--- Alertmanager Webhook → Laravel ---"
echo -n "Проверка POST /api/alerts/webhook с Bearer... "
webhook_status=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://localhost:8080/api/alerts/webhook" \
    -H "Authorization: Bearer ${WEBHOOK_SECRET}" \
    -H "Content-Type: application/json" \
    -d '{"version":"4","groupKey":"monitoring-check","status":"firing","receiver":"default-receiver","groupLabels":{"alertname":"MonitoringCheck"},"commonLabels":{"alertname":"MonitoringCheck","severity":"warning"},"commonAnnotations":{},"externalURL":"http://alertmanager:9093","alerts":[{"status":"firing","labels":{"alertname":"MonitoringCheck","severity":"warning"},"annotations":{"summary":"check_monitoring.sh smoke"},"startsAt":"2026-07-07T00:00:00Z","endsAt":"0001-01-01T00:00:00Z","generatorURL":"http://prometheus:9090"}]}' \
    2>/dev/null || echo "000")
if [ "$webhook_status" = "200" ] || [ "$webhook_status" = "202" ]; then
    echo -e "${GREEN}OK${NC} (HTTP ${webhook_status})"
else
    echo -e "${RED}FAILED${NC} (HTTP ${webhook_status})"
    ERRORS=$((ERRORS + 1))
fi
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
    echo "Проверьте логи сервисов: docker compose -f backend/docker-compose.dev.yml logs"
    exit 1
fi
