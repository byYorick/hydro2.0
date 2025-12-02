#!/bin/bash
set -e
# Включаем режим отладки для лучшего логирования
set -o pipefail

# Скрипт развертывания проекта Hydro 2.0 на сервере без Docker
# Использование: sudo ./deploy.sh [production|development]

ENVIRONMENT="${1:-production}"
PROJECT_DIR="/opt/hydro/hydro2.0"
APP_USER="hydro"
APP_GROUP="hydro"
LARAVEL_DIR="${PROJECT_DIR}/backend/laravel"
SERVICES_DIR="${PROJECT_DIR}/backend/services"

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
    log_error "Пожалуйста, запустите скрипт с правами root (sudo ./deploy.sh)"
    exit 1
fi

log_info "Начинаем развертывание проекта Hydro 2.0 в режиме: $ENVIRONMENT"

# ============================================================================
# 1. Установка системных зависимостей
# ============================================================================

log_info "Обновление списка пакетов..."
log_info "Это может занять некоторое время..."

# Выполняем apt-get update с таймаутом и логированием
if timeout 300 apt-get update 2>&1 | tee /tmp/apt-update.log; then
    log_info "Список пакетов обновлен успешно"
else
    UPDATE_EXIT=$?
    if [ $UPDATE_EXIT -eq 124 ]; then
        log_error "Обновление списка пакетов превысило таймаут (5 минут)"
        log_error "Проверьте подключение к интернету и доступность репозиториев"
        exit 1
    else
        log_warn "Обновление списка пакетов завершилось с ошибкой (код: $UPDATE_EXIT)"
        log_warn "Проверьте логи: tail -20 /tmp/apt-update.log"
        log_warn "Продолжаем работу, но некоторые пакеты могут быть недоступны"
    fi
fi

log_info "Установка базовых утилит..."
apt-get install -y -qq \
    curl \
    wget \
    git \
    build-essential \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    supervisor \
    nginx \
    postgresql-client \
    libpq-dev \
    python3-pip \
    gcc \
    gettext \
    unzip

# Установка Python 3.11 (требуется репозиторий deadsnakes для старых версий Ubuntu)
log_info "Установка Python 3.11..."
PYTHON_VERSION="3.11"
if ! apt-cache show python${PYTHON_VERSION} &>/dev/null; then
    log_info "Python ${PYTHON_VERSION} не найден в стандартных репозиториях, добавляем deadsnakes PPA..."
    add-apt-repository -y ppa:deadsnakes/ppa
    if ! timeout 180 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
        UPDATE_EXIT=$?
        if [ $UPDATE_EXIT -eq 124 ]; then
            log_error "Обновление списка пакетов превысило таймаут (3 минуты)"
            exit 1
        else
            log_warn "Ошибка при обновлении списка пакетов (код: $UPDATE_EXIT)"
        fi
    fi
fi

# Проверяем доступность Python 3.11, если нет - используем доступную версию
if apt-cache show python${PYTHON_VERSION} &>/dev/null; then
    apt-get install -y -qq \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-dev \
        python${PYTHON_VERSION}-venv
    PYTHON_CMD="python${PYTHON_VERSION}"
    log_info "Python ${PYTHON_VERSION} установлен"
else
    log_warn "Python ${PYTHON_VERSION} недоступен, используем системную версию Python 3"
    # Устанавливаем системный Python 3 и его зависимости
    apt-get install -y -qq \
        python3 \
        python3-dev \
        python3-venv
    PYTHON_CMD="python3"
    # Определяем версию установленного Python
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
    log_warn "Используется Python ${PYTHON_VERSION} (требуется Python 3.11+, возможны проблемы совместимости)"
fi

# ============================================================================
# 2. Установка PHP 8.2
# ============================================================================

log_info "Установка PHP 8.2 и расширений..."
if ! command -v php &> /dev/null; then
    PHP_INSTALLED=false
elif php -v 2>/dev/null | grep -q "8.2"; then
    PHP_INSTALLED=true
else
    PHP_INSTALLED=false
fi

if [ "$PHP_INSTALLED" = "false" ]; then
    add-apt-repository -y ppa:ondrej/php
    if ! timeout 180 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
        UPDATE_EXIT=$?
        if [ $UPDATE_EXIT -eq 124 ]; then
            log_error "Обновление списка пакетов превысило таймаут (3 минуты)"
            exit 1
        else
            log_warn "Ошибка при обновлении списка пакетов (код: $UPDATE_EXIT)"
        fi
    fi
    apt-get install -y -qq \
        php8.2 \
        php8.2-fpm \
        php8.2-cli \
        php8.2-common \
        php8.2-mysql \
        php8.2-pgsql \
        php8.2-zip \
        php8.2-gd \
        php8.2-mbstring \
        php8.2-curl \
        php8.2-xml \
        php8.2-bcmath \
        php8.2-intl \
        php8.2-redis \
        php8.2-opcache
else
    log_info "PHP 8.2 уже установлен"
fi

# ============================================================================
# 3. Установка Composer
# ============================================================================

log_info "Установка Composer..."
if ! command -v composer &> /dev/null; then
    curl -sS https://getcomposer.org/installer | php
    mv composer.phar /usr/local/bin/composer
    chmod +x /usr/local/bin/composer
else
    log_info "Composer уже установлен"
fi

# ============================================================================
# 4. Установка Node.js 20
# ============================================================================

log_info "Установка Node.js 20..."
if ! command -v node &> /dev/null || ! node -v | grep -q "v20"; then
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
    if ! timeout 180 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
        UPDATE_EXIT=$?
        if [ $UPDATE_EXIT -eq 124 ]; then
            log_error "Обновление списка пакетов превысило таймаут (3 минуты)"
            exit 1
        else
            log_warn "Ошибка при обновлении списка пакетов (код: $UPDATE_EXIT)"
        fi
    fi
    apt-get install -y -qq nodejs
else
    log_info "Node.js 20 уже установлен"
fi

# ============================================================================
# 5. Установка PostgreSQL с TimescaleDB
# ============================================================================

log_info "Установка PostgreSQL 16 с TimescaleDB..."

# Проверяем, установлен ли PostgreSQL правильно
POSTGRES_INSTALLED=false
if command -v psql &> /dev/null; then
    # Проверяем, что это действительно PostgreSQL 16
    PSQL_VERSION=$(psql --version 2>/dev/null | grep -oP '\d+' | head -1 || echo "")
    if [ "$PSQL_VERSION" = "16" ]; then
        # Проверяем, что пакет установлен
        if dpkg -l | grep -q "^ii.*postgresql-16"; then
            POSTGRES_INSTALLED=true
            log_info "PostgreSQL 16 уже установлен"
        fi
    fi
fi

