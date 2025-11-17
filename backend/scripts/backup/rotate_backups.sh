#!/bin/bash
# Backup Rotation Script
# Удаляет старые бэкапы согласно политике retention

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
FULL_BACKUP_RETENTION_DAYS="${FULL_BACKUP_RETENTION_DAYS:-30}"
WAL_RETENTION_DAYS="${WAL_RETENTION_DAYS:-7}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/wal_archive}"

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

log "Начало ротации бэкапов"
log "Директория бэкапов: ${BACKUP_DIR}"
log "Retention полных бэкапов: ${FULL_BACKUP_RETENTION_DAYS} дней"
log "Retention WAL архивов: ${WAL_RETENTION_DAYS} дней"

# Проверка свободного места на диске
check_disk_space() {
    if command -v df &> /dev/null; then
        AVAILABLE=$(df -BG "${BACKUP_DIR}" | tail -1 | awk '{print $4}' | sed 's/G//')
        if [ "${AVAILABLE}" -lt 5 ]; then
            warning "Мало свободного места на диске: ${AVAILABLE}GB"
        else
            log "Свободное место на диске: ${AVAILABLE}GB"
        fi
    fi
}

check_disk_space

# Удаление старых полных бэкапов
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Удаление старых полных бэкапов (старше ${FULL_BACKUP_RETENTION_DAYS} дней)"

DELETED_FULL=0
if [ -d "${BACKUP_DIR}/full" ]; then
    while IFS= read -r -d '' dir; do
        DIR_NAME=$(basename "${dir}")
        log "Удаление старого бэкапа: ${DIR_NAME}"
        rm -rf "${dir}"
        DELETED_FULL=$((DELETED_FULL + 1))
    done < <(find "${BACKUP_DIR}/full" -type d -mtime +${FULL_BACKUP_RETENTION_DAYS} -print0 2>/dev/null)
fi

# Удаление старых компонентных бэкапов
for component in postgres laravel python mqtt docker; do
    if [ -d "${BACKUP_DIR}/${component}" ]; then
        DELETED_COMPONENT=0
        while IFS= read -r -d '' dir; do
            DIR_NAME=$(basename "${dir}")
            rm -rf "${dir}"
            DELETED_COMPONENT=$((DELETED_COMPONENT + 1))
        done < <(find "${BACKUP_DIR}/${component}" -type d -mtime +${FULL_BACKUP_RETENTION_DAYS} -print0 2>/dev/null)
        
        if [ ${DELETED_COMPONENT} -gt 0 ]; then
            log "Удалено ${DELETED_COMPONENT} старых бэкапов компонента: ${component}"
        fi
    fi
done

# Удаление старых WAL архивов
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Удаление старых WAL архивов (старше ${WAL_RETENTION_DAYS} дней)"

DELETED_WAL=0
if [ -d "${WAL_ARCHIVE_DIR}" ]; then
    # Удаление сжатых WAL файлов
    while IFS= read -r -d '' file; do
        FILE_NAME=$(basename "${file}")
        rm -f "${file}"
        DELETED_WAL=$((DELETED_WAL + 1))
    done < <(find "${WAL_ARCHIVE_DIR}" -name "*.wal.gz" -type f -mtime +${WAL_RETENTION_DAYS} -print0 2>/dev/null)
    
    # Удаление несжатых WAL файлов
    while IFS= read -r -d '' file; do
        FILE_NAME=$(basename "${file}")
        rm -f "${file}"
        DELETED_WAL=$((DELETED_WAL + 1))
    done < <(find "${WAL_ARCHIVE_DIR}" -name "*.wal" -type f -mtime +${WAL_RETENTION_DAYS} -print0 2>/dev/null)
fi

# Итоговый отчет
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Ротация бэкапов завершена"
log "Удалено полных бэкапов: ${DELETED_FULL}"
log "Удалено WAL архивов: ${DELETED_WAL}"

# Проверка свободного места после ротации
check_disk_space

log "Ротация завершена успешно"

