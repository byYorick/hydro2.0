#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/backend/docker-compose.dev.yml"

RUN_ID="$(date +%s)"
TASK_ID="st-chaos-scheduler-restart-${RUN_ID}"
ZONE_ID=""
TASK_NAME=""

query_count() {
  docker exec backend-db-1 psql -U hydro -d hydro_dev -t -A -c "$1" | tr -d '[:space:]'
}

ensure_zone_id() {
  local zone_id
  zone_id="$(query_count "SELECT id FROM zones ORDER BY id LIMIT 1;")"
  if [[ -z "${zone_id}" ]]; then
    docker exec backend-laravel-1 php artisan e2e:auth-bootstrap --email=agronomist@example.com --role=agronomist --with-zone >/dev/null 2>&1 || true
    zone_id="$(query_count "SELECT id FROM zones ORDER BY id LIMIT 1;")"
  fi
  if [[ -z "${zone_id}" ]]; then
    echo "[chaos][FAIL] Cannot resolve valid zone_id for recovery scenario"
    exit 1
  fi
  ZONE_ID="${zone_id}"
  TASK_NAME="diagnostics_zone_${ZONE_ID}"
}

echo "[chaos] Ensure scheduler stack is up"
docker compose -f "${COMPOSE_FILE}" up -d db redis mqtt laravel automation-engine scheduler >/dev/null
ensure_zone_id

echo "[chaos] Insert accepted snapshot for restart recovery: ${TASK_ID}"
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "
INSERT INTO scheduler_logs(task_name, status, details)
VALUES (
  '${TASK_NAME}',
  'accepted',
  jsonb_build_object(
    'task_id', '${TASK_ID}',
    'zone_id', ${ZONE_ID},
    'task_type', 'diagnostics',
    'status', 'accepted',
    'schedule_key', 'chaos:restart-recovery',
    'correlation_id', 'sch:z${ZONE_ID}:diagnostics:chaos-restart-${RUN_ID}',
    'accepted_at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS')
  )
);
" >/dev/null

echo "[chaos] Restart scheduler container"
docker restart backend-scheduler-1 >/dev/null

echo "[chaos] Wait until recovered task is reconciled to terminal status"
for _ in $(seq 1 45); do
  failed_count="$(query_count "SELECT COUNT(*) FROM scheduler_logs WHERE details->>'task_id'='${TASK_ID}' AND status='failed';")"
  if [[ "${failed_count}" =~ ^[0-9]+$ ]] && [[ "${failed_count}" -gt 0 ]]; then
    echo "[chaos][PASS] Scheduler restart recovery finalized task ${TASK_ID}"
    exit 0
  fi
  sleep 2
done

echo "[chaos][FAIL] Scheduler did not finalize recovered task ${TASK_ID} within timeout"
docker logs backend-scheduler-1 | tail -n 120 || true
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT task_name, status, details FROM scheduler_logs WHERE details->>'task_id'='${TASK_ID}' ORDER BY id DESC LIMIT 10;"
exit 1
