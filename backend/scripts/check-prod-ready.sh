#!/usr/bin/env bash
# Проверка готовности к запуску backend/docker-compose.prod.yml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env.prod"
COMPOSE_FILE="${BACKEND_DIR}/docker-compose.prod.yml"
PASSWORDS_FILE="${BACKEND_DIR}/services/mqtt-bridge/passwords.txt"
ACL_FILE="${BACKEND_DIR}/services/mqtt-bridge/acl"

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
require_file "${PASSWORDS_FILE}" "MQTT passwords.txt"
require_file "${ACL_FILE}" "MQTT acl"

if [ -d "${PASSWORDS_FILE}" ]; then
    fail "passwords.txt — каталог, а не файл. Удалите: rm -rf ${PASSWORDS_FILE} && make prod-setup"
fi

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
    MQTT_MQTT_BRIDGE_PASS
    MQTT_AUTOMATION_ENGINE_PASS
    MQTT_HISTORY_LOGGER_PASS
    MQTT_ESP32_NODE_PASS
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
    esac
done

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
echo "Проверка volume backups_data в compose..."
if ${DOCKER_COMPOSE} --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config 2>/dev/null | grep -q 'backups_data:/backups'; then
    ok "laravel монтирует backups_data:/backups"
else
    fail "laravel не монтирует backups_data:/backups"
fi

if ! command -v docker >/dev/null 2>&1; then
    fail "docker не установлен"
else
    ok "docker доступен"
fi

echo ""
echo "Проверка docker compose config..."
COMPOSE_CONFIG_OUT="$(mktemp)"
if ${DOCKER_COMPOSE} --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config >"${COMPOSE_CONFIG_OUT}" 2>/tmp/hydro-prod-compose-err; then
    ok "docker compose config валиден"
    if grep -qE '^name:[[:space:]]*hydro-prod[[:space:]]*$' "${COMPOSE_CONFIG_OUT}"; then
        ok "compose project name = hydro-prod (изолирован от dev)"
    else
        fail "ожидался project name hydro-prod в docker-compose.prod.yml"
    fi
else
    fail "docker compose config — ошибка (см. вывод ниже)"
    tail -20 /tmp/hydro-prod-compose-err >&2 || true
fi
rm -f "${COMPOSE_CONFIG_OUT}"

echo ""
if [ "${errors}" -gt 0 ]; then
    echo "Проверка не пройдена: ${errors} проблем(ы)." >&2
    exit 1
fi

echo "Готово к production deploy."
