#!/bin/bash
set -e
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
# Функции для улучшения скрипта
# ============================================================================

# Функция для ожидания освобождения блокировки apt
wait_for_apt_lock() {
    local max_wait=300
    local waited=0
    
    while [ $waited -lt $max_wait ]; do
        local apt_processes=$(pgrep -x "apt-get|apt|dpkg" 2>/dev/null || echo "")
        if [ -n "$apt_processes" ]; then
            local apt_pid=$(echo "$apt_processes" | head -1)
            local apt_cmd=$(ps -p "$apt_pid" -o cmd= 2>/dev/null | head -1 || echo "unknown")
            log_info "Обнаружен запущенный процесс apt (PID: $apt_pid)"
            log_info "  Команда: $apt_cmd"
            log_info "  Ожидание завершения процесса..."
            sleep 5
            waited=$((waited + 5))
            continue
        fi
        
        local lock_files=""
        [ -f /var/lib/apt/lists/lock ] && lock_files="$lock_files /var/lib/apt/lists/lock"
        [ -f /var/lib/dpkg/lock ] && lock_files="$lock_files /var/lib/dpkg/lock"
        [ -f /var/cache/apt/archives/lock ] && lock_files="$lock_files /var/cache/apt/archives/lock"
        [ -f /var/lib/dpkg/lock-frontend ] && lock_files="$lock_files /var/lib/dpkg/lock-frontend"
        
        if [ -n "$lock_files" ]; then
            local lock_pid=""
            for lock_file in $lock_files; do
                if [ -f "$lock_file" ]; then
                    lock_pid=$(lsof -t "$lock_file" 2>/dev/null | head -1 || echo "")
                    if [ -n "$lock_pid" ]; then
                        local lock_cmd=$(ps -p "$lock_pid" -o cmd= 2>/dev/null | head -1 || echo "unknown")
                        log_info "Блокировка обнаружена: $lock_file"
                        log_info "  Удерживается процессом PID: $lock_pid"
                        log_info "  Команда: $lock_cmd"
                        
                        if ! ps -p "$lock_pid" >/dev/null 2>&1; then
                            log_warn "  Процесс $lock_pid не существует, но блокировка осталась"
                            log_warn "  Удаляем устаревшую блокировку..."
                            rm -f "$lock_file" 2>/dev/null || true
                            continue
                        fi
                    else
                        log_info "Блокировка обнаружена: $lock_file (процесс не определен)"
                    fi
                fi
            done
            
            if [ -n "$lock_pid" ] && ps -p "$lock_pid" >/dev/null 2>&1; then
                log_info "Ожидание завершения процесса $lock_pid..."
            else
                log_info "Ожидание освобождения блокировки..."
            fi
            sleep 5
            waited=$((waited + 5))
        else
            log_info "Блокировка apt освобождена"
            return 0
        fi
    done
    
    log_warn "Превышено время ожидания освобождения блокировки apt (5 минут)"
    log_warn "Текущие процессы apt/dpkg:"
    ps aux | grep -E '[a]pt|[d]pkg' | head -5 | while read line; do
        log_warn "  $line"
    done
    return 1
}

# Функция для безопасного перезапуска PostgreSQL
restart_postgresql() {
    local service="$1"
    if [ -n "$service" ]; then
        log_info "Перезапуск PostgreSQL через systemctl..."
        if systemctl restart "$service"; then
            sleep 5
            return 0
        else
            log_warn "Не удалось перезапустить через systemctl, пробуем альтернативные методы..."
            
            if command -v pg_ctl &>/dev/null; then
                log_info "Попытка перезапуска через pg_ctl..."
                PG_DATA=$(sudo -u postgres pg_ctl status 2>/dev/null | grep "Data directory" | cut -d: -f2 | xargs)
                if [ -n "$PG_DATA" ] && [ -d "$PG_DATA" ]; then
                    sudo -u postgres pg_ctl -D "$PG_DATA" restart -m fast
                    sleep 5
                    return 0
                fi
            fi
            
            log_info "Попытка прямого перезапуска через kill и запуск..."
            pkill -9 postgres 2>/dev/null || true
            sleep 2
            systemctl start "$service" 2>/dev/null || true
            sleep 5
            return 0
        fi
    fi
    return 1
}

