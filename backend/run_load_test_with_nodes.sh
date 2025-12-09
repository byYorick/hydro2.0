#!/bin/bash
# Скрипт для запуска нагрузочного тестирования с эмуляцией нод

set -e

echo "=========================================="
echo "LOAD TEST WITH 500 NODES"
echo "=========================================="

cd "$(dirname "$0")"

# 1. Создаем тестовые данные (500 нод)
echo ""
echo "[1/4] Creating test data (500 nodes)..."
docker-compose -f docker-compose.dev.yml exec laravel php artisan db:seed --class=LoadTestSeeder

# 2. Проверяем начальное состояние
echo ""
echo "[2/4] Checking initial state..."
docker-compose -f docker-compose.dev.yml exec laravel php artisan tinker --execute="
echo 'Zones: ' . \App\Models\Zone::count() . PHP_EOL;
echo 'Nodes: ' . \App\Models\DeviceNode::count() . PHP_EOL;
echo 'Telemetry samples (last hour): ' . \App\Models\TelemetrySample::where('ts', '>', now()->subHour())->count() . PHP_EOL;
"

# 3. Запускаем эмулятор нод
echo ""
echo "[3/4] Starting node emulator (500 nodes, 5 minutes)..."
echo "This will run for 5 minutes. Press Ctrl+C to stop early."
docker-compose -f docker-compose.dev.yml run --rm node-emulator \
    python node_emulator.py \
    --nodes 500 \
    --duration 300 \
    --mqtt-host mqtt \
    --mqtt-port 1883 \
    --mqtt-user node_emulator \
    --mqtt-password node_emulator_pass \
    --api-url http://laravel \
    --load-from-api

# 4. Проверяем результаты
echo ""
echo "[4/4] Checking results..."
docker-compose -f docker-compose.dev.yml exec laravel php artisan tinker --execute="
echo 'Telemetry samples (last 10 minutes): ' . \App\Models\TelemetrySample::where('ts', '>', now()->subMinutes(10))->count() . PHP_EOL;
echo 'Telemetry samples (last hour): ' . \App\Models\TelemetrySample::where('ts', '>', now()->subHour())->count() . PHP_EOL;
"

# Проверяем метрики Prometheus
echo ""
echo "Checking Prometheus metrics..."
curl -s "http://localhost:9090/api/v1/query?query=telemetry_queue_size" | python3 -m json.tool | grep -A 5 "value" | head -5
curl -s "http://localhost:9090/api/v1/query?query=telemetry_dropped_total" | python3 -m json.tool | grep -A 5 "value" | head -5
curl -s "http://localhost:9090/api/v1/query?query=telemetry_queue_overflow_total" | python3 -m json.tool | grep -A 5 "value" | head -5

echo ""
echo "=========================================="
echo "LOAD TEST COMPLETED"
echo "=========================================="

