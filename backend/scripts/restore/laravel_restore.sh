#!/bin/bash
# Laravel Restore Script
# Восстанавливает Laravel из ZIP архива

set -euo pipefail

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
ARCHIVE_FILE="${1:-}"
LARAVEL_DIR="${LARAVEL_DIR:-./laravel}"
BACKUP_TO_RESTORE="${BACKUP_DIR:-}"

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
if [ -z "${ARCHIVE_FILE}" ] && [ -z "${BACKUP_TO_RESTORE}" ]; then
    error "Использование: $0 <archive_file> [--laravel-dir <directory>]"
    error "Или: BACKUP_DIR=/path/to/backup $0"
    exit 1
fi

# Если указана директория бэкапа, ищем архив Laravel
if [ -n "${BACKUP_TO_RESTORE}" ] && [ -z "${ARCHIVE_FILE}" ]; then
    ARCHIVE_FILE=$(find "${BACKUP_TO_RESTORE}" -name "laravel_*.zip" | head -n 1)
    if [ -z "${ARCHIVE_FILE}" ]; then
        error "Архив Laravel не найден в ${BACKUP_TO_RESTORE}"
        exit 1
    fi
    log "Найден архив: ${ARCHIVE_FILE}"
fi

# Проверка наличия файла архива
if [ ! -f "${ARCHIVE_FILE}" ]; then
    error "Файл архива не найден: ${ARCHIVE_FILE}"
    exit 1
fi

# Проверка наличия unzip
if ! command -v unzip &> /dev/null; then
    error "unzip не найден. Установите unzip."
    exit 1
fi

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Восстановление Laravel из архива"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Файл архива: ${ARCHIVE_FILE}"
log "Laravel директория: ${LARAVEL_DIR}"

# Проверка существования Laravel директории
if [ ! -d "${LARAVEL_DIR}" ]; then
    error "Laravel директория не найдена: ${LARAVEL_DIR}"
    exit 1
fi

# Предупреждение о перезаписи данных
warning "ВНИМАНИЕ: Восстановление перезапишет существующие файлы в ${LARAVEL_DIR}"
if [ -z "${FORCE_RESTORE:-}" ]; then
    read -p "Продолжить? (yes/no): " confirm
    if [ "${confirm}" != "yes" ]; then
        log "Восстановление отменено"
        exit 0
    fi
fi

# Временная директория для распаковки
TEMP_DIR=$(mktemp -d)
trap "rm -rf ${TEMP_DIR}" EXIT

log "Распаковка архива..."
if unzip -q "${ARCHIVE_FILE}" -d "${TEMP_DIR}"; then
    log "✓ Архив распакован"
else
    error "Ошибка при распаковке архива"
    exit 1
fi

# Восстановление .env
if [ -f "${TEMP_DIR}/.env" ]; then
    log "Восстановление .env файла..."
    cp "${TEMP_DIR}/.env" "${LARAVEL_DIR}/.env"
    log "✓ .env восстановлен"
else
    warning ".env файл не найден в архиве"
fi

# Восстановление storage/app/ota
if [ -d "${TEMP_DIR}/storage/app/ota" ]; then
    log "Восстановление storage/app/ota..."
    mkdir -p "${LARAVEL_DIR}/storage/app"
    cp -r "${TEMP_DIR}/storage/app/ota" "${LARAVEL_DIR}/storage/app/"
    log "✓ storage/app/ota восстановлен"
else
    warning "storage/app/ota не найден в архиве"
fi

# Восстановление storage/app/public
if [ -d "${TEMP_DIR}/storage/app/public" ]; then
    log "Восстановление storage/app/public..."
    mkdir -p "${LARAVEL_DIR}/storage/app"
    cp -r "${TEMP_DIR}/storage/app/public" "${LARAVEL_DIR}/storage/app/"
    log "✓ storage/app/public восстановлен"
else
    warning "storage/app/public не найден в архиве"
fi

# Восстановление composer.lock
if [ -f "${TEMP_DIR}/composer.lock" ]; then
    log "Восстановление composer.lock..."
    cp "${TEMP_DIR}/composer.lock" "${LARAVEL_DIR}/composer.lock"
    log "✓ composer.lock восстановлен"
else
    warning "composer.lock не найден в архиве"
fi

# Генерация нового APP_KEY при необходимости
if [ -f "${LARAVEL_DIR}/.env" ]; then
    if ! grep -q "APP_KEY=" "${LARAVEL_DIR}/.env" || grep -q "APP_KEY=$" "${LARAVEL_DIR}/.env"; then
        log "Генерация нового APP_KEY..."
        cd "${LARAVEL_DIR}"
        if command -v php &> /dev/null && [ -f "artisan" ]; then
            php artisan key:generate --force 2>/dev/null || warning "Не удалось сгенерировать APP_KEY (возможно, требуется установка зависимостей)"
        else
            warning "PHP или artisan не найдены, пропускаем генерацию APP_KEY"
        fi
    fi
fi

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Восстановление Laravel завершено успешно"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Рекомендуется выполнить:"
log "  cd ${LARAVEL_DIR}"
log "  composer install"
log "  php artisan migrate --force"
log "  php artisan config:clear"
log "  php artisan cache:clear"