if [ "$POSTGRES_INSTALLED" = "false" ]; then
    # ============================================================================
    # Полная установка PostgreSQL 16
    # ============================================================================
    
    log_info "Начинаем полную установку PostgreSQL 16..."
    
    # Шаг 1: Добавление репозитория PostgreSQL
    log_info "Шаг 1: Добавление репозитория PostgreSQL..."
    mkdir -p /etc/apt/keyrings
    
    # Удаляем старые файлы, если они есть
    rm -f /etc/apt/sources.list.d/pgdg.list /etc/apt/keyrings/postgresql.gpg
    
    # Определяем кодовое имя дистрибутива
    DISTRO_CODENAME=$(lsb_release -cs)
    log_info "Кодовое имя дистрибутива: $DISTRO_CODENAME"
    
    # Добавляем репозиторий PostgreSQL
    log_info "Загрузка GPG ключа PostgreSQL..."
    if ! wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg; then
        log_error "Не удалось загрузить GPG ключ PostgreSQL"
        exit 1
    fi
    chmod 644 /etc/apt/keyrings/postgresql.gpg
    
    log_info "Добавление репозитория в sources.list..."
    echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $DISTRO_CODENAME-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    
    # Проверяем, что файл создан
    if [ ! -f "/etc/apt/sources.list.d/pgdg.list" ]; then
        log_error "Не удалось создать файл репозитория"
        exit 1
    fi
    
    # Шаг 2: Обновление списка пакетов
    log_info "Шаг 2: Обновление списка пакетов..."
    if ! apt-get update; then
        log_error "Ошибка при обновлении списка пакетов"
        log_error "Проверьте доступность репозитория: cat /etc/apt/sources.list.d/pgdg.list"
        exit 1
    fi
    
    # Проверяем доступность пакетов
    log_info "Проверка доступности пакетов PostgreSQL 16..."
    if ! apt-cache show postgresql-16 &>/dev/null; then
        log_error "Пакет postgresql-16 не найден в репозитории"
        log_error "Проверьте репозиторий: apt-cache search postgresql-16"
        exit 1
    fi
    
    # Шаг 3: Установка PostgreSQL 16
    log_info "Шаг 3: Установка PostgreSQL 16 и contrib..."
    if ! apt-get install -y postgresql-16 postgresql-contrib-16; then
        log_error "Ошибка при установке PostgreSQL 16"
        log_error "Проверьте логи: tail -50 /var/log/apt/history.log"
        exit 1
    fi
    
    # Шаг 4: Проверка установки PostgreSQL
    log_info "Шаг 4: Проверка установки PostgreSQL..."
    
    # Проверяем наличие команды psql
    if ! command -v psql &> /dev/null; then
        log_warn "Команда psql не найдена в PATH, ищем в стандартных местах..."
        # Добавляем путь к PostgreSQL в PATH для текущей сессии
        export PATH="$PATH:/usr/lib/postgresql/16/bin"
        if ! command -v psql &> /dev/null; then
            log_error "PostgreSQL установлен, но команда psql недоступна"
            log_error "Проверьте установку: dpkg -l | grep postgresql"
            log_error "Попробуйте: export PATH=\$PATH:/usr/lib/postgresql/16/bin"
            exit 1
        fi
    fi
    
    # Проверяем версию
    PSQL_VERSION=$(psql --version 2>/dev/null | head -1)
    if [ -z "$PSQL_VERSION" ]; then
        log_error "Не удалось определить версию PostgreSQL"
        exit 1
    fi
    log_info "Установлена версия: $PSQL_VERSION"
    
    # Проверяем установленные пакеты
    INSTALLED_PACKAGES=$(dpkg -l | grep "^ii.*postgresql-16" | wc -l)
    log_info "Установлено пакетов PostgreSQL 16: $INSTALLED_PACKAGES"
    
    if [ "$INSTALLED_PACKAGES" -lt 2 ]; then
        log_warn "Установлено меньше пакетов, чем ожидалось"
    fi
    
    # Шаг 5: Установка TimescaleDB
    log_info "Шаг 5: Установка TimescaleDB..."
    
    # Добавляем репозиторий TimescaleDB
    log_info "Добавление репозитория TimescaleDB..."
    rm -f /etc/apt/sources.list.d/timescaledb.list /etc/apt/keyrings/timescaledb.gpg
    
    # Определяем кодовое имя для Ubuntu
    UBUNTU_CODENAME=$(lsb_release -c -s)
    log_info "Кодовое имя Ubuntu: $UBUNTU_CODENAME"
    
    log_info "Загрузка GPG ключа TimescaleDB..."
    if ! wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg; then
        log_warn "Не удалось загрузить GPG ключ TimescaleDB"
        log_warn "Продолжаем без TimescaleDB"
    else
        chmod 644 /etc/apt/keyrings/timescaledb.gpg
        echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ $UBUNTU_CODENAME main" > /etc/apt/sources.list.d/timescaledb.list
        
        log_info "Обновление списка пакетов для TimescaleDB..."
        if ! apt-get update -qq; then
            log_warn "Ошибка при обновлении списка пакетов для TimescaleDB"
            log_warn "Продолжаем без TimescaleDB"
        else
            # Проверяем доступность пакета
            if apt-cache show timescaledb-2-postgresql-16 &>/dev/null; then
                log_info "Установка TimescaleDB..."
                if apt-get install -y timescaledb-2-postgresql-16; then
                    log_info "TimescaleDB установлен успешно"
                    
                    # Настройка TimescaleDB
                    log_info "Настройка TimescaleDB..."
                    if command -v timescaledb-tune &> /dev/null; then
                        if timescaledb-tune --quiet --yes; then
                            log_info "TimescaleDB настроен успешно"
                        else
                            log_warn "Не удалось настроить TimescaleDB автоматически"
                            log_warn "Выполните вручную: sudo timescaledb-tune"
                        fi
                    else
                        log_warn "Команда timescaledb-tune не найдена"
                    fi
                else
                    log_warn "Ошибка при установке TimescaleDB"
                    log_warn "Продолжаем без TimescaleDB (можно установить позже)"
                fi
            else
                log_warn "Пакет timescaledb-2-postgresql-16 не найден в репозитории"
                log_warn "Продолжаем без TimescaleDB"
            fi
        fi
    fi
    
    # Финальная проверка установки
    log_info "Финальная проверка установки PostgreSQL..."
    
    # Проверяем наличие основных команд
    for cmd in psql pg_ctl pg_config; do
        if command -v "$cmd" &> /dev/null; then
            log_info "  ✓ $cmd доступен"
        else
            log_warn "  ✗ $cmd не найден"
        fi
    done
    
    # Проверяем установленные пакеты
    log_info "Установленные пакеты PostgreSQL:"
    dpkg -l | grep "^ii.*postgresql" | awk '{print "  - " $2 " (" $3 ")"}'
    
    log_info "PostgreSQL 16 установлен и готов к использованию!"
fi

# Настройка и запуск PostgreSQL
log_info "Настройка и запуск PostgreSQL..."

# Определяем имя сервиса PostgreSQL (может быть postgresql, postgresql@16-main и т.д.)
POSTGRES_SERVICE=""

# Пробуем разные варианты поиска сервиса
if systemctl list-unit-files 2>/dev/null | grep -q "^postgresql.service"; then
    POSTGRES_SERVICE="postgresql"
