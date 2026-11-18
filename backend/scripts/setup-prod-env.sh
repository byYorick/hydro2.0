#!/usr/bin/env bash
# Генерирует backend/.env.prod и MQTT passwords.txt для production compose.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env.prod"
FORCE=0
PUBLIC_HOST="${PUBLIC_HOST:-}"
INVENTORY=""

usage() {
    cat <<'EOF'
Usage: setup-prod-env.sh [--force] [--host HOST] [--inventory FILE]

  --force       перезаписать существующий backend/.env.prod
  --host HOST   PUBLIC_HOST (домен или IP без схемы)
  --inventory FILE   JSON со списком username, node_uid и hardware_id (по умолчанию только сервисы)

Переменные окружения (опционально):
  PUBLIC_SCHEME, APP_URL, PUBLIC_WS_PORT, PUBLIC_WS_TLS

После генерации отредактируйте REVERB_ALLOWED_ORIGINS и SANCTUM_STATEFUL_DOMAINS под ваш домен.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        --inventory) INVENTORY="${2:?укажите inventory JSON}"; shift 2 ;;
        --host)
            PUBLIC_HOST="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Неизвестный аргумент: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ -f "${ENV_FILE}" ] && [ "${FORCE}" != "1" ]; then
    echo "Файл ${ENV_FILE} уже существует. Используйте --force для перезаписи." >&2
    exit 1
fi

rand_hex() {
    openssl rand -hex 32
}

rand_token() {
    openssl rand -hex 24
}

if [ -z "${PUBLIC_HOST}" ]; then
    read -r -p "PUBLIC_HOST (домен или IP сервера): " PUBLIC_HOST
fi

if [ -z "${PUBLIC_HOST}" ]; then
    echo "PUBLIC_HOST обязателен." >&2
    exit 1
fi

if [[ "${PUBLIC_HOST}" =~ ^[0-9.]+$ ]] || [ "${PUBLIC_HOST}" = "localhost" ]; then
    PUBLIC_SCHEME="${PUBLIC_SCHEME:-http}"
else
    PUBLIC_SCHEME="${PUBLIC_SCHEME:-https}"
fi

PUBLIC_WS_PORT="${PUBLIC_WS_PORT:-6001}"
if [ "${PUBLIC_SCHEME}" = "https" ]; then
    PUBLIC_WS_TLS="${PUBLIC_WS_TLS:-true}"
    DEFAULT_APP_URL="https://${PUBLIC_HOST}"
else
    PUBLIC_WS_TLS="${PUBLIC_WS_TLS:-false}"
    DEFAULT_APP_URL="http://${PUBLIC_HOST}:8080"
fi

APP_URL="${APP_URL:-${DEFAULT_APP_URL}}"

POSTGRES_PASSWORD="$(rand_hex)"
REDIS_PASSWORD="$(rand_hex)"
REVERB_APP_KEY="$(rand_hex)"
REVERB_APP_SECRET="$(rand_hex)"
APP_KEY="base64:$(openssl rand -base64 32)"
PY_API_TOKEN="$(rand_token)"
PY_INGEST_TOKEN="$(rand_token)"
LARAVEL_API_TOKEN="$(rand_token)"
HISTORY_LOGGER_API_TOKEN="${PY_INGEST_TOKEN}"
HISTORY_LOGGER_AE_TOKEN="$(rand_token)"
MQTT_MQTT_BRIDGE_PASS="$(rand_hex)"
MQTT_AUTOMATION_ENGINE_PASS="$(rand_hex)"
MQTT_HISTORY_LOGGER_PASS="$(rand_hex)"
MQTT_ESP32_NODE_PASS="$(rand_hex)"
# Совпадает с mqtt.password узла: history-logger шифрует им node_secret_enc.
NODE_SECRET_WRAP_PASSPHRASE="${MQTT_ESP32_NODE_PASS}"
GRAFANA_ADMIN_PASSWORD="$(rand_hex)"
ALERTMANAGER_WEBHOOK_SECRET="$(rand_hex)"

REVERB_ALLOWED_ORIGINS="${APP_URL}"
SANCTUM_STATEFUL_DOMAINS="${PUBLIC_HOST}"

staging=$(mktemp -d "${BACKEND_DIR}/.prod-setup-XXXXXXXX")
trap 'rm -rf "$staging"' EXIT
if [ -z "$INVENTORY" ]; then
    INVENTORY="$staging/inventory.json"
    echo '[]' > "$INVENTORY"
