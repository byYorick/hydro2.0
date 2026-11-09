# DATA_RETENTION_POLICY.md
# Полная политика хранения данных для системы 2.0
# Telemetry • Commands • Events • Logs • Backups • Archiving • Legal & Safety

Документ описывает полную стратегию хранения, архивации и очистки данных
в системе гидропонного комплекса 2.0.

**Source of truth** для сроков retention (telemetry / commands / events / alerts / logs).
Корневые сводки (`CLAUDE.md`, README и т.п.) только ссылаются сюда и не задают
альтернативные сроки. При изменении политики обновлять этот файл и связанные
env/compose/миграции/cron в той же итерации.

**Сверено с кодом:** 2026-11-07. Ниже разделены действующие механизмы очистки и целевые сроки архивов, для которых автоматизация отсутствует. Наличие миграции не подтверждает, что job успешно установлен в конкретной БД.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Цели и задачи политики хранения

Политика хранения данных обеспечивает:

- оптимальный объём базы данных,
- долгосрочное хранение важных данных,
- быстрое реагирование на аварийные ситуации,
- соблюдение требований безопасности,
- корректную работу AI-моделей,
- минимальные накладные расходы на инфраструктуру.

---

# 2. Классификация данных

Все данные делятся на 6 уровней:

```
L0 — Critical Control Data
L1 — Recent Telemetry
L2 — Historical Telemetry (compressed)
L3 — Events & Alerts
L4 — Logs (System, Node, AI)
L5 — Backup Archives
```

---

# 3. Хранение телеметрии

Telemetry хранится в двух формах:

## 3.1. Hot Telemetry (L1)
Используется для:

- контроллеров,
- AI,
- UI графиков в реальном времени,
- safety-алгоритмов.

Срок хранения:

```
30 дней (фактический)
```

> **Реализация (двойной механизм app-level):**
> - Laravel `telemetry:cleanup-raw` — env `TELEMETRY_RETENTION_DAYS` (дефолт **30**), ежедневно в 02:00
> - Python `telemetry-aggregator` — env `RETENTION_SAMPLES_DAYS` (compose default **30**; fallback в `main.py` должен совпадать)
>
> Оба дефолта заданы в `docker-compose.dev.yml` / `docker-compose.prod.yml`.
> **Timescale:** миграция `2026_08_02_120000_align_telemetry_samples_timescale_retention_to_30_days.php` снимает старый policy 90d (`2025_01_27_000007_*`) и ставит **30 days** на hypertable `telemetry_samples`.
> При изменении срока — обновлять env в compose, fallback Python, Timescale policy **и** этот документ.

Частота данных:

```
1–10 секунд
```

Таблицы:

```
telemetry_samples — история, retention 30 дней
telemetry_last — одна последняя запись на sensor_id; возрастная очистка 30d на неё не распространяется
```

## 3.2. Warm Telemetry (L2)
Данные агрегируются и сжимаются:

- усреднение: 1 минута,
- медиана pH/EC,
- min/max per interval,
- дневные суммарные показатели.

Срок хранения (фактический, не «6–12 месяцев» как единый срок):

| Таблица | Retention |
|--------|-----------|
| `telemetry_agg_1m` | **30 дней** (Timescale / aggregator) |
| `telemetry_agg_1h` | **365 дней** |
| `telemetry_daily` | **без авто-retention** (cold archive — planned) |

> **Реализация агрегации (один непрерывный writer):**
> - Непрерывный writer в dev/prod compose: Python `telemetry-aggregator` — фоновый цикл, `ON CONFLICT DO UPDATE SET`.
> - Laravel `telemetry:aggregate` **не** в Schedule. Команда оставлена для seed/backfill (`TelemetrySeeder`, ручной `--from/--to`). Использует `ON CONFLICT DO NOTHING`.
> - Laravel `telemetry:cleanup-raw` остаётся в Schedule (ежедневно 02:00) — retention raw samples, не агрегация.

Имя `telemetry_agg_daily` встречалось в старых черновиках; **актуальное имя в миграциях — `telemetry_daily`** (`2025_11_16_184939_create_telemetry_aggregated_tables.php`). В коде Laravel и Python используется только `telemetry_daily`.

Last-value кэш хранится в **PostgreSQL** в таблице `telemetry_last` (PK по `sensor_id`). Redis для последних значений telemetry **не используется** (исторический паттерн ранних версий проекта, удалён).

## 3.3. Cold Telemetry (архив)

Автоматического экспорта telemetry в CSV/Parquet/S3 и пятилетней ротации cold telemetry в текущем pipeline нет. `telemetry_daily` остаётся в PostgreSQL без автоматического TTL. Внешнее архивирование нужно настраивать отдельно; наличие daily-агрегатов его не обеспечивает.

