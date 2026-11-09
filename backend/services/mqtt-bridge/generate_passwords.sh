#!/bin/bash
# Script to generate MQTT password file
# Usage: ./generate_passwords.sh [passwords_file]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PASSWORDS_FILE="${1:-passwords.txt}"
if [[ "${PASSWORDS_FILE}" != /* ]]; then
    PASSWORDS_FILE="${SCRIPT_DIR}/${PASSWORDS_FILE}"
fi
PASSWORDS_BASENAME="$(basename "${PASSWORDS_FILE}")"
HOST_PASSWORDS_FILE="${SCRIPT_DIR}/${PASSWORDS_BASENAME}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Guard against historical wrong path type (directory named "passwords")
if [ -d "${HOST_PASSWORDS_FILE}" ]; then
    error "${HOST_PASSWORDS_FILE} is a directory. Expected a file path (e.g. passwords.txt)."
    exit 1
fi

# Check if mosquitto_passwd is available (host or via Docker)
MOSQUITTO_PASSWD_CMD=()
if command -v mosquitto_passwd &> /dev/null; then
    MOSQUITTO_PASSWD_CMD=(mosquitto_passwd)
elif command -v docker &> /dev/null; then
    log "mosquitto_passwd not on host — using eclipse-mosquitto Docker image"
    MOSQUITTO_PASSWD_CMD=(docker run --rm -i -v "${SCRIPT_DIR}:/work" -w /work eclipse-mosquitto:2 mosquitto_passwd)
    PASSWORDS_FILE="/work/${PASSWORDS_BASENAME}"
else
    error "mosquitto_passwd not found. Install mosquitto-clients or Docker."
    error "Ubuntu/Debian: sudo apt-get install mosquitto-clients"
    error "macOS: brew install mosquitto"
    exit 1
fi

log "Generating MQTT password file: ${HOST_PASSWORDS_FILE}"

# Remove existing file if it exists
if [ -f "${HOST_PASSWORDS_FILE}" ]; then
    warning "File ${HOST_PASSWORDS_FILE} already exists. Removing..."
    rm -f "${HOST_PASSWORDS_FILE}"
fi

require_pass() {
    local var_name="$1"
    local value="${!var_name:-}"
    if [ -z "$value" ]; then
        error "${var_name} is required (no default password). Export it or run: make ensure-dev-secrets"
        exit 1
    fi
    printf '%s' "$value"
}

PYTHON_SERVICE_PASS="$(require_pass MQTT_PYTHON_SERVICE_PASS)"
AUTOMATION_ENGINE_PASS="$(require_pass MQTT_AUTOMATION_ENGINE_PASS)"
HISTORY_LOGGER_PASS="$(require_pass MQTT_HISTORY_LOGGER_PASS)"
MQTT_BRIDGE_PASS="$(require_pass MQTT_MQTT_BRIDGE_PASS)"
ESP32_NODE_PASS="$(require_pass MQTT_ESP32_NODE_PASS)"

# Create password file and add users (-b: batch mode, без интерактивного ввода)
log "Creating password file..."
"${MOSQUITTO_PASSWD_CMD[@]}" -b -c "${PASSWORDS_FILE}" python_service "${PYTHON_SERVICE_PASS}"
"${MOSQUITTO_PASSWD_CMD[@]}" -b "${PASSWORDS_FILE}" automation_engine "${AUTOMATION_ENGINE_PASS}"
"${MOSQUITTO_PASSWD_CMD[@]}" -b "${PASSWORDS_FILE}" history_logger "${HISTORY_LOGGER_PASS}"
"${MOSQUITTO_PASSWD_CMD[@]}" -b "${PASSWORDS_FILE}" mqtt_bridge "${MQTT_BRIDGE_PASS}"
"${MOSQUITTO_PASSWD_CMD[@]}" -b "${PASSWORDS_FILE}" esp32_node "${ESP32_NODE_PASS}"

log "Password file created: ${HOST_PASSWORDS_FILE}"
log "Users added:"
log "  - python_service"
log "  - automation_engine"
log "  - history_logger"
log "  - mqtt_bridge"
log "  - esp32_node"

log "Passwords were taken from MQTT_*_PASS environment variables."
