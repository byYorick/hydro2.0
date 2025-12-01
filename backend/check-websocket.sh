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
    REVERB_PID=$(docker exec $LARAVEL_CONTAINER ps aux | grep "reverb:start" | grep -v grep | awk '{print $2}' | head -n1)
    echo "   PID: $REVERB_PID"
else
    echo "   ✗ Процесс Reverb не найден"
    echo "   Попытка запуска через supervisor..."
    docker exec $LARAVEL_CONTAINER supervisorctl -c /opt/docker/etc/supervisor.conf start reverb 2>&1 || echo "   Не удалось запустить"
fi

echo ""
echo "3. Проверка порта 6001:"
if docker exec $LARAVEL_CONTAINER netstat -tuln 2>/dev/null | grep -q ":6001"; then
    echo "   ✓ Порт 6001 прослушивается"
    docker exec $LARAVEL_CONTAINER netstat -tuln 2>/dev/null | grep ":6001" || true
elif docker exec $LARAVEL_CONTAINER ss -tuln 2>/dev/null | grep -q ":6001"; then
    echo "   ✓ Порт 6001 прослушивается (ss)"
    docker exec $LARAVEL_CONTAINER ss -tuln 2>/dev/null | grep ":6001" || true
else
    echo "   ✗ Порт 6001 не прослушивается"
fi

echo ""
echo "4. Проверка логов Reverb:"
echo "   Последние 30 строк логов:"
# Проверяем оба возможных пути к логам
if docker exec $LARAVEL_CONTAINER test -f /var/log/reverb/reverb.log 2>/dev/null; then
    docker exec $LARAVEL_CONTAINER tail -n 30 /var/log/reverb/reverb.log 2>/dev/null || echo "   Ошибка чтения логов"
elif docker exec $LARAVEL_CONTAINER test -f /tmp/reverb.log 2>/dev/null; then
    docker exec $LARAVEL_CONTAINER tail -n 30 /tmp/reverb.log 2>/dev/null || echo "   Ошибка чтения логов"
else
    echo "   Логи не найдены (проверены /var/log/reverb/reverb.log и /tmp/reverb.log)"
fi

echo ""
echo "5. Проверка переменных окружения (REVERB_*):"
docker exec $LARAVEL_CONTAINER env | grep -E "^REVERB_" | sort

echo ""
echo "6. Проверка переменных окружения (VITE_REVERB_*):"
docker exec $LARAVEL_CONTAINER env | grep -E "^VITE_REVERB_" | sort

echo ""
echo "7. Проверка BROADCAST_CONNECTION:"
BROADCAST_CONNECTION=$(docker exec $LARAVEL_CONTAINER env | grep "^BROADCAST_CONNECTION=" | cut -d= -f2)
echo "   BROADCAST_CONNECTION=$BROADCAST_CONNECTION"
if [ "$BROADCAST_CONNECTION" != "reverb" ]; then
    echo "   ⚠ ВНИМАНИЕ: BROADCAST_CONNECTION должен быть 'reverb'"
    echo "   (Laravel 11 использует BROADCAST_CONNECTION, а не BROADCAST_DRIVER)"
fi

echo ""
echo "8. Проверка конфигурации Reverb (Laravel config):"
docker exec $LARAVEL_CONTAINER php artisan config:show reverb 2>/dev/null | head -n 50 || echo "   Не удалось получить конфигурацию"

echo ""
echo "9. Проверка app key совпадения:"
REVERB_APP_KEY=$(docker exec $LARAVEL_CONTAINER env | grep "^REVERB_APP_KEY=" | cut -d= -f2)
VITE_REVERB_APP_KEY=$(docker exec $LARAVEL_CONTAINER env | grep "^VITE_REVERB_APP_KEY=" | cut -d= -f2)
echo "   REVERB_APP_KEY=$REVERB_APP_KEY"
echo "   VITE_REVERB_APP_KEY=$VITE_REVERB_APP_KEY"
if [ "$REVERB_APP_KEY" = "$VITE_REVERB_APP_KEY" ]; then
    echo "   ✓ App keys совпадают"