# Функция для настройки Redis
configure_redis() {
    log_info "Настройка Redis..."
    
    mkdir -p /var/log/redis
    mkdir -p /var/lib/redis
    
    chown redis:redis /var/log/redis 2>/dev/null || true
    chown redis:redis /var/lib/redis 2>/dev/null || true
    
    REDIS_CONF="/etc/redis/redis.conf"
    if [ -f "$REDIS_CONF" ]; then
        sed -i 's/^supervised.*/supervised systemd/' "$REDIS_CONF" 2>/dev/null || true
        sed -i 's/^bind.*/bind 127.0.0.1/' "$REDIS_CONF" 2>/dev/null || true
        
        if ! grep -q "^maxmemory " "$REDIS_CONF"; then
            echo "maxmemory 256mb" >> "$REDIS_CONF"
        fi
        if ! grep -q "^maxmemory-policy " "$REDIS_CONF"; then
            echo "maxmemory-policy allkeys-lru" >> "$REDIS_CONF"
        fi
        if ! grep -q "^save " "$REDIS_CONF"; then
            echo "save 900 1" >> "$REDIS_CONF"
            echo "save 300 10" >> "$REDIS_CONF"
            echo "save 60 10000" >> "$REDIS_CONF"
        fi
    fi
}

# Функция для проверки обязательных переменных окружения
check_required_env_vars() {
    local env_file="$LARAVEL_DIR/.env"
    local required_vars=("APP_KEY" "DB_PASSWORD" "REDIS_HOST")
    
    for var in "${required_vars[@]}"; do
        if ! grep -q "^${var}=" "$env_file" 2>/dev/null || [ -z "$(grep "^${var}=" "$env_file" 2>/dev/null | cut -d= -f2)" ]; then
            log_error "Обязательная переменная $var не установлена в .env файле"
            return 1
        fi
    done
    return 0
}

# Функция для диагностики системы
run_diagnostics() {
    log_info "Выполнение диагностики системы..."
    
    local services=("nginx" "php8.2-fpm" "postgresql" "redis-server" "mosquitto" "supervisor")
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            log_info "✓ Сервис $service запущен"
        else
            log_warn "✗ Сервис $service не запущен"
        fi
    done
    
    local ports=("80" "5432" "6379" "1883" "6001")
    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":$port "; then
            log_info "✓ Порт $port открыт"
        else
            log_warn "✗ Порт $port не открыт"
        fi
    done
    
    local dirs=("$LARAVEL_DIR" "$SERVICES_DIR" "/var/log/hydro")
    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ]; then
            log_info "✓ Директория $dir существует"
        else
            log_warn "✗ Директория $dir отсутствует"
        fi
    done
}

# Функция для настройки файрвола
setup_firewall() {
    if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
        log_info "Настройка UFW правил..."
        ufw allow 80/tcp 2>/dev/null || true
        ufw allow 6001/tcp 2>/dev/null || true
        ufw reload 2>/dev/null || true
        log_info "UFW настроен"
    else
        log_info "UFW не активен, пропускаем настройку файрвола"
    fi
}

# Функция для создания скрипта обновления
create_update_script() {
    cat > /usr/local/bin/update-hydro << 'EOF'
#!/bin/bash
set -e

cd /opt/hydro/hydro2.0/backend/laravel
sudo -u hydro git pull
sudo -u hydro composer install --no-interaction --prefer-dist --optimize-autoloader
sudo -u hydro npm ci
sudo -u hydro php artisan migrate --force
sudo -u hydro php artisan config:cache
sudo -u hydro php artisan route:cache
sudo -u hydro php artisan view:cache
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart all
EOF
    chmod +x /usr/local/bin/update-hydro
    log_info "Создан скрипт обновления: update-hydro"
}

