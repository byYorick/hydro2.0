# Laravel ↔ AE3 Read-Model Contract

**Версия:** 1.0
**Дата:** 2026-04-18
**Статус:** Active

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0.

---

## Зачем

AE3 (automation-engine, Python) читает состояние зоны **напрямую из PostgreSQL**, без HTTP к Laravel. Это быстро, но создаёт **скрытый контракт**: если Laravel-миграция переименует колонку `ae_tasks.status` → `ae_tasks.state`, AE3 упадёт только в runtime — компиляционной ошибки не будет.

Этот документ описывает механизм защиты скрытого контракта через двусторонний snapshot + diff test.

## Архитектура

```
┌──────────────────────────┐    generate     ┌────────────────────────────────────┐
│ Laravel                  │ ──────────────> │ schemas/                           │
│   migrations/*.php       │                 │   automation_read_model_schema.json│
│   AutomationReadModel-   │                 │   (committed в git)                │
│   SchemaTest.php         │                 └────────────────────────────────────┘
└──────────────────────────┘                             │
                                                         │ validate
                                                         ▼
                                   ┌──────────────────────────────────────────┐
                                   │ AE3                                      │
                                   │   laravel_schema_contract.py (manifest)  │
                                   │   test_read_model_contract.py (validator)│
                                   └──────────────────────────────────────────┘
```

**Snapshot** — дамп `information_schema.columns` по 24 таблицам, от которых зависит AE3. Хранится в [`schemas/automation_read_model_schema.json`](../../schemas/automation_read_model_schema.json).

**Python manifest** — декларация в [`ae3lite/infrastructure/read_models/laravel_schema_contract.py`](../../backend/services/automation-engine/ae3lite/infrastructure/read_models/laravel_schema_contract.py) о том, какие таблицы / колонки / enum-значения AE3 ждёт найти.

**Validator** — [`test_read_model_contract.py`](../../backend/services/automation-engine/test_read_model_contract.py) сверяет manifest против snapshot. Падает, если manifest ссылается на то, чего в snapshot нет.

## Что именно защищено

| Гарантия | Где проверяется |
|---|---|
| Таблица существует | `test_table_present_in_snapshot` |
| Required-колонка существует | `test_required_columns_present_and_typed` |
| Тип колонки совместим с ожидаемым `type_family` (integer/bigint/text/timestamp/jsonb/numeric/boolean/uuid/time/…) | `test_required_columns_present_and_typed` |
| Enum-колонка присутствует (если manifest требует определённые литералы) | `test_enum_literal_columns_present` |
| NOT NULL совпадает (**opt-in**, через `AE_READ_MODEL_CONTRACT_STRICT_NULLABILITY=1`) | `test_required_columns_present_and_typed` |

**Что НЕ защищено (пока):**

- Фактические enum-литералы в БД (требует runtime-запрос — отдельный integration test может быть добавлен)
- CHECK constraints
- Foreign keys
- Индексы
- PostgreSQL NOTIFY channels (`scheduler_intent_terminal`, `ae_zone_event`) — проверка наличия LISTEN-pipe требует отдельного integration-теста

## Рабочие процессы

### Добавить новое поле, которое AE3 читает

1. **Laravel:** создай миграцию, добавляющую колонку.
2. **Laravel:** добавь название таблицы в `AutomationReadModelSchemaTest::TRACKED_TABLES`, если таблица новая.
3. **AE3:** добавь `_col("my_new_col", "integer")` в соответствующую `Table(...)` в `laravel_schema_contract.py`.
4. **Регенерируй snapshot:**
   ```bash
   docker compose -f backend/docker-compose.dev.yml exec \
     -e UPDATE_SCHEMA_SNAPSHOT=1 laravel \
     php artisan test --filter=AutomationReadModelSchemaTest
   ```
   Файл `schemas/automation_read_model_schema.json` обновится.
5. **Проверь AE3:**
   ```bash
   make test-ae PYTEST_ARGS="test_read_model_contract.py"
   ```
6. **Коммит:** миграция + manifest + snapshot в одном PR. CI-job `read-model-contract` валидирует, что они согласованы.

### Переименовать колонку

Breaking change — проект в активной разработке, обратная совместимость не нужна.

1. Laravel: миграция-rename.
2. AE3: обнови SQL-запрос в репозитории / read_model.
3. AE3: обнови manifest (`_col(...)`).
4. Регенерируй snapshot.
5. Проверь: manifest → тест падает, пока старое имя не убрано; сразу после rename — зелёный.

### CI падает с "Схема БД разошлась с committed snapshot"

Кто-то добавил миграцию, но не регенерировал snapshot. Запусти у себя:

```bash
docker compose -f backend/docker-compose.dev.yml exec \
  -e UPDATE_SCHEMA_SNAPSHOT=1 laravel \
  php artisan test --filter=AutomationReadModelSchemaTest
git diff schemas/automation_read_model_schema.json
```

Проверь, что diff ожидаем (новая колонка, а не случайное расхождение из-за kosher migrations локально). Закоммить обновлённый snapshot.

### CI падает с "<table>: отсутствуют колонки [...]"

AE3 manifest требует колонку, которую Laravel-миграция не создала (или уронила). Решение:

- Либо **добавь миграцию**, создающую колонку (если AE3 действительно должен её читать).
- Либо **убери колонку из manifest**, если от неё отказались.

## Отслеживаемые таблицы (24)

AE3-owned (AE3 primary writer): `ae_tasks`, `ae_commands`, `ae_stage_transitions`, `ae_zone_leases`, `pid_state`, `zone_workflow_state`.

Laravel-owned, AE3 reads: `zone_automation_intents`, `zones`, `greenhouses`, `grow_cycles`, `grow_cycle_phases`, `automation_effective_bundles`, `automation_config_documents`, `sensors`, `telemetry_last`, `telemetry_samples`, `zone_events`, `nodes`, `node_channels`, `channel_bindings`, `pump_calibrations`, `alerts`, `commands`, `unassigned_node_errors`.

Полный список и источники SQL-запросов: см. manifest и Explore-отчёт в истории commit-ов (от 2026-04-18).

## NOTIFY-каналы

AE3 подписывается на:

- `scheduler_intent_terminal` — триггер `trg_intent_terminal` на `zone_automation_intents` ([`2026_03_12_120000_add_intent_terminal_notify_trigger.php`](../../backend/laravel/database/migrations/))
- `ae_zone_event` — NOTIFY из `common/db.py::notify_zone_event_ingested()` (history-logger publishes)

Контракт LISTEN-каналов проверяется через integration test (`make test-ae` / `test_notify_partition_smoke.py`). В этот read-model contract они **не включены** — snapshot информации об LISTEN-channels не содержит.

## Ограничения

- Snapshot генерируется на свежей миграции (`RefreshDatabase`) — пост-миграционные seed-изменения не попадают. Для AE3 read-model это корректно, т.к. AE3 читает только то, что создаётся миграциями.
- PostgreSQL-специфичные типы (`tsvector`, custom ENUMs) требуют явной поддержки в `TYPE_FAMILIES`. Пока поддержано: integer/bigint/text/timestamp/jsonb/boolean/numeric/uuid/bytea/interval/inet/time/array.
- Snapshot не различает `timestamp without tz` и `timestamp with tz` — обе входят в `type_family="timestamp"`. Это осознанный trade-off (миграция tz → notz редка и всегда breaking).

## Связанные документы

- [AE3 Runtime Event Contract](AE3_RUNTIME_EVENT_CONTRACT.md)
- [Data Model Reference](../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md)
- [Automation Config Authority](AUTOMATION_CONFIG_AUTHORITY.md)
