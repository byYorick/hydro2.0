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
RUN_HIL_TIMING="${RUN_HIL_TIMING:-0}"
HIL_CHANNEL="${HIL_CHANNEL:-ph_sensor}"
HIL_CMD="${HIL_CMD:-set_relay}"
HIL_SIM_DELAY_MS="${HIL_SIM_DELAY_MS:-1200}"
HIL_SIM_STATUS="${HIL_SIM_STATUS:-DONE}"

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
echo "  RUN_HIL_TIMING: $RUN_HIL_TIMING"
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

if [ "$RUN_HIL_TIMING" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: ACK -> terminal timing"
    echo "=========================================="
    python3 firmware/tests/test_command_ack_terminal_timing.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID" \
        --channel "$HIL_CHANNEL" \
        --cmd "$HIL_CMD" \
        --sim-delay-ms "$HIL_SIM_DELAY_MS" \
        --sim-status "$HIL_SIM_STATUS"
fi

exit $?
