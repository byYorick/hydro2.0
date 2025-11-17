#!/bin/bash
# WAL Archive Script
# Архивирует WAL файлы PostgreSQL (вызывается PostgreSQL через archive_command)

set -euo pipefail

# Параметры
WAL_FILE="${1:-}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/wal_archive}"
RETENTION_DAYS="${WAL_RETENTION_DAYS:-7}"

# Логирование
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "${WAL_ARCHIVE_DIR}/archive.log"
}

error() {
    echo "[ERROR] $1" >&2
    log "ERROR: $1"
}

# Проверка параметров
if [ -z "${WAL_FILE}" ]; then
    error "WAL файл не указан"
    exit 1
fi

# Создание директории архива, если не существует
mkdir -p "${WAL_ARCHIVE_DIR}"

# Копирование WAL файла
if [ -f "${WAL_FILE}" ]; then
    WAL_NAME=$(basename "${WAL_FILE}")
    ARCHIVE_PATH="${WAL_ARCHIVE_DIR}/${WAL_NAME}"
    
    if cp "${WAL_FILE}" "${ARCHIVE_PATH}"; then
        log "WAL файл заархивирован: ${WAL_NAME}"
        
        # Сжатие старых WAL файлов (старше 1 дня)
        find "${WAL_ARCHIVE_DIR}" -name "*.wal" -type f -mtime +1 ! -name "*.gz" -exec gzip {} \; 2>/dev/null || true
        
        # Удаление старых WAL файлов (старше retention дней)
        find "${WAL_ARCHIVE_DIR}" -name "*.wal.gz" -type f -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
        find "${WAL_ARCHIVE_DIR}" -name "*.wal" -type f -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
        
        exit 0
    else
        error "Ошибка при копировании WAL файла: ${WAL_FILE}"
        exit 1
    fi
else
    error "WAL файл не найден: ${WAL_FILE}"
    exit 1
fi