elif systemctl list-unit-files 2>/dev/null | grep -q "^postgresql@"; then
    # Находим первый доступный сервис postgresql@
    POSTGRES_SERVICE=$(systemctl list-unit-files 2>/dev/null | grep "^postgresql@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
elif systemctl list-units 2>/dev/null | grep -q "postgresql"; then
    # Пробуем найти запущенный сервис
    POSTGRES_SERVICE=$(systemctl list-units 2>/dev/null | grep "postgresql" | grep -v "@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
fi

# Если не нашли через systemctl, пробуем найти через установленные пакеты
if [ -z "$POSTGRES_SERVICE" ]; then
    # Проверяем, установлен ли postgresql-16
    if dpkg -l | grep -q "postgresql-16"; then
        # В Debian/Ubuntu с postgresql-16 обычно используется postgresql@16-main
        if systemctl list-unit-files 2>/dev/null | grep -q "postgresql@16-main"; then
            POSTGRES_SERVICE="postgresql@16-main"
        elif systemctl list-unit-files 2>/dev/null | grep -q "postgresql@16"; then
            POSTGRES_SERVICE=$(systemctl list-unit-files 2>/dev/null | grep "postgresql@16" | head -1 | awk '{print $1}' | sed 's/\.service$//')
        fi
    fi
fi

# Запускаем PostgreSQL
if [ -n "$POSTGRES_SERVICE" ]; then
    log_info "Найден сервис PostgreSQL: $POSTGRES_SERVICE"
    log_info "Включение автозапуска PostgreSQL..."
    systemctl enable "$POSTGRES_SERVICE" 2>/dev/null || log_warn "Не удалось включить сервис $POSTGRES_SERVICE (возможно, уже включен)"
    
    log_info "Запуск PostgreSQL..."
    systemctl start "$POSTGRES_SERVICE" 2>/dev/null || {
        log_error "Не удалось запустить сервис $POSTGRES_SERVICE"
        log_error "Проверьте статус: systemctl status $POSTGRES_SERVICE"
        log_error "Проверьте логи: journalctl -u $POSTGRES_SERVICE -n 50"
        exit 1
    }
    
    # Ждем, пока PostgreSQL запустится
    log_info "Ожидание запуска PostgreSQL..."
    max_wait=30
    waited=0
    while [ $waited -lt $max_wait ]; do
        if systemctl is-active --quiet "$POSTGRES_SERVICE"; then
            log_info "PostgreSQL запущен успешно"
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done
    
    if ! systemctl is-active --quiet "$POSTGRES_SERVICE"; then
        log_error "PostgreSQL не запустился за $max_wait секунд"
        log_error "Проверьте статус: systemctl status $POSTGRES_SERVICE"
        exit 1
    fi
    
    # Дополнительная проверка - процесс должен быть запущен
    if ! pgrep -x postgres >/dev/null 2>&1; then
        log_error "Процесс PostgreSQL не запущен, хотя сервис активен"
        exit 1
    fi
    
    log_info "Процесс PostgreSQL запущен (PID: $(pgrep -x postgres | head -1))"
else
    log_warn "Не удалось определить имя сервиса PostgreSQL"
    
    # Проверяем, запущен ли процесс
    if pgrep -x postgres >/dev/null 2>&1; then
        log_info "Процесс PostgreSQL запущен (PID: $(pgrep -x postgres | head -1))"
        log_info "Продолжаем работу с существующим процессом PostgreSQL"
    else
        log_error "PostgreSQL не запущен и не удалось определить способ запуска"
        log_error "Попробуйте запустить вручную:"
        log_error "  - sudo systemctl start postgresql"
        log_error "  - Или проверьте доступные сервисы: systemctl list-unit-files | grep postgresql"
        exit 1
    fi
fi

# Настройка PostgreSQL для приема TCP/IP подключений
log_info "Настройка PostgreSQL для TCP/IP подключений..."
# Находим конфигурационный файл PostgreSQL (проверяем все возможные пути)
PG_CONF=""
PG_HBA=""

# Сначала пробуем найти через find (самый надежный способ)
PG_CONF=$(find /etc/postgresql -name "postgresql.conf" -type f 2>/dev/null | head -1)
if [ -n "$PG_CONF" ]; then
    PG_HBA=$(dirname "$PG_CONF")/pg_hba.conf
    log_info "Найден конфигурационный файл через find: $PG_CONF"
fi

# Если не нашли через find, пробуем через psql
if [ -z "$PG_CONF" ] && command -v psql &> /dev/null; then
    # Получаем полную версию PostgreSQL
    PG_FULL_VERSION=$(psql --version 2>/dev/null | awk '{print $3}' || echo "")
    if [ -n "$PG_FULL_VERSION" ]; then
        # Пробуем разные варианты путей
        PG_MAJOR=$(echo "$PG_FULL_VERSION" | cut -d. -f1)
        PG_MINOR=$(echo "$PG_FULL_VERSION" | cut -d. -f2)
        
        # Вариант 1: /etc/postgresql/16/main/
        if [ -f "/etc/postgresql/${PG_MAJOR}/main/postgresql.conf" ]; then
            PG_CONF="/etc/postgresql/${PG_MAJOR}/main/postgresql.conf"
            PG_HBA="/etc/postgresql/${PG_MAJOR}/main/pg_hba.conf"
        # Вариант 2: /etc/postgresql/16.10/main/
        elif [ -f "/etc/postgresql/${PG_FULL_VERSION}/main/postgresql.conf" ]; then
            PG_CONF="/etc/postgresql/${PG_FULL_VERSION}/main/postgresql.conf"
            PG_HBA="/etc/postgresql/${PG_FULL_VERSION}/main/pg_hba.conf"
        fi
    fi
fi

# Если не нашли, пробуем найти через pg_config
if [ -z "$PG_CONF" ] && command -v pg_config &> /dev/null; then
    PG_DATA=$(pg_config --sysconfdir 2>/dev/null || echo "")
    if [ -n "$PG_DATA" ] && [ -f "$PG_DATA/postgresql.conf" ]; then
        PG_CONF="$PG_DATA/postgresql.conf"
        PG_HBA="$PG_DATA/pg_hba.conf"
    fi
fi

# Если все еще не нашли, пробуем найти через переменные окружения процесса postgres
if [ -z "$PG_CONF" ] && pgrep -x postgres >/dev/null 2>&1; then
    # Пробуем найти через ps aux
    PG_DATA_DIR=$(ps aux | grep "[p]ostgres:" | head -1 | grep -oP '\-D\s+\K[^\s]+' || ps aux | grep "[p]ostgres:" | head -1 | awk '{for(i=1;i<=NF;i++) if($i=="-D" && i<NF) print $(i+1)}' || echo "")
    if [ -n "$PG_DATA_DIR" ] && [ -f "$PG_DATA_DIR/postgresql.conf" ]; then
        PG_CONF="$PG_DATA_DIR/postgresql.conf"
        PG_HBA="$PG_DATA_DIR/pg_hba.conf"
        log_info "Найден конфигурационный файл через процесс postgres: $PG_CONF"
    fi
fi

if [ -f "$PG_CONF" ]; then
    log_info "Найден конфигурационный файл: $PG_CONF"
    
    # Настраиваем listen_addresses для приема подключений на localhost
    if ! grep -q "^listen_addresses" "$PG_CONF"; then
        echo "listen_addresses = 'localhost'" >> "$PG_CONF"
        log_info "Добавлен listen_addresses в $PG_CONF"
    elif ! grep -q "^listen_addresses.*localhost" "$PG_CONF" && ! grep -q "^listen_addresses.*'\*'" "$PG_CONF"; then
        # Комментируем старую строку и добавляем новую
        sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
        sed -i "s/^listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
        log_info "Обновлен listen_addresses в $PG_CONF"
    fi
    
    # Перезапускаем PostgreSQL для применения изменений
    if [ -n "$POSTGRES_SERVICE" ]; then
        log_info "Перезапуск PostgreSQL для применения изменений..."
        systemctl restart "$POSTGRES_SERVICE" 2>/dev/null || {
            log_warn "Не удалось перезапустить через systemctl"
            log_warn "Изменения в конфигурации применены, но требуется перезапуск PostgreSQL вручную"
            log_warn "Выполните: sudo systemctl restart $POSTGRES_SERVICE"
        }
        sleep 5
    else
        log_warn "Сервис PostgreSQL не определен, изменения в конфигурации применены"
        log_warn "Требуется перезапуск PostgreSQL вручную для применения изменений"
        log_warn "Найдите способ перезапуска PostgreSQL на вашей системе"
    fi
else
    log_warn "Конфигурационный файл PostgreSQL не найден"
    log_warn "Попробуйте найти вручную: find /etc/postgresql -name postgresql.conf"
    log_warn "Или проверьте: psql --version и pg_config --sysconfdir"
fi

# Проверяем pg_hba.conf для разрешения подключений
if [ -f "$PG_HBA" ]; then
    log_info "Найден файл pg_hba.conf: $PG_HBA"
    if ! grep -q "^host.*all.*all.*127.0.0.1/32.*md5" "$PG_HBA" && ! grep -q "^host.*all.*all.*127.0.0.1/32.*password" "$PG_HBA" && ! grep -q "^host.*all.*all.*127.0.0.1/32.*trust" "$PG_HBA"; then
        echo "host    all             all             127.0.0.1/32            md5" >> "$PG_HBA"
        log_info "Добавлено правило в pg_hba.conf для подключений с localhost"
        
        # Перезапускаем PostgreSQL для применения изменений
        if [ -n "$POSTGRES_SERVICE" ]; then
            log_info "Перезапуск PostgreSQL для применения изменений pg_hba.conf..."
            systemctl restart "$POSTGRES_SERVICE" 2>/dev/null || {
                log_warn "Не удалось перезапустить через systemctl"
                log_warn "Изменения в pg_hba.conf применены, но требуется перезапуск PostgreSQL вручную"
            }
            sleep 5
        else
            log_warn "Сервис PostgreSQL не определен, изменения в pg_hba.conf применены"
            log_warn "Требуется перезапуск PostgreSQL вручную для применения изменений"
            log_warn "Найдите способ перезапуска PostgreSQL на вашей системе"
        fi
    else
        log_info "Правило для localhost уже существует в pg_hba.conf"
    fi
else
    log_warn "Файл pg_hba.conf не найден: $PG_HBA"
fi

# Создание базы данных и пользователя
log_info "Создание базы данных и пользователя PostgreSQL..."
if [ "$ENVIRONMENT" = "production" ]; then
    DB_NAME="hydro"
    DB_USER="hydro"
    DB_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 32)}"
else
    DB_NAME="hydro_dev"
    DB_USER="hydro"
    DB_PASSWORD="hydro"
fi

# Проверяем, существует ли пользователь postgres
if ! id postgres &>/dev/null; then
    log_error "Пользователь postgres не существует"
    log_error "PostgreSQL установлен неправильно"
    exit 1
fi

# Создаем пользователя БД
log_info "Создание пользователя БД: ${DB_USER}..."
if sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}';" 2>/dev/null | grep -q "1"; then
    log_info "Пользователь ${DB_USER} уже существует, обновляем пароль..."
    sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || {
        log_error "Не удалось обновить пароль пользователя ${DB_USER}"
        exit 1
    }
else
    log_info "Создание нового пользователя ${DB_USER}..."
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || {
        log_error "Не удалось создать пользователя ${DB_USER}"
        exit 1
    }
fi

# Даем пользователю необходимые права
log_info "Настройка прав пользователя ${DB_USER}..."
sudo -u postgres psql -c "ALTER USER ${DB_USER} CREATEDB;" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH SUPERUSER;" 2>/dev/null || true

# Создаем базу данных
log_info "Создание базы данных: ${DB_NAME}..."
if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
    log_info "База данных ${DB_NAME} уже существует"
    # Обновляем владельца базы данных
    sudo -u postgres psql -c "ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};" 2>/dev/null || true
else
    log_info "Создание новой базы данных ${DB_NAME}..."
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || {
        log_error "Не удалось создать базу данных ${DB_NAME}"
        exit 1
    }
fi

# Устанавливаем расширение TimescaleDB
log_info "Установка расширения TimescaleDB..."
sudo -u postgres psql -d ${DB_NAME} -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>/dev/null || log_warn "Расширение TimescaleDB не установлено (можно установить позже)"

log_info "Пароль PostgreSQL для пользователя ${DB_USER}: ${DB_PASSWORD}"
log_warn "Сохраните этот пароль! Он понадобится для настройки .env файла"

# ============================================================================
# 6. Установка Redis
# ============================================================================

log_info "Установка Redis..."
if ! command -v redis-server &> /dev/null; then
    log_info "Установка Redis..."
    if ! apt-get install -y redis-server; then
        log_error "Ошибка при установке Redis"
        exit 1
    fi
    log_info "Redis установлен успешно"
else
    log_info "Redis уже установлен"
fi

