#!/usr/bin/env bash
# Периодический срез БД/логов во время real-hardware прогона (запускать параллельно).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
COMPOSE=(docker compose -f docker-compose.e2e.yml)
START_EPOCH="${1:-$(cat /tmp/e2e_retest_start 2>/dev/null || date +%s)}"
SINCE=$(date -u -d "@$START_EPOCH" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -r "$START_EPOCH" +"%Y-%m-%dT%H:%M:%SZ")

while [ -f /tmp/e2e_retest_running ]; do
  echo "===== $(date '+%H:%M:%S') snapshot (since $SINCE) ====="
  "${COMPOSE[@]}" exec -T postgres psql -qX -U hydro -d hydro_e2e -At -c "
    SELECT 'tasks_active='||COUNT(*) FROM ae_tasks WHERE zone_id=1 AND status IN ('pending','claimed','running','waiting_command');
    SELECT 'leases='||COUNT(*) FROM ae_zone_leases WHERE zone_id=1;
    SELECT 'open_biz='||COUNT(*) FROM alerts WHERE code LIKE 'biz_%' AND (UPPER(COALESCE(status,''))='ACTIVE' OR LOWER(COALESCE(status,''))='open');
    SELECT 'non_done_cmds='||COUNT(*) FROM commands WHERE status NOT IN ('DONE','SENT') AND created_at>=to_timestamp($START_EPOCH);
  " 2>/dev/null | sed 's/^/  /'
  for svc in automation-engine history-logger laravel; do
    n=$("${COMPOSE[@]}" logs --since "$SINCE" "$svc" 2>&1 | rg -c " - (ERROR|CRITICAL) - |Traceback" || echo 0)
    echo "  ${svc}_errors=$n"
  done
  echo
  sleep 45
done
