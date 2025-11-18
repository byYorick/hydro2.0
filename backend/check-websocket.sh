#!/bin/bash
# Скрипт для проверки статуса WebSocket (Reverb)

echo "=== Проверка WebSocket (Reverb) ==="
echo ""

# Проверка контейнера Laravel
echo "1. Проверка контейнера Laravel:"
if docker ps | grep -q "laravel"; then
    echo "   ✓ Контейнер Laravel запущен"
    LARAVEL_CONTAINER=$(docker ps | grep "laravel" | awk '{print $1}' | head -n1)
    echo "   Контейнер ID: $LARAVEL_CONTAINER"
else
    echo "   ✗ Контейнер Laravel не найден"
    exit 1
fi

echo ""
echo "2. Проверка процесса Reverb:"
if docker exec $LARAVEL_CONTAINER ps aux | grep -q "reverb:start"; then
    echo "   ✓ Процесс Reverb запущен"
else
    echo "   ✗ Процесс Reverb не найден"
fi

echo ""
echo "3. Проверка порта 6001:"
if docker exec $LARAVEL_CONTAINER netstat -tuln | grep -q ":6001"; then
    echo "   ✓ Порт 6001 прослушивается"
else
    echo "   ✗ Порт 6001 не прослушивается"
fi

echo ""
echo "4. Проверка логов Reverb:"
echo "   Последние 20 строк логов:"
docker exec $LARAVEL_CONTAINER tail -n 20 /tmp/reverb.log 2>/dev/null || echo "   Логи не найдены"

echo ""
echo "5. Проверка переменных окружения:"
docker exec $LARAVEL_CONTAINER env | grep -E "REVERB_|BROADCAST_DRIVER" | sort

echo ""
echo "6. Проверка конфигурации Reverb:"
docker exec $LARAVEL_CONTAINER php artisan config:show reverb 2>/dev/null | head -n 30 || echo "   Не удалось получить конфигурацию"

echo ""
echo "7. Тест подключения WebSocket:"
if command -v websocat &> /dev/null; then
    echo "   Попытка подключения к ws://localhost:6001..."
    timeout 2 websocat ws://localhost:6001/app/local 2>&1 | head -n 5 || echo "   ✗ Не удалось подключиться"
else
    echo "   Установите websocat для тестирования: cargo install websocat"
fi

echo ""
echo "=== Проверка завершена ==="

