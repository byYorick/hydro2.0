#!/usr/bin/env bash
# Проверка готовности к запуску backend/docker-compose.prod.yml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env.prod"
COMPOSE_FILE="${BACKEND_DIR}/docker-compose.prod.yml"
DOCKER_COMPOSE="${DOCKER_COMPOSE:-$(command -v docker-compose >/dev/null 2>&1 && echo docker-compose || echo "docker compose")}"

errors=0

fail() {
    echo "✗ $1" >&2
    errors=$((errors + 1))
}

ok() {
    echo "✓ $1"
}

require_file() {
    local path="$1"
    local label="$2"
    if [ ! -f "${path}" ]; then
        fail "${label} не найден: ${path}"
        return 1
    fi
    ok "${label}"
}

require_file "${ENV_FILE}" "backend/.env.prod"
# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

required_vars=(
    PUBLIC_HOST
    APP_URL
    APP_KEY
    POSTGRES_PASSWORD
    REDIS_PASSWORD
    REVERB_APP_KEY
    REVERB_APP_SECRET
    REVERB_ALLOWED_ORIGINS
    SANCTUM_STATEFUL_DOMAINS
    PY_API_TOKEN
    PY_INGEST_TOKEN
    LARAVEL_API_TOKEN
    HISTORY_LOGGER_AE_TOKEN
    MQTT_MQTT_BRIDGE_PASS
    MQTT_AUTOMATION_ENGINE_PASS
    MQTT_HISTORY_LOGGER_PASS
    MQTT_ESP32_NODE_PASS
    NODE_SECRET_WRAP_PASSPHRASE
    GRAFANA_ADMIN_PASSWORD
    ALERTMANAGER_WEBHOOK_SECRET
)

for var in "${required_vars[@]}"; do
    value="${!var:-}"
    if [ -z "${value}" ]; then
        fail "Пустая переменная: ${var}"
        continue
    fi
    case "${value}" in
        your-server.example.com|change-me|*example.com*)
            if [ "${var}" != "REVERB_APP_ID" ]; then
                fail "${var} содержит placeholder — задайте реальное значение"
            fi
            ;;
        esp32_pass|logger_pass|bridge_pass|automation_pass|python_service_pass)
            fail "${var} использует публичный dev-пароль"
            ;;
        admin)
            if [ "${var}" = "GRAFANA_ADMIN_PASSWORD" ]; then
                fail "GRAFANA_ADMIN_PASSWORD не может быть admin"
            fi
            ;;
    esac
done

if [ -n "${HISTORY_LOGGER_AE_TOKEN:-}" ]; then
    if [ "${HISTORY_LOGGER_AE_TOKEN}" = "${HISTORY_LOGGER_API_TOKEN:-}" ] || [ "${HISTORY_LOGGER_AE_TOKEN}" = "${PY_INGEST_TOKEN:-}" ]; then
        fail "HISTORY_LOGGER_AE_TOKEN должен отличаться от HISTORY_LOGGER_API_TOKEN и PY_INGEST_TOKEN"
    fi
fi

if [ "${errors}" -eq 0 ]; then
    ok "Обязательные переменные заданы"
fi

echo ""
echo "Проверка Alertmanager config (без placeholder SMTP/Telegram)..."
am_config="${BACKEND_DIR}/configs/prod/alertmanager/config.yml"
if grep -qE 'smtp_smarthost|telegram_configs|email_configs' "${am_config}"; then
    fail "prod alertmanager/config.yml содержит placeholder SMTP/Telegram/email receivers"
else
    ok "Alertmanager: доставка только через Laravel webhook"
fi

if ! grep -q 'credentials_file: /alertmanager/webhook_token' "${am_config}"; then
    fail "prod alertmanager/config.yml не содержит bearer credentials_file"
else
    ok "Alertmanager webhook bearer credentials_file настроен"
fi

echo ""
echo "Проверка mounts и project name в production Compose..."
if ! ${DOCKER_COMPOSE} --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --format json | python3 -c '
import json, sys
from pathlib import Path
config = json.load(sys.stdin)
if config["name"] != "hydro-prod":
    sys.exit("Неверное имя Compose-проекта")
def mount(service, target):
    return next(v for v in config["services"][service]["volumes"] if v["target"] == target)
if mount("laravel", "/backups")["source"] != "backups_data":
    sys.exit("Отсутствует том backups_data")
for service, target in [("mqtt", "/mosquitto/config/passwords"), ("mqtt", "/mosquitto/config/acl"),
                        ("history-logger", "/run/secrets/mqtt_node_passwords.json")]:
    path = Path(mount(service, target)["source"])
    if not path.is_file() or not path.stat().st_size:
        sys.exit(f"Проверьте файл для {service} {target}")
if config["services"]["mqtt"]["environment"]["MQTT_PLAINTEXT_ENABLED"] == "0" or config["services"]["history-logger"]["environment"]["MQTT_TLS"] == "1":
    certs = Path(mount("mqtt", "/mosquitto/certs")["source"])
    for name in ("server.crt", "server.key", "ca.crt"):
        if not (certs / name).is_file():
            sys.exit(f"Отсутствует MQTT {name}")
'; then
    fail "Production Compose не прошёл проверку"
fi

echo ""
if [ "${errors}" -gt 0 ]; then
    echo "Проверка не пройдена: ${errors} проблем(ы)." >&2
    exit 1
fi

echo "Готово к production deploy."
