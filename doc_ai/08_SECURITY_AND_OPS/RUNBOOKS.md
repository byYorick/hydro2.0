# RUNBOOKS.md

Быстрые процедуры на случай инцидентов.

## 1. Backend не стартует / 500
- Проверить логи контейнера `laravel` (LOG_CHANNEL=stderr): `docker compose logs -f laravel`.
- Применить миграции: `docker compose exec laravel php artisan migrate --force`.
- Очистить кеши: `php artisan config:clear && php artisan cache:clear && php artisan view:clear`.
- Проверить переменные окружения (.env / compose): DB_HOST/DB_PORT/DB_DATABASE/DB_USERNAME/DB_PASSWORD.

## 2. БД недоступна
- Проверить `docker compose ps` и логи `db`.
- Локально: `docker compose exec db psql -U hydro -d hydro_dev -c '\l'`.
- Восстановить из бэкапа (см. BACKUP_RESTORE.md).

## 3. WebSockets/Realtime не работает
- Проверить `reverb` конфиг (`config/reverb.php`) и переменные REVERB_*.
- Убедиться, что фронтенд использует правильные VITE_WS_HOST/PORT/TLS.
- Проверить авторизацию приватных каналов (`routes/channels.php`) и токен сессии.

## 4. Playwright E2E падает (webServer)
- Освободить порт 8000, проверить `php artisan serve` локально.
- Запустить `php artisan migrate:fresh --seed` перед прогоном.
- См. артефакт `playwright-report` в GitHub Actions.

## 5. Миграции упали на CI
- Проверить Postgres сервис в CI (здоровье).
- Убедиться, что .env в CI переписан на pgsql.
- Логи шага `DB migrate + seed` в Actions.

## 6. Алерты/подтверждения не работают
- Проверить `PATCH /api/alerts/{id}/ack` (sanctum + role).
- Провалиться в логи запросов (Laravel HTTP logging при DEBUG).
- Убедиться, что `useAlertsStore.setResolved` вызывается на фронте.

## 7. Метрики/здоровье сервисов
- `GET /api/system/health` — базовая проверка приложения.
- MQTT bridge: `http://localhost:9000/metrics` (healthcheck в docker-compose).

## 8. Обновление зависимостей
- Node: `rm -rf node_modules && npm install`.
- PHP: `composer install` и `php artisan optimize:clear`.

## 9. Безопасность
- Composer audit и NPM audit (см. CI). Критичные — оформить тикеты.

---

## 10. Восстановление PostgreSQL из бэкапа

### 10.1. Быстрое восстановление
```bash
# Найти последний бэкап
BACKUP_DIR=/backups/postgres/$(ls -t /backups/postgres | head -1)
DUMP_FILE=$(find $BACKUP_DIR -name "*.dump" | head -1)

# Восстановить
cd backend/scripts/restore
./postgres_restore.sh $DUMP_FILE
```

### 10.2. Восстановление с проверкой
```bash
# Список доступных бэкапов
php artisan backup:list

# Восстановление с проверкой целостности
BACKUP_DIR=/backups/postgres/YYYYMMDD_HHMMSS
./postgres_restore.sh $BACKUP_DIR/*.dump --wal-dir /wal_archive
```

### 10.3. Point-in-Time Recovery (PITR)
1. Восстановить последний полный дамп
2. Настроить `recovery.conf` (PostgreSQL 12+) или `postgresql.conf`
3. Поместить WAL файлы в директорию восстановления
4. Запустить PostgreSQL в режиме recovery

---

## 11. Восстановление Laravel

### 11.1. Восстановление из архива
```bash
# Найти архив
ARCHIVE=$(find /backups/laravel -name "laravel_*.zip" | sort -r | head -1)

# Восстановить
cd backend/scripts/restore
./laravel_restore.sh $ARCHIVE
```

### 11.2. После восстановления
```bash
cd backend/laravel
composer install
php artisan migrate --force
php artisan config:clear
php artisan cache:clear
php artisan key:generate  # если нужно
```

---

## 12. Полное восстановление системы

### 12.1. Восстановление всех компонентов
```bash
# Найти последний полный бэкап
BACKUP_DIR=/backups/full/$(ls -t /backups/full | head -1)

# Выполнить полное восстановление
cd backend/scripts/restore
./full_restore.sh $BACKUP_DIR
```

### 12.2. Последовательность восстановления
1. **PostgreSQL** — восстановление БД
2. **Laravel** — восстановление файлов и конфигураций
3. **Python Services** — восстановление конфигураций (вручную)
4. **MQTT** — восстановление конфигураций (вручную)
5. **Docker Volumes** — восстановление volumes (требует остановки сервисов)

### 12.3. После полного восстановления
```bash
# Перезапуск сервисов
docker-compose restart

# Проверка логов
docker-compose logs -f

# Проверка миграций
docker-compose exec laravel php artisan migrate:status
```

---

## 13. Диагностика бэкапов

### 13.1. Проверка целостности бэкапов
```bash
# Список бэкапов с проверкой
php artisan backup:list --verify

# Проверка конкретного бэкапа
BACKUP_DIR=/backups/full/YYYYMMDD_HHMMSS
if [ -f "$BACKUP_DIR/manifest.json" ]; then
    cat $BACKUP_DIR/manifest.json | jq .
fi
```

