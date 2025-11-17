#!/bin/bash
# Master Backup Script
# Координирует создание всех компонентных бэкапов

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/full/${TIMESTAMP}"

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

# Создание директории для полного бэкапа
mkdir -p "${BACKUP_SUBDIR}"
log "Начало полного бэкапа системы"
log "Директория бэкапа: ${BACKUP_SUBDIR}"

# Массив для хранения результатов
BACKUP_RESULTS=()
FAILED_BACKUPS=()

# Функция для выполнения бэкапа компонента
backup_component() {
    local component=$1
    local script=$2
    local description=$3
    
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Бэкап компонента: ${description}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ -f "${SCRIPT_DIR}/${script}" ]; then
        # Экспорт BACKUP_DIR для всех скриптов
        export BACKUP_DIR="${BACKUP_SUBDIR}"
        
        if OUTPUT=$("${SCRIPT_DIR}/${script}" 2>&1); then
            BACKUP_FILE=$(echo "${OUTPUT}" | tail -n 1)
            BACKUP_RESULTS+=("{\"component\":\"${component}\",\"status\":\"success\",\"file\":\"${BACKUP_FILE}\"}")
            log "✓ ${description} - успешно"
        else
            FAILED_BACKUPS+=("${component}")
            BACKUP_RESULTS+=("{\"component\":\"${component}\",\"status\":\"failed\"}")
            error "✗ ${description} - ошибка"
        fi
    else
        error "Скрипт ${script} не найден"
        FAILED_BACKUPS+=("${component}")
        BACKUP_RESULTS+=("{\"component\":\"${component}\",\"status\":\"skipped\",\"reason\":\"script_not_found\"}")
    fi
}

# Выполнение бэкапов компонентов
backup_component "postgres" "postgres_backup.sh" "PostgreSQL Database"
backup_component "laravel" "laravel_backup.sh" "Laravel Backend"
backup_component "python" "python_backup.sh" "Python Services"
backup_component "mqtt" "mqtt_backup.sh" "MQTT Configuration"
backup_component "docker" "docker_volumes_backup.sh" "Docker Volumes"

# Создание общего manifest файла
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Создание общего manifest файла"

RESULTS_JSON=$(printf '%s\n' "${BACKUP_RESULTS[@]}" | jq -s . 2>/dev/null || echo "[]")
FAILED_JSON=$(printf '%s\n' "${FAILED_BACKUPS[@]}" | jq -R . 2>/dev/null | jq -s . 2>/dev/null || echo "[]")

cat > "${BACKUP_SUBDIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "backup_dir": "${BACKUP_SUBDIR}",
  "created_by": "full_backup.sh",
  "components": ${RESULTS_JSON},
  "failed_components": ${FAILED_JSON},
  "total_components": ${#BACKUP_RESULTS[@]},
  "failed_count": ${#FAILED_BACKUPS[@]},
  "success_count": $((${#BACKUP_RESULTS[@]} - ${#FAILED_BACKUPS[@]}))
}
EOF

# Проверка целостности бэкапов
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Проверка целостности бэкапов"

INTEGRITY_CHECK_PASSED=true

# Проверка наличия файлов бэкапов
for result in "${BACKUP_RESULTS[@]}"; do
    STATUS=$(echo "${result}" | jq -r '.status' 2>/dev/null || echo "unknown")
    if [ "${STATUS}" = "success" ]; then
        FILE=$(echo "${result}" | jq -r '.file' 2>/dev/null || echo "")
        if [ -n "${FILE}" ] && [ -f "${FILE}" ]; then
            FILE_SIZE=$(stat -f%z "${FILE}" 2>/dev/null || stat -c%s "${FILE}" 2>/dev/null || echo 0)
            if [ "${FILE_SIZE}" -eq 0 ]; then
                warning "Файл бэкапа пуст: ${FILE}"
                INTEGRITY_CHECK_PASSED=false
            fi
        else
            warning "Файл бэкапа не найден: ${FILE}"
            INTEGRITY_CHECK_PASSED=false
        fi
    fi
done

# Итоговый отчет
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Итоговый отчет"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ${#FAILED_BACKUPS[@]} -eq 0 ] && [ "${INTEGRITY_CHECK_PASSED}" = true ]; then
    log "✓ Все бэкапы успешно созданы и проверены"
    log "✓ Директория бэкапа: ${BACKUP_SUBDIR}"
    TOTAL_SIZE=$(du -sh "${BACKUP_SUBDIR}" | cut -f1)
    log "✓ Общий размер: ${TOTAL_SIZE}"
    echo "${BACKUP_SUBDIR}"
    exit 0
else
    error "Некоторые бэкапы не удались или не прошли проверку целостности"
    if [ ${#FAILED_BACKUPS[@]} -gt 0 ]; then
        error "Неудачные компоненты: ${FAILED_BACKUPS[*]}"
    fi
    exit 1
fi

