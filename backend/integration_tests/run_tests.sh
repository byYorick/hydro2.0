#!/bin/bash
# Скрипт для запуска интеграционных тестов

set -e

echo "=== Integration Tests for Error Reporting ==="
echo ""

# Проверка доступности сервисов
echo "Checking services availability..."

# MQTT
if docker exec backend-mqtt-1 mosquitto_pub -h localhost -t test -m test 2>/dev/null; then
    echo "✓ MQTT broker is available"
else
    echo "✗ MQTT broker is not available"
    exit 1
fi

# Laravel
if curl -s -f http://localhost:8080/api/system/health > /dev/null; then
    echo "✓ Laravel API is available"
else
    echo "✗ Laravel API is not available"
    exit 1
fi

# History Logger
if curl -s -f http://localhost:9300/health > /dev/null; then
    echo "✓ History Logger is available"
else
    echo "⚠ History Logger is not available (tests may be limited)"
fi

# Prometheus
if curl -s -f http://localhost:9090/-/healthy > /dev/null; then
    echo "✓ Prometheus is available"
else
    echo "⚠ Prometheus is not available (tests may be limited)"
fi

echo ""
echo "Running integration tests..."
echo ""

# Запуск тестов через docker-compose
cd "$(dirname "$0")/.."
docker-compose -f docker-compose.dev.yml --profile tests run --rm integration-tests


