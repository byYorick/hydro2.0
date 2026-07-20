#!/usr/bin/env bash
# Ops helper: clear retained MQTT status/lwt on stale namespaces after detach/rebind.
#
# После bind нода публикует status в целевом namespace, но retained ONLINE/LWT
# на gh-temp (или старой зоне) остаётся на брокере → «зомби» в UI/probe.
#
# Usage:
#   ./backend/scripts/clear-zombie-mqtt-status.sh --from-db
#   ./backend/scripts/clear-zombie-mqtt-status.sh --uid nd-test-ph-1 --uid nd-test-ec-1
#   ./backend/scripts/clear-zombie-mqtt-status.sh --prefix nd-test- --from-db --dry-run
#
# Env: MQTT_HOST (default localhost), MQTT_PORT (1883),
#      PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE (defaults for hydro_dev).
set -euo pipefail

MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-hydro}"
PGPASSWORD="${PGPASSWORD:-hydro}"
PGDATABASE="${PGDATABASE:-hydro_dev}"
export PGPASSWORD

DRY_RUN=0
FROM_DB=0
SCAN_SEC=3
PREFIX=""
declare -a UID_FILTER=()

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --from-db) FROM_DB=1; shift ;;
    --uid) UID_FILTER+=("$2"); shift 2 ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --host) MQTT_HOST="$2"; shift 2 ;;
    --port) MQTT_PORT="$2"; shift 2 ;;
    --scan-sec) SCAN_SEC="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

if ! command -v mosquitto_sub >/dev/null 2>&1 || ! command -v mosquitto_pub >/dev/null 2>&1; then
  echo "ERROR: mosquitto_sub/mosquitto_pub required on PATH" >&2
  exit 1
fi

# uid -> "gh_uid/zone_uid" (empty string = unassigned → keep only gh-temp/zn-temp)
declare -A CANONICAL_NS=()

load_canonical_from_db() {
  if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: --from-db requires psql" >&2
    exit 1
  fi

  local sql
  sql=$(cat <<'SQL'
SELECT n.uid,
       COALESCE(g.uid, '') AS gh_uid,
       COALESCE(z.uid, '') AS zone_uid
FROM nodes n
LEFT JOIN zones z ON z.id = n.zone_id
LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
WHERE n.uid IS NOT NULL
ORDER BY n.uid;
SQL
)

  while IFS=$'\t' read -r uid gh zone; do
    [[ -z "${uid}" ]] && continue
    if [[ -n "${PREFIX}" && "${uid}" != ${PREFIX}* ]]; then
      continue
    fi
    if ((${#UID_FILTER[@]} > 0)); then
      local match=0 u
      for u in "${UID_FILTER[@]}"; do
        [[ "${uid}" == "${u}" ]] && match=1 && break
      done
      ((match == 0)) && continue
    fi
    if [[ -n "${gh}" && -n "${zone}" ]]; then
      CANONICAL_NS["${uid}"]="${gh}/${zone}"
    else
      # unassigned / pending: канон = temp namespace
      CANONICAL_NS["${uid}"]="gh-temp/zn-temp"
    fi
  done < <(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -w -At -F $'\t' -c "${sql}")
}

scan_retained_status_topics() {
  timeout "${SCAN_SEC}" mosquitto_sub \
    -h "${MQTT_HOST}" -p "${MQTT_PORT}" \
    -t 'hydro/+/+/+/status' -t 'hydro/+/+/+/lwt' \
    -v --retained-only 2>/dev/null \
    | awk '{print $1}' \
    | sort -u \
    || true
}

clear_topic() {
  local topic="$1"
  if ((DRY_RUN)); then
    echo "dry-run: clear retained ${topic}"
    return 0
  fi
  if mosquitto_pub -h "${MQTT_HOST}" -p "${MQTT_PORT}" -t "${topic}" -n -r -q 1; then
    echo "cleared: ${topic}"
    return 0
  fi
  echo "FAILED: ${topic}" >&2
  return 1
}

if ((FROM_DB)); then
  load_canonical_from_db
  echo "Loaded ${#CANONICAL_NS[@]} node namespace(s) from ${PGDATABASE}"
elif ((${#UID_FILTER[@]} > 0)) || [[ -n "${PREFIX}" ]]; then
  # Без БД: чистим только gh-temp/zn-temp для указанных uid (типичный zombie после rebind).
  echo "No --from-db: will clear only hydro/gh-temp/zn-temp/{uid}/{status|lwt} for filter"
else
  echo "ERROR: specify --from-db and/or --uid / --prefix" >&2
  usage 1
fi

cleared=0
skipped=0
mapfile -t TOPICS < <(scan_retained_status_topics)

for topic in "${TOPICS[@]:-}"; do
  [[ -z "${topic}" ]] && continue
  # hydro/{gh}/{zone}/{node_uid}/status|lwt
  if [[ ! "${topic}" =~ ^hydro/([^/]+)/([^/]+)/([^/]+)/(status|lwt)$ ]]; then
    continue
  fi
  gh="${BASH_REMATCH[1]}"
  zone="${BASH_REMATCH[2]}"
  uid="${BASH_REMATCH[3]}"
  kind="${BASH_REMATCH[4]}"

  if [[ -n "${PREFIX}" && "${uid}" != ${PREFIX}* ]]; then
    continue
  fi
  if ((${#UID_FILTER[@]} > 0)); then
    match=0
    for u in "${UID_FILTER[@]}"; do
      [[ "${uid}" == "${u}" ]] && match=1 && break
    done
    ((match == 0)) && continue
  fi

  ns="${gh}/${zone}"

  if ((FROM_DB)); then
    if [[ -z "${CANONICAL_NS[${uid}]+x}" ]]; then
      # uid не в БД — не трогаем (может быть чужой ESP)
      skipped=$((skipped + 1))
      continue
    fi
    canon="${CANONICAL_NS[${uid}]}"
    if [[ "${ns}" == "${canon}" ]]; then
      skipped=$((skipped + 1))
      continue
    fi
  else
    # filter-only mode: только temp namespace
    if [[ "${ns}" != "gh-temp/zn-temp" ]]; then
      skipped=$((skipped + 1))
      continue
    fi
  fi

  if clear_topic "${topic}"; then
    cleared=$((cleared + 1))
  fi
done

echo "==> done: cleared=${cleared} skipped=${skipped} dry_run=${DRY_RUN} host=${MQTT_HOST}:${MQTT_PORT}"
