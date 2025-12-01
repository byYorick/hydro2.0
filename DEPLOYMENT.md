# Инструкция по развертыванию проекта Hydro 2.0 без Docker

Этот документ описывает процесс развертывания проекта Hydro 2.0 на сервере без использования Docker.

## Требования

- Ubuntu 20.04+ или Debian 11+
- Минимум 4GB RAM
- Минимум 20GB свободного места на диске
- Права root (sudo)

## Быстрый старт

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt-get update && sudo apt-get upgrade -y

# Клонирование проекта (или копирование файлов)
git clone <repository-url> /opt/hydro
# ИЛИ скопируйте проект в /opt/hydro вручную
```

### 2. Запуск скрипта развертывания

```bash
cd /opt/hydro
sudo ./deploy.sh production
```

Для development окружения:
```bash
sudo ./deploy.sh development
```

### 3. Настройка переменных окружения

После развертывания необходимо настроить переменные окружения:

#### Laravel (.env)

```bash
nano /opt/hydro/backend/laravel/.env
```

Обязательные переменные для production:
- `APP_KEY` - уже сгенерирован автоматически
- `REVERB_APP_KEY` - ключ для Laravel Reverb
- `REVERB_APP_SECRET` - секретный ключ для Laravel Reverb
- `REVERB_ALLOWED_ORIGINS` - разрешенные домены для WebSocket
- `SANCTUM_STATEFUL_DOMAINS` - домены для Sanctum
- `PY_API_TOKEN` - токен для Python сервисов
- `PY_INGEST_TOKEN` - токен для приема данных
- `LARAVEL_API_TOKEN` - токен для Laravel API

#### Python сервисы (.env)

```bash
nano /opt/hydro/backend/services/.env
```

Добавьте токены безопасности:
```env
PY_API_TOKEN=your-secure-token-here
PY_INGEST_TOKEN=your-secure-token-here
LARAVEL_API_TOKEN=your-secure-token-here
MQTT_MQTT_BRIDGE_PASS=your-mqtt-password
MQTT_AUTOMATION_ENGINE_PASS=your-mqtt-password
MQTT_HISTORY_LOGGER_PASS=your-mqtt-password
MQTT_SCHEDULER_PASS=your-mqtt-password
```

### 4. Настройка MQTT аутентификации (опционально)

Если требуется аутентификация MQTT:

```bash
cd /opt/hydro/backend/services/mqtt-bridge
sudo -u hydro ./generate_passwords.sh
```

Затем настройте `/etc/mosquitto/passwords` и `/etc/mosquitto/acl`.

### 5. Перезапуск сервисов

```bash
# Перезапуск всех сервисов через Supervisor
sudo supervisorctl restart all

# Проверка статуса
sudo supervisorctl status
```

## Структура развертывания

```
/opt/hydro/
├── backend/
│   ├── laravel/          # Laravel приложение
│   │   ├── .env          # Конфигурация Laravel
│   │   └── storage/      # Логи и файлы
│   └── services/         # Python сервисы
│       ├── .env          # Общие переменные окружения
│       ├── mqtt-bridge/
│       │   └── venv/     # Виртуальное окружение Python
│       ├── automation-engine/
│       │   └── venv/
│       └── ...
└── ...

/var/log/hydro/           # Логи сервисов
├── reverb.log
├── mqtt-bridge.log
├── automation-engine.log
└── ...
```

## Управление сервисами

### Supervisor

Все сервисы управляются через Supervisor:

```bash
# Статус всех сервисов
sudo supervisorctl status

# Перезапуск конкретного сервиса
sudo supervisorctl restart hydro-reverb
sudo supervisorctl restart hydro-mqtt-bridge

# Перезапуск всех сервисов
sudo supervisorctl restart all

# Просмотр логов
sudo supervisorctl tail -f hydro-reverb
```

### Системные сервисы

```bash
# Nginx
sudo systemctl status nginx
sudo systemctl restart nginx

# PHP-FPM
sudo systemctl status php8.2-fpm
sudo systemctl restart php8.2-fpm

# PostgreSQL
sudo systemctl status postgresql
sudo systemctl restart postgresql

# Redis
sudo systemctl status redis-server
sudo systemctl restart redis-server

# Mosquitto (MQTT)
sudo systemctl status mosquitto
sudo systemctl restart mosquitto
```

## Просмотр логов

```bash
# Laravel логи
tail -f /opt/hydro/backend/laravel/storage/logs/laravel.log

