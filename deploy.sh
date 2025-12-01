#!/bin/bash
set -e

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
apt-get update -qq

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
    apt-get update -qq
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
    apt-get update -qq
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
    apt-get update -qq
    apt-get install -y -qq nodejs
else
    log_info "Node.js 20 уже установлен"
fi

# ============================================================================
# 5. Установка PostgreSQL с TimescaleDB
# ============================================================================

log_info "Установка PostgreSQL 16 с TimescaleDB..."
if ! command -v psql &> /dev/null; then
    # Установка PostgreSQL (используем современный метод без apt-key)
    mkdir -p /etc/apt/keyrings
    sh -c 'echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg
    chmod 644 /etc/apt/keyrings/postgresql.gpg
    sh -c 'echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
    apt-get update -qq
    apt-get install -y -qq postgresql-16 postgresql-contrib-16

    # Установка TimescaleDB (используем современный метод)
    sh -c 'echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main" > /etc/apt/sources.list.d/timescaledb.list'
    wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg
    chmod 644 /etc/apt/keyrings/timescaledb.gpg
    sh -c 'echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main" > /etc/apt/sources.list.d/timescaledb.list'
    apt-get update -qq
    apt-get install -y -qq timescaledb-2-postgresql-16
    timescaledb-tune --quiet --yes
else
    log_info "PostgreSQL уже установлен"
fi

# Настройка PostgreSQL
log_info "Настройка PostgreSQL..."
# Определяем имя сервиса PostgreSQL (может быть postgresql, postgresql@16-main и т.д.)
POSTGRES_SERVICE=""
if systemctl list-unit-files | grep -q "^postgresql.service"; then
    POSTGRES_SERVICE="postgresql"
elif systemctl list-unit-files | grep -q "^postgresql@"; then
    # Находим первый доступный сервис postgresql@
    POSTGRES_SERVICE=$(systemctl list-unit-files | grep "^postgresql@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
elif systemctl list-unit-files | grep -q "postgresql"; then
    # Пробуем найти любой сервис с postgresql в имени
    POSTGRES_SERVICE=$(systemctl list-unit-files | grep "postgresql" | grep -v "@" | head -1 | awk '{print $1}' | sed 's/\.service$//')
fi

if [ -n "$POSTGRES_SERVICE" ]; then
    log_info "Используется сервис PostgreSQL: $POSTGRES_SERVICE"
    systemctl enable "$POSTGRES_SERVICE" 2>/dev/null || log_warn "Не удалось включить сервис $POSTGRES_SERVICE (возможно, уже включен)"
    systemctl start "$POSTGRES_SERVICE" 2>/dev/null || log_warn "Не удалось запустить сервис $POSTGRES_SERVICE (возможно, уже запущен)"
    
    # Ждем, пока PostgreSQL запустится
    log_info "Ожидание запуска PostgreSQL..."
    sleep 3
    if systemctl is-active --quiet "$POSTGRES_SERVICE"; then
        log_info "PostgreSQL запущен успешно"
    else
        log_warn "PostgreSQL может быть не запущен, проверьте вручную: systemctl status $POSTGRES_SERVICE"
    fi
else
    log_warn "Не удалось определить имя сервиса PostgreSQL"
    log_warn "Попробуйте запустить вручную: sudo systemctl start postgresql"
    log_warn "Или проверьте доступные сервисы: systemctl list-unit-files | grep postgresql"
fi

# Настройка PostgreSQL для приема TCP/IP подключений
log_info "Настройка PostgreSQL для TCP/IP подключений..."
# Находим конфигурационный файл PostgreSQL
PG_VERSION=$(psql --version 2>/dev/null | awk '{print $3}' | cut -d. -f1,2 || echo "16")
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

if [ -f "$PG_CONF" ]; then
    # Настраиваем listen_addresses для приема подключений на localhost
    if ! grep -q "^listen_addresses" "$PG_CONF"; then
        echo "listen_addresses = 'localhost'" >> "$PG_CONF"
        log_info "Добавлен listen_addresses в $PG_CONF"
    elif ! grep -q "^listen_addresses.*localhost" "$PG_CONF"; then
        sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
        sed -i "s/^listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
        log_info "Обновлен listen_addresses в $PG_CONF"
    fi
    
    # Перезапускаем PostgreSQL для применения изменений
    if [ -n "$POSTGRES_SERVICE" ] && systemctl is-active --quiet "$POSTGRES_SERVICE"; then
        log_info "Перезапуск PostgreSQL для применения изменений..."
        systemctl restart "$POSTGRES_SERVICE" 2>/dev/null || true
        sleep 3
    fi
else
    log_warn "Конфигурационный файл PostgreSQL не найден: $PG_CONF"
    log_warn "Убедитесь, что PostgreSQL настроен на прослушивание localhost"
fi

# Проверяем pg_hba.conf для разрешения подключений
if [ -f "$PG_HBA" ]; then
    if ! grep -q "^host.*all.*all.*127.0.0.1/32.*md5" "$PG_HBA" && ! grep -q "^host.*all.*all.*127.0.0.1/32.*password" "$PG_HBA"; then
        echo "host    all             all             127.0.0.1/32            md5" >> "$PG_HBA"
        log_info "Добавлено правило в pg_hba.conf для подключений с localhost"
        
        # Перезапускаем PostgreSQL для применения изменений
        if [ -n "$POSTGRES_SERVICE" ] && systemctl is-active --quiet "$POSTGRES_SERVICE"; then
            log_info "Перезапуск PostgreSQL для применения изменений pg_hba.conf..."
            systemctl restart "$POSTGRES_SERVICE" 2>/dev/null || true
            sleep 3
        fi
    fi
fi

# Создание базы данных и пользователя
if [ "$ENVIRONMENT" = "production" ]; then
    DB_NAME="hydro"
    DB_USER="hydro"
    DB_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 32)}"
