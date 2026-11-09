#!/bin/bash
# MQTT Backup Script
# Архивирует конфигурации MQTT (mosquitto)

set -euo pipefail
umask 077

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
MQTT_CONFIG_DIR="${MQTT_CONFIG_DIR:-./services/mqtt-bridge}"
CONFIGS_DIR="${CONFIGS_DIR:-./configs}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/mqtt/${TIMESTAMP}"

# Логирование
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка наличия zip
if ! command -v zip &> /dev/null; then
    error "zip не найден. Установите zip."
    exit 1
fi

# Создание директории для бэкапа
mkdir -p "${BACKUP_SUBDIR}"
log "Создана директория для бэкапа: ${BACKUP_SUBDIR}"

# Временная директория для архивации
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

log "Начало создания бэкапа MQTT конфигураций..."

# Match the broker bind mounts, including credentials and TLS material.
mkdir -p "${TEMP_DIR}/mqtt-bridge"
for required in passwords.txt acl; do
    if [ ! -f "${MQTT_CONFIG_DIR}/${required}" ]; then
        error "Required MQTT source is missing: ${required}"
        exit 1
    fi
    cp "${MQTT_CONFIG_DIR}/${required}" "${TEMP_DIR}/mqtt-bridge/"
done
config_found=false
for config_name in mosquitto.dev.conf mosquitto.prod.conf; do
    if [ -f "${MQTT_CONFIG_DIR}/${config_name}" ]; then
        cp "${MQTT_CONFIG_DIR}/${config_name}" "${TEMP_DIR}/mqtt-bridge/"
        config_found=true
    fi
done
if [ "${config_found}" != true ]; then
    error "Mosquitto configuration is missing"
    exit 1
fi
if [ -d "${MQTT_CONFIG_DIR}/certs" ]; then
    cp -RL "${MQTT_CONFIG_DIR}/certs" "${TEMP_DIR}/mqtt-bridge/"
fi

# Копирование конфигураций из configs (если есть mosquitto директория)
if [ -d "${CONFIGS_DIR}/dev" ] || [ -d "${CONFIGS_DIR}/prod" ]; then
    mkdir -p "${TEMP_DIR}/configs"
    
    # Копирование dev конфигураций
    if [ -d "${CONFIGS_DIR}/dev" ]; then
        if [ -f "${CONFIGS_DIR}/dev/mqtt.yaml" ]; then
            cp "${CONFIGS_DIR}/dev/mqtt.yaml" "${TEMP_DIR}/configs/mqtt.dev.yaml"
            log "Скопирован mqtt.dev.yaml"
        fi
    fi
    
    # Копирование prod конфигураций
    if [ -d "${CONFIGS_DIR}/prod" ]; then
        if [ -f "${CONFIGS_DIR}/prod/mqtt.yaml" ]; then
            cp "${CONFIGS_DIR}/prod/mqtt.yaml" "${TEMP_DIR}/configs/mqtt.prod.yaml"
            log "Скопирован mqtt.prod.yaml"
        fi
    fi
fi

# Проверка наличия файлов для бэкапа
if [ -z "$(find "${TEMP_DIR}" -type f)" ]; then
    warning "Не найдено файлов MQTT конфигураций для бэкапа"
    exit 1
fi

# Создание ZIP архива
BACKUP_FILE="${BACKUP_SUBDIR}/mqtt_${TIMESTAMP}.zip"
cd "${TEMP_DIR}"
if zip -r "${BACKUP_FILE}" . > /dev/null 2>&1; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    log "Архив успешно создан: ${BACKUP_FILE}"
    log "Размер файла: ${FILE_SIZE}"
    
    # Создание manifest файла
    cat > "${BACKUP_SUBDIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "backup_file": "mqtt_${TIMESTAMP}.zip",
  "size_bytes": $(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null || echo 0),
  "mqtt_config_dir": "${MQTT_CONFIG_DIR}",
  "configs_dir": "${CONFIGS_DIR}",
  "created_by": "mqtt_backup.sh"
}
EOF
    log "Manifest создан: ${BACKUP_SUBDIR}/manifest.json"
    echo "${BACKUP_FILE}"
    exit 0
else
    error "Ошибка при создании ZIP архива"
    exit 1
fi

