#!/bin/bash
# Скрипт для обновления файла /app/public/hot с правильным URL через прокси
# В dev режиме используем прокси через nginx на порту 8080
VITE_URL="http://localhost:8080"

# Убеждаемся, что директория public доступна для записи
chmod 777 /app/public 2>/dev/null || true
chown -R application:application /app/public 2>/dev/null || true

# Обновляем файл сразу при запуске
echo "$VITE_URL" > /app/public/hot
chmod 666 /app/public/hot 2>/dev/null || chmod 777 /app/public/hot 2>/dev/null || true
chown application:application /app/public/hot 2>/dev/null || true
echo "Updated /app/public/hot to $VITE_URL"

# Периодически проверяем и обновляем файл
while true; do
    CURRENT=$(cat /app/public/hot 2>/dev/null || echo "")
    # Игнорируем шаблонные значения (содержат ${ или $)
    if [[ "$CURRENT" == *'${'* ]] || [[ "$CURRENT" == *'$'* ]] || [ "$CURRENT" != "$VITE_URL" ]; then
        if [ "$CURRENT" != "$VITE_URL" ]; then
            echo "$VITE_URL" > /app/public/hot
            chmod 666 /app/public/hot 2>/dev/null || chmod 777 /app/public/hot 2>/dev/null || true
            chown application:application /app/public/hot 2>/dev/null || true
            echo "$(date): Updated /app/public/hot from '$CURRENT' to '$VITE_URL'"
        fi
    fi
    sleep 3
done

