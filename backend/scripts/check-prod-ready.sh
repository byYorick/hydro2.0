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

if ! command -v docker >/dev/null 2>&1; then
    fail "docker не установлен"
else
    ok "docker доступен"
fi

echo ""
echo "Проверка docker compose config..."
if ${DOCKER_COMPOSE} --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config >/dev/null 2>&1; then
    ok "docker compose config валиден"
else
    fail "docker compose config — ошибка (см. вывод ниже)"
    ${DOCKER_COMPOSE} --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config 2>&1 | tail -20 >&2 || true
fi

echo ""
if [ "${errors}" -gt 0 ]; then
    echo "Проверка не пройдена: ${errors} проблем(ы)." >&2
    exit 1
fi

echo "Готово к production deploy."