# Функция для создания файла с учетными данными
create_credentials_file() {
    local server_ip=$(hostname -I | awk '{print $1}')
    if [ -z "$server_ip" ]; then
        server_ip=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $7; exit}' || echo "не определен")
    fi
    
    local cred_file="/root/hydro-credentials.txt"
    cat > "$cred_file" << EOF
=== Hydro 2.0 Учетные данные ===
Дата развертывания: $(date)
URL: http://${server_ip}
WebSocket: ws://${server_ip}:6001

База данных:
  Имя: ${DB_NAME}
  Пользователь: ${DB_USER}
  Пароль: ${DB_PASSWORD}

Директории:
  Проект: ${PROJECT_DIR}
  Laravel: ${LARAVEL_DIR}
  Сервисы: ${SERVICES_DIR}

Команды:
  Проверка статуса: supervisorctl status
  Логи Laravel: tail -f ${LARAVEL_DIR}/storage/logs/laravel.log
  Обновление: update-hydro

Не забудьте:
  1. Настроить .env файлы
  2. Настроить SSL/TLS сертификаты
  3. Настроить MQTT аутентификацию
EOF
    chmod 600 "$cred_file"
    log_info "Учетные данные сохранены в: $cred_file"
}

# Функция для обновления переменных в .env файле
update_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"
    
    if sudo -u "$APP_USER" grep -q "^${key}=" "$file" 2>/dev/null; then
        local escaped_value=$(echo "$value" | sed 's/[[\.*^$()+?{|]/\\&/g')
        sudo -u "$APP_USER" sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" | sudo -u "$APP_USER" tee -a "$file" > /dev/null
    fi
}

# ============================================================================
# 1. Установка системных зависимостей
# ============================================================================

log_info "Обновление списка пакетов..."
log_info "Это может занять некоторое время..."

log_info "Проверка блокировки apt..."
if ! wait_for_apt_lock; then
    log_error "Не удалось получить доступ к apt"
    log_error "Выполните вручную: sudo killall apt-get apt dpkg 2>/dev/null; sudo rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/cache/apt/archives/lock"
    exit 1
fi

log_info "Выполнение: apt-get update"
if timeout 300 apt-get update 2>&1 | tee /tmp/apt-update.log; then
    log_info "Список пакетов обновлен успешно"
else
    UPDATE_EXIT=$?
    if [ $UPDATE_EXIT -eq 124 ]; then
        log_error "Обновление списка пакетов превысило таймаут (5 минут)"
        exit 1
    elif [ $UPDATE_EXIT -eq 100 ]; then
        log_warn "Ошибка блокировки apt (код: 100)"
        sleep 10
        log_info "Повторное выполнение: apt-get update"
        if wait_for_apt_lock && timeout 300 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
            log_info "Список пакетов обновлен успешно после повторной попытки"
        else
            log_error "Не удалось обновить список пакетов после повторной попытки"
            exit 1
        fi
    else
        log_warn "Обновление списка пакетов завершилось с ошибкой (код: $UPDATE_EXIT)"
        log_warn "Последние строки лога:"
        tail -20 /tmp/apt-update.log 2>/dev/null | while read line; do
            log_warn "  $line"
        done
    fi
fi

log_info "Установка всех системных зависимостей..."
if ! apt-get install -y \
    curl wget git build-essential software-properties-common \
    apt-transport-https ca-certificates gnupg lsb-release \
    supervisor nginx postgresql-client libpq-dev \
    python3.11 python3.11-dev python3.11-venv python3-pip \
    gcc gettext unzip; then
    log_error "Ошибка при установке базовых пакетов"
    exit 1
fi
PYTHON_CMD="python3.11"
log_info "Базовые пакеты установлены успешно"

# ============================================================================
# 2. Установка PHP 8.2
# ============================================================================

