#!/bin/bash
# Скрипт для мониторинга 30-минутного теста в реальном времени

cd "$(dirname "$0")"

echo "Monitoring 30-minute load test..."
echo "Press Ctrl+C to stop monitoring"
echo ""

INTERVAL=30  # Обновление каждые 30 секунд
START_TIME=$(date +%s)

while true; do
    ELAPSED=$(( $(date +%s) - START_TIME ))
    MINUTES=$(( ELAPSED / 60 ))
    SECONDS=$(( ELAPSED % 60 ))
    
    echo "=========================================="
    echo "Time elapsed: ${MINUTES}m ${SECONDS}s"
    echo "=========================================="
    
    # Телеметрия
    SAMPLES=$(docker-compose -f docker-compose.dev.yml exec -T laravel php artisan tinker --execute="
        echo \App\Models\TelemetrySample::where('ts', '>', now()->subMinutes(35))->count();
    " 2>&1 | tail -1 | tr -d '[:space:]')
    
    echo "Telemetry samples (last 35 min): $SAMPLES"
    
    # Очередь
    QUEUE_SIZE=$(curl -s "http://localhost:9090/api/v1/query?query=telemetry_queue_size" 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else 'N/A')" 2>&1 | head -1)
    echo "Queue size: $QUEUE_SIZE"
    
    # Потери
    DROPPED=$(curl -s "http://localhost:9090/api/v1/query?query=telemetry_dropped_total" 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); r=d['data']['result']; print(int(sum(float(x['value'][1]) for x in r)) if r else 0)" 2>&1 | head -1)
    echo "Dropped telemetry: $DROPPED"
    
    # Throughput
    if [ "$SAMPLES" != "" ] && [ "$SAMPLES" != "0" ]; then
        RATE=$(echo "scale=2; $SAMPLES / ($ELAPSED / 60)" | bc 2>/dev/null || echo "N/A")
        echo "Samples per minute: $RATE"
    fi
    
    echo ""
    sleep $INTERVAL
done

