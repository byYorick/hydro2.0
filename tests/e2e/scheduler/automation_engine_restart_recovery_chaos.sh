#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/backend/docker-compose.dev.yml"

RUN_ID="$(date +%s)"
TASK_ID="st-chaos-ae-restart-${RUN_ID}"
TASK_NAME="ae_scheduler_task_${TASK_ID}"
ZONE_ID=""

query_scalar() {
  docker exec backend-db-1 psql -U hydro -d hydro_dev -t -A -c "$1" | tr -d '[:space:]'
}

ensure_zone_id() {
  local zone_id
  zone_id="$(query_scalar "SELECT id FROM zones ORDER BY id LIMIT 1;")"
  if [[ -z "${zone_id}" ]]; then
    docker exec backend-laravel-1 php artisan e2e:auth-bootstrap --email=agronomist@example.com --role=agronomist --with-zone >/dev/null 2>&1 || true
    zone_id="$(query_scalar "SELECT id FROM zones ORDER BY id LIMIT 1;")"
  fi
  if [[ -z "${zone_id}" ]]; then
    echo "[chaos][FAIL] Cannot resolve valid zone_id for automation-engine recovery scenario"
    exit 1
  fi
  ZONE_ID="${zone_id}"
}

wait_for_ae_live() {
  local timeout_sec="${1:-90}"
  local i
  for ((i=0; i<timeout_sec; i++)); do
    if docker exec backend-automation-engine-1 python -c "import urllib.request; urllib.request.urlopen('http://localhost:9405/health/live', timeout=2)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "[chaos] Ensure automation-engine stack is up"
docker compose -f "${COMPOSE_FILE}" up -d db redis mqtt laravel automation-engine >/dev/null
ensure_zone_id

echo "[chaos] Insert running snapshot for recovery scanner: ${TASK_ID}"
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "
INSERT INTO scheduler_logs(task_name, status, details)
VALUES (
  '${TASK_NAME}',
  'running',
  jsonb_build_object(
    'task_id', '${TASK_ID}',
    'zone_id', ${ZONE_ID},
    'task_type', 'diagnostics',
    'status', 'running',
    'created_at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS'),
    'updated_at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS'),
    'correlation_id', 'sch:z${ZONE_ID}:diagnostics:chaos-ae-restart-${RUN_ID}'
  )
);
" >/dev/null

echo "[chaos] Restart automation-engine container"
docker restart backend-automation-engine-1 >/dev/null

if ! wait_for_ae_live 120; then
  echo "[chaos][FAIL] automation-engine did not become live after restart"
  docker logs backend-automation-engine-1 | tail -n 120 || true
  exit 1
fi

echo "[chaos] Verify recovered task terminal status"
for _ in $(seq 1 45); do
  status_and_error="$(docker exec backend-automation-engine-1 python -c "import json,urllib.request; data=json.loads(urllib.request.urlopen('http://localhost:9405/scheduler/task/${TASK_ID}', timeout=2).read().decode()).get('data', {}); print(f\"{data.get('status','')}|{data.get('error_code','')}\")" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "${status_and_error}" == "failed|task_recovered_after_restart" ]]; then
    echo "[chaos][PASS] automation-engine recovery scanner finalized ${TASK_ID}"
    exit 0
  fi
  sleep 2
done

echo "[chaos][FAIL] automation-engine did not expose recovered terminal status for ${TASK_ID}"
docker exec backend-automation-engine-1 python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:9405/scheduler/task/${TASK_ID}', timeout=2).read().decode())" || true
docker logs backend-automation-engine-1 | tail -n 120 || true
exit 1
