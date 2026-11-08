# BACKUP_AND_RECOVERY.md
# Полная система резервного копирования и восстановления 2.0
# PostgreSQL • MQTT • Laravel • Python • ESP32 • OTA • Docker

Документ описывает полную стратегию резервного копирования (Backup) 
и восстановления (Recovery) для гидропонной системы 2.0.

**Сверено:** 2026-11-07. Логический backup/restore реализован скриптами
`backend/scripts/backup/postgres_backup.sh` и `backend/scripts/restore/postgres_restore.sh`.
Полноценная процедура физического PITR этими скриптами не реализована.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Общая концепция Backup & Recovery

Система состоит из нескольких уровней:

1. **PostgreSQL** — основная БД (критически важная)
2. **Laravel Backend** — конфигурации, .env, файлы OTA
3. **Python-сервисы** (automation-engine, history-logger, mqtt-bridge) — конфигурации и secrets
4. **MQTT Broker** — ACL, пароли
5. **ESP32 узлы** — прошивки + конфигурация NVS
6. **Docker** — тома, образы, сеть

Целевой RTO — ≤30 минут. Фактические RTO/RPO фиксируются после восстановления
на изолированном стенде; наличие скрипта или WAL-архива не подтверждает достижение цели.

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

### Логическая копия — реализовано

`postgres_backup.sh` создаёт custom-format dump через `pg_dump -Fc`. Перед запуском
выбираются `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` и `BACKUP_DIR`;
секреты передаются через защищённое окружение, не выводятся в отчёт.
Скрипт требует доступные PostgreSQL client tools и доступ к выбранной БД.
Расписание и успешность ежедневного запуска проверяются отдельно.

Dump содержит схему и данные одной БД. Глобальные роли кластера сохраняются
отдельно: `pg_dump` не является их резервной копией.

### Физическая копия + WAL — отдельная процедура PITR

В production Compose настроено архивирование WAL в `wal_archive`. WAL-сегменты
архивируются по мере завершения; интервал «каждые 15 минут» не гарантирован.
Для PITR нужны согласованная физическая base backup (например, `pg_basebackup`)
и непрерывная цепочка WAL от начала этой копии до целевой точки восстановления.
Один `pg_dump` вместе с WAL такой копией не является.

