#!/usr/bin/env bash
# Coordinate application backups; Docker volumes are explicitly optional.
set -euo pipefail
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backups}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SOURCE_ROOT="${BACKUP_SOURCE_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
export LARAVEL_DIR="${LARAVEL_DIR:-${BACKUP_SOURCE_ROOT}/laravel}"
export SERVICES_DIR="${SERVICES_DIR:-${BACKUP_SOURCE_ROOT}/services}"
export MQTT_CONFIG_DIR="${MQTT_CONFIG_DIR:-${SERVICES_DIR}/mqtt-bridge}"
export CONFIGS_DIR="${CONFIGS_DIR:-${BACKUP_SOURCE_ROOT}/configs}"
export DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-${BACKUP_SOURCE_ROOT}/.env}"
export DEPLOY_COMPOSE_FILE="${DEPLOY_COMPOSE_FILE:-${BACKUP_SOURCE_ROOT}/docker-compose.dev.yml}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
mkdir -p "${BACKUP_DIR}/full"
BACKUP_SUBDIR=$(mktemp -d "${BACKUP_DIR}/full/${TIMESTAMP}_XXXXXX")
BACKUP_RESULTS=()

backup_component() {
    local component=$1 script=$2 skip=$3 output artifact status
    if [ "${skip}" = 1 ]; then
        BACKUP_RESULTS+=("$(jq -cn --arg component "${component}" '{component:$component,status:"skipped",reason:"explicitly_disabled"}')")
        return
    fi
    echo "Backing up ${component}"
    status=failed
    artifact=""
    if output=$(BACKUP_DIR="${BACKUP_SUBDIR}" bash "${SCRIPT_DIR}/${script}" 2>&1); then
        artifact=$(printf '%s\n' "${output}" | tail -n 1)
        if [ -f "${artifact}" ] && [ -s "${artifact}" ]; then
            status=success
        elif [ -d "${artifact}" ] && [ -f "${artifact}/manifest.json" ] &&
             [ -n "$(find "${artifact}" -type f -name '*.tar.gz' -size +0c -print -quit)" ]; then
            status=success
        fi
    fi
    if [ "${status}" != success ]; then
        printf '%s\n' "${output}" >&2
        echo "Backup failed or artifact is empty: ${component}" >&2
    fi
    BACKUP_RESULTS+=("$(jq -cn --arg component "${component}" --arg status "${status}" --arg file "${artifact}" '{component:$component,status:$status,file:$file}')")
}

backup_component postgres postgres_backup.sh 0
backup_component laravel laravel_backup.sh 0
backup_component python python_backup.sh 0
backup_component mqtt mqtt_backup.sh "${SKIP_MQTT:-0}"
backup_component docker docker_volumes_backup.sh "${SKIP_DOCKER:-0}"

RESULTS_JSON=$(printf '%s\n' "${BACKUP_RESULTS[@]}" | jq -s .)
SCOPE=full
if [ "${SKIP_DOCKER:-0}" = 1 ]; then SCOPE=application; fi
if [ "${SKIP_MQTT:-0}" = 1 ]; then SCOPE=partial_application; fi
jq -n --arg timestamp "${TIMESTAMP}" --arg dir "${BACKUP_SUBDIR}" \
    --arg scope "${SCOPE}" --argjson components "${RESULTS_JSON}" '
    {timestamp:$timestamp,backup_dir:$dir,created_by:"full_backup.sh",scope:$scope,
     components:$components,
     failed_components:[$components[] | select(.status=="failed") | .component],
     total_components:($components|length),
     failed_count:([$components[]|select(.status=="failed")]|length),
     success_count:([$components[]|select(.status=="success")]|length),
     skipped_count:([$components[]|select(.status=="skipped")]|length)}
    ' > "${BACKUP_SUBDIR}/manifest.json"
if jq -e '.failed_count == 0' "${BACKUP_SUBDIR}/manifest.json" >/dev/null; then
    echo "Backup completed (scope=${SCOPE}); see manifest for skipped components"
    echo "${BACKUP_SUBDIR}"
else
    echo "Backup failed; inspect ${BACKUP_SUBDIR}/manifest.json" >&2
    exit 1
fi