# Настройка Redis
log_info "Настройка Redis..."
if [ -f "/etc/redis/redis.conf" ]; then
    # Настройка supervised для systemd
    if grep -q "^supervised no" /etc/redis/redis.conf; then
        sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
        log_info "Настроен supervised для systemd"
    fi
    
    # Настройка maxmemory
    if grep -q "^# maxmemory <bytes>" /etc/redis/redis.conf; then
        sed -i 's/^# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf
        log_info "Настроен maxmemory: 512mb"
    elif ! grep -q "^maxmemory" /etc/redis/redis.conf; then
        echo "maxmemory 512mb" >> /etc/redis/redis.conf
        log_info "Добавлен maxmemory: 512mb"
    fi
    
    # Настройка maxmemory-policy
    if grep -q "^# maxmemory-policy noeviction" /etc/redis/redis.conf; then
        sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
        log_info "Настроен maxmemory-policy: allkeys-lru"
    elif ! grep -q "^maxmemory-policy" /etc/redis/redis.conf; then
        echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
        log_info "Добавлен maxmemory-policy: allkeys-lru"
    fi
    
    # КРИТИЧНО: Создаем директорию для логов Redis
    REDIS_LOG_DIR=""
    REDIS_LOG_FILE=$(grep "^logfile " /etc/redis/redis.conf 2>/dev/null | awk '{print $2}' | head -1 || echo "")
    if [ -n "$REDIS_LOG_FILE" ]; then
        REDIS_LOG_DIR=$(dirname "$REDIS_LOG_FILE")
        # Если путь относительный, используем стандартную директорию
        if [ "$REDIS_LOG_DIR" = "." ] || [ -z "$REDIS_LOG_DIR" ]; then
            REDIS_LOG_DIR="/var/log/redis"
        fi
    else
        # Если logfile не указан, используем стандартную директорию
        REDIS_LOG_DIR="/var/log/redis"
    fi
    
    log_info "Создание директории для логов Redis: $REDIS_LOG_DIR"
    mkdir -p "$REDIS_LOG_DIR"
    chown redis:redis "$REDIS_LOG_DIR" 2>/dev/null || true
    chmod 755 "$REDIS_LOG_DIR" 2>/dev/null || true
    
    # Если logfile не указан или указан неправильно, добавляем его
    if [ -z "$REDIS_LOG_FILE" ] || [ "$REDIS_LOG_FILE" = "" ]; then
        if ! grep -q "^logfile " /etc/redis/redis.conf; then
            echo "logfile $REDIS_LOG_DIR/redis-server.log" >> /etc/redis/redis.conf
            log_info "Добавлен logfile: $REDIS_LOG_DIR/redis-server.log"
        fi
    fi
    
    # Проверяем права доступа к конфигурации
    chown redis:redis /etc/redis/redis.conf 2>/dev/null || true
    chmod 640 /etc/redis/redis.conf 2>/dev/null || true
else
    log_warn "Файл конфигурации Redis не найден: /etc/redis/redis.conf"
    # Создаем стандартную директорию для логов на всякий случай
    mkdir -p /var/log/redis
    chown redis:redis /var/log/redis 2>/dev/null || true
    chmod 755 /var/log/redis 2>/dev/null || true
fi

# Проверяем директорию для данных Redis
REDIS_DIR="/var/lib/redis"
if [ -f "/etc/redis/redis.conf" ]; then
    REDIS_DIR=$(grep "^dir " /etc/redis/redis.conf 2>/dev/null | awk '{print $2}' | head -1 || echo "/var/lib/redis")
fi

if [ ! -d "$REDIS_DIR" ]; then
    log_info "Создание директории для данных Redis: $REDIS_DIR"
    mkdir -p "$REDIS_DIR"
    chown redis:redis "$REDIS_DIR" 2>/dev/null || true
    chmod 755 "$REDIS_DIR" 2>/dev/null || true
fi

# Включаем автозапуск Redis
log_info "Включение автозапуска Redis..."
if ! systemctl enable redis-server 2>/dev/null; then
    log_warn "Не удалось включить автозапуск Redis (возможно, уже включен или используется SysV)"
    # Пробуем через update-rc.d для SysV
    if command -v update-rc.d &> /dev/null; then
        update-rc.d redis-server enable 2>/dev/null || true
    fi
fi

# Запускаем Redis
log_info "Запуск Redis..."
if ! systemctl start redis-server; then
    log_warn "Не удалось запустить Redis через systemctl, выполняем диагностику..."
    
    # Диагностика: проверяем логи
    REDIS_ERROR=$(journalctl -u redis-server.service -n 20 --no-pager 2>/dev/null | grep -i "error\|fatal\|failed" | head -3 || echo "")
    if [ -n "$REDIS_ERROR" ]; then
        log_info "Ошибки из логов Redis:"
        echo "$REDIS_ERROR" | while read line; do
            log_info "  $line"
        done
    fi
    
    # Исправление проблем
    
    # 1. Проверяем и исправляем права на директорию данных
    if [ -d "$REDIS_DIR" ]; then
        log_info "Проверка прав доступа к директории данных: $REDIS_DIR"
        chown -R redis:redis "$REDIS_DIR" 2>/dev/null || true
        chmod 755 "$REDIS_DIR" 2>/dev/null || true
        
        # Проверяем файлы в директории
        if [ -f "$REDIS_DIR/dump.rdb" ]; then
            chown redis:redis "$REDIS_DIR/dump.rdb" 2>/dev/null || true
            chmod 660 "$REDIS_DIR/dump.rdb" 2>/dev/null || true
        fi
    fi
    
    # 2. Проверяем, не занят ли порт 6379
    if netstat -tlnp 2>/dev/null | grep -q ":6379" || ss -tlnp 2>/dev/null | grep -q ":6379"; then
        log_warn "Порт 6379 уже занят"
        OCCUPIED_PID=$(netstat -tlnp 2>/dev/null | grep ":6379" | awk '{print $7}' | cut -d'/' -f1 | head -1 || \
                      ss -tlnp 2>/dev/null | grep ":6379" | grep -oP 'pid=\K\d+' | head -1 || echo "")
        if [ -n "$OCCUPIED_PID" ]; then
            log_warn "Порт занят процессом PID: $OCCUPIED_PID"
            if [ "$OCCUPIED_PID" != "$$" ]; then
                log_warn "Останавливаем процесс, занимающий порт..."
                kill "$OCCUPIED_PID" 2>/dev/null || true
                sleep 2
            fi
        fi
    fi
    
    # 3. Проверяем конфигурацию Redis
    if [ -f "/etc/redis/redis.conf" ]; then
        log_info "Проверка конфигурации Redis..."
        
        # Проверяем синтаксис конфигурации
        if command -v redis-server &> /dev/null; then
            if redis-server /etc/redis/redis.conf --test-memory 1 2>&1 | grep -qi "error\|fatal"; then
                log_warn "Обнаружены проблемы в конфигурации Redis"
            fi
        fi
        
        # Убеждаемся, что директория для данных существует и доступна
        CONFIG_DIR=$(grep "^dir " /etc/redis/redis.conf 2>/dev/null | awk '{print $2}' | head -1 || echo "")
        if [ -n "$CONFIG_DIR" ] && [ "$CONFIG_DIR" != "$REDIS_DIR" ]; then
            REDIS_DIR="$CONFIG_DIR"
        fi
        
        if [ -n "$REDIS_DIR" ] && [ ! -d "$REDIS_DIR" ]; then
            log_info "Создание директории из конфигурации: $REDIS_DIR"
            mkdir -p "$REDIS_DIR"
            chown redis:redis "$REDIS_DIR" 2>/dev/null || true
            chmod 755 "$REDIS_DIR" 2>/dev/null || true
        fi
    fi
    
    # 4. Убиваем старые процессы Redis, если они есть
    if pgrep -x redis-server >/dev/null 2>&1; then
        log_info "Обнаружены запущенные процессы Redis, останавливаем..."
        pkill -x redis-server 2>/dev/null || true
        sleep 2
    fi
    
    # 5. Пробуем запустить еще раз
    log_info "Повторная попытка запуска Redis после исправлений..."
    sleep 2
    
    if ! systemctl start redis-server; then
        # Пробуем запустить через service (для SysV)
        if command -v service &> /dev/null; then
            log_info "Попытка запуска через service..."
            if service redis-server start 2>/dev/null; then
                log_info "Redis запущен через service"
            else
                # Последняя попытка - запуск напрямую для диагностики
                log_warn "Попытка запуска Redis напрямую для диагностики..."
                if command -v redis-server &> /dev/null && [ -f "/etc/redis/redis.conf" ]; then
                    # Проверяем конфигурацию перед запуском
                    REDIS_TEST_OUTPUT=$(sudo -u redis redis-server /etc/redis/redis.conf --test-memory 1 2>&1)
                    if echo "$REDIS_TEST_OUTPUT" | grep -qi "error\|fatal"; then
                        log_error "Ошибка в конфигурации Redis:"
                        echo "$REDIS_TEST_OUTPUT" | grep -i "error\|fatal" | head -3 | while read line; do
                            log_error "  $line"
                        done
                        
                        # Пробуем исправить проблему с логом
                        if echo "$REDIS_TEST_OUTPUT" | grep -qi "log file"; then
                            log_info "Исправление проблемы с файлом лога..."
                            REDIS_LOG_DIR="/var/log/redis"
                            mkdir -p "$REDIS_LOG_DIR"
                            chown redis:redis "$REDIS_LOG_DIR" 2>/dev/null || true
                            chmod 755 "$REDIS_LOG_DIR" 2>/dev/null || true
                            
                            # Обновляем logfile в конфигурации
                            if grep -q "^logfile " /etc/redis/redis.conf; then
                                sed -i "s|^logfile .*|logfile $REDIS_LOG_DIR/redis-server.log|" /etc/redis/redis.conf
                            else
                                echo "logfile $REDIS_LOG_DIR/redis-server.log" >> /etc/redis/redis.conf
                            fi
                            
                            log_info "Повторная попытка запуска после исправления лога..."
                            sleep 1
                        fi
                    fi
                    
                    # Пробуем запустить
                    if sudo -u redis redis-server /etc/redis/redis.conf --daemonize yes 2>&1; then
                        sleep 2
                        if pgrep -x redis-server >/dev/null 2>&1; then
                            log_info "Redis запущен напрямую"
                        else
                            log_error "Redis не запустился, проверьте конфигурацию"
                            exit 1
                        fi
                    else
                        log_error "Redis не удалось запустить даже напрямую"
                        log_error "Выполните диагностику вручную:"
                        log_error "  sudo systemctl status redis-server"
                        log_error "  sudo journalctl -xeu redis-server"
                        log_error "  sudo -u redis redis-server /etc/redis/redis.conf"
                        exit 1
                    fi
                else
                    log_error "Redis не удалось запустить"
                    exit 1
                fi
            fi
        else
            log_error "Redis не удалось запустить"
            exit 1
        fi
    fi