Версия production — PostgreSQL 16 / TimescaleDB; версии расширений и образа
при восстановлении должны быть совместимы с копией. Порядок физического recovery
сверяется с [документацией PostgreSQL 16](https://www.postgresql.org/docs/16/continuous-archiving.html).

## 2.3. Ротация

- хранить **30 дней** полных бэкапов
- хранить **7 дней** WAL журналов

При настроенном PITR нельзя удалять WAL, необходимые для любой сохраняемой
физической base backup. Фактические сроки и реализация ротации сверяются с
`DATA_RETENTION_POLICY.md` и `backend/scripts/backup/rotate_backups.sh`.

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

- `backend/.env` / `backend/.env.prod` и используемые внешние secret files;
- конфиги сервисов (`automation-engine`, `history-logger`, `mqtt-bridge`, при наличии);
- per-node secrets из БД (`nodes.config.node_secret`) и отдельно NVS устройств. Обязательного runtime-файла `nodes.json` нет.

## 4.2. Команда:

`backend/scripts/backup/python_backup.sh` сохраняет service `.env` / config-каталоги и deployment `compose.env` / `docker-compose.yml`, переданные `FullBackupCommand`. Отсутствие заданного deployment source завершает компонент ошибкой. Источник — read-only mounts `/backup-sources`; копии содержат secrets и хранятся с закрытыми правами.

---

# 5. Уровень 4: MQTT Backup

## 5.1. Что нужно бэкапить:

- `backend/services/mqtt-bridge/mosquitto.dev.conf` либо `mosquitto.prod.conf`;
- `backend/services/mqtt-bridge/passwords.txt` и `acl`;
- production `certs/` и внешний источник сертификатов/ключей, если используется.

## 5.2. Команда:

Точные источники — mounts сервиса `mqtt` в выбранном Compose. `mqtt_backup.sh` сохраняет имеющиеся dev/prod конфиги, обязательные `passwords.txt` и `acl`, а также `certs/` (включая содержимое symlink targets) и MQTT YAML. Отсутствие обязательных auth/config файлов завершает backup ошибкой; пустой zip не считается успехом. Внешние источники сертификатов/секретов, которые не представлены в этих mounts, сохраняются отдельно.

---

# 6. Уровень 5: ESP32 Backup

## 6.1. Что нужно бэкапить:

- бинарные прошивки (Laravel OTA storage)
- конфигурации узлов (node_secret и параметры в NVS)

## 6.2. Варианты восстановления:

- прошить вручную через USB
- OTA — planned; текущая процедура восстановления через USB описана в §9.5

---

# 7. Уровень 6: Docker Backup

## 7.1. Бэкап Docker Volumes

Нельзя считать обычный `tar` работающего PGDATA согласованной копией БД.
Для PostgreSQL выбирается либо логический dump, либо корректная процедура
физической base backup + WAL. Offline-копия PGDATA требует остановленного
кластера и всех необходимых файлов/томов; она не заменяет проверку восстановления.
Имена томов определяются по выбранному Compose-проекту, а не по шаблону `pgdata`.

## 7.2. Бэкап docker-compose.yml

```
cp backend/docker-compose.prod.yml backups/
```

Production env и секреты сохраняются отдельно в защищённом хранилище.

---

# 8. Полный Backup Script (автоматизация)

Используйте `backend/scripts/backup/full_backup.sh` и компонентные скрипты из
`backend/scripts/backup/`, предварительно сверив пути, права и целевое окружение.
Dev/prod Compose монтирует `/scripts/backup` и read-only `/backup-sources` (services, configs, выбранные Compose/env). `config/backup.php` задаёт пути; `FullBackupCommand` передаёт активные DB host/port/name/user/password и `APP_KEY` из Laravel config, в том числе при config cache. Dockerfiles устанавливают `postgresql-client-16`, `zip`, `jq`; клиент соответствует серверу PostgreSQL 16.

Artisan по умолчанию создаёт **application backup**: логический DB dump + Laravel files/активный APP_KEY + Python/deployment config + MQTT. Docker daemon не требуется. `BACKUP_INCLUDE_DOCKER_VOLUMES=true` включает отдельный volume-компонент только в подготовленном окружении с Docker; `--skip-docker` / `--skip-mqtt` реально передаются скрипту. Manifest содержит `scope`, component `success|failed|skipped` и точные счётчики; пропуск MQTT делает scope `partial_application`. Запрошенный компонент с ошибкой или пустым artifact приводит к ненулевому exit code.

Каталоги/архивы создаются с `umask 077`; подпапка полного backup уникальна даже при одновременных запусках. Расписание и наличие файлов всё равно проверяются по manifest и пробному восстановлению.
Состав, manifest и exit code проверяются после запуска; частично созданный архив
не считается успешной полной копией. Сырые архивы активных Docker volumes
не подтверждают согласованность PostgreSQL; БД проверяется по логическому dump
или отдельной корректной физической копии.

---

# 9. Recovery (восстановление)

## 9.1. Постгрес восстановление

### Логическое восстановление

Сначала проверьте выбранный архив (`pg_restore --list /absolute/path/backup.dump`),
его manifest и совместимость PostgreSQL/TimescaleDB. Для проверки используйте
отдельную БД и окружение без активного AE3/scheduler и подключения к актуаторам.

```bash
# Из корня репозитория; параметры соединения заранее настроены для тестового кластера.
# Скрипт удаляет и пересоздаёт БД DB_NAME. Не указывайте действующую БД стенда.
DB_NAME=hydro_restore_check backend/scripts/restore/postgres_restore.sh /absolute/path/backup.dump
```

После восстановления проверьте таблицы и Timescale extensions, schema snapshot,
телеметрию и конфигурацию. Возобновление AE3/scheduler — отдельный шаг после
подтверждения готовности оборудования; восстановленный active task не означает
разрешение повторно отправлять дозу или включать насос.

### Физическое восстановление на момент времени (PITR)

1. Выберите проверенную физическую base backup и её timeline; подтвердите наличие
   всех WAL до целевой точки. Логический dump для этого пути не используется.
2. Восстановите полный кластер в отдельный остановленный PostgreSQL 16 с совместимым TimescaleDB.
3. Задайте `restore_command` и целевую точку (`recovery_target_time` или другой target)
   в конфигурации PostgreSQL; создайте `recovery.signal` в PGDATA.
4. Запустите изолированный кластер, проверьте логи WAL replay и фактическую точку
   остановки recovery. Проверьте данные до переключения приложения.

В PostgreSQL 12+ файл `recovery.conf` не применяется.
Параметр `--wal-dir` в `postgres_restore.sh` лишь выводит предупреждение:
скрипт не выполняет PITR и не заменяет эту процедуру.

---

## 9.2. Восстановление Laravel

Восстановите `.env` и файлы приложения из копии. Сохраните прежний `APP_KEY`:
`key:generate` предназначен для новой установки, а не для восстановления
существующего приложения. Если ключ отсутствует, найдите исходную копию ключа
до продолжения. Ротация с `APP_PREVIOUS_KEYS` — отдельная процедура.

`laravel_restore.sh` при пустом ключе генерирует новый; перед запуском восстановления
существующих данных убедитесь, что выбранный архив содержит исходный ключ.
После восстановления выполняются проверки/очистка кеша внутри Laravel-контейнера:

```bash
# Из корня репозитория, для dev Compose:
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan config:clear
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan migrate:status
```

Применение недостающих миграций выполняется по процедуре выбранного развёртывания,
после проверки восстановленных данных и совместимости версии приложения.

---

## 9.3. Восстановление Python-сервисов

```
unzip python-services.zip
# Развернуть конфиги для automation-engine / history-logger / mqtt-bridge
docker compose -f backend/docker-compose.dev.yml up -d history-logger mqtt-bridge
```

AE3 и scheduler запускаются после проверки восстановленного состояния и оборудования.

---

## 9.4. Восстановление MQTT

Распакуйте выбранный архив во временный каталог, проверьте его состав и восстановите
файлы в реальные bind-mount источники выбранного Compose (`services/mqtt-bridge/`).
Один `unzip mqtt.zip` не обновляет эти источники. Проверьте соответствие dev/prod конфигурации и полноту сертификатов; старые архивы до исправления 2026-11-07 могли не содержать ACL/passwords/prod config/certs. После восстановления полного набора
перезапустите `mqtt` и проверьте listener, ACL и подключение нод.

---

## 9.5. Восстановление ESP32

Варианты:

1. USB прошивка:
```
esptool write_flash 0x0 firmware.bin
```

2. OTA (**planned** — UI/API нет): после реализации — `storage/app/ota` + push через history-logger.  
   Сейчас — только USB/`esptool` (выше).

---

# 10. Disaster Recovery (аварийное восстановление)

Сценарии:

### 10.1. Потеря PostgreSQL
- выбрать логическое восстановление из dump или физический PITR (§9.1)
- восстановить и проверить данные в изолированном окружении
- подключить приложение, затем отдельно возобновить scheduler/AE3 после проверки safety-state

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
2. Проверены WAL-архивирование, непрерывность цепочки и наличие base backup, если требуется PITR?
3. OTA прошивки сохранены? 
4. Docker тома архивируются? 
5. Все .env файлы сохранены? 
6. MQTT ACL/пароли есть в архиве? 
7. Python secrets сохранены? 
8. Проверено восстановление хотя бы раз в месяц? 
9. Disaster Recovery документ актуален? 

---

# Конец файла BACKUP_AND_RECOVERY.md
