#!/bin/bash
# Обновляет файл /app/public/hot только если dev-сервер Vite доступен.
# Это предотвращает бесконечные перезагрузки браузера, когда hot-файл существует,
# а dev-сервер не запущен или недоступен.

set -o errexit
set -o nounset
set -o pipefail

HOT_FILE="/app/public/hot"
# Убираем кавычки из переменной окружения, если они есть
VITE_URL_RAW="${VITE_DEV_SERVER_URL:-http://localhost:8080}"
VITE_URL="${VITE_URL_RAW//\"/}"  # Удаляем все кавычки
# Проверяем Vite напрямую на порту 5173 внутри контейнера
PING_URL="http://127.0.0.1:5173/@vite/client"
CHECK_INTERVAL=${CHECK_INTERVAL:-5}

ensure_permissions() {
    chmod 777 /app/public 2>/dev/null || true
    chown -R application:application /app/public 2>/dev/null || true
}

write_hot_file() {
    local current
    current="$(cat "$HOT_FILE" 2>/dev/null || echo "")"

    # Не перезаписываем, если значение уже корректное
    if [[ "$current" == "$VITE_URL" ]]; then
        return
    fi

    printf '%s\n' "$VITE_URL" > "$HOT_FILE"
    chmod 666 "$HOT_FILE" 2>/dev/null || chmod 777 "$HOT_FILE" 2>/dev/null || true
    chown application:application "$HOT_FILE" 2>/dev/null || true
    echo "$(date): Updated $HOT_FILE to $VITE_URL"
}

remove_hot_file() {
    if [ -f "$HOT_FILE" ]; then
        rm -f "$HOT_FILE" 2>/dev/null || true
        echo "$(date): Removed $HOT_FILE because Vite dev server is unreachable"
    fi
}

is_vite_available() {
    # Проверяем, запущен ли процесс Vite
    pgrep -f "vite" >/dev/null 2>&1 || \
    curl -sf --max-time 1 --connect-timeout 1 "$PING_URL" >/dev/null 2>&1
}

ensure_permissions

while true; do
    if is_vite_available; then
        write_hot_file
    else
        remove_hot_file
    fi
    sleep "$CHECK_INTERVAL"
done
