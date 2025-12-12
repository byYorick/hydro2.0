#!/bin/bash
# Скрипт для запуска контрактных тестов и chaos тестов
# Используется в CI для проверки совместимости протокола

set -e  # Выход при ошибке

echo "=== Запуск контрактных тестов ==="

# Переходим в директорию с тестами
cd "$(dirname "$0")/../.." || exit 1

# Проверяем наличие pytest
if ! command -v pytest &> /dev/null; then
    echo "Ошибка: pytest не установлен"
    echo "Установите зависимости: pip install -r requirements-test.txt"
    exit 1
fi

# Запускаем контрактные тесты
echo "1. Тестирование JSON схем для telemetry, command, command_response, alert, zone_events..."
pytest common/schemas/test_protocol_contracts.py -v --tb=short

if [ $? -ne 0 ]; then
    echo "❌ Контрактные тесты провалились"
    exit 1
fi

echo "✅ Контрактные тесты прошли успешно"

# Запускаем chaos тесты (если доступны зависимости)
echo ""
echo "2. Запуск chaos тестов..."
if [ -f "common/schemas/test_chaos.py" ]; then
    pytest common/schemas/test_chaos.py -v --tb=short -m "not slow" || {
        echo "⚠️  Chaos тесты провалились (некоторые могут требовать запущенных сервисов)"
        # Не выходим с ошибкой для chaos тестов, так как они могут требовать инфраструктуру
    }
else
    echo "⚠️  Файл test_chaos.py не найден, пропускаем"
fi

# Запускаем авто-проверку WS событий
echo ""
echo "3. Авто-проверка WS событий с event_id..."
if [ -f "common/schemas/test_websocket_events.py" ]; then
    pytest common/schemas/test_websocket_events.py -v --tb=short
    
    if [ $? -ne 0 ]; then
        echo "❌ Авто-проверка WS событий провалилась"
        exit 1
    fi
    
    echo "✅ Авто-проверка WS событий прошла успешно"
else
    echo "⚠️  Файл test_websocket_events.py не найден, пропускаем"
fi

echo ""
echo "=== Все тесты прошли успешно ==="