fi

# Проверяем, что Redis запущен
log_info "Проверка статуса Redis..."
sleep 2
if systemctl is-active --quiet redis-server || pgrep -x redis-server >/dev/null 2>&1; then
    log_info "Redis запущен успешно"
    
    # Проверяем подключение
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &>/dev/null; then
            log_info "Redis отвечает на команды (PING)"
        else
            log_warn "Redis запущен, но не отвечает на команды"
        fi
    fi
else
    log_error "Redis не запущен, хотя команда start выполнена успешно"
    log_error "Проверьте: systemctl status redis-server"
    exit 1
fi

# ============================================================================
# 7. Установка Mosquitto MQTT Broker
# ============================================================================

log_info "Установка Mosquitto MQTT Broker..."
if ! command -v mosquitto &> /dev/null; then
    apt-get install -y -qq mosquitto mosquitto-clients
else
    log_info "Mosquitto уже установлен"
fi

systemctl enable mosquitto
systemctl start mosquitto

# ============================================================================
# 8. Создание пользователя и директорий
# ============================================================================

log_info "Создание пользователя и групп..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$PROJECT_DIR" "$APP_USER"
    log_info "Пользователь $APP_USER создан"
else
    log_info "Пользователь $APP_USER уже существует"
fi

log_info "Создание директорий проекта..."
mkdir -p "$PROJECT_DIR"
mkdir -p "$LARAVEL_DIR/storage/logs"
mkdir -p "$LARAVEL_DIR/storage/framework/cache"
mkdir -p "$LARAVEL_DIR/storage/framework/sessions"
mkdir -p "$LARAVEL_DIR/storage/framework/views"
mkdir -p "$LARAVEL_DIR/storage/app/public"
mkdir -p "$LARAVEL_DIR/storage/app/private/backups"
mkdir -p /var/log/hydro
mkdir -p /var/run/hydro

chown -R "$APP_USER:$APP_GROUP" "$PROJECT_DIR"
chown -R "$APP_USER:$APP_GROUP" /var/log/hydro
chown -R "$APP_USER:$APP_GROUP" /var/run/hydro

# ============================================================================
# 9. Клонирование/копирование проекта
# ============================================================================

log_info "Проверка наличия проекта..."
if [ ! -d "$LARAVEL_DIR" ] || [ ! -f "$LARAVEL_DIR/artisan" ]; then
    log_warn "Проект не найден в $PROJECT_DIR"
    log_warn "Пожалуйста, скопируйте проект в $PROJECT_DIR или настройте git clone"
    log_warn "Структура должна быть:"
    log_warn "  $PROJECT_DIR/backend/laravel/"
    log_warn "  $PROJECT_DIR/backend/services/"
    exit 1
fi

# ============================================================================
# 10. Установка зависимостей Laravel
# ============================================================================

log_info "Установка зависимостей Laravel (Composer)..."
cd "$LARAVEL_DIR"
sudo -u "$APP_USER" composer install --no-interaction --prefer-dist --optimize-autoloader

# ============================================================================
# 11. Настройка Laravel .env
# ============================================================================

log_info "Настройка Laravel .env файла..."
if [ ! -f "$LARAVEL_DIR/.env" ]; then
    if [ -f "$LARAVEL_DIR/.env.example" ]; then
        cp "$LARAVEL_DIR/.env.example" "$LARAVEL_DIR/.env"
        log_info "Создан .env файл из .env.example"
    else
        log_error ".env.example не найден!"
        exit 1
    fi
fi

# Устанавливаем права доступа на .env файл ДО его редактирования
chown "$APP_USER:$APP_GROUP" "$LARAVEL_DIR/.env"
chmod 640 "$LARAVEL_DIR/.env"

# Обновление .env с правильными значениями
# Используем более надежный метод: добавляем или обновляем строки
update_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"
    # Выполняем от имени пользователя hydro, чтобы избежать проблем с правами
    if sudo -u "$APP_USER" grep -q "^${key}=" "$file" 2>/dev/null; then
        # Экранируем специальные символы для sed
        local escaped_value=$(echo "$value" | sed 's/[[\.*^$()+?{|]/\\&/g')
        sudo -u "$APP_USER" sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        # Добавляем новую строку
        echo "${key}=${value}" | sudo -u "$APP_USER" tee -a "$file" > /dev/null
    fi
}

update_env_var "$LARAVEL_DIR/.env" "DB_CONNECTION" "pgsql"
update_env_var "$LARAVEL_DIR/.env" "DB_HOST" "127.0.0.1"
update_env_var "$LARAVEL_DIR/.env" "DB_PORT" "5432"
update_env_var "$LARAVEL_DIR/.env" "DB_DATABASE" "$DB_NAME"
update_env_var "$LARAVEL_DIR/.env" "DB_USERNAME" "$DB_USER"
update_env_var "$LARAVEL_DIR/.env" "DB_PASSWORD" "$DB_PASSWORD"
update_env_var "$LARAVEL_DIR/.env" "REDIS_HOST" "127.0.0.1"
update_env_var "$LARAVEL_DIR/.env" "REDIS_PORT" "6379"

if [ "$ENVIRONMENT" = "production" ]; then
    update_env_var "$LARAVEL_DIR/.env" "APP_ENV" "production"
    update_env_var "$LARAVEL_DIR/.env" "APP_DEBUG" "false"
    update_env_var "$LARAVEL_DIR/.env" "LOG_LEVEL" "info"
else
    update_env_var "$LARAVEL_DIR/.env" "APP_ENV" "local"
    update_env_var "$LARAVEL_DIR/.env" "APP_DEBUG" "true"
    update_env_var "$LARAVEL_DIR/.env" "LOG_LEVEL" "debug"
fi

# Убеждаемся, что права доступа установлены правильно перед генерацией ключа
chown "$APP_USER:$APP_GROUP" "$LARAVEL_DIR/.env"
chmod 640 "$LARAVEL_DIR/.env"

# Генерация ключа приложения
sudo -u "$APP_USER" php artisan key:generate --force

# ============================================================================
# 12. Настройка прав доступа Laravel
# ============================================================================

log_info "Настройка прав доступа Laravel..."
chown -R "$APP_USER:$APP_GROUP" "$LARAVEL_DIR"
chmod -R 755 "$LARAVEL_DIR"
chmod -R 775 "$LARAVEL_DIR/storage"
chmod -R 775 "$LARAVEL_DIR/bootstrap/cache"

# ============================================================================
# 13. Проверка подключения к базе данных и миграции
# ============================================================================

log_info "Проверка подключения к базе данных..."

# Проверяем, запущен ли PostgreSQL процесс и слушает ли на порту 5432
if ! pgrep -x postgres >/dev/null 2>&1; then
    log_warn "Процесс PostgreSQL не запущен, пытаемся запустить..."
    # Пробуем запустить через systemctl, если сервис определен
    if [ -n "$POSTGRES_SERVICE" ]; then
        systemctl start "$POSTGRES_SERVICE" 2>/dev/null || true
        sleep 3
    else
        log_warn "Не удалось определить способ запуска PostgreSQL"
        log_warn "Попробуйте запустить PostgreSQL вручную перед продолжением"
    fi
else
    log_info "Процесс PostgreSQL запущен (PID: $(pgrep -x postgres | head -1))"
fi

# Проверяем, слушает ли PostgreSQL на порту 5432
if netstat -tlnp 2>/dev/null | grep -q ":5432" || ss -tlnp 2>/dev/null | grep -q ":5432"; then
    log_info "PostgreSQL слушает на порту 5432"
else
    log_warn "PostgreSQL не слушает на порту 5432"
    log_warn "Проверяем подключение через socket..."
fi

# Проверяем подключение напрямую через psql с паролем
log_info "Проверка подключения к базе данных через psql..."
log_info "Параметры подключения:"
log_info "  Хост: 127.0.0.1"
log_info "  Порт: 5432"
log_info "  Пользователь: ${DB_USER}"
log_info "  База данных: ${DB_NAME}"

max_attempts=15
attempt=0
DB_READY=false