---

# 4. Хранение команд

Команды важны для:

- аудита,
- восстановления алгоритмов AI,
- диагностики проблем.

Сроки:

```
commands: 365 дней hot (retention_policy_commands функция + pg_cron job `retention-commands` @ 02:00 ежедневно)
commands_archive: автоматического TTL нет; целевой срок архива — 3 года
```

Источник hot retention: миграция `2025_12_25_152231_add_partitioning_and_retention_for_commands_and_zone_events.php` (Timescale/pg_cron, **365 дней**).

Retention удаляет hot-записи, не копируя их в архив. Миграция пытается установить pg_cron/Timescale policy и может пропустить её при отсутствии extension или ошибке; работающую job нужно проверять в БД.

> **Secondary path (не в Schedule):** artisan `commands:archive --days=90` копирует/чистит в `commands_archive`. Дефолт **90** ≠ hot policy 365; команда ручная/опциональная, не заменяет Timescale retention. Архивные таблицы восстановлены миграцией `2026_04_30_195000_restore_archive_tables_*`.

Команды включают:

- cmd_id,
- параметры,
- статус (canonical enum: `QUEUED | SENT | ACK | DONE | NO_EFFECT | ERROR | INVALID | BUSY | TIMEOUT | SEND_FAILED`),
- source / request_id / trace_id,
- error_code, error_message, result_code, duration_ms,
- response (через `command_acks` для детального ACK lifecycle).

Старые статусы `sent/ack/error` (lowercase) и `pending` использовались в pre-3.0 эпохе; canonical enum выше.

---

# 5. Хранение событий (Events)

Events имеют ключевое значение для анализа проблем.

Сроки:

```
zone_events: 365 дней hot (retention_policy_zone_events функция + pg_cron job `retention-zone_events` @ 02:00 ежедневно)
zone_events_archive: автоматического TTL нет; целевой срок архива — 5 лет
```

Источник hot retention: миграция `2025_12_25_152231_add_partitioning_and_retention_for_commands_and_zone_events.php` (**365 дней**).

Hot cleanup удаляет записи без автоматического переноса в `zone_events_archive`; успешное создание retention job проверяется в конкретной БД.

> **Secondary path (не в Schedule):** artisan `zone-events:archive --days=180` — дефолт **180** ≠ hot policy 365; ручная/опциональная архивация в `zone_events_archive`, не заменяет Timescale retention.

Типы:

- IRRIGATION_CYCLE
- DOSING
- ALERT
- NODE_OFFLINE
- CONTROLLER_ERROR
- AI_RECOMMENDATION

---

# 6. Хранение алертов

Alerts важны для истории безопасности.

**Целевой срок (planned):** `alerts` ≈ 365 дней.

**Факт 2026-08-02:** отдельного Schedule/`alerts:cleanup` / Timescale policy на таблице `alerts` **нет**.  
Lifecycle: создание через Laravel `AlertService`. Подтверждение пишет `acknowledged_at` / `acknowledged_by` и **не** меняет `status` (остаётся `ACTIVE`, отдельного статуса `acknowledged` нет). Закрытие (`RESOLVED`) — автоматический resolve при снятии условия или ручной resolve некритичных кодов. Ручное закрытие safety-кодов при ещё активном условии отклоняется (`409 alert_manual_resolve_refused`).  
Рост таблицы — до ручной очистки или будущей команды purge.  
`alerts:dlq-replay` относится к `pending_alerts`, не к retention `alerts`.

---

# 6.1. AE3 runtime tables (`ae_tasks`, intents)

Операционные таблицы automation-engine (не hypertables):

| Таблица / сущность | Hot retention | Реализация |
|-------------------|---------------|------------|
| `ae_tasks` / связанные terminal AE rows | **90 дней** | `ae3:cleanup-old-tasks --days=90` ежедневно (`routes/console.php`) |
| `zone_automation_intents` (terminal) | следует lifecycle cleanup AE3 / sync из task | не отдельный Timescale policy |
| `ae_zone_leases` | только live lease | без archive retention |

При изменении срока AE3 cleanup — обновлять команду Schedule, `DATA_MODEL_REFERENCE.md` §6.11.3 и этот раздел.

---

# 7. Хранение логов

## 7.1. Hot Logs

`logs:cleanup --days=30` запускается Laravel Schedule еженедельно, в воскресенье в `02:00` (`routes/console.php`). Команда удаляет записи старше 30 дней; между запусками они могут оставаться дольше. Параметр `--days` доступен для ручного запуска.

Таблицы:

```
system_logs
node_logs
ai_logs
scheduler_logs
```

## 7.2. Warm Logs

