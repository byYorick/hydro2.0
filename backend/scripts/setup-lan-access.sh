#!/usr/bin/env bash
# Определяет LAN IP и пишет backend/.env для доступа к dev-стеку из локальной сети.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${BACKEND_DIR}/.env"

detect_lan_host() {
    if [ -n "${LAN_HOST:-}" ]; then
        echo "${LAN_HOST}"
        return
    fi
    ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") print $(i + 1)}' | head -1
}

LAN_IP="$(detect_lan_host)"
if [ -z "${LAN_IP}" ]; then
    echo "Не удалось определить LAN IP. Задайте LAN_HOST=... вручную." >&2
    exit 1
fi

APP_URL="http://${LAN_IP}:8080"

cat > "${ENV_FILE}" <<EOF
# Сгенерировано backend/scripts/setup-lan-access.sh — доступ к dev из LAN
LAN_HOST=${LAN_IP}
APP_URL=${APP_URL}
VITE_DEV_SERVER_URL=${APP_URL}
EOF

echo "Записано ${ENV_FILE}:"
cat "${ENV_FILE}"
echo ""
echo "Откройте в браузере на любом устройстве в сети: ${APP_URL}"
echo "Перезапустите стек: make up  (или docker compose -f backend/docker-compose.dev.yml up -d --force-recreate laravel)"