# Логи сервисов
tail -f /var/log/hydro/*.log

# Логи Nginx
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log

# Логи PHP-FPM
tail -f /var/log/php8.2-fpm.log
```

## Обновление проекта

### 1. Обновление кода

```bash
cd /opt/hydro
# Если используется git:
sudo -u hydro git pull

# Или скопируйте новые файлы вручную
```

### 2. Обновление зависимостей

```bash
# Laravel
cd /opt/hydro/backend/laravel
sudo -u hydro composer install --no-interaction --prefer-dist --optimize-autoloader
sudo -u hydro npm ci

# Python сервисы
cd /opt/hydro/backend/services
for service in mqtt-bridge automation-engine history-logger scheduler digital-twin telemetry-aggregator; do
    if [ -d "$service" ] && [ -f "$service/requirements.txt" ]; then
        sudo -u hydro "$service/venv/bin/pip" install -r "$service/requirements.txt"
    fi
done
```

### 3. Миграции базы данных

```bash
cd /opt/hydro/backend/laravel
sudo -u hydro php artisan migrate --force
```

### 4. Пересборка фронтенда (production)

```bash
cd /opt/hydro/backend/laravel
sudo -u hydro npm run build
```

### 5. Очистка кеша Laravel

```bash
cd /opt/hydro/backend/laravel
sudo -u hydro php artisan config:clear
sudo -u hydro php artisan cache:clear
sudo -u hydro php artisan view:clear
sudo -u hydro php artisan route:clear
```

### 6. Перезапуск сервисов

```bash
sudo supervisorctl restart all
sudo systemctl restart php8.2-fpm
sudo systemctl restart nginx
```

## Настройка SSL/TLS (Production)

### Использование Let's Encrypt

```bash
# Установка Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com

# Автоматическое обновление
sudo certbot renew --dry-run
```

### Ручная настройка SSL

Отредактируйте `/etc/nginx/sites-available/hydro`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    # ... остальная конфигурация
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## Настройка файрвола

```bash
# Установка UFW (если не установлен)
sudo apt-get install -y ufw

# Разрешение необходимых портов
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 6001/tcp  # WebSocket (Laravel Reverb)

# Включение файрвола
sudo ufw enable
```

## Резервное копирование

### База данных

```bash
# Создание бэкапа
cd /opt/hydro/backend/laravel
sudo -u hydro php artisan backup:database --compress

# Или вручную через pg_dump
sudo -u postgres pg_dump -Fc hydro > /opt/hydro/backend/laravel/storage/app/private/backups/hydro_$(date +%Y%m%d_%H%M%S).dump
```

### Файлы проекта

```bash
# Создание архива
tar -czf /backup/hydro_$(date +%Y%m%d_%H%M%S).tar.gz \
    /opt/hydro/backend/laravel/storage \
    /opt/hydro/backend/laravel/.env
```

## Мониторинг

### Проверка здоровья системы

```bash
# Использование ресурсов
htop

# Дисковое пространство
df -h

# Использование памяти
free -h

# Статус сервисов
sudo supervisorctl status
systemctl status nginx php8.2-fpm postgresql redis-server mosquitto
```

### Метрики Prometheus (если настроен)

Доступны на портах:
- Automation Engine: `http://localhost:9401/metrics`
- History Logger: `http://localhost:9301/metrics`
- Digital Twin: `http://localhost:9403/metrics`
- Telemetry Aggregator: `http://localhost:9404/metrics`

## Устранение неполадок

### Проблемы с правами доступа

```bash
# Исправление прав Laravel
sudo chown -R hydro:hydro /opt/hydro/backend/laravel
sudo chmod -R 755 /opt/hydro/backend/laravel
sudo chmod -R 775 /opt/hydro/backend/laravel/storage
sudo chmod -R 775 /opt/hydro/backend/laravel/bootstrap/cache
```

### Проблемы с базой данных

```bash
# Проверка подключения
sudo -u postgres psql -d hydro -c "SELECT version();"

# Проверка расширений
sudo -u postgres psql -d hydro -c "\dx"

# Перезапуск PostgreSQL
sudo systemctl restart postgresql
```

### Проблемы с сервисами

```bash
# Просмотр логов Supervisor
sudo tail -f /var/log/supervisor/supervisord.log

# Перезапуск Supervisor
sudo systemctl restart supervisor
sudo supervisorctl reread
sudo supervisorctl update
```

### Проблемы с Nginx

```bash
# Проверка конфигурации
sudo nginx -t

# Просмотр логов ошибок
sudo tail -f /var/log/nginx/error.log

# Перезапуск
sudo systemctl restart nginx
```

## Удаление развертывания

Если нужно полностью удалить развертывание:

```bash
# Остановка сервисов
sudo supervisorctl stop all
sudo systemctl stop nginx php8.2-fpm

# Удаление конфигураций
sudo rm -f /etc/supervisor/conf.d/hydro-*.conf
sudo rm -f /etc/nginx/sites-available/hydro
sudo rm -f /etc/nginx/sites-enabled/hydro

# Удаление проекта (опционально)
sudo rm -rf /opt/hydro

# Удаление логов
sudo rm -rf /var/log/hydro
```

**ВНИМАНИЕ:** Это не удалит базу данных и установленные системные пакеты. Для полного удаления выполните удаление вручную.

## Дополнительная информация

- Документация Laravel: https://laravel.com/docs
- Документация Supervisor: http://supervisord.org/
- Документация Nginx: https://nginx.org/en/docs/
- Документация PostgreSQL: https://www.postgresql.org/docs/

