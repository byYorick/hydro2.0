#!/bin/bash
# Скрипт для запуска Reverb с debug в контейнере
# Использование: docker exec <container> /app/start-reverb-debug.sh

cd /app

# Очистить кеш конфигурации
php artisan config:clear

# Запустить Reverb в фоне с debug
nohup php artisan reverb:start --host=0.0.0.0 --port=6001 --debug > /tmp/reverb.log 2>&1 &

echo "Reverb запущен в фоне. Логи: /tmp/reverb.log"
echo "Проверка статуса: tail -f /tmp/reverb.log"



