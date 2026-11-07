# RUNBOOKS.md

Быстрые процедуры на случай инцидентов.

**Сверено:** 2026-11-07. Shell-примеры ниже — из корня репозитория для dev Compose. В production используйте `--env-file backend/.env.prod -f backend/docker-compose.prod.yml` вместо dev-файла и проверяйте доступ из Compose-сети. Пути `/backups` в примерах должны указывать на доступный выбранному инструменту архив; named volume контейнера не является одноимённым каталогом хоста.

## 1. Backend не стартует / 500
- Проверить логи контейнера `laravel` (LOG_CHANNEL=stderr): `docker compose -f backend/docker-compose.dev.yml logs -f laravel`.
- Применить миграции: `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan migrate --force`.
- Очистить кеши: `docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan config:clear && docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan cache:clear && docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan view:clear`.
- Проверить переменные окружения (.env / compose): DB_HOST/DB_PORT/DB_DATABASE/DB_USERNAME/DB_PASSWORD.

## 2. БД недоступна
- Проверить `docker compose -f backend/docker-compose.dev.yml ps` и логи `db`.
- Локально: `docker compose -f backend/docker-compose.dev.yml exec db psql -U hydro -d hydro_dev -c '\l'`.
- Восстановить из бэкапа (см. [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md)).

## 3. WebSockets/Realtime не работает
- Проверить `reverb` конфиг (`config/reverb.php`) и переменные REVERB_*.
- Убедиться, что фронтенд использует правильные VITE_WS_HOST/PORT/TLS.
- Проверить авторизацию приватных каналов (`routes/channels.php`) и токен сессии.

## 3.1. Планировщик (Laravel scheduler-dispatch)

Владелец расписаний и wake-up в automation-engine — **Laravel**.

### 3.1.1. Конфигурация (dev/prod)
- Laravel env: `AUTOMATION_LARAVEL_SCHEDULER_ENABLED=1` для активного dispatch.
- Операционные параметры tick/lock (пример значений по умолчанию в `config/services.php`):
  - `AUTOMATION_LARAVEL_SCHEDULER_DISPATCH_INTERVAL_SEC` — целевой шаг dispatcher (согласовать с частотой регистрации команды в `routes/console.php`).
  - `AUTOMATION_LARAVEL_SCHEDULER_DISPATCH_PARALLELISM` — параллельные HTTP-вызовы AE в одном batch.
  - `AUTOMATION_LARAVEL_SCHEDULER_LOCK_TTL_SEC` — нижняя граница TTL Cache-lock; фактический TTL не ниже `max(…, p99 cycle + margin)`.
  - `AUTOMATION_LARAVEL_SCHEDULER_LOCK_TTL_MARGIN_SEC` — запас к p99 длительности цикла scheduler для расчёта lock TTL.
- Синхронизация токенов ingress с automation-engine:
  - `AUTOMATION_LARAVEL_SCHEDULER_API_TOKEN=<token>`
  - `SCHEDULER_API_TOKEN=<тот_же_token>`
  - `PY_INGEST_TOKEN=<тот_же_token>`
- В production запрещено оставлять разные значения для этих переменных:
  рассинхронизация даёт `401 unauthorized` на `POST /zones/{id}/start-cycle`.
- После смены env: `docker compose -f backend/docker-compose.dev.yml up -d laravel`.

### 3.1.2. Проверки
- Команда зарегистрирована: `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan list | rg automation:dispatch-schedules`.
- Ручной прогон: `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan automation:dispatch-schedules --zone-id=1`.
- В compose не должно быть сервиса с именем `scheduler` — планирование выполняется в контейнере `laravel`.
- Security smoke `POST /zones/{id}/start-cycle`:
  - без токена — `401`;
  - с токеном, без `X-Trace-Id` — `422` (см. актуальные требования в `doc_ai/04_BACKEND_CORE/ae3lite.md`).

### 3.1.3. Отключение dispatch
- `AUTOMATION_LARAVEL_SCHEDULER_ENABLED=0` и перезапуск `laravel` — останавливает автоматический dispatch; исполнение уже запущенных задач в AE смотреть отдельно.

### 3.1.4. Инциденты `start-cycle` / intents / active tasks

Симптомы:
- повторяющиеся `accepted`, но нет terminal статусов;
- в `zone_automation_intents` долго висят `claimed|running`;
- в `laravel_scheduler_active_tasks` растет backlog.

Проверки:
```sql
-- Застрявшие intents (старше 5 минут)
SELECT id, zone_id, idempotency_key, status, claimed_at, updated_at, retry_count, max_retries
FROM zone_automation_intents
WHERE status IN ('claimed','running')
  AND updated_at < now() - interval '5 minutes'
ORDER BY updated_at ASC;

-- Активные задачи scheduler, которые не терминировались
SELECT task_id, zone_id, task_type, status, accepted_at, due_at, expires_at, last_polled_at
FROM laravel_scheduler_active_tasks
WHERE terminal_at IS NULL
ORDER BY accepted_at ASC;
```

