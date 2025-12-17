#!/bin/bash
# Скрипт для запуска тестов совместимости

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Параметры по умолчанию
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1884}"
GH_UID="${GH_UID:-gh-test-1}"
ZONE_UID="${ZONE_UID:-zn-test-1}"
NODE_UID="${NODE_UID:-nd-test-001}"

echo "=========================================="
echo "Тестирование совместимости с эталоном node-sim"
echo "=========================================="
echo ""
echo "Параметры:"
echo "  MQTT Host: $MQTT_HOST"
echo "  MQTT Port: $MQTT_PORT"
echo "  GH UID: $GH_UID"
echo "  Zone UID: $ZONE_UID"
echo "  Node UID: $NODE_UID"
echo ""

# Проверка зависимостей
echo "Проверка зависимостей..."
MISSING_DEPS=0

if ! python3 -c "import paho.mqtt.client" 2>/dev/null; then
    echo "  ❌ paho-mqtt не установлен"
    MISSING_DEPS=1
else
    echo "  ✅ paho-mqtt установлен"
fi

if ! python3 -c "import jsonschema" 2>/dev/null; then
    echo "  ❌ jsonschema не установлен"
    MISSING_DEPS=1
else
    echo "  ✅ jsonschema установлен"
fi

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "Установка зависимостей..."
    pip3 install paho-mqtt jsonschema
    echo ""
fi

# Запуск тестов
cd "$ROOT_DIR"
python3 firmware/tests/test_node_compatibility.py \
    --mqtt-host "$MQTT_HOST" \
    --mqtt-port "$MQTT_PORT" \
    --gh-uid "$GH_UID" \
    --zone-uid "$ZONE_UID" \
    --node-uid "$NODE_UID"

exit $?

