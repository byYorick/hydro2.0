#!/bin/sh
# Самоподписанный CA и серверный сертификат для Mosquitto TLS (listener 8883).
# Не коммитить ca.key / server.key / *.crt. Для публичного CA этот скрипт не нужен.
#
# Usage:
#   ./generate_mqtt_certs.sh [output_dir]
# Env:
#   MQTT_CERT_CN   CN сертификата (по умолчанию mqtt.hydro.local)
#   MQTT_CERT_SAN  доп. SAN через запятую, например DNS:mqtt,IP:192.168.1.10
#   MQTT_CERT_DAYS срок, по умолчанию 825
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
OUT=${1:-"$SCRIPT_DIR/certs"}
CN=${MQTT_CERT_CN:-mqtt.hydro.local}
DAYS=${MQTT_CERT_DAYS:-825}
EXTRA_SAN=${MQTT_CERT_SAN:-}

if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl не найден" >&2
    exit 1
fi

mkdir -p "$OUT"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

SAN="DNS:${CN},DNS:localhost,IP:127.0.0.1"
if [ -n "$EXTRA_SAN" ]; then
    SAN="${SAN},${EXTRA_SAN}"
fi

cat > "$TMP" << EOF
[req]
distinguished_name = dn
x509_extensions = v3_req
prompt = no
[dn]
CN = ${CN}
[v3_req]
subjectAltName = ${SAN}
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF

openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$OUT/ca.key" -out "$OUT/ca.crt" \
    -days "$DAYS" -subj "/CN=hydro-mqtt-ca"

openssl req -newkey rsa:2048 -nodes \
    -keyout "$OUT/server.key" -out "$OUT/server.csr" \
    -subj "/CN=${CN}"

openssl x509 -req -in "$OUT/server.csr" \
    -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
    -out "$OUT/server.crt" -days "$DAYS" \
    -extfile "$TMP" -extensions v3_req

rm -f "$OUT/server.csr" "$OUT/ca.srl"
chmod 600 "$OUT/ca.key" "$OUT/server.key"

echo "Сертификаты: $OUT"
echo "  ca.crt, ca.key, server.crt, server.key"
echo "Смонтируйте каталог в брокер как /mosquitto/certs (entrypoint поднимет listener 8883)."
echo "Клиентам: MQTT_TLS=1 MQTT_PORT=8883 MQTT_CA_FILE=/etc/mqtt/certs/ca.crt"
echo "Прошивка: скопируйте ca.crt в firmware/nodes/common/components/mqtt_manager/ca.pem и пересоберите узлы с mqtt.use_tls=true и port=8883."
echo "После перевода клиентов: MQTT_PLAINTEXT_ENABLED=0"