### 13.2. Проверка доступности WAL архивов
```bash
# Проверка WAL директории
ls -lh /wal_archive

# Проверка последних WAL файлов
ls -lt /wal_archive | head -10

# Проверка размера WAL архивов
du -sh /wal_archive
```

### 13.3. Проверка свободного места
```bash
# Проверка места на диске
df -h /backups

# Размер директории бэкапов
du -sh /backups/*

# Поиск больших файлов
find /backups -type f -size +1G -ls
```

### 13.4. Проверка расписания бэкапов
```bash
# Проверка расписания в Laravel
docker-compose exec laravel php artisan schedule:list

# Проверка последнего выполнения
docker-compose exec laravel php artisan schedule:test
```

---

## 14. Аварийные ситуации

### 14.1. Полный сбой сервера

**Последовательность восстановления:**

1. **Поднять Docker инфраструктуру**
   ```bash
   cd backend
   docker-compose up -d db
   ```

2. **Восстановить PostgreSQL**
   ```bash
   ./scripts/restore/postgres_restore.sh /backups/postgres/.../postgres_*.dump
   ```

3. **Восстановить Laravel**
   ```bash
   ./scripts/restore/laravel_restore.sh /backups/laravel/.../laravel_*.zip
   ```

4. **Запустить все сервисы**
   ```bash
   docker-compose up -d
   ```

5. **Проверить миграции**
   ```bash
   docker-compose exec laravel php artisan migrate --force
   ```

6. **Перепривязать ESP32 узлы** (если потеряли node_secret)
   - Через UI: настройки узлов
   - Через API: `POST /api/nodes/{id}/register`

### 14.2. Потеря БД

**Быстрое восстановление:**
```bash
# Остановить сервисы, использующие БД
docker-compose stop laravel automation-engine scheduler history-logger

# Восстановить БД
./scripts/restore/postgres_restore.sh /backups/postgres/.../postgres_*.dump

# Запустить сервисы
docker-compose start
```

### 14.3. Потеря MQTT конфигурации

**Восстановление:**
```bash
# Распаковать архив MQTT
unzip /backups/mqtt/.../mqtt_*.zip -d /tmp/mqtt_restore

# Восстановить конфигурации
cp /tmp/mqtt_restore/mosquitto*.conf ./services/mqtt-bridge/

# Перезапустить MQTT
docker-compose restart mqtt
```

### 14.4. Потеря всех узлов ESP32

**Восстановление:**

1. **Перепрошить вручную через USB**
   ```bash
   esptool.py --port /dev/ttyUSB0 write_flash 0x0 firmware.bin
   ```

2. **Загрузить конфиги NVS** (если есть бэкап)
   - Использовать `nvs_flash` утилиту ESP-IDF

3. **Авто-регистрация узлов через API**
   ```bash
   curl -X POST http://localhost:8080/api/nodes/register \
     -H "Authorization: Bearer TOKEN" \
     -d '{"node_id": "...", "secret": "..."}'
   ```

### 14.5. Перегрузка PostgreSQL

**Действия:**

1. **Переход в read-only режим** (через Laravel)
   ```php
   // Временно в config/database.php
   'pgsql' => [
       'options' => [PDO::ATTR_EMULATE_PREPARES => true],
       'read' => ['host' => 'db'],
       'write' => ['host' => 'db'],
   ]
   ```

2. **Локальное буферирование** (Python сервисы)
   - Включить локальное кэширование телеметрии
   - Отложить запись в БД

3. **Ограничение AI** (если используется)
   - Перевести AI в restricted mode
   - Запретить генерацию команд

---

## 15. Профилактика и мониторинг

### 15.1. Ежедневные проверки
- Проверка успешности бэкапов: `php artisan backup:list`
- Проверка логов бэкапов: `tail -f /var/log/backup.log`
- Проверка свободного места: `df -h /backups`

### 15.2. Еженедельные проверки
- Тестирование восстановления одного компонента
- Проверка ротации бэкапов
- Проверка целостности старых бэкапов

### 15.3. Ежемесячные проверки
- Полное тестирование disaster recovery
- Проверка всех процедур восстановления
- Обновление документации при необходимости

---

## 16. Полезные команды

### 16.1. Ручной бэкап
```bash
# Полный бэкап через Laravel
php artisan backup:full

# Только БД
php artisan backup:database

# Список бэкапов
php artisan backup:list --verify
```

### 16.2. Ручная ротация
```bash
# Запуск ротации вручную
./scripts/backup/rotate_backups.sh
```

### 16.3. Проверка WAL архивирования
```bash
# Проверка настройки WAL
docker-compose exec db psql -U hydro -c "SHOW archive_mode;"
docker-compose exec db psql -U hydro -c "SHOW archive_command;"
```

---

## 17. Контакты и эскалация

При критических инцидентах:
1. Проверить логи: `docker-compose logs`
2. Проверить статус сервисов: `docker-compose ps`
3. Проверить бэкапы: `php artisan backup:list`
4. При необходимости — восстановление из бэкапа
5. Эскалация при невозможности восстановления


