#!/bin/bash
# Скрипт для просмотра логов Laravel контейнера

CONTAINER_NAME="backend-laravel-1"

echo "=== Просмотр логов Laravel ==="
echo ""
echo "Выберите опцию:"
echo "1. Последние 50 строк логов"
echo "2. Последние 100 строк логов"
echo "3. Только ошибки (ERROR)"
echo "4. Ошибки и предупреждения (ERROR, WARNING)"
echo "5. Следить за логами в реальном времени (tail -f)"
echo "6. Логи Reverb (WebSocket)"
echo ""

read -p "Введите номер опции (1-6): " option

case $option in
    1)
        docker logs $CONTAINER_NAME --tail 50 2>&1
        ;;
    2)
        docker logs $CONTAINER_NAME --tail 100 2>&1
        ;;
    3)
        docker logs $CONTAINER_NAME 2>&1 | grep -i "ERROR\|Exception\|Fatal" | tail -50
        ;;
    4)
        docker logs $CONTAINER_NAME 2>&1 | grep -i "ERROR\|WARNING\|Exception\|Fatal" | tail -50
        ;;
    5)
        echo "Следим за логами в реальном времени (Ctrl+C для выхода)..."
        docker logs $CONTAINER_NAME -f 2>&1
        ;;
    6)
        echo "Логи Reverb (WebSocket):"
        docker exec $CONTAINER_NAME tail -50 /tmp/reverb.log 2>/dev/null || echo "Логи Reverb не найдены"
        ;;
    *)
        echo "Неверный выбор"
        exit 1
        ;;
esac





