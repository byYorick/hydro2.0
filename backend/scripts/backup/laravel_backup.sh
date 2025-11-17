#!/bin/bash
# Laravel Backup Script
# Архивирует .env, storage/app/ota, storage/app/public, composer.lock

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
LARAVEL_DIR="${LARAVEL_DIR:-./laravel}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/laravel/${TIMESTAMP}"

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

# Проверка существования Laravel директории
if [ ! -d "${LARAVEL_DIR}" ]; then
    error "Laravel директория не найдена: ${LARAVEL_DIR}"
    exit 1
fi

# Создание директории для бэкапа
mkdir -p "${BACKUP_SUBDIR}"
log "Создана директория для бэкапа: ${BACKUP_SUBDIR}"

# Временная директория для архивации
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

log "Начало создания бэкапа Laravel..."

# Копирование .env
if [ -f "${LARAVEL_DIR}/.env" ]; then
    cp "${LARAVEL_DIR}/.env" "${TEMP_DIR}/.env"
    log "Скопирован .env"
else
    warning ".env файл не найден"
fi

# Копирование storage/app/ota
if [ -d "${LARAVEL_DIR}/storage/app/ota" ]; then
    mkdir -p "${TEMP_DIR}/storage/app"
    cp -r "${LARAVEL_DIR}/storage/app/ota" "${TEMP_DIR}/storage/app/"
    log "Скопирован storage/app/ota"
else
    warning "storage/app/ota не найден"
fi

# Копирование storage/app/public
if [ -d "${LARAVEL_DIR}/storage/app/public" ]; then
    mkdir -p "${TEMP_DIR}/storage/app"
    cp -r "${LARAVEL_DIR}/storage/app/public" "${TEMP_DIR}/storage/app/"
    log "Скопирован storage/app/public"
else
    warning "storage/app/public не найден"
fi

# Копирование composer.lock
if [ -f "${LARAVEL_DIR}/composer.lock" ]; then
    cp "${LARAVEL_DIR}/composer.lock" "${TEMP_DIR}/composer.lock"
    log "Скопирован composer.lock"
else
    warning "composer.lock не найден"
fi

# Создание ZIP архива
BACKUP_FILE="${BACKUP_SUBDIR}/laravel_${TIMESTAMP}.zip"
cd "${TEMP_DIR}"
if zip -r "${BACKUP_FILE}" . > /dev/null; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    log "Архив успешно создан: ${BACKUP_FILE}"
    log "Размер файла: ${FILE_SIZE}"
    
    # Создание manifest файла
    cat > "${BACKUP_SUBDIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "backup_file": "laravel_${TIMESTAMP}.zip",
  "size_bytes": $(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null || echo 0),
  "laravel_dir": "${LARAVEL_DIR}",
  "created_by": "laravel_backup.sh",
  "contents": [
    ".env",
    "storage/app/ota",
    "storage/app/public",
    "composer.lock"
  ]
}
EOF
    log "Manifest создан: ${BACKUP_SUBDIR}/manifest.json"
    echo "${BACKUP_FILE}"
    exit 0
else
    error "Ошибка при создании ZIP архива"
    exit 1
fi