log_info "Установка PHP 8.2 и расширений..."
if ! command -v php &> /dev/null || ! php -v 2>/dev/null | grep -q "8.2"; then
    add-apt-repository -y ppa:ondrej/php
    
    if ! wait_for_apt_lock; then
        log_warn "Не удалось получить доступ к apt, пропускаем обновление"
        return 0
    fi
    
    log_info "Выполнение: apt-get update"
    if ! timeout 180 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
        log_warn "Ошибка при обновлении списка пакетов для PHP"
        log_warn "Последние строки лога:"
        tail -10 /tmp/apt-update.log 2>/dev/null | while read line; do
            log_warn "  $line"
        done
    fi
    
    log_info "Выполнение: apt-get install (прогресс будет виден ниже)"
    apt-get install -y \
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
    
    if ! wait_for_apt_lock; then
        log_warn "Не удалось получить доступ к apt, пропускаем обновление"
        return 0
    fi
    
    log_info "Выполнение: apt-get update"
    if ! timeout 180 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
        log_warn "Ошибка при обновлении списка пакетов для Node.js"
    fi
    
    log_info "Выполнение: apt-get install (прогресс будет виден ниже)"
    apt-get install -y nodejs
else
    log_info "Node.js 20 уже установлен"
fi

# ============================================================================
# 5. Установка PostgreSQL 16 с TimescaleDB
# ============================================================================

log_info "Установка PostgreSQL 16 с TimescaleDB..."

POSTGRES_INSTALLED=false
if command -v psql &> /dev/null; then
    PSQL_VERSION=$(psql --version 2>/dev/null | grep -oP '\d+' | head -1 || echo "")
    if [ "$PSQL_VERSION" = "16" ] && dpkg -l | grep -q "^ii.*postgresql-16"; then
        POSTGRES_INSTALLED=true
        log_info "PostgreSQL 16 уже установлен"
    fi
fi

if [ "$POSTGRES_INSTALLED" = "false" ]; then
    log_info "Начинаем полную установку PostgreSQL 16..."
    
    log_info "Шаг 1: Добавление репозитория PostgreSQL..."
    mkdir -p /etc/apt/keyrings
    rm -f /etc/apt/sources.list.d/pgdg.list /etc/apt/keyrings/postgresql.gpg
    
    DISTRO_CODENAME=$(lsb_release -cs)
    log_info "Кодовое имя дистрибутива: $DISTRO_CODENAME"
    
    log_info "Загрузка GPG ключа PostgreSQL..."
    if ! wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg; then
        log_error "Не удалось загрузить GPG ключ PostgreSQL"
        exit 1
    fi
    chmod 644 /etc/apt/keyrings/postgresql.gpg
    
    log_info "Добавление репозитория в sources.list..."
    echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $DISTRO_CODENAME-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    
    log_info "Шаг 2: Обновление списка пакетов..."
    if ! wait_for_apt_lock; then
        log_error "Не удалось получить доступ к apt"
        exit 1
    fi
    
    log_info "Выполнение: apt-get update"
    if ! timeout 180 apt-get update 2>&1 | tee -a /tmp/apt-update.log; then
        log_error "Ошибка при обновлении списка пакетов"
        exit 1
    fi
    
    log_info "Шаг 3: Установка PostgreSQL 16 и contrib..."
    if ! apt-get install -y postgresql-16 postgresql-contrib-16; then
        log_error "Ошибка при установке PostgreSQL 16"
        exit 1
    fi
    
    log_info "Шаг 4: Проверка установки PostgreSQL..."
    export PATH="$PATH:/usr/lib/postgresql/16/bin"
    PSQL_VERSION=$(psql --version 2>/dev/null | head -1)
    log_info "Установлена версия: $PSQL_VERSION"
    
    log_info "Шаг 5: Установка TimescaleDB..."
    rm -f /etc/apt/sources.list.d/timescaledb.list /etc/apt/keyrings/timescaledb.gpg
    
    UBUNTU_CODENAME=$(lsb_release -c -s)
    log_info "Кодовое имя Ubuntu: $UBUNTU_CODENAME"
    
    log_info "Загрузка GPG ключа TimescaleDB..."
    if wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg; then
        chmod 644 /etc/apt/keyrings/timescaledb.gpg
        echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ $UBUNTU_CODENAME main" > /etc/apt/sources.list.d/timescaledb.list
        
        if apt-get update -qq; then
            if apt-cache show timescaledb-2-postgresql-16 &>/dev/null; then
                log_info "Установка TimescaleDB..."
                if apt-get install -y timescaledb-2-postgresql-16; then
                    log_info "TimescaleDB установлен успешно"
                    
                    if command -v timescaledb-tune &> /dev/null; then
                        timescaledb-tune --quiet --yes 2>/dev/null || log_warn "Не удалось настроить TimescaleDB автоматически"
                    fi
                else
                    log_warn "Ошибка при установке TimescaleDB"
                fi
            else
                log_warn "Пакет timescaledb-2-postgresql-16 не найден в репозитории"
            fi
        else
            log_warn "Ошибка при обновлении списка пакетов для TimescaleDB"
        fi
    else
        log_warn "Не удалось загрузить GPG ключ TimescaleDB"
    fi
    
    log_info "Финальная проверка установки PostgreSQL..."
    for cmd in psql pg_ctl pg_config; do
        if command -v "$cmd" &> /dev/null; then
            log_info "  ✓ $cmd доступен"
        else
            log_warn "  ✗ $cmd не найден"
        fi
    done
