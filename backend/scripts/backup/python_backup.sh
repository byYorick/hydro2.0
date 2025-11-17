#!/bin/bash
# Python Services Backup Script
# Архивирует .env файлы и конфигурации Python сервисов

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
SERVICES_DIR="${SERVICES_DIR:-./services}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/python/${TIMESTAMP}"

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

# Проверка существования services директории
if [ ! -d "${SERVICES_DIR}" ]; then
    error "Services директория не найдена: ${SERVICES_DIR}"
    exit 1
fi

# Создание директории для бэкапа
mkdir -p "${BACKUP_SUBDIR}"
log "Создана директория для бэкапа: ${BACKUP_SUBDIR}"

# Временная директория для архивации
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

log "Начало создания бэкапа Python сервисов..."

# Список сервисов для бэкапа
SERVICES=("automation-engine" "scheduler" "mqtt-bridge" "history-logger")
BACKED_UP_SERVICES=()

# Копирование конфигураций для каждого сервиса
for service in "${SERVICES[@]}"; do
    SERVICE_DIR="${SERVICES_DIR}/${service}"
    if [ -d "${SERVICE_DIR}" ]; then
        mkdir -p "${TEMP_DIR}/${service}"
        
        # Копирование .env файла
        if [ -f "${SERVICE_DIR}/.env" ]; then
            cp "${SERVICE_DIR}/.env" "${TEMP_DIR}/${service}/.env"
            log "Скопирован .env для ${service}"
        fi
        
        # Копирование конфигурационных файлов
        if [ -f "${SERVICE_DIR}/config.yaml" ]; then
            cp "${SERVICE_DIR}/config.yaml" "${TEMP_DIR}/${service}/config.yaml"
            log "Скопирован config.yaml для ${service}"
        fi
        
        # Копирование secrets директории (если есть)
        if [ -d "${SERVICE_DIR}/secrets" ]; then
            cp -r "${SERVICE_DIR}/secrets" "${TEMP_DIR}/${service}/"
            log "Скопирована директория secrets для ${service}"
        fi
        
        # Копирование config директории (если есть)
        if [ -d "${SERVICE_DIR}/config" ]; then
            cp -r "${SERVICE_DIR}/config" "${TEMP_DIR}/${service}/"
            log "Скопирована директория config для ${service}"
        fi
        
        BACKED_UP_SERVICES+=("${service}")
    else
        warning "Сервис ${service} не найден"
    fi
done

# Проверка, что хотя бы один сервис был скопирован
if [ ${#BACKED_UP_SERVICES[@]} -eq 0 ]; then
    error "Не найдено ни одного сервиса для бэкапа"
    exit 1
fi

# Создание ZIP архива
BACKUP_FILE="${BACKUP_SUBDIR}/python_${TIMESTAMP}.zip"
cd "${TEMP_DIR}"
if zip -r "${BACKUP_FILE}" . > /dev/null; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    log "Архив успешно создан: ${BACKUP_FILE}"
    log "Размер файла: ${FILE_SIZE}"
    
    # Создание manifest файла
    SERVICES_JSON=$(printf '%s\n' "${BACKED_UP_SERVICES[@]}" | jq -R . | jq -s .)
    cat > "${BACKUP_SUBDIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "backup_file": "python_${TIMESTAMP}.zip",
  "size_bytes": $(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null || echo 0),
  "services_dir": "${SERVICES_DIR}",
  "created_by": "python_backup.sh",
  "services": ${SERVICES_JSON}
}
EOF
    log "Manifest создан: ${BACKUP_SUBDIR}/manifest.json"
    echo "${BACKUP_FILE}"
    exit 0
else
    error "Ошибка при создании ZIP архива"
    exit 1
fi

