#!/bin/bash
# Скрипт для 30-минутного нагрузочного теста с 100 нодами

set -e

echo "=========================================="
echo "30-MINUTE LOAD TEST WITH 100 NODES"
echo "=========================================="

cd "$(dirname "$0")"

# 1. Создаем тестовые данные (100 нод)
echo ""
echo "[1/5] Creating test data (100 nodes)..."
docker-compose -f docker-compose.dev.yml exec laravel php artisan db:seed --class=ThirtyMinLoadTestSeeder 2>&1 | tail -3

# 2. Проверяем начальное состояние
echo ""
echo "[2/5] Checking initial state..."
docker-compose -f docker-compose.dev.yml exec laravel php artisan tinker --execute="
echo 'Zones: ' . \App\Models\Zone::where('uid', 'like', 'zone-30min-test%')->count() . PHP_EOL;
echo 'Nodes: ' . \App\Models\DeviceNode::where('uid', 'like', 'node-30min-test%')->count() . PHP_EOL;
echo 'Telemetry samples (last hour): ' . \App\Models\TelemetrySample::where('ts', '>', now()->subHour())->count() . PHP_EOL;
" 2>&1 | tail -4

# 3. Запускаем эмулятор нод на 30 минут
echo ""
echo "[3/5] Starting node emulator (100 nodes, 30 minutes)..."
echo "This will run for 30 minutes. Press Ctrl+C to stop early."
START_TIME=$(date +%s)
docker-compose -f docker-compose.dev.yml run --rm node-emulator \
    python node_emulator.py \
    --nodes 100 \
    --duration 1800 \
    --mqtt-host mqtt \
    --mqtt-port 1883 \
    --api-url http://laravel \
    --load-from-api

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "Test completed in $((DURATION / 60)) minutes"

# 4. Проверяем результаты
echo ""
echo "[4/5] Checking results..."
docker-compose -f docker-compose.dev.yml exec laravel php artisan tinker --execute="
\$start = now()->subMinutes(35);
\$end = now();
\$samples = \App\Models\TelemetrySample::whereBetween('ts', [\$start, \$end])->count();
\$nodes = \App\Models\DeviceNode::where('uid', 'like', 'node-30min-test%')->count();
echo 'Telemetry samples (during test): ' . \$samples . PHP_EOL;
echo 'Test nodes: ' . \$nodes . PHP_EOL;
echo 'Avg samples per node: ' . round(\$samples / max(\$nodes, 1), 2) . PHP_EOL;
echo 'Samples per second: ' . round(\$samples / 1800, 2) . PHP_EOL;
" 2>&1 | tail -5

# 5. Проверяем метрики Prometheus
echo ""
echo "[5/5] Checking Prometheus metrics..."
QUEUE_SIZE=$(curl -s "http://localhost:9090/api/v1/query?query=telemetry_queue_size" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else 'N/A')" 2>&1)
DROPPED=$(curl -s "http://localhost:9090/api/v1/query?query=telemetry_dropped_total" | python3 -c "import sys, json; d=json.load(sys.stdin); r=d['data']['result']; print(sum(float(x['value'][1]) for x in r) if r else 0)" 2>&1)
OVERFLOW=$(curl -s "http://localhost:9090/api/v1/query?query=telemetry_queue_overflow_total" | python3 -c "import sys, json; d=json.load(sys.stdin); r=d['data']['result']; print(sum(float(x['value'][1]) for x in r) if r else 0)" 2>&1)

echo "Queue size: $QUEUE_SIZE"
echo "Dropped telemetry: $DROPPED"
echo "Queue overflow: $OVERFLOW"

echo ""
echo "=========================================="
echo "30-MINUTE LOAD TEST COMPLETED"
echo "=========================================="