fi

log_info "Настройка и запуск PostgreSQL..."
POSTGRES_SERVICE=""
if systemctl list-unit-files 2>/dev/null | grep -q "^postgresql.service"; then
    POSTGRES_SERVICE="postgresql"
elif systemctl list-unit-files 2>/dev/null | grep -q "^postgresql@"; then
    POSTGRES_SERVICE=$(systemctl list-unit-files 2>/dev/null | grep "^postgresql@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
elif systemctl list-units 2>/dev/null | grep -q "postgresql"; then
    POSTGRES_SERVICE=$(systemctl list-units 2>/dev/null | grep "postgresql" | grep -v "@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
fi

if [ -z "$POSTGRES_SERVICE" ]; then
    if dpkg -l | grep -q "postgresql-16"; then
        if systemctl list-unit-files 2>/dev/null | grep -q "postgresql@16-main"; then
            POSTGRES_SERVICE="postgresql@16-main"
        elif systemctl list-unit-files 2>/dev/null | grep -q "postgresql@16"; then
            POSTGRES_SERVICE=$(systemctl list-unit-files 2>/dev/null | grep "postgresql@16" | head -1 | awk '{print $1}' | sed 's/\.service$//')
        fi
    fi
fi

if [ -n "$POSTGRES_SERVICE" ]; then
    log_info "Найден сервис PostgreSQL: $POSTGRES_SERVICE"
    systemctl enable "$POSTGRES_SERVICE" 2>/dev/null || log_warn "Не удалось включить сервис $POSTGRES_SERVICE"
    
    log_info "Запуск PostgreSQL..."
    systemctl start "$POSTGRES_SERVICE" 2>/dev/null || {
        log_error "Не удалось запустить сервис $POSTGRES_SERVICE"
        exit 1
    }
    
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
else
    if pgrep -x postgres >/dev/null 2>&1; then
        log_info "Процесс PostgreSQL запущен (PID: $(pgrep -x postgres | head -1))"
    else
        log_error "PostgreSQL не запущен и не удалось определить способ запуска"
        exit 1
    fi
fi

log_info "Настройка PostgreSQL для TCP/IP подключений..."
PG_CONF=$(find /etc/postgresql -name "postgresql.conf" -type f 2>/dev/null | head -1)
if [ -z "$PG_CONF" ] && command -v psql &> /dev/null; then
    PG_FULL_VERSION=$(psql --version 2>/dev/null | awk '{print $3}' || echo "")
    if [ -n "$PG_FULL_VERSION" ]; then
        PG_MAJOR=$(echo "$PG_FULL_VERSION" | cut -d. -f1)
        if [ -f "/etc/postgresql/${PG_MAJOR}/main/postgresql.conf" ]; then
            PG_CONF="/etc/postgresql/${PG_MAJOR}/main/postgresql.conf"
        fi
    fi
fi

if [ -f "$PG_CONF" ]; then
    log_info "Найден конфигурационный файл: $PG_CONF"
    
    if ! grep -q "^listen_addresses" "$PG_CONF"; then
        echo "listen_addresses = 'localhost'" >> "$PG_CONF"
        log_info "Добавлен listen_addresses в $PG_CONF"
    elif ! grep -q "^listen_addresses.*localhost" "$PG_CONF" && ! grep -q "^listen_addresses.*'\*'" "$PG_CONF"; then
        sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
        sed -i "s/^listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
        log_info "Обновлен listen_addresses в $PG_CONF"
    fi
    
    restart_postgresql "$POSTGRES_SERVICE"
fi

PG_HBA=$(dirname "$PG_CONF")/pg_hba.conf
if [ -f "$PG_HBA" ]; then
    log_info "Найден файл pg_hba.conf: $PG_HBA"
    if ! grep -q "^host.*all.*all.*127.0.0.1/32.*md5" "$PG_HBA" && ! grep -q "^host.*all.*all.*127.0.0.1/32.*password" "$PG_HBA" && ! grep -q "^host.*all.*all.*127.0.0.1/32.*trust" "$PG_HBA"; then
        echo "host    all             all             127.0.0.1/32            md5" >> "$PG_HBA"
        log_info "Добавлено правило в pg_hba.conf для подключений с localhost"
        restart_postgresql "$POSTGRES_SERVICE"
    fi
fi

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

log_info "Создание пользователя БД: ${DB_USER}..."
if sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}';" 2>/dev/null | grep -q "1"; then
    log_info "Пользователь ${DB_USER} уже существует, обновляем пароль..."
    sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || log_error "Не удалось обновить пароль пользователя ${DB_USER}"
else
    log_info "Создание нового пользователя ${DB_USER}..."
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || log_error "Не удалось создать пользователя ${DB_USER}"
fi

sudo -u postgres psql -c "ALTER USER ${DB_USER} CREATEDB;" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH SUPERUSER;" 2>/dev/null || true

log_info "Создание базы данных: ${DB_NAME}..."
if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
    log_info "База данных ${DB_NAME} уже существует"
    sudo -u postgres psql -c "ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};" 2>/dev/null || true
else
    log_info "Создание новой базы данных ${DB_NAME}..."
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || log_error "Не удалось создать базу данных ${DB_NAME}"
fi

log_info "Установка расширения TimescaleDB..."
sudo -u postgres psql -d ${DB_NAME} -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>/dev/null || log_warn "Расширение TimescaleDB не установлено"

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

configure_redis

log_info "Включение автозапуска Redis..."
systemctl enable redis-server 2>/dev/null || true

log_info "Запуск Redis..."
if ! systemctl start redis-server; then
    log_warn "Не удалось запустить Redis через systemctl, выполняем диагностику..."
    
    REDIS_ERROR=$(journalctl -u redis-server.service -n 20 --no-pager 2>/dev/null | grep -i "error\|fatal\|failed" | head -3 || echo "")
    if [ -n "$REDIS_ERROR" ]; then
        log_info "Ошибки из логов Redis:"
        echo "$REDIS_ERROR" | while read line; do
            log_info "  $line"
        done
    fi
    
    if [ -d "/var/lib/redis" ]; then
        chown -R redis:redis "/var/lib/redis" 2>/dev/null || true
    fi
    
    if netstat -tlnp 2>/dev/null | grep -q ":6379" || ss -tlnp 2>/dev/null | grep -q ":6379"; then
        OCCUPIED_PID=$(netstat -tlnp 2>/dev/null | grep ":6379" | awk '{print $7}' | cut -d'/' -f1 | head -1 || \
                      ss -tlnp 2>/dev/null | grep ":6379" | grep -oP 'pid=\K\d+' | head -1 || echo "")
        if [ -n "$OCCUPIED_PID" ]; then
            kill "$OCCUPIED_PID" 2>/dev/null || true
            sleep 2
        fi
    fi
    
    if pgrep -x redis-server >/dev/null 2>&1; then
        pkill -x redis-server 2>/dev/null || true
        sleep 2
    fi
    
    sleep 2
    if ! systemctl start redis-server; then
        if command -v service &> /dev/null; then
            service redis-server start 2>/dev/null || log_error "Redis не удалось запустить"
        else
            log_error "Redis не удалось запустить"
            exit 1
        fi
    fi
fi

log_info "Проверка статуса Redis..."
sleep 2
if systemctl is-active --quiet redis-server || pgrep -x redis-server >/dev/null 2>&1; then
    log_info "Redis запущен успешно"
else
    log_error "Redis не запущен"
    exit 1
fi

# ============================================================================
# 7. Установка Mosquitto MQTT Broker
# ============================================================================

log_info "Установка Mosquitto MQTT Broker..."
if ! command -v mosquitto &> /dev/null; then
    apt-get install -y mosquitto mosquitto-clients
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

chown "$APP_USER:$APP_GROUP" "$LARAVEL_DIR/.env"
chmod 640 "$LARAVEL_DIR/.env"

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

chown "$APP_USER:$APP_GROUP" "$LARAVEL_DIR/.env"
chmod 640 "$LARAVEL_DIR/.env"

log_info "Проверка обязательных переменных окружения..."
if ! check_required_env_vars; then
    log_error "Не все обязательные переменные окружения установлены"
    log_error "Запустите: sudo -u $APP_USER php artisan key:generate"
    exit 1
fi

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

max_attempts=15
attempt=0
DB_READY=false

while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    log_info "Попытка подключения $attempt/$max_attempts"
    
    if pgrep -x postgres >/dev/null 2>&1; then
        log_info "  ✓ Процесс PostgreSQL запущен"
    else
        log_warn "  ✗ Процесс PostgreSQL не запущен"
        if [ -n "$POSTGRES_SERVICE" ]; then
            systemctl start "$POSTGRES_SERVICE" 2>/dev/null || true
            sleep 2
        fi
        sleep 2
        continue
    fi
    
    if netstat -tlnp 2>/dev/null | grep -q ":5432" || ss -tlnp 2>/dev/null | grep -q ":5432"; then
        log_info "  ✓ PostgreSQL слушает на порту 5432"
    else
        log_warn "  ✗ PostgreSQL не слушает на порту 5432"
        sleep 2
        continue
    fi
    
    TCP_RESULT=$(PGPASSWORD="${DB_PASSWORD}" timeout 10 psql -h 127.0.0.1 -p 5432 -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1;" 2>&1)
    TCP_EXIT_CODE=$?
    
    if [ $TCP_EXIT_CODE -eq 0 ]; then
        DB_READY=true
        log_info "  ✓ Подключение через TCP/IP работает!"
        break
    else
        log_warn "  ✗ Подключение через TCP/IP не работает"
        sleep 2
    fi
done

if [ "$DB_READY" = "false" ]; then
    log_error "Не удалось подключиться к базе данных после $max_attempts попыток"
    exit 1
fi

log_info "Запуск миграций базы данных..."
update_env_var "$LARAVEL_DIR/.env" "DB_TIMEOUT" "30"
update_env_var "$LARAVEL_DIR/.env" "DB_CONNECTION_TIMEOUT" "30"

MIGRATION_ATTEMPTS=3
MIGRATION_SUCCESS=false

for attempt in $(seq 1 $MIGRATION_ATTEMPTS); do
    log_info "Попытка выполнения миграций $attempt/$MIGRATION_ATTEMPTS..."
    
    cd "$LARAVEL_DIR" || exit 1
    
    MIGRATION_OUTPUT=$(timeout 300 sudo -u "$APP_USER" php artisan migrate --force 2>&1) || {
        MIGRATION_EXIT=$?
        if [ $MIGRATION_EXIT -eq 124 ]; then
            log_error "Команда миграций превысила таймаут (5 минут)"
            exit 1
        fi
    }
    MIGRATION_EXIT=$?
    
    if [ $MIGRATION_EXIT -eq 0 ]; then
        MIGRATION_SUCCESS=true
        log_info "  ✓ Миграции выполнены успешно"
        break
    else
        log_warn "  ✗ Ошибка при выполнении миграций"
        if [ $attempt -lt $MIGRATION_ATTEMPTS ]; then
            sleep 5
        fi
    fi
done

if [ "$MIGRATION_SUCCESS" = "false" ]; then
    log_error "Не удалось выполнить миграции после $MIGRATION_ATTEMPTS попыток"
    exit 1
fi

log_info "Запуск сидеров базы данных..."
sudo -u "$APP_USER" php artisan db:seed --force 2>/dev/null || log_warn "Предупреждение: ошибка при выполнении сидеров"

# ============================================================================
# 14. Установка зависимостей Node.js
# ============================================================================

log_info "Установка зависимостей Node.js..."
cd "$LARAVEL_DIR"
sudo -u "$APP_USER" npm ci

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
    fi
done

# ============================================================================
# 17. Настройка переменных окружения для Python сервисов
# ============================================================================

log_info "Создание файла с переменными окружения для Python сервисов..."
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
fi

load_env_vars() {
    local env_file="$SERVICES_DIR/.env"
    if [ -f "$env_file" ]; then
        local env_string="PYTHONUNBUFFERED=1,PYTHONPATH=$SERVICES_DIR"
        while IFS='=' read -r key value || [ -n "$key" ]; do
            [[ "$key" =~ ^#.*$ ]] && continue
            [[ -z "$key" ]] && continue
            value=$(echo "$value" | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")
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
        
        fastcgi_buffers 16 16k;
        fastcgi_buffer_size 32k;
        fastcgi_busy_buffers_size 64k;
        fastcgi_temp_file_write_size 64k;
    }

    location ~ /\.(?!well-known).* {
        deny all;
    }

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

ln -sf /etc/nginx/sites-available/hydro /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

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

supervisorctl reread
supervisorctl update

log_warn "ВАЖНО: Настройте переменные окружения в $SERVICES_DIR/.env"
log_warn "Добавьте токены безопасности (PY_API_TOKEN, LARAVEL_API_TOKEN и т.д.)"

# ============================================================================
# 23. Финальная настройка
# ============================================================================

log_info "Настройка файрвола..."
setup_firewall

log_info "Создание скрипта обновления..."
create_update_script

log_info "Создание файла с учетными данными..."
create_credentials_file

log_info "Выполнение диагностики системы..."
run_diagnostics

# ============================================================================
# 24. Финальная информация
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
echo "  - Обновление проекта: update-hydro"
echo ""
log_warn "Не забудьте:"
echo "  1. Настроить переменные окружения в $LARAVEL_DIR/.env"
echo "     (REVERB_APP_KEY, REVERB_APP_SECRET, REVERB_ALLOWED_ORIGINS и т.д.)"
echo "  2. Настроить переменные окружения в $SERVICES_DIR/.env"
echo "     (PY_API_TOKEN, LARAVEL_API_TOKEN, MQTT пароли и т.д.)"
echo "  3. Настроить MQTT аутентификацию (если требуется)"
echo "  4. Настроить SSL/TLS для Nginx (для production)"
echo ""
log_info "Учетные данные сохранены в: /root/hydro-credentials.txt"
log_info "Для проверки доступности сайта из локальной сети:"
echo "  Откройте в браузере: http://${SERVER_IP}"
echo ""