# BACKUP_AND_RECOVERY.md
# Полная система резервного копирования и восстановления 2.0
# PostgreSQL • MQTT • Laravel • Python • ESP32 • OTA • Docker

Документ описывает полную стратегию резервного копирования (Backup) 
и восстановления (Recovery) для гидропонной системы 2.0.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Общая концепция Backup & Recovery

Система состоит из нескольких уровней:

1. **PostgreSQL** — основная БД (критически важная)
2. **Laravel Backend** — конфигурации, .env, файлы OTA
3. **Python Scheduler** — конфигурации и secrets
4. **MQTT Broker** — ACL, пароли
5. **ESP32 узлы** — прошивки + конфигурация NVS
6. **Docker** — тома, образы, сеть

Цель: обеспечить восстановление **всей системы** за ≤ 30 минут.

---

# 2. Уровень 1: PostgreSQL Backup

## 2.1. Что нужно бэкапить:

- Полная БД (все таблицы):
 - zones
 - nodes
 - telemetry_last
 - telemetry_samples
 - alerts
 - events
 - recipes & phases
 - commands
 - users
- Схема БД (DDL)
- Роли PostgreSQL

## 2.2. Типы бэкапов

### Полный dump (ежедневно)
```
pg_dump -Fc -U postgres hydro2 > backup/full_2025_01_01.dump
```

### Инкрементальный WAL архив (каждые 15 мин)
```
archive_mode = on
archive_command = 'cp %p /wal_archive/%f'
```

## 2.3. Ротация

- хранить **30 дней** полных бэкапов
- хранить **7 дней** WAL журналов

---

# 3. Уровень 2: Laravel Backup

## 3.1. Что нужно бэкапить:

- `.env`
- `storage/app/ota/` — прошивки ESP32
- `storage/app/public/`
- `composer.lock`
- файлы кэша конфигов (опционально)

## 3.2. Команда:

```
zip -r laravel_backup.zip .env storage/app/ota storage/app/public composer.lock
```

---

# 4. Уровень 3: Python Service Backup

## 4.1. Что нужно бэкапить:

- `.env`
- конфиг nodes secrets (`nodes.json`)
- scheduler config (`config.yaml`)

## 4.2. Команда:

```
zip python_backup.zip .env secrets/ config/
```

---

# 5. Уровень 4: MQTT Backup

## 5.1. Что нужно бэкапить:

- `mosquitto/passwd`
- `mosquitto/acl`
- конфиг mosquitto.conf

## 5.2. Команда:

```
zip mqtt_backup.zip mosquitto/passwd mosquitto/acl mosquitto.conf
```

---

# 6. Уровень 5: ESP32 Backup

## 6.1. Что нужно бэкапить:

- бинарные прошивки (Laravel OTA storage)
- конфигурации узлов (node_secret и параметры в NVS)

## 6.2. Варианты восстановления:

- прошить вручную через USB
- OTA (если узел работает)
- автоматические скрипты `esp-update`

---

# 7. Уровень 6: Docker Backup

## 7.1. Бэкап Docker Volumes

```
docker run --rm \
 -v pgdata:/volume \
 -v $(pwd):/backup \
 alpine \
 tar czf /backup/pgdata_backup.tar.gz /volume
```

## 7.2. Бэкап docker-compose.yml

```
cp docker-compose.yml backups/
```

---

# 8. Полный Backup Script (автоматизация)

Пример bash-скрипта:

```bash
#!/bin/bash
DATE=$(date +%Y-%m-%d_%H-%M)

mkdir -p /backups/$DATE

# PostgreSQL
pg_dump -Fc -U postgres hydro2 > /backups/$DATE/db.dump

# WAL
cp -r /wal_archive /backups/$DATE/wal/

# Laravel
zip -r /backups/$DATE/laravel.zip /var/www/laravel/.env /var/www/laravel/storage/app/ota

# Python
zip -r /backups/$DATE/python.zip /srv/python/.env /srv/python/secrets

# MQTT
zip -r /backups/$DATE/mqtt.zip /mosquitto/

# Docker volumes
tar czf /backups/$DATE/docker_pgdata.tar.gz /var/lib/docker/volumes/pgdata/
```

---

# 9. Recovery (восстановление)

## 9.1. Постгрес восстановление

```
pg_restore -U postgres -d hydro2 backup.dump
```

Если нужны WAL журналы:

1. восстановить dump
2. включить recovery.conf
3. поместить WAL
4. запустить PostgreSQL

---

## 9.2. Восстановление Laravel

```
unzip laravel.zip
cp .env /var/www/
php artisan key:generate
php artisan migrate --force
```

---

## 9.3. Восстановление Python Service

```
unzip python.zip
cp .env /srv/python
systemctl restart python_scheduler
```

---

## 9.4. Восстановление MQTT

```
unzip mqtt.zip
systemctl restart mosquitto
```

---

## 9.5. Восстановление ESP32

Варианты:

1. USB прошивка:
```
esptool write_flash 0x0 firmware.bin
```

2. OTA:
- добавить прошивку в Laravel OTA storage
- инициировать OTA из UI

---

# 10. Disaster Recovery (аварийное восстановление)

Сценарии:

### 10.1. Потеря PostgreSQL
- восстановить последний полный dump
- применить WAL-журналы
- запустить Laravel

### 10.2. Потеря MQTT
- восстановить конфиг
- перезапустить узлы ESP32 через команду «reboot»

### 10.3. Полный сбой сервера
Последовательность восстановления:

1. поднять Docker-инфраструктуру
2. восстановить PostgreSQL
3. восстановить Laravel
4. восстановить Python
5. восстановить MQTT
6. перепривязать ESP32‑узлы (если потеряли node_secret)

### 10.4. Потеря всех узлов ESP32
- перепрошить вручную
- загрузить конфиги NVS
- выполнить авто-регистрацию узлов через API

---

# 11. Правила для ИИ

ИИ может:
- добавлять новые стратегии бэкапов,
- оптимизировать recovery шаги,
- улучшать хранение секретов,
- создавать автоматические скрипты.

ИИ НЕ может:
- отключать бэкапы,
- упрощать безопасность (например, хранить секреты в БД без шифрования),
- удалять критически важные элементы.

---

# 12. Чек‑лист Backup & Recovery

1. PostgreSQL бэкап создаётся ежедневно? 
2. WAL архивируются каждые 15 минут? 
3. OTA прошивки сохранены? 
4. Docker тома архивируются? 
5. Все .env файлы сохранены? 
6. MQTT ACL/пароли есть в архиве? 
7. Python secrets сохранены? 
8. Проверено восстановление хотя бы раз в месяц? 
9. Disaster Recovery документ актуален? 

---

# Конец файла BACKUP_AND_RECOVERY.md
