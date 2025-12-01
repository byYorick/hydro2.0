#!/bin/bash
set -e

# Скрипт удаления PostgreSQL и TimescaleDB
# Использование: sudo ./remove_postgresql.sh

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    log_error "Этот скрипт должен быть запущен с правами root (sudo)"
    exit 1
fi

log_warn "ВНИМАНИЕ: Этот скрипт удалит PostgreSQL и все данные!"
read -p "Вы уверены, что хотите продолжить? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    log_info "Отменено пользователем"
    exit 0
fi

# ============================================================================
# 1. Остановка PostgreSQL
# ============================================================================

log_info "Остановка PostgreSQL..."

# Определяем имя сервиса PostgreSQL
POSTGRES_SERVICE=""
if systemctl list-unit-files 2>/dev/null | grep -q "^postgresql.service"; then
    POSTGRES_SERVICE="postgresql"
elif systemctl list-unit-files 2>/dev/null | grep -q "^postgresql@"; then
    POSTGRES_SERVICE=$(systemctl list-unit-files 2>/dev/null | grep "^postgresql@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
fi

if [ -n "$POSTGRES_SERVICE" ]; then
    log_info "Остановка сервиса: $POSTGRES_SERVICE"
    systemctl stop "$POSTGRES_SERVICE" 2>/dev/null || log_warn "Не удалось остановить сервис (возможно, уже остановлен)"
    systemctl disable "$POSTGRES_SERVICE" 2>/dev/null || log_warn "Не удалось отключить автозапуск"
else
    log_warn "Сервис PostgreSQL не найден, пробуем остановить процессы вручную"
    pkill -x postgres 2>/dev/null || log_warn "Процессы PostgreSQL не найдены"
    sleep 2
fi

# ============================================================================
# 2. Удаление пакетов PostgreSQL
# ============================================================================

log_info "Удаление пакетов PostgreSQL и TimescaleDB..."

# Удаляем TimescaleDB
if dpkg -l | grep -q "timescaledb"; then
    log_info "Удаление TimescaleDB..."
    apt-get remove -y --purge timescaledb-2-postgresql-* 2>/dev/null || true
fi

# Удаляем PostgreSQL
if dpkg -l | grep -q "postgresql"; then
    log_info "Удаление PostgreSQL..."
    apt-get remove -y --purge postgresql-* postgresql-contrib-* 2>/dev/null || true
fi

# Удаляем клиентские утилиты
if dpkg -l | grep -q "postgresql-client"; then
    log_info "Удаление PostgreSQL клиента..."
    apt-get remove -y --purge postgresql-client-* 2>/dev/null || true
fi

# Автоочистка
apt-get autoremove -y -qq
apt-get autoclean -y -qq

# ============================================================================
# 3. Удаление данных и конфигурации
# ============================================================================

log_info "Удаление данных и конфигурации PostgreSQL..."

# Удаляем данные PostgreSQL
if [ -d "/var/lib/postgresql" ]; then
    log_warn "Удаление директории данных: /var/lib/postgresql"
    read -p "Удалить все данные PostgreSQL? (yes/no): " confirm_data
    if [ "$confirm_data" = "yes" ]; then
        rm -rf /var/lib/postgresql
        log_info "Данные PostgreSQL удалены"
    else
        log_info "Данные PostgreSQL сохранены в /var/lib/postgresql"
    fi
fi

# Удаляем конфигурацию
if [ -d "/etc/postgresql" ]; then
    log_info "Удаление конфигурации: /etc/postgresql"
    rm -rf /etc/postgresql
fi

# Удаляем логи
if [ -d "/var/log/postgresql" ]; then
    log_info "Удаление логов: /var/log/postgresql"
    rm -rf /var/log/postgresql
fi

# ============================================================================
# 4. Удаление репозиториев
# ============================================================================

log_info "Удаление репозиториев PostgreSQL и TimescaleDB..."

# Удаляем репозиторий PostgreSQL
if [ -f "/etc/apt/sources.list.d/pgdg.list" ]; then
    log_info "Удаление репозитория PostgreSQL..."
    rm -f /etc/apt/sources.list.d/pgdg.list
    rm -f /etc/apt/keyrings/postgresql.gpg
fi

# Удаляем репозиторий TimescaleDB
if [ -f "/etc/apt/sources.list.d/timescaledb.list" ]; then
    log_info "Удаление репозитория TimescaleDB..."
    rm -f /etc/apt/sources.list.d/timescaledb.list
    rm -f /etc/apt/keyrings/timescaledb.gpg
fi

# Обновляем список пакетов
apt-get update -qq

# ============================================================================
# 5. Удаление пользователя postgres (опционально)
# ============================================================================

if id postgres &>/dev/null; then
    log_warn "Обнаружен пользователь postgres"
    read -p "Удалить пользователя postgres? (yes/no): " confirm_user
    if [ "$confirm_user" = "yes" ]; then
        log_info "Удаление пользователя postgres..."
        userdel -r postgres 2>/dev/null || log_warn "Не удалось удалить пользователя postgres"
    else
        log_info "Пользователь postgres сохранен"
    fi
fi

# ============================================================================
# 6. Финальная проверка
# ============================================================================

log_info "Проверка удаления..."

if command -v psql &> /dev/null; then
    log_warn "Команда psql все еще доступна, возможно установлена из другого источника"
else
    log_info "PostgreSQL клиент удален"
fi

if pgrep -x postgres >/dev/null 2>&1; then
    log_warn "Процессы PostgreSQL все еще запущены"
    log_warn "Выполните: sudo pkill -9 postgres"
else
    log_info "Процессы PostgreSQL остановлены"
fi

if dpkg -l | grep -q "postgresql"; then
    log_warn "Некоторые пакеты PostgreSQL все еще установлены:"
    dpkg -l | grep postgresql
else
    log_info "Все пакеты PostgreSQL удалены"
fi

log_info "Удаление PostgreSQL завершено!"
log_info "Для полной очистки выполните: sudo apt-get autoremove -y && sudo apt-get autoclean"