while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Попытка подключения $attempt/$max_attempts"
    
    # Проверка 1: Процесс PostgreSQL
    if pgrep -x postgres >/dev/null 2>&1; then
        log_info "  ✓ Процесс PostgreSQL запущен (PID: $(pgrep -x postgres | head -1))"
    else
        log_warn "  ✗ Процесс PostgreSQL не запущен"
        if [ -n "$POSTGRES_SERVICE" ]; then
            log_info "  → Попытка запуска через systemctl..."
            systemctl start "$POSTGRES_SERVICE" 2>/dev/null || true
            sleep 2
        fi
        sleep 2
        continue
    fi
    
    # Проверка 2: Порт 5432
    if netstat -tlnp 2>/dev/null | grep -q ":5432" || ss -tlnp 2>/dev/null | grep -q ":5432"; then
        log_info "  ✓ PostgreSQL слушает на порту 5432"
    else
        log_warn "  ✗ PostgreSQL не слушает на порту 5432"
        if [ -f "$PG_CONF" ]; then
            if ! grep -q "^listen_addresses.*localhost" "$PG_CONF" && ! grep -q "^listen_addresses.*'\*'" "$PG_CONF"; then
                log_info "  → Настройка listen_addresses..."
                if ! grep -q "^listen_addresses" "$PG_CONF"; then
                    echo "listen_addresses = 'localhost'" >> "$PG_CONF"
                else
                    sed -i "s/^listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
                fi
                if [ -n "$POSTGRES_SERVICE" ]; then
                    log_info "  → Перезапуск PostgreSQL для применения изменений..."
                    systemctl restart "$POSTGRES_SERVICE" 2>/dev/null || true
                    sleep 3
                fi
            fi
        fi
        sleep 2
        continue
    fi
    
    # Проверка 3: Подключение через socket (локально)
    log_info "  → Проверка подключения через socket..."
    SOCKET_RESULT=$(sudo -u postgres psql -d ${DB_NAME} -c "SELECT 1;" 2>&1)
    if [ $? -eq 0 ]; then
        log_info "  ✓ Подключение через socket работает"
    else
        log_warn "  ✗ Подключение через socket не работает"
        log_warn "    Ошибка: $(echo "$SOCKET_RESULT" | head -1)"
        sleep 2
        continue
    fi
    
    # Проверка 4: Подключение через TCP/IP с паролем
    log_info "  → Проверка подключения через TCP/IP (127.0.0.1:5432)..."
    TCP_RESULT=$(PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" 2>&1)
    TCP_EXIT_CODE=$?
    
    if [ $TCP_EXIT_CODE -eq 0 ]; then
        DB_READY=true
        log_info "  ✓ Подключение через TCP/IP работает!"
        log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        log_info "Подключение к базе данных установлено успешно"
        break
    else
        log_warn "  ✗ Подключение через TCP/IP не работает"
        ERROR_MSG=$(echo "$TCP_RESULT" | grep -i "error\|fatal\|failed" | head -1 || echo "$TCP_RESULT" | head -1)
        log_warn "    Ошибка: $ERROR_MSG"
        
        # Диагностика проблем
        if echo "$TCP_RESULT" | grep -qi "password authentication failed"; then
            log_warn "    → Проблема с аутентификацией пароля"
            log_warn "    → Проверьте пароль в .env файле"
        elif echo "$TCP_RESULT" | grep -qi "connection refused"; then
            log_warn "    → Подключение отклонено"
            log_warn "    → Проверьте pg_hba.conf"
        elif echo "$TCP_RESULT" | grep -qi "could not connect"; then
            log_warn "    → Не удалось подключиться"
            log_warn "    → Проверьте, что PostgreSQL слушает на localhost"
        fi
        
        # Проверяем pg_hba.conf
        if [ -f "$PG_HBA" ]; then
            if ! grep -q "^host.*all.*all.*127.0.0.1/32" "$PG_HBA"; then
                log_info "  → Добавление правила в pg_hba.conf..."
                echo "host    all             all             127.0.0.1/32            md5" >> "$PG_HBA"
                if [ -n "$POSTGRES_SERVICE" ]; then
                    log_info "  → Перезапуск PostgreSQL для применения pg_hba.conf..."
                    systemctl restart "$POSTGRES_SERVICE" 2>/dev/null || true
                    sleep 3
                fi
            else
                log_info "  ✓ Правило для 127.0.0.1/32 существует в pg_hba.conf"
            fi
        else
            log_warn "  ✗ Файл pg_hba.conf не найден: $PG_HBA"
        fi
    fi
    
    sleep 2
done

# Если прямое подключение не работает, пробуем через Laravel
if [ "$DB_READY" = "false" ]; then
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Прямое подключение не работает, проверяем через Laravel..."
    log_info "  → Выполнение: php artisan db:show"
    
    LARAVEL_DB_RESULT=$(sudo -u "$APP_USER" php artisan db:show 2>&1)
    LARAVEL_DB_EXIT=$?
    
    if [ $LARAVEL_DB_EXIT -eq 0 ]; then
        DB_READY=true
        log_info "  ✓ Подключение к базе данных установлено через Laravel"
        log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    else
        log_warn "  ✗ Laravel не может подключиться к базе данных"
        ERROR_MSG=$(echo "$LARAVEL_DB_RESULT" | grep -i "error\|exception\|failed" | head -3)
        if [ -n "$ERROR_MSG" ]; then
            log_warn "    Ошибки Laravel:"
            echo "$ERROR_MSG" | while read line; do
                log_warn "      $line"
            done
        fi
    fi
fi

if [ "$DB_READY" = "false" ]; then
    log_error "Не удалось подключиться к базе данных после $max_attempts попыток"
    log_error "Диагностика:"
    log_error "  1. Проверьте статус PostgreSQL: sudo systemctl status postgresql"
    log_error "  2. Проверьте listen_addresses: sudo grep 'listen_addresses' /etc/postgresql/*/main/postgresql.conf"
    log_error "  3. Проверьте pg_hba.conf: sudo grep '127.0.0.1' /etc/postgresql/*/main/pg_hba.conf"
    log_error "  4. Проверьте подключение вручную:"
    log_error "     PGPASSWORD='${DB_PASSWORD}' psql -h 127.0.0.1 -U ${DB_USER} -d ${DB_NAME} -c 'SELECT 1;'"
    log_error "  5. Проверьте пароль в .env файле"
    exit 1
fi

log_info "Запуск миграций базы данных..."

# Проверяем подключение перед миграциями
log_info "Проверка подключения к базе данных перед миграциями..."
if ! PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" >/dev/null 2>&1; then
    log_error "Не удалось подключиться к базе данных перед миграциями"
    log_error "Проверьте настройки подключения в .env файле"
    exit 1
fi
log_info "Подключение к базе данных подтверждено"

# Увеличиваем таймауты для миграций
log_info "Настройка параметров подключения для миграций..."
# Обновляем .env с увеличенными таймаутами
update_env_var "$LARAVEL_DIR/.env" "DB_TIMEOUT" "30"
update_env_var "$LARAVEL_DIR/.env" "DB_CONNECTION_TIMEOUT" "30"

# Выполняем миграции с повторными попытками
MIGRATION_ATTEMPTS=3
MIGRATION_SUCCESS=false

for attempt in $(seq 1 $MIGRATION_ATTEMPTS); do
    log_info "Попытка выполнения миграций $attempt/$MIGRATION_ATTEMPTS..."
    
    # Проверяем подключение перед каждой попыткой
    if ! PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" >/dev/null 2>&1; then
        log_warn "Подключение потеряно, ожидание восстановления..."
        sleep 3
        
        # Пробуем переподключиться
        if ! PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" >/dev/null 2>&1; then
            log_error "Не удалось восстановить подключение к базе данных"
            if [ $attempt -lt $MIGRATION_ATTEMPTS ]; then
                log_info "Повторная попытка через 5 секунд..."
                sleep 5
                continue
            else
                log_error "Исчерпаны все попытки восстановления подключения"
                exit 1
            fi
        fi
        log_info "Подключение восстановлено"
    fi
    
    # Выполняем миграции с детальным логированием
    log_info "  → Выполнение команды: php artisan migrate --force"
    log_info "  → Рабочая директория: $LARAVEL_DIR"
    log_info "  → Пользователь: $APP_USER"
    
    # Проверяем, что директория Laravel существует
    if [ ! -d "$LARAVEL_DIR" ]; then
        log_error "Директория Laravel не существует: $LARAVEL_DIR"
        exit 1
    fi
    
    # Проверяем, что artisan файл существует
    if [ ! -f "$LARAVEL_DIR/artisan" ]; then
        log_error "Файл artisan не найден в $LARAVEL_DIR"
        exit 1
    fi
    
    # Переходим в директорию Laravel и выполняем миграции
    cd "$LARAVEL_DIR" || {
        log_error "Не удалось перейти в директорию Laravel: $LARAVEL_DIR"
        exit 1
    }
    
    log_info "  → Текущая директория: $(pwd)"
    log_info "  → Проверка доступности artisan..."
    if ! sudo -u "$APP_USER" php artisan --version >/dev/null 2>&1; then
        log_error "Команда artisan не работает"
        log_error "Проверьте установку Laravel и права доступа"
        cd - >/dev/null
        exit 1
    fi
    log_info "  ✓ Artisan доступен"
    
    # Выполняем миграции с таймаутом и логированием
    log_info "  → Запуск миграций (может занять некоторое время)..."
    
    # Используем timeout для предотвращения зависания
    MIGRATION_OUTPUT=$(timeout 300 sudo -u "$APP_USER" php artisan migrate --force 2>&1) || {
        MIGRATION_EXIT=$?
        if [ $MIGRATION_EXIT -eq 124 ]; then
            log_error "Команда миграций превысила таймаут (5 минут)"
            cd - >/dev/null
            exit 1
        fi
    }
    MIGRATION_EXIT=$?
    
    # Возвращаемся в исходную директорию
    cd - >/dev/null
    
    log_info "  → Команда завершена с кодом: $MIGRATION_EXIT"
    
    if [ $MIGRATION_EXIT -eq 0 ]; then
        MIGRATION_SUCCESS=true
        log_info "  ✓ Миграции выполнены успешно (код выхода: 0)"
        
        # Выводим последние строки успешного вывода
        if [ -n "$MIGRATION_OUTPUT" ]; then
            log_info "  Последние строки вывода миграций:"
            echo "$MIGRATION_OUTPUT" | tail -15 | while read line; do
                if echo "$line" | grep -qi "migrated\|migrating\|done\|success"; then
                    log_info "    ✓ $line"
                elif echo "$line" | grep -qi "error\|exception\|failed"; then
                    log_warn "    ⚠ $line"
                else
                    log_info "    $line"
                fi
            done
        else
            log_warn "  ⚠ Нет вывода от команды миграций (возможно, все миграции уже выполнены)"
        fi
        break
        else
            log_warn "  ✗ Ошибка при выполнении миграций (попытка $attempt/$MIGRATION_ATTEMPTS)"
            log_warn "  Код выхода: $MIGRATION_EXIT"
            
            # Выводим полный вывод для диагностики
            if [ -n "$MIGRATION_OUTPUT" ]; then
                log_info "  Полный вывод команды миграций:"
                echo "$MIGRATION_OUTPUT" | while IFS= read -r line || [ -n "$line" ]; do
                    if echo "$line" | grep -qi "error\|exception\|failed\|fatal"; then
                        log_error "    ✗ $line"
                    elif echo "$line" | grep -qi "warning\|warn"; then
                        log_warn "    ⚠ $line"
                    elif echo "$line" | grep -qi "migrated\|migrating\|done"; then
                        log_info "    ✓ $line"
                    else
                        log_info "    $line"
                    fi
                done
            else
                log_warn "  ⚠ Нет вывода от команды миграций"
                log_warn "  Это может означать, что команда зависла или завершилась неожиданно"
            fi
            
            # Анализируем ошибку
        if echo "$MIGRATION_OUTPUT" | grep -qi "no connection to the server\|connection.*lost\|connection.*closed"; then
            log_warn "Обнаружена ошибка разрыва соединения"
            log_warn "Проверяем состояние базы данных..."
            
            # Проверяем, запущен ли PostgreSQL
            if ! pgrep -x postgres >/dev/null 2>&1; then
                log_error "PostgreSQL не запущен!"
                if [ -n "$POSTGRES_SERVICE" ]; then
                    log_info "Попытка запуска PostgreSQL..."
                    systemctl start "$POSTGRES_SERVICE" 2>/dev/null || true
                    sleep 5
                fi
            fi
            
            # Проверяем подключение
            if PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" >/dev/null 2>&1; then
                log_info "Подключение восстановлено, повторная попытка..."
                if [ $attempt -lt $MIGRATION_ATTEMPTS ]; then
                    sleep 3
                    continue
                fi
            else
                log_error "Не удалось восстановить подключение"
                if [ $attempt -lt $MIGRATION_ATTEMPTS ]; then
                    log_info "Повторная попытка через 5 секунд..."
                    sleep 5
                    continue
                fi
            fi
        elif echo "$MIGRATION_OUTPUT" | grep -qi "already exists\|duplicate"; then
            log_warn "Обнаружена ошибка дублирования (таблица/индекс уже существует)"
            log_warn "Это может быть нормально, если миграции выполнялись ранее"
            # Пробуем продолжить с --force
            log_info "Попытка продолжить миграции..."
            if [ $attempt -lt $MIGRATION_ATTEMPTS ]; then
                sleep 2
                continue
            fi
        fi
        
        # Дополнительная диагностика
        log_info "  → Проверка состояния базы данных..."
        if PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" >/dev/null 2>&1; then
            TABLE_COUNT=$(PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
            log_info "  → Количество таблиц в базе данных: $TABLE_COUNT"
        else
            log_warn "  ✗ Не удалось проверить состояние базы данных"
        fi
        
        if [ $attempt -lt $MIGRATION_ATTEMPTS ]; then
            log_info "Повторная попытка через 5 секунд..."
            sleep 5
        else
            log_error "Все попытки выполнения миграций исчерпаны"
            log_error "Последний вывод команды:"
            echo "$MIGRATION_OUTPUT" | tail -20
            exit 1
        fi
    fi
done

if [ "$MIGRATION_SUCCESS" = "false" ]; then
    log_error "Не удалось выполнить миграции после $MIGRATION_ATTEMPTS попыток"
    exit 1
fi

log_info "Запуск сидеров базы данных..."
if sudo -u "$APP_USER" php artisan db:seed --force; then
    log_info "Сидеры выполнены успешно"
else
    log_warn "Предупреждение: ошибка при выполнении сидеров (возможно, данные уже существуют)"
fi

# ============================================================================
# 14. Установка зависимостей Node.js
# ============================================================================

log_info "Установка зависимостей Node.js..."
cd "$LARAVEL_DIR"
sudo -u "$APP_USER" npm ci

# Сборка фронтенда
if [ "$ENVIRONMENT" = "production" ]; then
    log_info "Сборка фронтенда для production..."
    sudo -u "$APP_USER" npm run build
else
    log_info "Режим development: фронтенд будет собираться через Vite dev server"
fi

# ============================================================================
# 15. Оптимизация Laravel (production)
# ============================================================================

if [ "$ENVIRONMENT" = "production" ]; then
    log_info "Оптимизация Laravel для production..."
    sudo -u "$APP_USER" php artisan config:cache
    sudo -u "$APP_USER" php artisan route:cache
    sudo -u "$APP_USER" php artisan view:cache
    sudo -u "$APP_USER" php artisan event:cache
fi

# ============================================================================
# 16. Установка Python зависимостей для сервисов
# ============================================================================

log_info "Установка Python зависимостей для сервисов..."

# Создание виртуальных окружений для каждого сервиса
SERVICES=("mqtt-bridge" "automation-engine" "history-logger" "scheduler" "digital-twin" "telemetry-aggregator")

for service in "${SERVICES[@]}"; do
    service_dir="$SERVICES_DIR/$service"
    if [ -d "$service_dir" ] && [ -f "$service_dir/requirements.txt" ]; then
        log_info "Установка зависимостей для $service..."
        venv_dir="$service_dir/venv"
        
        if [ ! -d "$venv_dir" ]; then
            sudo -u "$APP_USER" $PYTHON_CMD -m venv "$venv_dir"
        fi
        
        sudo -u "$APP_USER" "$venv_dir/bin/pip" install --upgrade pip
        sudo -u "$APP_USER" "$venv_dir/bin/pip" install -r "$service_dir/requirements.txt"
        
        log_info "Зависимости для $service установлены"
    else
        log_warn "Сервис $service не найден или не имеет requirements.txt"
    fi
done

# ============================================================================
# 17. Настройка переменных окружения для Python сервисов
# ============================================================================

log_info "Создание файла с переменными окружения для Python сервисов..."
# Создаем .env файл только если его еще нет, чтобы не перезаписать существующие настройки
if [ ! -f "$SERVICES_DIR/.env" ]; then
    cat > "$SERVICES_DIR/.env" <<EOF
# Database
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DB=${DB_NAME}
PG_USER=${DB_USER}
PG_PASS=${DB_PASSWORD}

# MQTT
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_TLS=0

# Laravel API
LARAVEL_API_URL=http://127.0.0.1

# Redis
REDIS_HOST=127.0.0.1
REDIS_PORT=6379

# Environment
APP_ENV=${ENVIRONMENT}
EOF
    chown "$APP_USER:$APP_GROUP" "$SERVICES_DIR/.env"
    chmod 600 "$SERVICES_DIR/.env"
    log_info "Создан файл $SERVICES_DIR/.env с базовыми настройками"
else
    log_warn "Файл $SERVICES_DIR/.env уже существует, оставляем без изменений"
fi

# Функция для загрузки переменных окружения из .env файла
load_env_vars() {
    local env_file="$SERVICES_DIR/.env"
    if [ -f "$env_file" ]; then
        # Читаем .env файл и формируем строку environment для Supervisor
        local env_string="PYTHONUNBUFFERED=1,PYTHONPATH=$SERVICES_DIR"
        while IFS='=' read -r key value || [ -n "$key" ]; do
            # Пропускаем комментарии и пустые строки
            [[ "$key" =~ ^#.*$ ]] && continue
            [[ -z "$key" ]] && continue
            # Удаляем кавычки из значения, если они есть
            value=$(echo "$value" | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")
            # Экранируем специальные символы для Supervisor
            value=$(echo "$value" | sed 's/,/\\,/g')
            env_string="${env_string},${key}=${value}"
        done < "$env_file"
        echo "$env_string"
    else
        echo "PYTHONUNBUFFERED=1,PYTHONPATH=$SERVICES_DIR"
    fi
}

ENV_VARS=$(load_env_vars)

# ============================================================================
# 18. Настройка Supervisor для Laravel Reverb
# ============================================================================

log_info "Настройка Supervisor для Laravel Reverb..."
cat > /etc/supervisor/conf.d/hydro-reverb.conf <<EOF
[program:hydro-reverb]
process_name=%(program_name)s
command=php $LARAVEL_DIR/artisan reverb:start --host=0.0.0.0 --port=6001
directory=$LARAVEL_DIR
autostart=true
autorestart=true
user=$APP_USER
redirect_stderr=true
stdout_logfile=/var/log/hydro/reverb.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stopwaitsecs=10
EOF

# ============================================================================
# 19. Настройка Supervisor для Python сервисов
# ============================================================================

log_info "Настройка Supervisor для Python сервисов..."

# MQTT Bridge (FastAPI - запускается через uvicorn)
if [ -d "$SERVICES_DIR/mqtt-bridge" ]; then
    cat > /etc/supervisor/conf.d/hydro-mqtt-bridge.conf <<EOF
[program:hydro-mqtt-bridge]
process_name=%(program_name)s
command=$SERVICES_DIR/mqtt-bridge/venv/bin/uvicorn main:app --host 0.0.0.0 --port 9000
directory=$SERVICES_DIR/mqtt-bridge
autostart=true
autorestart=true
user=$APP_USER
environment=$ENV_VARS
redirect_stderr=true
stdout_logfile=/var/log/hydro/mqtt-bridge.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stopwaitsecs=10
EOF
fi

# Automation Engine
if [ -d "$SERVICES_DIR/automation-engine" ]; then
    cat > /etc/supervisor/conf.d/hydro-automation-engine.conf <<EOF
[program:hydro-automation-engine]
process_name=%(program_name)s
command=$SERVICES_DIR/automation-engine/venv/bin/python $SERVICES_DIR/automation-engine/main.py
directory=$SERVICES_DIR/automation-engine
autostart=true
autorestart=true
user=$APP_USER
environment=$ENV_VARS
redirect_stderr=true
stdout_logfile=/var/log/hydro/automation-engine.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
EOF
fi

# History Logger (FastAPI - запускается через uvicorn)
if [ -d "$SERVICES_DIR/history-logger" ]; then
    cat > /etc/supervisor/conf.d/hydro-history-logger.conf <<EOF
[program:hydro-history-logger]
process_name=%(program_name)s
command=$SERVICES_DIR/history-logger/venv/bin/python $SERVICES_DIR/history-logger/main.py
directory=$SERVICES_DIR/history-logger
autostart=true
autorestart=true
user=$APP_USER
environment=$ENV_VARS
redirect_stderr=true
stdout_logfile=/var/log/hydro/history-logger.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stopwaitsecs=10
EOF
fi

# Scheduler
if [ -d "$SERVICES_DIR/scheduler" ]; then
    cat > /etc/supervisor/conf.d/hydro-scheduler.conf <<EOF
[program:hydro-scheduler]
process_name=%(program_name)s
command=$SERVICES_DIR/scheduler/venv/bin/python $SERVICES_DIR/scheduler/main.py
directory=$SERVICES_DIR/scheduler
autostart=true
autorestart=true
user=$APP_USER
environment=$ENV_VARS
redirect_stderr=true
stdout_logfile=/var/log/hydro/scheduler.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
EOF
fi

# Digital Twin (FastAPI - запускается через uvicorn)
if [ -d "$SERVICES_DIR/digital-twin" ]; then
    cat > /etc/supervisor/conf.d/hydro-digital-twin.conf <<EOF
[program:hydro-digital-twin]
process_name=%(program_name)s
command=$SERVICES_DIR/digital-twin/venv/bin/python $SERVICES_DIR/digital-twin/main.py
directory=$SERVICES_DIR/digital-twin
autostart=true
autorestart=true
user=$APP_USER
environment=$ENV_VARS
redirect_stderr=true
stdout_logfile=/var/log/hydro/digital-twin.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stopwaitsecs=10
EOF
fi

# Telemetry Aggregator
if [ -d "$SERVICES_DIR/telemetry-aggregator" ]; then
    cat > /etc/supervisor/conf.d/hydro-telemetry-aggregator.conf <<EOF
[program:hydro-telemetry-aggregator]
process_name=%(program_name)s
command=$SERVICES_DIR/telemetry-aggregator/venv/bin/python $SERVICES_DIR/telemetry-aggregator/main.py
directory=$SERVICES_DIR/telemetry-aggregator
autostart=true
autorestart=true
user=$APP_USER
environment=$ENV_VARS
redirect_stderr=true
stdout_logfile=/var/log/hydro/telemetry-aggregator.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
EOF
fi

# ============================================================================
# 20. Настройка Nginx
# ============================================================================

log_info "Настройка Nginx..."
# Получение IP адреса сервера для вывода в финальной информации
SERVER_IP=$(hostname -I | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}' || echo "не определен")
fi

cat > /etc/nginx/sites-available/hydro <<EOF
server {
    listen 0.0.0.0:80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root $LARAVEL_DIR/public;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    index index.php;

    charset utf-8;

    location / {
        try_files \$uri \$uri/ /index.php?\$query_string;
    }

    location = /favicon.ico { access_log off; log_not_found off; }
    location = /robots.txt  { access_log off; log_not_found off; }

    error_page 404 /index.php;

    location ~ \.php$ {
        fastcgi_pass unix:/var/run/php/php8.2-fpm.sock;
        fastcgi_param SCRIPT_FILENAME \$realpath_root\$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
        
        # FastCGI buffers для больших заголовков
        fastcgi_buffers 16 16k;
        fastcgi_buffer_size 32k;
        fastcgi_busy_buffers_size 64k;
        fastcgi_temp_file_write_size 64k;
    }

    location ~ /\.(?!well-known).* {
        deny all;
    }

    # WebSocket proxy для Laravel Reverb
    location /app {
        proxy_pass http://127.0.0.1:6001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF

# Активация сайта
ln -sf /etc/nginx/sites-available/hydro /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Проверка конфигурации Nginx
if nginx -t; then
    log_info "Конфигурация Nginx валидна"
else
    log_error "Ошибка в конфигурации Nginx!"
    exit 1
fi

# ============================================================================
# 21. Настройка PHP-FPM
# ============================================================================

log_info "Настройка PHP-FPM..."
if grep -q "^user = www-data" /etc/php/8.2/fpm/pool.d/www.conf; then
    sed -i 's/^user = www-data/user = hydro/' /etc/php/8.2/fpm/pool.d/www.conf
fi
if grep -q "^group = www-data" /etc/php/8.2/fpm/pool.d/www.conf; then
    sed -i 's/^group = www-data/group = hydro/' /etc/php/8.2/fpm/pool.d/www.conf
fi

# ============================================================================
# 22. Запуск сервисов
# ============================================================================

log_info "Перезапуск и включение сервисов..."

systemctl enable php8.2-fpm
systemctl restart php8.2-fpm

systemctl enable nginx
systemctl restart nginx

systemctl enable supervisor
systemctl restart supervisor

# Обновление конфигурации Supervisor
supervisorctl reread
supervisorctl update

log_warn "ВАЖНО: Настройте переменные окружения в $SERVICES_DIR/.env"
log_warn "Добавьте токены безопасности (PY_API_TOKEN, LARAVEL_API_TOKEN и т.д.)"

# ============================================================================
# 23. Финальная информация
# ============================================================================

log_info "Развертывание завершено!"
echo ""
log_info "Информация о развертывании:"
echo "  - Проект: $PROJECT_DIR"
echo "  - Пользователь: $APP_USER"
echo "  - База данных: $DB_NAME"
echo "  - Пользователь БД: $DB_USER"
echo "  - Пароль БД: $DB_PASSWORD"
echo ""
log_info "Доступ к приложению:"
echo "  - Локально: http://localhost"
echo "  - В локальной сети: http://${SERVER_IP}"
echo "  - WebSocket (Reverb): ws://${SERVER_IP}:6001"
echo ""
log_info "Полезные команды:"
echo "  - Проверка статуса сервисов: supervisorctl status"
echo "  - Логи Laravel: tail -f $LARAVEL_DIR/storage/logs/laravel.log"
echo "  - Логи сервисов: tail -f /var/log/hydro/*.log"
echo "  - Перезапуск сервисов: supervisorctl restart all"
echo "  - Перезапуск Nginx: systemctl restart nginx"
echo "  - Перезапуск PHP-FPM: systemctl restart php8.2-fpm"
echo ""
log_warn "Не забудьте:"
echo "  1. Настроить переменные окружения в $LARAVEL_DIR/.env"
echo "     (REVERB_APP_KEY, REVERB_APP_SECRET, REVERB_ALLOWED_ORIGINS и т.д.)"
echo "  2. Настроить переменные окружения в $SERVICES_DIR/.env"
echo "     (PY_API_TOKEN, LARAVEL_API_TOKEN, MQTT пароли и т.д.)"
echo "  3. Настроить MQTT аутентификацию (если требуется)"
echo "  4. Настроить файрвол для доступа из локальной сети:"
echo "     sudo ufw allow from 192.168.0.0/16 to any port 80"
echo "     sudo ufw allow from 192.168.0.0/16 to any port 6001"
echo "  5. Настроить SSL/TLS для Nginx (для production)"
echo ""
log_info "Для проверки доступности сайта из локальной сети:"
echo "  Откройте в браузере: http://${SERVER_IP}"
echo ""