Автоматического переноса удаляемых строк в годовые `tar.gz`-архивы нет. `CleanupLogs` выполняет `DELETE` по существующим таблицам.

## 7.3. Cold Logs

Встроенного экспорта этих логов в S3/Backblaze и пятилетней ротации нет. Срок внешнего хранения определяется отдельно настроенным сборщиком логов.

---

# 8. Бэкапы

В `routes/console.php` запланированы `backup:full` ежедневно в `03:00` и вызов `rotate_backups.sh` в `03:30`. Для исполнения нужны доступные shell-скрипты, утилиты, Docker и каталоги в окружении запуска; расписание само по себе не подтверждает успешную копию.

Стандартный Laravel Compose предоставляет `/scripts/backup` и read-only `/backup-sources`. `backup:full` создаёт application scope без Docker volumes по умолчанию; пропуски/ошибки видны в manifest. Правила состава, сохранение активного APP_KEY и проверка восстановления описаны в `BACKUP_AND_RECOVERY.md`.

| Механизм | Фактическая ротация |
|---|---|
| `backend/scripts/backup/rotate_backups.sh` | `FULL_BACKUP_RETENTION_DAYS=30` для full/component каталогов; `WAL_RETENTION_DAYS=7` для WAL-архива |
| Artisan `backup:database` | удаляет файлы старше **7 дней** в своём output-каталоге при каждом запуске |

Логический PostgreSQL backup использует `pg_dump`; weekly incremental, monthly encrypted и многолетняя offsite-ротация этими механизмами не реализованы. Требования к физическому PITR и восстановлению — в [BACKUP_AND_RECOVERY.md](../08_SECURITY_AND_OPS/BACKUP_AND_RECOVERY.md).

---

# 9. Оптимизация размера базы

Автоматическая очистка выполняется только перечисленными выше app/DB jobs. Еженедельного `VACUUM FULL` или уплотнения архивов в Schedule нет. Обслуживание PostgreSQL и анализ размеров таблиц настраиваются отдельно; `VACUUM FULL` не является штатной командой этого retention pipeline.

---

# 10. Архивирование (Archiving Engine)

Retention raw samples: Laravel `telemetry:cleanup-raw` по расписанию + Timescale policy на `telemetry_samples`.
Прогрессия агрегатов (`raw → agg_1m → agg_1h → daily`) — непрерывный Python `telemetry-aggregator` (единственный writer в проде).
Laravel `telemetry:aggregate` — seed/backfill, не production schedule.

```
telemetry_samples → telemetry_agg_1m → telemetry_agg_1h → telemetry_daily
```

Cold archive не входит в этот исполняемый pipeline. Retention raw/1m/1h удаляет записи; он не гарантирует предварительную архивацию.

---

# 11. AI‑интеграция

AI получает доступ к:

- hot данные → обучение контроллеров,
- aggregate данные → прогнозы,
- архивные данные → обучение крупных моделей.

ИИ НЕ получает:

- личные данные пользователей,
- токены,
- конфигурации безопасности,
- закрытые ключи.

---

# 12. Политика удаления данных

Удаление зоны/ноды выполняют `ZoneService::delete` / `NodeService::delete` в транзакции. Зона с active grow cycle или привязанными нодами не удаляется; ноду сначала нужно отвязать. Дальнейшие изменения зависимостей определяют FK и model hooks.

В частности, `telemetry_last.sensor_id` и `telemetry_samples.sensor_id` имеют `ON DELETE CASCADE`; zone/node FK агрегатов используют `SET NULL`. Обнуление FK не является полной анонимизацией данных. Автоматической архивации events/logs при этих delete-операциях сервисы не выполняют.

`UserController::destroy` запрещает удалить собственную учётную запись и вызывает `$user->delete()`. Отдельного pipeline анонимизации команд и очистки API-логов в этом методе нет. Сохранность истории и удаление зависимых записей нельзя выводить из общей retention-политики: нужно проверять фактические FK/hooks соответствующей сущности.

---

# 13. Правила для ИИ

ИИ может:

- анализировать историю данных,
- оптимизировать retention уровни,
- предлагать новые схемы агрегации.

ИИ НЕ может:

- увеличивать срок хранения команд > 3 лет,
- отключать архивирование,
- удалять события,
- сокращать retention безопасности.

---

# 14. Чек‑лист Retention перед релизом

1. Hot telemetry очищается? 
2. Aggregation работает? 
3. Архивирование включено? 
4. Логи ротации работают? 
5. Бэкапы выполняются? 
6. Данные доступны AI? 
7. Удаление зон/узлов корректное? 
8. Нет переполнения базы? 

---

# Конец файла DATA_RETENTION_POLICY.md
