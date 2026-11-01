#!/bin/sh
# Готовит runtime-конфиг Mosquitto: пароли из файла или из env, опциональный TLS.
# Базовый конфиг монтируется в /mosquitto/config/mosquitto.conf (dev или prod).
set -eu

BASE_CONF=/mosquitto/config/mosquitto.conf
RUNTIME_CONF=/tmp/mosquitto.conf
MOUNTED_PASS=/mosquitto/config/passwords
GENERATED_PASS=/tmp/mosquitto.passwords

if [ ! -f "$BASE_CONF" ]; then
    echo "mosquitto-entrypoint: missing $BASE_CONF" >&2
    exit 1
fi

cp "$BASE_CONF" "$RUNTIME_CONF"

use_mounted_pass=0
if [ -f "$MOUNTED_PASS" ] && [ ! -d "$MOUNTED_PASS" ] && [ -s "$MOUNTED_PASS" ]; then
    use_mounted_pass=1
fi

if [ "$use_mounted_pass" -eq 1 ]; then
    PASSFILE=$MOUNTED_PASS
else
    echo "mosquitto-entrypoint: passwords file missing, generating from MQTT_*_PASS env" >&2
    rm -f "$GENERATED_PASS"
    mosquitto_passwd -b -c "$GENERATED_PASS" python_service "${MQTT_PYTHON_SERVICE_PASS:-python_service_pass}"
    mosquitto_passwd -b "$GENERATED_PASS" automation_engine "${MQTT_AUTOMATION_ENGINE_PASS:-automation_pass}"
    mosquitto_passwd -b "$GENERATED_PASS" history_logger "${MQTT_HISTORY_LOGGER_PASS:-logger_pass}"
    mosquitto_passwd -b "$GENERATED_PASS" mqtt_bridge "${MQTT_MQTT_BRIDGE_PASS:-bridge_pass}"
    mosquitto_passwd -b "$GENERATED_PASS" esp32_node "${MQTT_ESP32_NODE_PASS:-esp32_pass}"
    chmod 600 "$GENERATED_PASS"
    PASSFILE=$GENERATED_PASS
fi

# password_file в базовом конфиге может указывать на ещё не созданный файл.
sed -i "s|^password_file .*|password_file ${PASSFILE}|" "$RUNTIME_CONF"

if [ "${MQTT_PLAINTEXT_ENABLED:-1}" = "0" ]; then
    sed -i '/^listener 1883$/d' "$RUNTIME_CONF"
fi

CERT=/mosquitto/certs/server.crt
KEY=/mosquitto/certs/server.key
if [ -f "$CERT" ] && [ -f "$KEY" ]; then
    {
        echo ""
        echo "# TLS listener (сертификаты смонтированы в /mosquitto/certs)"
        echo "listener 8883"
        echo "certfile ${CERT}"
        echo "keyfile ${KEY}"
        if [ -f /mosquitto/certs/ca.crt ]; then
            echo "cafile /mosquitto/certs/ca.crt"
        fi
        echo "require_certificate false"
        echo "tls_version tlsv1.2"
    } >> "$RUNTIME_CONF"
    echo "mosquitto-entrypoint: TLS listener 8883 enabled" >&2
fi

if ! grep -q '^listener ' "$RUNTIME_CONF"; then
    echo "mosquitto-entrypoint: no listeners configured (plaintext disabled and TLS certs missing)" >&2
    exit 1
fi

exec mosquitto -c "$RUNTIME_CONF"
