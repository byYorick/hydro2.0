#!/bin/bash
# PostgreSQL Restore Script
# Восстанавливает БД из custom dump

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
DUMP_FILE="${1:-}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-hydro_dev}"
DB_USER="${DB_USER:-hydro}"
DB_PASSWORD="${DB_PASSWORD:-}"
WAL_DIR="${WAL_DIR:-}"

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

# Проверка параметров
if [ -z "${DUMP_FILE}" ]; then
    error "Использование: $0 <dump_file> [--wal-dir <wal_directory>]"
    error "Пример: $0 /backups/postgres/20250101_120000/postgres_hydro_dev_20250101_120000.dump"
    exit 1
fi

# Парсинг опций
while [[ $# -gt 0 ]]; do
    case $1 in
        --wal-dir)
            WAL_DIR="$2"
            shift 2
            ;;
        --dump-file)
            DUMP_FILE="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Проверка наличия файла дампа
if [ ! -f "${DUMP_FILE}" ]; then
    error "Файл дампа не найден: ${DUMP_FILE}"
    exit 1
fi

# Проверка наличия pg_restore
if ! command -v pg_restore &> /dev/null; then
    error "pg_restore не найден. Установите PostgreSQL client tools."
    exit 1
fi

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Восстановление PostgreSQL из дампа"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Файл дампа: ${DUMP_FILE}"
log "База данных: ${DB_NAME}"
log "Хост: ${DB_HOST}:${DB_PORT}"
log "Пользователь: ${DB_USER}"

# Экспорт пароля
export PGPASSWORD="${DB_PASSWORD}"

# Проверка подключения к БД
log "Проверка подключения к БД..."
if ! psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "postgres" -c "SELECT 1;" > /dev/null 2>&1; then
    error "Не удалось подключиться к PostgreSQL"
    exit 1
fi
log "✓ Подключение к БД успешно"

# Предупреждение о перезаписи данных
warning "ВНИМАНИЕ: Восстановление перезапишет существующие данные в БД ${DB_NAME}"
if [ -z "${FORCE_RESTORE:-}" ]; then
    read -p "Продолжить? (yes/no): " confirm
    if [ "${confirm}" != "yes" ]; then
        log "Восстановление отменено"
        exit 0
    fi
fi

# Закрытие активных подключений (если возможно)
log "Закрытие активных подключений..."
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "postgres" \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" \
    2>/dev/null || true

# Удаление существующей БД (если нужно)
log "Проверка существования БД..."
if psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "postgres" -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}';" | grep -q 1; then
    log "БД ${DB_NAME} существует, будет пересоздана"
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "postgres" \
        -c "DROP DATABASE IF EXISTS ${DB_NAME};"
    log "БД удалена"
fi

# Создание новой БД
log "Создание новой БД ${DB_NAME}..."
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "postgres" \
    -c "CREATE DATABASE ${DB_NAME};"
log "✓ БД создана"

# Восстановление из дампа
log "Восстановление данных из дампа..."
if pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --verbose \
    --no-owner \
    --no-privileges \
    "${DUMP_FILE}" 2>&1 | tee /tmp/restore.log; then
    
    log "✓ Данные восстановлены из дампа"
    
    # Проверка целостности
    log "Проверка целостности данных..."
    TABLE_COUNT=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
    log "✓ Найдено таблиц: ${TABLE_COUNT}"
    
    # Если указан WAL директорий, предупреждаем о point-in-time recovery
    if [ -n "${WAL_DIR}" ] && [ -d "${WAL_DIR}" ]; then
        warning "WAL директория указана. Для point-in-time recovery используйте специальные процедуры."
        warning "См. документацию PostgreSQL по восстановлению с WAL."
    fi
    
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Восстановление завершено успешно"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
else
    error "Ошибка при восстановлении из дампа"
    error "Проверьте лог: /tmp/restore.log"
    exit 1
fi

