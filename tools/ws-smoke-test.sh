#!/bin/bash

# WebSocket Smoke Test для проверки доступности Reverb сервера
# Использование: ./tools/ws-smoke-test.sh [host] [port]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Параметры по умолчанию
HOST="${1:-localhost}"
PORT="${2:-6001}"
SCHEME="${3:-ws}"

echo -e "${BLUE}=== WebSocket Smoke Test для Reverb ===${NC}"
echo -e "Host: ${HOST}"
echo -e "Port: ${PORT}"
echo -e "Scheme: ${SCHEME}"
echo ""

# Проверка доступности порта
echo -e "${YELLOW}1. Проверка доступности порта ${PORT}...${NC}"
if command -v nc >/dev/null 2>&1; then
    if nc -z "${HOST}" "${PORT}" 2>/dev/null; then
        echo -e "${GREEN}✓ Порт ${PORT} доступен${NC}"
    else
        echo -e "${RED}✗ Порт ${PORT} недоступен${NC}"
        echo -e "${YELLOW}Убедитесь, что Reverb запущен: php artisan reverb:start${NC}"
        exit 1
    fi
elif command -v timeout >/dev/null 2>&1; then
    if timeout 1 bash -c "echo > /dev/tcp/${HOST}/${PORT}" 2>/dev/null; then
        echo -e "${GREEN}✓ Порт ${PORT} доступен${NC}"
    else
        echo -e "${RED}✗ Порт ${PORT} недоступен${NC}"
        echo -e "${YELLOW}Убедитесь, что Reverb запущен: php artisan reverb:start${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ Не удалось проверить порт (nc или timeout не найдены)${NC}"
fi

# Проверка HTTP endpoint (если доступен)
echo ""
echo -e "${YELLOW}2. Проверка HTTP endpoint...${NC}"
HTTP_URL="http://${HOST}:${PORT}"
if command -v curl >/dev/null 2>&1; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "${HTTP_URL}" || echo "000")
    if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "400" ] || [ "${HTTP_CODE}" = "426" ]; then
        echo -e "${GREEN}✓ HTTP endpoint отвечает (код: ${HTTP_CODE})${NC}"
    else
        echo -e "${YELLOW}⚠ HTTP endpoint вернул код: ${HTTP_CODE}${NC}"
    fi
else
    echo -e "${YELLOW}⚠ curl не найден, пропускаем проверку HTTP${NC}"
fi

# Проверка WebSocket через wscat (если установлен)
echo ""
echo -e "${YELLOW}3. Проверка WebSocket соединения...${NC}"
if command -v wscat >/dev/null 2>&1; then
    WS_URL="${SCHEME}://${HOST}:${PORT}/app/test-key"
    echo -e "Попытка подключения к: ${WS_URL}"
    
    # Пытаемся подключиться с таймаутом
    timeout 3 wscat -c "${WS_URL}" 2>&1 | head -5 || {
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 124 ]; then
            echo -e "${YELLOW}⚠ Таймаут подключения (это может быть нормально, если требуется авторизация)${NC}"
        elif [ $EXIT_CODE -eq 1 ]; then
            echo -e "${YELLOW}⚠ Ошибка подключения (возможно, требуется авторизация или правильный app key)${NC}"
        else
            echo -e "${RED}✗ Ошибка подключения (код: ${EXIT_CODE})${NC}"
        fi
    }
else
    echo -e "${YELLOW}⚠ wscat не установлен${NC}"
    echo -e "  Установите: npm install -g wscat"
    echo -e "  Или используйте curl для проверки WebSocket:"
    echo -e "  curl --include \\"
    echo -e "    --no-buffer \\"
    echo -e "    --header \"Connection: Upgrade\" \\"
    echo -e "    --header \"Upgrade: websocket\" \\"
    echo -e "    --header \"Sec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==\" \\"
    echo -e "    --header \"Sec-WebSocket-Version: 13\" \\"
    echo -e "    ${SCHEME}://${HOST}:${PORT}/app/test-key"
fi

# Проверка переменных окружения
echo ""
echo -e "${YELLOW}4. Проверка переменных окружения...${NC}"
if [ -f ".env" ]; then
    if grep -q "REVERB_APP_KEY" .env 2>/dev/null; then
        REVERB_KEY=$(grep "REVERB_APP_KEY" .env | cut -d '=' -f2 | tr -d ' ' | head -1)
        if [ -n "${REVERB_KEY}" ]; then
            echo -e "${GREEN}✓ REVERB_APP_KEY найден в .env${NC}"
        else
            echo -e "${RED}✗ REVERB_APP_KEY пустой в .env${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ REVERB_APP_KEY не найден в .env${NC}"
    fi
    
    if grep -q "REVERB_PORT" .env 2>/dev/null; then
        REVERB_PORT=$(grep "REVERB_PORT" .env | cut -d '=' -f2 | tr -d ' ' | head -1)
        if [ -n "${REVERB_PORT}" ]; then
            echo -e "${GREEN}✓ REVERB_PORT найден в .env: ${REVERB_PORT}${NC}"
            if [ "${REVERB_PORT}" != "${PORT}" ]; then
                echo -e "${YELLOW}⚠ Порт в .env (${REVERB_PORT}) отличается от проверяемого (${PORT})${NC}"
            fi
        fi
    else
        echo -e "${YELLOW}⚠ REVERB_PORT не найден в .env (используется значение по умолчанию: 6001)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Файл .env не найден${NC}"
fi

# Проверка процессов Reverb
echo ""
echo -e "${YELLOW}5. Проверка процессов Reverb...${NC}"
if pgrep -f "reverb" > /dev/null; then
    REVERB_PID=$(pgrep -f "reverb" | head -1)
    echo -e "${GREEN}✓ Процесс Reverb найден (PID: ${REVERB_PID})${NC}"
    ps -p "${REVERB_PID}" -o pid,cmd --no-headers 2>/dev/null || true
else
    echo -e "${RED}✗ Процесс Reverb не найден${NC}"
    echo -e "${YELLOW}Запустите Reverb: php artisan reverb:start${NC}"
fi

# Итоговый результат
echo ""
echo -e "${BLUE}=== Результаты проверки ===${NC}"
echo -e "Если все проверки пройдены успешно, Reverb должен быть доступен."
echo -e "Для детальной диагностики проверьте логи:"
echo -e "  - Laravel: tail -f storage/logs/laravel.log | grep reverb"
echo -e "  - Browser console: фильтр [echoClient] или [WebSocket]"
echo ""