fi
bundle_parent="${BACKEND_DIR}/.mqtt-bundles"
bundle_name="credentials-${staging##*.prod-setup-}"
printf '{"history_logger":"%s","mqtt_bridge":"%s"}\n' \
    "$MQTT_HISTORY_LOGGER_PASS" "$MQTT_MQTT_BRIDGE_PASS" > "$staging/services.json"
python3 "${BACKEND_DIR}/../tools/mqtt/prepare_node_credentials.py" \
    "$INVENTORY" "$staging/services.json" "$bundle_parent/$bundle_name"
# Mosquitto reads the bind-mounted ACL after dropping privileges.
chmod 644 "$bundle_parent/$bundle_name/production.acl"

cat > "$staging/env" <<EOF
# Сгенерировано backend/scripts/setup-prod-env.sh — $(date -Iseconds)
# Не коммитьте этот файл.

PUBLIC_HOST=${PUBLIC_HOST}
APP_URL=${APP_URL}
PUBLIC_SCHEME=${PUBLIC_SCHEME}
PUBLIC_WS_PORT=${PUBLIC_WS_PORT}
PUBLIC_WS_TLS=${PUBLIC_WS_TLS}

APP_KEY=${APP_KEY}

REVERB_APP_ID=app
REVERB_APP_KEY=${REVERB_APP_KEY}
REVERB_APP_SECRET=${REVERB_APP_SECRET}
REVERB_AUTO_START=true
REVERB_ALLOWED_ORIGINS=${REVERB_ALLOWED_ORIGINS}
SANCTUM_STATEFUL_DOMAINS=${SANCTUM_STATEFUL_DOMAINS}
SESSION_DOMAIN=
SESSION_SECURE_COOKIE=$([ "${PUBLIC_SCHEME}" = "https" ] && echo true || echo false)

POSTGRES_USER=hydro
POSTGRES_DB=hydro
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}

PY_API_TOKEN=${PY_API_TOKEN}
PY_INGEST_TOKEN=${PY_INGEST_TOKEN}
LARAVEL_API_TOKEN=${LARAVEL_API_TOKEN}
HISTORY_LOGGER_API_TOKEN=${HISTORY_LOGGER_API_TOKEN}
HISTORY_LOGGER_AE_TOKEN=${HISTORY_LOGGER_AE_TOKEN}

MQTT_PRODUCTION_PASSWORD_FILE=./.mqtt-bundles/${bundle_name}/passwords
MQTT_PRODUCTION_ACL_FILE=./.mqtt-bundles/${bundle_name}/production.acl
MQTT_NODE_PASSWORDS_FILE=./.mqtt-bundles/${bundle_name}/node_passwords.json
MQTT_TLS=1
MQTT_PORT=8883
MQTT_PLAINTEXT_ENABLED=0
MQTT_MQTT_BRIDGE_PASS=${MQTT_MQTT_BRIDGE_PASS}
MQTT_AUTOMATION_ENGINE_PASS=${MQTT_AUTOMATION_ENGINE_PASS}
MQTT_HISTORY_LOGGER_PASS=${MQTT_HISTORY_LOGGER_PASS}
MQTT_ESP32_NODE_PASS=${MQTT_ESP32_NODE_PASS}
NODE_SECRET_WRAP_PASSPHRASE=${NODE_SECRET_WRAP_PASSPHRASE}

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
ALERTMANAGER_WEBHOOK_SECRET=${ALERTMANAGER_WEBHOOK_SECRET}
EOF

mv "$staging/env" "${ENV_FILE}"
echo "Записано ${ENV_FILE} и MQTT bundle ${bundle_name}."
echo "Production env готов. Дальше:"
echo "  1. Проверьте домены в ${ENV_FILE} (REVERB_ALLOWED_ORIGINS, SANCTUM_STATEFUL_DOMAINS)"
echo "  2. make prod-check"
echo "  3. make prod-up"
echo "  4. make prod-migrate"
echo "  5. make prod-seed   # первый админ (StartUsersSeeder)"
echo ""
echo "До prod-check подготовьте CA и сертификат брокера с SAN для mqtt и адреса устройств."
echo "Индивидуальные MQTT credentials узлов находятся в закрытом файле ${bundle_parent}/${bundle_name}/node_credentials.json."
