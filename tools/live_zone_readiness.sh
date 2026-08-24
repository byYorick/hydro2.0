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

check_http "Laravel" "http://localhost:8080/api/system/health"
check_http "history-logger" "http://localhost:9300/health"
check_http "automation-engine" "http://localhost:9405/health/live"

if command -v psql >/dev/null 2>&1; then
  ae3=$(PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -Atqc \
    "SELECT count(*) FROM zones WHERE automation_runtime = 'ae3'" 2>/dev/null || echo 0)
  if [ "${ae3:-0}" -gt 0 ]; then
    ok "zones.automation_runtime=ae3 count=$ae3"
  else
    bad "нет зон с automation_runtime=ae3"
  fi
  fresh=$(PGPASSWORD="${PGPASSWORD:-hydro}" psql -h localhost -U hydro -d hydro_dev -w -Atqc \
    "SELECT count(*) FROM telemetry_last WHERE ts > NOW() - interval '10 minutes'" 2>/dev/null || echo 0)
  if [ "${fresh:-0}" -gt 0 ]; then
    ok "telemetry_last за 10 мин: $fresh"
  else
    bad "нет свежей telemetry_last (нужны живые ноды или node-sim)"
  fi
else
  bad "psql не найден"
fi

if docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan tinker --execute="echo app(\\App\\Services\\TelegramAlertNotifier::class)->isConfigured() ? '1' : '0';" 2>/dev/null | tail -1 | grep -qx 1; then
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
