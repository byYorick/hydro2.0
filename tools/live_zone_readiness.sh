#!/usr/bin/env bash
# Проверка готовности живого контура pH/EC/полив (не замена 2–4 недель на железе).
set -euo pipefail

fail=0
ok() { printf 'OK  %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

check_http() {
  local name="$1" url="$2"
  if curl -sf --max-time 3 "$url" >/dev/null; then
    ok "$name $url"
  else
    bad "$name $url"
  fi
}

check_http "Laravel" "${LARAVEL_URL:-http://localhost:8080}/api/system/health"
check_http "history-logger" "${HISTORY_LOGGER_URL:-http://localhost:9300}/health/ready"
check_http "automation-engine" "${AUTOMATION_ENGINE_URL:-http://localhost:9405}/health/ready"

# ZONE_ID selects the pilot zone. Auto-select only when precisely one AE3 zone exists.
if result=$(PGPASSWORD="${PGPASSWORD:-hydro}" psql -X -w -Atq -v ON_ERROR_STOP=1 \
    -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:-hydro}" -d "${PGDATABASE:-hydro_dev}" \
    -v zone_id="${ZONE_ID:-}" <<'SQL'
WITH selected AS (
  SELECT id FROM zones WHERE automation_runtime = 'ae3'
    AND (NULLIF(:'zone_id', '') IS NULL OR id = NULLIF(:'zone_id', '')::bigint)
)
SELECT CASE
  WHEN (SELECT count(*) FROM selected) <> 1 THEN 'укажите ZONE_ID одной существующей AE3-зоны'
  WHEN count(s.id) = 0 THEN 'в зоне нет активных датчиков'
  WHEN count(s.id) FILTER (WHERE t.last_quality = 'GOOD' AND
    t.last_ts BETWEEN (now() AT TIME ZONE 'UTC') - interval '10 minutes' AND (now() AT TIME ZONE 'UTC')) <> count(s.id)
    THEN 'у активных датчиков зоны отсутствуют свежие качественные показания'
  ELSE 'ready' END
FROM selected JOIN sensors s ON s.zone_id = selected.id AND s.is_active
LEFT JOIN telemetry_last t ON t.sensor_id = s.id;
SQL
); then
  if [ "$result" = ready ]; then ok "телеметрия выбранной AE3-зоны"; else bad "$result"; fi
else
  bad "не удалось проверить зону в PostgreSQL"
fi

compose=(docker compose -f "${COMPOSE_FILE:-backend/docker-compose.dev.yml}")
if [ -n "${COMPOSE_ENV_FILE:-}" ]; then compose+=(--env-file "$COMPOSE_ENV_FILE"); fi
if "${compose[@]}" exec -T laravel php artisan tinker --execute="echo app(\\App\\Services\\TelegramAlertNotifier::class)->isConfigured() ? '1' : '0';" | grep -qx 1; then
  ok "Telegram настроен"
else
  bad "Telegram не настроен (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS)"
fi

if [ "$fail" -ne 0 ]; then
  echo "Контур не готов к автономии 2–4 недели. Нужны ноды с телеметрией и (для этапа E) Telegram."
  exit 1
fi
echo "Базовый health зелёный. 2–4 недели на железе — полевой прогон, не этот скрипт."
exit 0
