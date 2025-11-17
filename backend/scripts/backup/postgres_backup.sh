#!/bin/bash
# PostgreSQL Backup Script
# Создает полный дамп БД в формате custom

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-hydro_dev}"
DB_USER="${DB_USER:-hydro}"
DB_PASSWORD="${DB_PASSWORD:-}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/postgres/${TIMESTAMP}"

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

# Проверка наличия pg_dump
if ! command -v pg_dump &> /dev/null; then
    error "pg_dump не найден. Установите PostgreSQL client tools."
    exit 1
fi

# Создание директории для бэкапа
mkdir -p "${BACKUP_SUBDIR}"
log "Создана директория для бэкапа: ${BACKUP_SUBDIR}"

# Имя файла бэкапа
BACKUP_FILE="${BACKUP_SUBDIR}/postgres_${DB_NAME}_${TIMESTAMP}.dump"

# Экспорт пароля для pg_dump
export PGPASSWORD="${DB_PASSWORD}"

log "Начало создания бэкапа PostgreSQL..."
log "База данных: ${DB_NAME}"
log "Хост: ${DB_HOST}:${DB_PORT}"
log "Пользователь: ${DB_USER}"

# Создание дампа
if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -Fc \
    -f "${BACKUP_FILE}" \
    --verbose 2>&1 | tee "${BACKUP_SUBDIR}/backup.log"; then
    
    # Проверка размера файла
    if [ -f "${BACKUP_FILE}" ] && [ -s "${BACKUP_FILE}" ]; then
        FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
        log "Бэкап успешно создан: ${BACKUP_FILE}"
        log "Размер файла: ${FILE_SIZE}"
        
        # Создание manifest файла
        cat > "${BACKUP_SUBDIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "database": "${DB_NAME}",
  "host": "${DB_HOST}",
  "port": "${DB_PORT}",
  "backup_file": "postgres_${DB_NAME}_${TIMESTAMP}.dump",
  "size_bytes": $(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null || echo 0),
  "format": "custom",
  "created_by": "postgres_backup.sh"
}
EOF
        log "Manifest создан: ${BACKUP_SUBDIR}/manifest.json"
        echo "${BACKUP_FILE}"
        exit 0
    else
        error "Файл бэкапа пуст или не создан"
        exit 1
    fi
else
    error "Ошибка при создании бэкапа PostgreSQL"
    exit 1
fi

