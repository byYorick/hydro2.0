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
NODE_UID="${NODE_UID:-nd-irrig-1}"
RUN_HIL_TIMING="${RUN_HIL_TIMING:-0}"
RUN_HIL_STORAGE_STATE="${RUN_HIL_STORAGE_STATE:-0}"
RUN_HIL_INTERLOCK="${RUN_HIL_INTERLOCK:-0}"
RUN_HIL_COOLDOWN="${RUN_HIL_COOLDOWN:-0}"
RUN_HIL_MAX_DURATION="${RUN_HIL_MAX_DURATION:-0}"
RUN_HIL_STORAGE_EVENTS="${RUN_HIL_STORAGE_EVENTS:-0}"
RUN_HIL_STAGE_TIMEOUT="${RUN_HIL_STAGE_TIMEOUT:-0}"
HIL_CHANNEL="${HIL_CHANNEL:-valve_clean_fill}"
HIL_DURATION_CHANNEL="${HIL_DURATION_CHANNEL:-valve_solution_supply}"
HIL_EVENT_CODE="${HIL_EVENT_CODE:-clean_fill_completed}"
HIL_STAGE="${HIL_STAGE:-solution_fill}"
HIL_STAGE_TIMEOUT_MS="${HIL_STAGE_TIMEOUT_MS:-5000}"
HIL_CMD="${HIL_CMD:-set_relay}"
HIL_PARAMS_JSON="${HIL_PARAMS_JSON:-{\"state\":true}}"

echo "=========================================="
echo "Тестирование совместимости production IRR node"
echo "=========================================="
echo ""
echo "Параметры:"
echo "  MQTT Host: $MQTT_HOST"
echo "  MQTT Port: $MQTT_PORT"
echo "  GH UID: $GH_UID"
echo "  Zone UID: $ZONE_UID"
echo "  Node UID: $NODE_UID"
echo "  RUN_HIL_TIMING: $RUN_HIL_TIMING"
echo "  RUN_HIL_STORAGE_STATE: $RUN_HIL_STORAGE_STATE"
echo "  RUN_HIL_INTERLOCK: $RUN_HIL_INTERLOCK"
echo "  RUN_HIL_COOLDOWN: $RUN_HIL_COOLDOWN"
echo "  RUN_HIL_MAX_DURATION: $RUN_HIL_MAX_DURATION"
echo "  RUN_HIL_STORAGE_EVENTS: $RUN_HIL_STORAGE_EVENTS"
echo "  RUN_HIL_STAGE_TIMEOUT: $RUN_HIL_STAGE_TIMEOUT"
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
        --params-json "$HIL_PARAMS_JSON"
fi

if [ "$RUN_HIL_STORAGE_STATE" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: storage_state/state contract"
    echo "=========================================="
    python3 firmware/tests/test_storage_state_contract.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID"
fi

if [ "$RUN_HIL_INTERLOCK" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: pump_main interlock"
    echo "=========================================="
    python3 firmware/tests/test_pump_main_interlock.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID"
fi

if [ "$RUN_HIL_COOLDOWN" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: actuator cooldown"
    echo "=========================================="
    python3 firmware/tests/test_actuator_cooldown.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID" \
        --channel "$HIL_CHANNEL"
fi

if [ "$RUN_HIL_MAX_DURATION" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: actuator max duration"
    echo "=========================================="
    python3 firmware/tests/test_actuator_max_duration.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID" \
        --channel "$HIL_DURATION_CHANNEL"
fi

if [ "$RUN_HIL_STORAGE_EVENTS" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: storage_state/event"
    echo "=========================================="
    python3 firmware/tests/test_storage_events.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID" \
        --event-code "$HIL_EVENT_CODE"
fi

if [ "$RUN_HIL_STAGE_TIMEOUT" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "HIL: stage timeout guard"
    echo "=========================================="
    python3 firmware/tests/test_stage_timeout_guard.py \
        --mqtt-host "$MQTT_HOST" \
        --mqtt-port "$MQTT_PORT" \
        --gh-uid "$GH_UID" \
        --zone-uid "$ZONE_UID" \
        --node-uid "$NODE_UID" \
        --stage "$HIL_STAGE" \
        --timeout-ms "$HIL_STAGE_TIMEOUT_MS"
fi

exit $?
