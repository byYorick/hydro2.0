#!/bin/bash
# Docker Volumes Backup Script
# Создает бэкап Docker volumes

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_SUBDIR="${BACKUP_DIR}/docker/${TIMESTAMP}"

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

# Проверка наличия docker
if ! command -v docker &> /dev/null; then
    error "docker не найден. Установите Docker."
    exit 1
fi

# Создание директории для бэкапа
mkdir -p "${BACKUP_SUBDIR}"
log "Создана директория для бэкапа: ${BACKUP_SUBDIR}"

log "Начало создания бэкапа Docker volumes..."

# Список volumes для бэкапа
VOLUMES=("postgres_data" "prometheus_data" "grafana_data" "alertmanager_data")
BACKED_UP_VOLUMES=()

# Бэкап каждого volume
for volume in "${VOLUMES[@]}"; do
    # Проверка существования volume
    if docker volume inspect "${volume}" > /dev/null 2>&1; then
        BACKUP_FILE="${BACKUP_SUBDIR}/${volume}_${TIMESTAMP}.tar.gz"
        
        log "Создание бэкапа volume: ${volume}"
        
        # Создание бэкапа через временный контейнер
        if docker run --rm \
            -v "${volume}:/volume:ro" \
            -v "${BACKUP_SUBDIR}:/backup" \
            alpine \
            tar czf "/backup/${volume}_${TIMESTAMP}.tar.gz" -C /volume .; then
            
            FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
            log "Бэкап volume ${volume} создан: ${FILE_SIZE}"
            BACKED_UP_VOLUMES+=("${volume}")
        else
            error "Ошибка при создании бэкапа volume: ${volume}"
        fi
    else
        warning "Volume ${volume} не найден, пропускаем"
    fi
done

# Проверка, что хотя бы один volume был скопирован
if [ ${#BACKED_UP_VOLUMES[@]} -eq 0 ]; then
    warning "Не найдено ни одного volume для бэкапа"
    # Не выходим с ошибкой, так как volumes могут быть опциональными
fi

# Создание manifest файла
VOLUMES_JSON=$(printf '%s\n' "${BACKED_UP_VOLUMES[@]}" | jq -R . 2>/dev/null | jq -s . 2>/dev/null || echo "[]")
cat > "${BACKUP_SUBDIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "created_by": "docker_volumes_backup.sh",
  "volumes": ${VOLUMES_JSON}
}
EOF
log "Manifest создан: ${BACKUP_SUBDIR}/manifest.json"
log "Бэкап Docker volumes завершен"
echo "${BACKUP_SUBDIR}"