else
    DB_NAME="hydro_dev"
    DB_USER="hydro"
    DB_PASSWORD="hydro"
fi

sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || log_warn "Пользователь ${DB_USER} уже существует"
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || log_warn "База данных ${DB_NAME} уже существует"
sudo -u postgres psql -d ${DB_NAME} -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>/dev/null || log_warn "Расширение TimescaleDB уже установлено"
sudo -u postgres psql -c "ALTER USER ${DB_USER} CREATEDB;" 2>/dev/null || true

log_info "Пароль PostgreSQL для пользователя ${DB_USER}: ${DB_PASSWORD}"
log_warn "Сохраните этот пароль! Он понадобится для настройки .env файла"

# ============================================================================
# 6. Установка Redis
# ============================================================================

log_info "Установка Redis..."
if ! command -v redis-server &> /dev/null; then
    apt-get install -y -qq redis-server
else
    log_info "Redis уже установлен"
fi

# Настройка Redis
if grep -q "^supervised no" /etc/redis/redis.conf; then
    sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
fi
if grep -q "^# maxmemory <bytes>" /etc/redis/redis.conf; then
    sed -i 's/^# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf
elif ! grep -q "^maxmemory" /etc/redis/redis.conf; then
    echo "maxmemory 512mb" >> /etc/redis/redis.conf
fi
if grep -q "^# maxmemory-policy noeviction" /etc/redis/redis.conf; then
    sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
elif ! grep -q "^maxmemory-policy" /etc/redis/redis.conf; then
    echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
fi

systemctl enable redis-server
systemctl restart redis-server

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
# Ждем, пока PostgreSQL будет готов принимать подключения
max_attempts=30
attempt=0
DB_READY=false

while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    if sudo -u postgres psql -c "SELECT 1;" >/dev/null 2>&1; then
        # Проверяем подключение от имени пользователя БД
        if PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" >/dev/null 2>&1; then
            DB_READY=true
            log_info "Подключение к базе данных установлено"
            break
        else
            log_info "Попытка $attempt/$max_attempts: PostgreSQL запущен, но подключение не установлено, ожидание..."
        fi
    else
        log_info "Попытка $attempt/$max_attempts: PostgreSQL не готов, ожидание..."
    fi
    sleep 2
done

if [ "$DB_READY" = "false" ]; then
    log_error "Не удалось подключиться к базе данных после $max_attempts попыток"
    log_error "Проверьте:"
    log_error "  1. Запущен ли PostgreSQL: sudo systemctl status postgresql"
    log_error "  2. Настроен ли PostgreSQL на прослушивание TCP/IP: sudo grep 'listen_addresses' /etc/postgresql/*/main/postgresql.conf"
    log_error "  3. Правильность пароля в .env файле"
    exit 1
fi

log_info "Запуск миграций базы данных..."
if sudo -u "$APP_USER" php artisan migrate --force; then
    log_info "Миграции выполнены успешно"
else
    log_error "Ошибка при выполнении миграций!"
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