Восстановление:
1. Проверить readiness AE: `curl -fsS http://automation-engine:9405/health/ready`.
2. Перезапустить `automation-engine` (startup recovery должен финализировать in-flight).
3. Прогнать reconcile: `docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan automation:dispatch-schedules --zone-id=<id>`.
4. Если задача уже просрочена, убедиться что в `laravel_scheduler_active_tasks` выставлен terminal status (`timeout|failed`) и выполнен повторный dispatch.

## 3.2. Рестарт automation-engine и startup recovery

Действующий контракт: [`ae3lite.md`, §9](../04_BACKEND_CORE/ae3lite.md).
Startup-recovery plan архивирован; его фазы 1–6 реализованы. Проверено по runtime-коду 2026-11-06.

### 3.2.1. Нормальный рестарт (deploy / `docker compose -f backend/docker-compose.dev.yml restart automation-engine`)

1. Проверить readiness: `curl -fsS http://localhost:9405/health/ready` (или `automation-engine:9405` внутри compose-сети).
2. В логах AE найти проход startup recovery (`Startup recovery` / `AE3 startup recovery outcome`).
3. Для затронутых зон проверить `zone_events` с типом `AE_STARTUP_RECOVERY_OUTCOME` (поля `task_id`, `outcome`, `error_code`, `stage`).
4. Если `outcome=failed` — в UI появится алерт `biz_ae3_task_failed`; проверить вкладку Automation / Alerts.
5. Убедиться, что `ae_zone_leases` для зоны пуст после recovery-fail (зона не должна оставаться busy).
6. При необходимости перезапустить цикл: `POST /zones/{id}/start-cycle` (через UI или scheduler dispatch).

**Несколько реплик AE (prod):** startup recovery координируется через PostgreSQL advisory lock — только один экземпляр выполняет проход; остальные пишут в лог `пропуск прохода`. На зону по-прежнему действует invariant «один active writer» (`ae_zone_leases` + partial unique index). См. `ae3lite.md` §9.1 п.10.

### 3.2.2. `waiting_command_stuck` после рестарта

**Симптом:** зона в `waiting_command`, hint `waiting_command_stuck`, команда ещё не terminal в `commands`.

**Разбор:** ожидание ответа узла само по себе не является ошибкой. Текущий worker
запускает `WaitingCommandReconcileUseCase` и сверяет terminal команды без повторной
публикации. Если прогресса нет, проверяются связь с узлом, дедлайны, claim/lease
и ошибки reconcile loop, а не наличие исторической «фазы 3».

**Действия оператора:**

1. Проверить `ae_tasks` (`status`, `current_stage`, `claimed_by`, `updated_at`).
2. Проверить последнюю строку `ae_commands` + `commands` по `cmd_id` / `external_id` (terminal status).
3. Если команда **уже DONE**, проверьте `planner_step`, `stage_name` и остальные команды batch: один DONE не завершает весь stage. При отсутствии прогресса зафиксируйте `task_id`, `external_id`, дедлайны, lease и ошибки reconcile loop.
4. Если команда **ещё in-flight** — проверить связь с узлом (MQTT, питание) и дедлайны task/stage; следить за janitor AE3 (`stale_task_reconcile`, fail-safe OFF → fail). Не переводить строки в `failed` ручным SQL и не отправлять повторную дозу. Laravel `ae3:reap-stale-tasks` **не** переводит `ae_tasks` в `failed`.
5. Проверить `ae_zone_leases` — при stuck после fail не должно блокировать новый цикл.
6. Прогнать `docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan ae3:reap-stale-tasks` только для orphan pending intents без `ae_task` и для лога stale tasks; зомби-task reclaim — зона ответственности AE janitor.

### 3.2.3. `startup_recovery_unconfirmed_command`

**Симптом:** task `failed`, `error_code=startup_recovery_unconfirmed_command`, workflow rollback в `idle`.

**Разбор:** recovery не смог безопасно подтвердить переход/возобновление задачи.
Точный контекст берётся из `error_message`, `ae_commands` и событий recovery.
Crash между командами batch не означает обязательный fail: текущий recovery умеет
возобновлять batch и пропускать подтверждённые DONE steps в границах execution token.

**Действия:** сохраните идентификаторы task/command, stage и terminal статусы,
проверьте фактическое состояние оборудования. Новый цикл запускается оператором
через UI/Laravel после устранения причины и проверки готовности; historical план
не является инструкцией повторной отправки команд.

