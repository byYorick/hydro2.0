#!/bin/bash
# Script to generate MQTT password file
# Usage: ./generate_passwords.sh [passwords_file]

set -euo pipefail

PASSWORDS_FILE="${1:-passwords}"

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

# Check if mosquitto_passwd is available
if ! command -v mosquitto_passwd &> /dev/null; then
    error "mosquitto_passwd not found. Install mosquitto-clients package."
    error "Ubuntu/Debian: sudo apt-get install mosquitto-clients"
    error "macOS: brew install mosquitto"
    exit 1
fi

log "Generating MQTT password file: ${PASSWORDS_FILE}"

# Remove existing file if it exists
if [ -f "${PASSWORDS_FILE}" ]; then
    warning "File ${PASSWORDS_FILE} already exists. Removing..."
    rm -f "${PASSWORDS_FILE}"
fi

# Default passwords (CHANGE IN PRODUCTION!)
# These are weak passwords for development only!
PYTHON_SERVICE_PASS="${MQTT_PYTHON_SERVICE_PASS:-python_service_pass}"
AUTOMATION_ENGINE_PASS="${MQTT_AUTOMATION_ENGINE_PASS:-automation_pass}"
HISTORY_LOGGER_PASS="${MQTT_HISTORY_LOGGER_PASS:-logger_pass}"
SCHEDULER_PASS="${MQTT_SCHEDULER_PASS:-scheduler_pass}"
MQTT_BRIDGE_PASS="${MQTT_MQTT_BRIDGE_PASS:-bridge_pass}"
ESP32_NODE_PASS="${MQTT_ESP32_NODE_PASS:-esp32_pass}"

# Create password file and add users
log "Creating password file..."
mosquitto_passwd -c "${PASSWORDS_FILE}" python_service <<< "${PYTHON_SERVICE_PASS}" || true
mosquitto_passwd "${PASSWORDS_FILE}" automation_engine <<< "${AUTOMATION_ENGINE_PASS}" || true
mosquitto_passwd "${PASSWORDS_FILE}" history_logger <<< "${HISTORY_LOGGER_PASS}" || true
mosquitto_passwd "${PASSWORDS_FILE}" scheduler <<< "${SCHEDULER_PASS}" || true
mosquitto_passwd "${PASSWORDS_FILE}" mqtt_bridge <<< "${MQTT_BRIDGE_PASS}" || true
mosquitto_passwd "${PASSWORDS_FILE}" esp32_node <<< "${ESP32_NODE_PASS}" || true

log "Password file created: ${PASSWORDS_FILE}"
log "Users added:"
log "  - python_service"
log "  - automation_engine"
log "  - history_logger"
log "  - scheduler"
log "  - mqtt_bridge"
log "  - esp32_node"

warning "IMPORTANT: Change default passwords in production!"
warning "Set environment variables:"
warning "  MQTT_PYTHON_SERVICE_PASS"
warning "  MQTT_AUTOMATION_ENGINE_PASS"
warning "  MQTT_HISTORY_LOGGER_PASS"
warning "  MQTT_SCHEDULER_PASS"
warning "  MQTT_MQTT_BRIDGE_PASS"
warning "  MQTT_ESP32_NODE_PASS"

