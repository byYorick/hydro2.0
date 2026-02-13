#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/backend/docker-compose.dev.yml"

RUN_ID="$(date +%s)"
LOCK_SCOPE="chaos-r2-${RUN_ID}"
SCHED_A="scheduler-chaos-a-${RUN_ID}"
SCHED_B="scheduler-chaos-b-${RUN_ID}"
CHAOS_LOG_DIR="${CHAOS_LOG_DIR:-}"

if [[ -n "${CHAOS_LOG_DIR}" && "${CHAOS_LOG_DIR}" != /* ]]; then
  CHAOS_LOG_DIR="${ROOT_DIR}/${CHAOS_LOG_DIR}"
fi

collect_logs_if_present() {
  local container="$1"
  if [[ -z "${CHAOS_LOG_DIR}" ]]; then
    return 0
  fi

  mkdir -p "${CHAOS_LOG_DIR}"
  if docker ps -a --format '{{.Names}}' | grep -Fxq "${container}"; then
    docker logs "${container}" > "${CHAOS_LOG_DIR}/${container}.log" 2>&1 || true
  fi
}

cleanup() {
  collect_logs_if_present "${SCHED_A}"
  collect_logs_if_present "${SCHED_B}"
  docker rm -f "${SCHED_A}" >/dev/null 2>&1 || true
  docker rm -f "${SCHED_B}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_log() {
  local container="$1"
  local pattern="$2"
  local timeout_sec="${3:-30}"
  local i
  for ((i=0; i<timeout_sec; i++)); do
    if docker logs "${container}" 2>&1 | grep -q "${pattern}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

metric_value() {
  local container="$1"
  local metric="$2"
  docker exec "${container}" python -c "import urllib.request; d=urllib.request.urlopen('http://localhost:9402', timeout=2).read().decode(); values=[line.split()[-1] for line in d.splitlines() if line.startswith('${metric} ')]; print(values[0] if values else '')" 2>/dev/null || true
}

wait_for_single_leader() {
  local timeout_sec="${1:-60}"
  local i
  for ((i=0; i<timeout_sec; i++)); do
    local a b
    a="$(metric_value "${SCHED_A}" "scheduler_leader_role")"
    b="$(metric_value "${SCHED_B}" "scheduler_leader_role")"

    if [[ "${a}" == "1.0" && "${b}" == "0.0" ]]; then
      echo "${SCHED_A}|${SCHED_B}"
      return 0
    fi
    if [[ "${a}" == "0.0" && "${b}" == "1.0" ]]; then
      echo "${SCHED_B}|${SCHED_A}"
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_leader_metric() {
  local container="$1"
  local timeout_sec="${2:-60}"
  local i
  for ((i=0; i<timeout_sec; i++)); do
    local value
    value="$(metric_value "${container}" "scheduler_leader_role")"
    if [[ "${value}" == "1.0" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "[chaos] Ensure dependencies are up"
docker compose -f "${COMPOSE_FILE}" up -d db redis mqtt laravel automation-engine >/dev/null

echo "[chaos] Start scheduler instance A"
docker compose -f "${COMPOSE_FILE}" run -d --no-deps \
  --name "${SCHED_A}" \
  -e SCHEDULER_LEADER_ELECTION=1 \
  -e SCHEDULER_LEADER_LOCK_SCOPE="${LOCK_SCOPE}" \
  -e SCHEDULER_ID="${SCHED_A}" \
  scheduler >/dev/null

echo "[chaos] Start scheduler instance B"
docker compose -f "${COMPOSE_FILE}" run -d --no-deps \
  --name "${SCHED_B}" \
  -e SCHEDULER_LEADER_ELECTION=1 \
  -e SCHEDULER_LEADER_LOCK_SCOPE="${LOCK_SCOPE}" \
  -e SCHEDULER_ID="${SCHED_B}" \
  scheduler >/dev/null

echo "[chaos] Wait until exactly one instance is leader"
leader_pair="$(wait_for_single_leader 80 || true)"
if [[ -z "${leader_pair}" ]]; then
  echo "[chaos][FAIL] Did not observe single-leader state (role 1/0) for scheduler pair"
  echo "[chaos] ${SCHED_A} role=$(metric_value "${SCHED_A}" "scheduler_leader_role")"
  echo "[chaos] ${SCHED_B} role=$(metric_value "${SCHED_B}" "scheduler_leader_role")"
  exit 1
fi

leader="${leader_pair%%|*}"
follower="${leader_pair##*|}"

echo "[chaos] Leader=${leader}, follower=${follower}"
echo "[chaos] Stop leader and wait for follower takeover"
collect_logs_if_present "${leader}"
docker rm -f "${leader}" >/dev/null

if ! wait_for_leader_metric "${follower}" 80; then
  echo "[chaos][FAIL] Follower did not acquire leader role after leader termination"
  exit 1
fi

echo "[chaos][PASS] Container-level leader failover validated"
