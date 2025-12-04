# Инструкция по обновлению проекта на сервере

## Быстрое обновление (рекомендуется)

### 1. Подключитесь к серверу по SSH
```bash
ssh user@your-server-ip
```

### 2. Перейдите в директорию проекта
```bash
cd /opt/hydro/hydro2.0
# или если проект в другой директории:
# cd /path/to/your/project
```

### 3. Сохраните текущие изменения (если есть)
```bash
# Проверьте статус
git status

# Если есть незакоммиченные изменения, сохраните их
git stash
```

### 4. Получите обновления из репозитория
```bash
# Для ветки main
git pull origin main

# Или для ветки ubuntu
git pull origin ubuntu

# Если ветки разошлись, используйте merge:
git pull --no-rebase origin main
```

### 5. Обновите зависимости Laravel
```bash
cd backend/laravel
composer install --no-dev --optimize-autoloader
npm ci --legacy-peer-deps
npm run build
```

### 6. Примените миграции базы данных (если есть)
```bash
php artisan migrate --force
```

### 7. Очистите кэши Laravel
```bash
php artisan config:clear
php artisan cache:clear
php artisan route:clear
php artisan view:clear
php artisan optimize
```

### 8. Перезапустите сервисы
```bash
# Если используется Supervisor
sudo supervisorctl restart all

# Или перезапустите конкретные сервисы:
sudo supervisorctl restart hydro-laravel
sudo supervisorctl restart hydro-mqtt-bridge
sudo supervisorctl restart hydro-history-logger
sudo supervisorctl restart hydro-automation-engine
sudo supervisorctl restart hydro-digital-twin
sudo supervisorctl restart hydro-scheduler

# Проверьте статус
sudo supervisorctl status
```

### 9. Если используется Docker
```bash
cd backend
docker-compose pull
docker-compose up -d --build
docker-compose restart
```

## Полный скрипт обновления

Создайте файл `update.sh` на сервере:

```bash
#!/bin/bash
set -e

PROJECT_DIR="/opt/hydro/hydro2.0"
LARAVEL_DIR="${PROJECT_DIR}/backend/laravel"
BRANCH="${1:-main}"

echo "🔄 Начинаем обновление проекта..."

cd "$PROJECT_DIR"

# Сохраняем изменения
echo "📦 Сохраняем текущие изменения..."
git stash

# Получаем обновления
echo "⬇️  Получаем обновления из репозитория..."
git pull --no-rebase origin "$BRANCH"

# Обновляем зависимости Laravel
echo "📚 Обновляем зависимости Laravel..."
cd "$LARAVEL_DIR"
composer install --no-dev --optimize-autoloader
npm ci --legacy-peer-deps
npm run build

# Применяем миграции
echo "🗄️  Применяем миграции базы данных..."
php artisan migrate --force

# Очищаем кэши
echo "🧹 Очищаем кэши..."
php artisan config:clear
php artisan cache:clear
php artisan route:clear
php artisan view:clear
php artisan optimize

# Перезапускаем сервисы
echo "🔄 Перезапускаем сервисы..."
sudo supervisorctl restart all

echo "✅ Обновление завершено!"
echo "📊 Статус сервисов:"
sudo supervisorctl status
```

Использование:
```bash
chmod +x update.sh
sudo ./update.sh main  # или ubuntu
```

## Обновление с бэкапом (безопасный вариант)

### 1. Создайте бэкап перед обновлением
```bash
cd /opt/hydro/hydro2.0/backend/laravel
php artisan backup:full
```

### 2. Выполните обновление (шаги 3-8 из быстрого обновления)

### 3. Проверьте работоспособность
```bash
# Проверьте логи
sudo tail -f /var/log/hydro/laravel.log
sudo tail -f /var/log/hydro/mqtt-bridge.log

# Проверьте API
curl http://localhost/api/system/health
```

## Решение проблем

### Если git pull не работает из-за расходящихся веток:
```bash
git pull --no-rebase origin main
# или
git pull --rebase origin main
```

### Если есть конфликты:
```bash
# Посмотрите конфликты
git status

# Разрешите конфликты вручную, затем:
git add .
git commit -m "Resolve merge conflicts"
```

### Если миграции не применяются:
```bash
# Проверьте статус миграций
php artisan migrate:status

# Примените миграции с откатом при ошибке
php artisan migrate --force --pretend
```

### Если сервисы не запускаются:
```bash
# Проверьте логи
sudo tail -n 100 /var/log/hydro/*.log

# Перезапустите Supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart all
```

## Автоматическое обновление через webhook (опционально)

Можно настроить автоматическое обновление при push в репозиторий через GitHub Actions или webhook.