## 4. Playwright E2E падает (webServer)
- Проверить порт 8010 и `playwright.config.ts` выбранного suite; приложение запускается в проектном Docker-окружении.
- Проверить отдельную тестовую БД и настройку миграций suite. Не выполнять `migrate:fresh` на dev/prod БД как способ исправить webServer.
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
- MQTT bridge: `http://localhost:9000/metrics` (metrics probe; Compose healthcheck проверяет TCP-порт).

## 8. Обновление зависимостей
- Node: `docker compose -f backend/docker-compose.dev.yml exec -T laravel npm ci`.
- PHP: `docker compose -f backend/docker-compose.dev.yml exec -T laravel composer install` и `docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan optimize:clear`.

## 9. Безопасность
- Composer audit и NPM audit (см. CI). Критичные — оформить тикеты.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 10. Восстановление PostgreSQL из бэкапа

### 10.1. Быстрое восстановление
```bash
# Найти последний бэкап
BACKUP_DIR=/backups/postgres/$(ls -t /backups/postgres | head -1)
DUMP_FILE=$(find $BACKUP_DIR -name "*.dump" | head -1)

# Восстановить в отдельную проверочную БД; параметры выбранного кластера настроены заранее.
# Скрипт удаляет и пересоздаёт DB_NAME, не используйте действующую БД стенда.
cd backend/scripts/restore
DB_NAME=hydro_restore_check ./postgres_restore.sh "$DUMP_FILE"
```

### 10.2. Восстановление с проверкой
```bash
# Список доступных бэкапов
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:list

# Проверка содержимого выбранного custom dump до восстановления
pg_restore --list /absolute/path/backup.dump
```

Само восстановление удаляет и пересоздаёт целевую БД. Для проверки задайте отдельную
`DB_NAME` и параметры изолированного кластера; порядок — в
[BACKUP_AND_RECOVERY.md, §9.1](BACKUP_AND_RECOVERY.md).

### 10.3. Point-in-Time Recovery (PITR)
Требуются физическая base backup и непрерывная цепочка WAL, не логический `pg_dump`.
В PostgreSQL 16 используются `restore_command`, целевая точка recovery и
`recovery.signal`; `recovery.conf` не поддерживается. `postgres_restore.sh --wal-dir`
не выполняет WAL replay. Полный порядок и границы автоматизации — в
[BACKUP_AND_RECOVERY.md, §9.1](BACKUP_AND_RECOVERY.md).

---

## 11. Восстановление Laravel

### 11.1. Восстановление из архива
```bash
# Найти архив
ARCHIVE=$(find /backups/laravel -name "laravel_*.zip" | sort -r | head -1)

# Восстановить
backend/scripts/restore/laravel_restore.sh $ARCHIVE
```

### 11.2. После восстановления
```bash
# Из корня репозитория, после восстановления dev-конфигурации:
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan migrate:status
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan config:clear
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan cache:clear
```

Сохраняйте восстановленный `APP_KEY`. При его отсутствии восстановите исходный
ключ из защищённой копии; генерация нового не является шагом восстановления.
Миграции/зависимости применяются по процедуре выбранной версии приложения.

---

## 12. Полное восстановление системы

### 12.1. Восстановление всех компонентов
```bash
# Найти последний полный бэкап
BACKUP_DIR=/backups/full/$(ls -t /backups/full | head -1)

# Выполнить полное восстановление
backend/scripts/restore/full_restore.sh $BACKUP_DIR
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
docker compose -f backend/docker-compose.dev.yml restart

# Проверка логов
docker compose -f backend/docker-compose.dev.yml logs -f

# Проверка миграций
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan migrate:status
```

---

## 13. Диагностика бэкапов

### 13.1. Проверка целостности бэкапов
```bash
# Список бэкапов с проверкой
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:list --verify

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
# План заданий, не история выполнения
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan schedule:list

# Результаты в логах
docker compose -f backend/docker-compose.dev.yml logs --tail=200 laravel | rg -i 'backup|scheduler'
```

`docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan schedule:test` запускает выбранный job. Для проверки прошлого выполнения его не используют. Стандартный Compose монтирует `/scripts/backup`; для backup проверяйте manifest scope, failed/skipped components и закрытые права; см. [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md).

---

## 14. Аварийные ситуации

### 14.1. Полный сбой сервера