else
    echo "   ✗ App keys НЕ совпадают!"
fi

echo ""
echo "10. Проверка host/port совпадения:"
REVERB_HOST=$(docker exec $LARAVEL_CONTAINER env | grep "^REVERB_HOST=" | cut -d= -f2)
REVERB_PORT=$(docker exec $LARAVEL_CONTAINER env | grep "^REVERB_PORT=" | cut -d= -f2)
VITE_REVERB_HOST=$(docker exec $LARAVEL_CONTAINER env | grep "^VITE_REVERB_HOST=" | cut -d= -f2)
VITE_REVERB_PORT=$(docker exec $LARAVEL_CONTAINER env | grep "^VITE_REVERB_PORT=" | cut -d= -f2)
echo "   REVERB_HOST=$REVERB_HOST (сервер)"
echo "   REVERB_PORT=$REVERB_PORT (сервер)"
echo "   VITE_REVERB_HOST=$VITE_REVERB_HOST (клиент)"
echo "   VITE_REVERB_PORT=$VITE_REVERB_PORT (клиент)"
if [ "$REVERB_PORT" = "$VITE_REVERB_PORT" ]; then
    echo "   ✓ Порты совпадают"
else
    echo "   ✗ Порты НЕ совпадают!"
fi
if [ "$REVERB_HOST" = "0.0.0.0" ] && [ "$VITE_REVERB_HOST" = "localhost" ]; then
    echo "   ✓ Host конфигурация корректна (сервер слушает 0.0.0.0, клиент подключается к localhost)"
else
    echo "   ⚠ Проверьте host конфигурацию"
fi

echo ""
echo "11. Проверка supervisor статуса:"
docker exec $LARAVEL_CONTAINER supervisorctl -c /opt/docker/etc/supervisor.conf status reverb 2>/dev/null || echo "   Supervisor недоступен"

echo ""
echo "12. Тест подключения WebSocket (с хоста):"
echo "   Примечание: curl не может выполнить полный WebSocket handshake, поэтому ошибка 400 нормальна"
echo "   Для реального теста используйте браузер или websocat"
if command -v websocat &> /dev/null; then
    echo "   Попытка подключения к ws://localhost:6001/app/${REVERB_APP_KEY:-local}..."
    timeout 3 websocat ws://localhost:6001/app/${REVERB_APP_KEY:-local} 2>&1 | head -n 10 || echo "   ✗ Не удалось подключиться"
elif command -v curl &> /dev/null; then
    echo "   Тест HTTP upgrade запроса (ожидается ошибка 400 - это нормально для curl):"
    curl -s -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: $(echo -n test | base64)" http://localhost:6001/app/${REVERB_APP_KEY:-local} 2>&1 | head -n 5
    echo "   (Ошибка 400 Invalid Sec-WebSocket-Key ожидаема - curl не может выполнить полный WebSocket handshake)"
else
    echo "   Установите websocat для полного теста WebSocket или используйте браузер"
fi

echo ""
echo "=== Проверка завершена ==="
echo ""
echo "Если Reverb не запущен, выполните:"
echo "  docker exec $LARAVEL_CONTAINER supervisorctl -c /opt/docker/etc/supervisor.conf start reverb"
echo ""
echo "Для просмотра логов в реальном времени:"
echo "  docker exec $LARAVEL_CONTAINER tail -f /var/log/reverb/reverb.log"
echo "  или"
echo "  docker exec $LARAVEL_CONTAINER tail -f /tmp/reverb.log"
echo ""
echo "Для запуска Reverb вручную с debug:"
echo "  docker exec -it $LARAVEL_CONTAINER php artisan reverb:start --debug --host=0.0.0.0 --port=6001"

