#!/bin/bash
# Full Restore Script
# Координирует восстановление всех компонентов системы

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
if [ -z "${BACKUP_DIR}" ]; then
    error "Использование: $0 <backup_directory>"
    error "Пример: $0 /backups/full/20250101_120000"
    exit 1
fi

# Проверка существования директории бэкапа
if [ ! -d "${BACKUP_DIR}" ]; then
    error "Директория бэкапа не найдена: ${BACKUP_DIR}"
    exit 1
fi

# Проверка наличия manifest файла
MANIFEST_FILE="${BACKUP_DIR}/manifest.json"
if [ ! -f "${MANIFEST_FILE}" ]; then
    error "Manifest файл не найден: ${MANIFEST_FILE}"
    exit 1
fi

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Полное восстановление системы"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Директория бэкапа: ${BACKUP_DIR}"

# Чтение manifest
TIMESTAMP=$(jq -r '.timestamp' "${MANIFEST_FILE}" 2>/dev/null || echo "unknown")
log "Временная метка бэкапа: ${TIMESTAMP}"

# Предупреждение
warning "ВНИМАНИЕ: Восстановление перезапишет существующие данные"
warning "Последовательность восстановления:"
warning "  1. PostgreSQL Database"
warning "  2. Laravel Backend"
warning "  3. Python Services (конфигурации)"
warning "  4. MQTT Configuration"
warning "  5. Docker Volumes (опционально)"

if [ -z "${FORCE_RESTORE:-}" ]; then
    read -p "Продолжить? (yes/no): " confirm
    if [ "${confirm}" != "yes" ]; then
        log "Восстановление отменено"
        exit 0
    fi
fi

# Функция для восстановления компонента
restore_component() {
    local component=$1
    local script=$2
    local description=$3
    
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Восстановление компонента: ${description}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ -f "${SCRIPT_DIR}/${script}" ]; then
        export BACKUP_DIR="${BACKUP_DIR}"
        export FORCE_RESTORE=1
        
        if "${SCRIPT_DIR}/${script}" 2>&1; then
            log "✓ ${description} - успешно восстановлен"
            return 0
        else
            error "✗ ${description} - ошибка восстановления"
            return 1
        fi
    else
        error "Скрипт ${script} не найден"
        return 1
    fi
}

# Последовательность восстановления
RESTORE_FAILED=false

# 1. PostgreSQL
if [ -d "${BACKUP_DIR}/postgres" ]; then
    DUMP_FILE=$(find "${BACKUP_DIR}/postgres" -name "*.dump" | head -n 1)
    if [ -n "${DUMP_FILE}" ]; then
        if ! restore_component "postgres" "postgres_restore.sh" "PostgreSQL Database" "${DUMP_FILE}"; then
            RESTORE_FAILED=true
        fi
    else
        warning "PostgreSQL dump не найден, пропускаем"
    fi
else
    warning "PostgreSQL бэкап не найден, пропускаем"
fi

# 2. Laravel
if [ -d "${BACKUP_DIR}/laravel" ]; then
    ARCHIVE_FILE=$(find "${BACKUP_DIR}/laravel" -name "laravel_*.zip" | head -n 1)
    if [ -n "${ARCHIVE_FILE}" ]; then
        if ! restore_component "laravel" "laravel_restore.sh" "Laravel Backend" "${ARCHIVE_FILE}"; then
            RESTORE_FAILED=true
        fi
    else
        warning "Laravel архив не найден, пропускаем"
    fi
else
    warning "Laravel бэкап не найден, пропускаем"
fi

# 3. Python Services (опционально, так как обычно конфигурации восстанавливаются вручную)
if [ -d "${BACKUP_DIR}/python" ]; then
    warning "Python Services: восстановление конфигураций вручную"
    warning "См. архив: ${BACKUP_DIR}/python"
fi

# 4. MQTT (опционально)
if [ -d "${BACKUP_DIR}/mqtt" ]; then
    warning "MQTT: восстановление конфигураций вручную"
    warning "См. архив: ${BACKUP_DIR}/mqtt"
fi

# 5. Docker Volumes (опционально, требует остановки контейнеров)
if [ -d "${BACKUP_DIR}/docker" ]; then
    warning "Docker Volumes: восстановление требует остановки контейнеров"
    warning "См. архивы: ${BACKUP_DIR}/docker"
    warning "Используйте docker_volumes_restore.sh вручную после остановки сервисов"
fi

# Итоговый отчет
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Итоговый отчет восстановления"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "${RESTORE_FAILED}" = false ]; then
    log "✓ Основные компоненты восстановлены успешно"
    log ""
    log "Следующие шаги:"
    log "  1. Проверьте восстановленные данные"
    log "  2. Перезапустите сервисы: docker-compose restart"
    log "  3. Проверьте логи: docker-compose logs"
    log "  4. Выполните миграции Laravel: php artisan migrate --force"
    exit 0
else
    error "Некоторые компоненты не удалось восстановить"
    error "Проверьте ошибки выше и выполните восстановление вручную"
    exit 1
fi

