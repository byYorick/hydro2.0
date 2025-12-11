#!/bin/bash
# Скрипт для мониторинга запросов к бэкенду от Android приложения

echo "=== Мониторинг запросов к бэкенду ==="
echo "Ожидание запросов от Android приложения..."
echo "Попробуйте войти в приложение сейчас"
echo ""
echo "Фильтры:"
echo "  - POST /api/auth/login"
echo "  - IP: 10.0.2.2 (эмулятор)"
echo "  - IP: 192.168.* (реальное устройство)"
echo ""
echo "Нажмите Ctrl+C для выхода"
echo ""

tail -f /home/georgiy/esp/hydro/hydro2.0/backend/laravel/storage/logs/laravel.log | \
  grep --line-buffered -E "(POST|GET|10.0.2.2|192.168|api/auth|login)" | \
  grep --line-buffered -v "boost:mcp"

