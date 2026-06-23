#!/usr/bin/env bash
# Стресс-тест test_node: UART-монитор + MQTT-бомбардировка.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="${STRESS_SERIAL_PORT:-/dev/ttyACM0}"
DURATION="${STRESS_DURATION:-120}"
WORKERS="${STRESS_WORKERS:-6}"
RATE="${STRESS_RATE:-30}"
MQTT_HOST="${STRESS_MQTT_HOST:-localhost}"
MQTT_PORT="${STRESS_MQTT_PORT:-1883}"
SERIAL_LOG="/tmp/test_node_stress_serial.log"
STRESS_LOG="/tmp/test_node_stress_mqtt.log"

echo "=== test_node stress run ==="
echo "serial=$PORT duration=${DURATION}s workers=$WORKERS rate=$RATE/s mqtt=$MQTT_HOST:$MQTT_PORT"

python3 "$ROOT/firmware/tests/stress_test_node_serial_watch.py" \
  --port "$PORT" \
  --duration "$((DURATION + 15))" \
  --log-file "$SERIAL_LOG" \
  > >(tee -a "$SERIAL_LOG.watch") 2>&1 &
WATCH_PID=$!

sleep 2

set +e
python3 "$ROOT/firmware/tests/stress_test_node_bombard.py" \
  --mqtt-host "$MQTT_HOST" \
  --mqtt-port "$MQTT_PORT" \
  --duration "$DURATION" \
  --workers "$WORKERS" \
  --rate "$RATE" \
  2>&1 | tee "$STRESS_LOG"
STRESS_RC=${PIPESTATUS[0]}
set -e

echo "Waiting for serial watcher (pid=$WATCH_PID)..."
wait "$WATCH_PID" || WATCH_RC=$?
WATCH_RC=${WATCH_RC:-0}

echo ""
echo "=== RESULT ==="
echo "mqtt stress exit: $STRESS_RC"
echo "serial watch exit: $WATCH_RC"
echo "logs: $SERIAL_LOG , $STRESS_LOG"

if [[ "$WATCH_RC" -ne 0 ]]; then
  echo "FAIL: crash/reboot detected on UART"
  exit 1
fi
if [[ "$STRESS_RC" -ne 0 ]]; then
  echo "FAIL: MQTT stress script error"
  exit "$STRESS_RC"
fi

echo "PASS: no UART crash signals during stress"
exit 0