1. Выбрать проверенный revision, Compose/env, secrets и backup set. Сохранить прежний `APP_KEY`.
2. Поднять PostgreSQL выбранного окружения. В dev из корня: `docker compose -f backend/docker-compose.dev.yml up -d db`.
3. Проверить dump и восстановление в отдельной БД по [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md). `postgres_restore.sh` использует host `pg_restore` и `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`; production DB без host-порта требует подготовленного сетевого доступа.
4. Восстановить файлы Laravel, Compose/env и полный набор MQTT ACL/passwords/config/certificates. `full_restore.sh` не заменяет ручные шаги для Python/MQTT.
5. Проверить схему, secrets и состояние оборудования, затем запускать runtime. Для production — deployment guide и `make prod-check` / `make prod-up` / `make prod-migrate`.
6. Дождаться `node_hello`, публикации NodeConfig и подтверждения `config_report`; lifecycle/binding — [NODE_LIFECYCLE_AND_PROVISIONING.md](../01_SYSTEM/NODE_LIFECYCLE_AND_PROVISIONING.md). Маршрута `/api/nodes/{id}/register` нет; device registration — `POST /api/nodes/register` с service auth, не восстановление секрета одним вызовом.

### 14.2. Потеря БД

Остановить writers выбранной инсталляции (включая Laravel scheduler, AE3, history-logger и telemetry-aggregator), выбрать архив и параметры целевой БД. Сначала выполнить пробное восстановление в изоляции; порядок и destructive semantics скрипта — §10 и backup guide. После восстановления проверить БД/схему и только затем запускать writers и reconciliation.

### 14.3. Потеря MQTT конфигурации

Распаковать архив во временный каталог и проверить состав. Реальные bind-mount источники — `backend/services/mqtt-bridge/{mosquitto.dev.conf,mosquitto.prod.conf,passwords.txt,acl,certs/}` в зависимости от окружения. Текущий `mqtt_backup.sh` сохраняет этот набор; старые архивы до 2026-11-07 могли быть неполными, поэтому состав проверяется до восстановления. После восстановления перезапустить `mqtt` выбранного Compose и проверить listener/ACL и reconnect нод.

### 14.4. Потеря всех узлов ESP32

**Восстановление:**

1. **Перепрошить вручную через USB**
   ```bash
   esptool.py --port /dev/ttyUSB0 write_flash 0x0 firmware.bin
   ```

2. **Загрузить конфиги NVS** (если есть бэкап)
   - Использовать `nvs_flash` утилиту ESP-IDF

3. **Регистрация и binding**
   - после настройки Wi-Fi/MQTT дождаться `node_hello` и server-side registration;
   - восстановить согласованные per-node secrets и NodeConfig;
   - binding подтверждается только `config_report` из целевого namespace.

Формат registration payload и service auth — `RegisterNodeRequest` / `NodeController::register`; поля `node_id` + `secret` из старого примера не являются текущим контрактом.

### 14.5. Перегрузка PostgreSQL

Проверить CPU/I/O, соединения, blocking queries, размеры таблиц и backlog существующих очередей. Сопоставить telemetry-aggregator/retention jobs и AE3 readiness с временем деградации. Для уменьшения нагрузки использовать предусмотренные режимы остановки/паузы и инцидентные процедуры владельца системы.

Настройка Laravel read/write hosts на тот же `db` и `PDO::ATTR_EMULATE_PREPARES` не включает read-only. Универсального переключателя «локальное буферирование» или AI restricted mode для этого инцидента в коде нет; не считать их готовыми средствами восстановления.

---

## 15. Профилактика и мониторинг

### 15.1. Ежедневные проверки
- Проверка успешности бэкапов: `docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:list`
- Проверка логов бэкапов: stdout `backup:full` / `docker compose -f backend/docker-compose.dev.yml logs laravel | rg -i backup` (отдельного `/var/log/backup.log` нет)
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

`backup:full` в стандартном Compose создаёт application scope; Docker volumes по умолчанию пропущены и явно отмечены в manifest. Отдельный volume backup требует подготовленного окружения. Состав и проверка восстановления — в backup guide.
```bash
# Полный бэкап через Laravel
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:full

# Только БД
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:database

# Список бэкапов
docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:list --verify
```

### 16.2. Ручная ротация
```bash
# Запуск ротации вручную
backend/scripts/backup/rotate_backups.sh
```

### 16.3. Проверка WAL архивирования
```bash
# Проверка настройки WAL
docker compose -f backend/docker-compose.dev.yml exec db psql -U hydro -c "SHOW archive_mode;"
docker compose -f backend/docker-compose.dev.yml exec db psql -U hydro -c "SHOW archive_command;"
```

---

## 17. Контакты и эскалация

При критических инцидентах:
1. Проверить логи: `docker compose -f backend/docker-compose.dev.yml logs`
2. Проверить статус сервисов: `docker compose -f backend/docker-compose.dev.yml ps`
3. Проверить бэкапы: `docker compose -f backend/docker-compose.dev.yml exec -T laravel php artisan backup:list`
4. При необходимости — восстановление из бэкапа
5. Эскалация при невозможности восстановления
