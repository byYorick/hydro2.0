#!/usr/bin/env bash
# Снимок отклонений AE3 / команд при прогоне real-hardware E2E (test_node).
# Не требует pytest; использует psql + docker compose logs.
#
# Usage:
#   ./tools/watch_ae3_realhw_deviations.sh [zone_id]
# Env (опционально):
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE  — БД E2E (по умолчанию hydro_e2e на localhost:5433)
#   E2E_COMPOSE_FILE — путь к docker-compose.e2e.yml
#   LOG_LINES — сколько последних строк логов показать на сервис (default 80)
set -euo pipefail

ZONE_ID="${1:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
E2E_COMPOSE_FILE="${E2E_COMPOSE_FILE:-$E2E_ROOT/docker-compose.e2e.yml}"
LOG_LINES="${LOG_LINES:-80}"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hydro_e2e}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

if ! command -v psql >/dev/null 2>&1; then
  echo "❌ Нужен psql (postgresql-client)"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Нужен docker"
  exit 1
fi

dc() {
  docker compose -f "$E2E_COMPOSE_FILE" "$@"
}

echo "=== AE3 / зона $ZONE_ID — снимок БД ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1 <<SQL
\x on
SELECT id, status, topology, current_stage, error_code, left(coalesce(error_message,''), 120) AS err,
       updated_at
FROM ae_tasks
WHERE zone_id = $ZONE_ID
ORDER BY id DESC
LIMIT 8;

SELECT status, count(*) AS n
FROM ae_tasks
WHERE zone_id = $ZONE_ID
GROUP BY status
ORDER BY n DESC;

SELECT publish_status, count(*) AS n
FROM ae_commands c
JOIN ae_tasks t ON t.id = c.task_id
WHERE t.zone_id = $ZONE_ID
  AND c.created_at > NOW() - INTERVAL '2 hours'
GROUP BY publish_status
ORDER BY n DESC;

SELECT channel, payload->>'cmd' AS cmd, count(*) AS n
FROM ae_commands c
JOIN ae_tasks t ON t.id = c.task_id
WHERE t.zone_id = $ZONE_ID
  AND c.created_at > NOW() - INTERVAL '2 hours'
  AND c.publish_status IN ('rejected', 'failed')
GROUP BY 1, 2
ORDER BY n DESC
LIMIT 20;

SELECT type, count(*) AS n
FROM zone_events
WHERE zone_id = $ZONE_ID
  AND created_at > NOW() - INTERVAL '2 hours'
GROUP BY type
ORDER BY n DESC
LIMIT 25;
SQL

echo ""
echo "=== Последние строки логов (ERROR / correction / AE3) ==="
for svc in automation-engine history-logger; do
  echo "--- $svc (tail $LOG_LINES) ---"
  dc logs --tail "$LOG_LINES" "$svc" 2>/dev/null | rg -i 'error|exception|correction|ae3|irrigation|fail' || true
  echo ""
done

echo "✅ Снимок готов. Для непрерывного мониторинга: watch -n5 $0 $ZONE_ID"
