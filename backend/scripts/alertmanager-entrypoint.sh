#!/bin/sh
# Записывает bearer token для webhook → Laravel до старта Alertmanager.
set -eu

TOKEN_FILE=/alertmanager/webhook_token

if [ -n "${ALERTMANAGER_WEBHOOK_SECRET:-}" ]; then
    umask 077
    printf '%s' "${ALERTMANAGER_WEBHOOK_SECRET}" > "${TOKEN_FILE}"
else
    echo "warning: ALERTMANAGER_WEBHOOK_SECRET is empty; webhook bearer file not written" >&2
fi

exec /bin/alertmanager "$@"
