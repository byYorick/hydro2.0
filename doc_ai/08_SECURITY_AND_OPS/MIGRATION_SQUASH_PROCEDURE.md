# Migration Squash Procedure

**Версия:** 1.1
**Дата:** 2026-04-23
**Статус:** НЕ ВЫПОЛНЕН — отложено из-за TimescaleDB incompat с `pg_dump`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0.

---

## TL;DR

На момент 2026-04-18 накоплено **199 Laravel-миграций** (~1 год истории).
Стандартный Laravel `schema:dump --prune` для консолидации **не работает** из
коробки из-за **TimescaleDB hypertables**: `pg_dump` не дампит вызовы
`create_hypertable()`, `add_retention_policy()`, `create_continuous_aggregate()`
и pg_cron jobs. После `migrate:fresh` телеметрические таблицы получились бы
обычными (без партицирования) — это сломало бы производительность prod.

**Решение:** отложить squash до одного из двух путей:

1. **Post-dump patching**: после `pg_dump` вручную добавить блок `SELECT
   create_hypertable(...)` + `add_retention_policy(...)` + pg_cron jobs в
   конец `database/schema/pgsql-schema.sql`.
2. **Hybrid squash с cutoff ДО TimescaleDB-миграций** (`2025_11_16`) — только 14
   миграций (7%) уйдут в baseline; TimescaleDB-migrations (3 файла) и все
   последующие останутся как есть. Выигрыш маленький, не оправдывает работу.

---

## Что уже сделано (2026-04-18, обновлено 2026-04-23)

- [`backend/laravel/database/schema/pgsql-schema.reference.sql`](../../backend/laravel/database/schema/pgsql-schema.reference.sql) — 10 527 строк,
  dump схемы hydro_test через `pg_dump --schema-only --no-owner --no-acl
  --no-comments`. Содержит все 199 миграций консолидированно, **кроме**
  `create_hypertable()` вызовов.

Файл существует как **справочник/baseline** для разработчиков — удобно
посмотреть финальную структуру без перечитывания 199 миграций.

Миграции **не удалены** (safe).

> ⚠️ **Важно: суффикс `.reference.sql`, а не `.sql`.**
>
> Laravel `MigrateCommand::loadSchemaState()` автоматически подхватывает любой
> файл по пути `database/schema/{connection}-schema.{sql,dump}` и пытается
> загрузить его как squashed baseline. Наш dump сделан через `pg_dump
> --schema-only` (без `--data-only` на `migrations`), поэтому в нём **нет**
> записей `INSERT INTO migrations`. Laravel после load'а не знает какие
> миграции считать применёнными и перезапускает их все → падение на
> `relation "users" already exists`. Плюс контейнер laravel падает ещё
> раньше: base-образ `webdevops/php-nginx:8.2` не содержит `psql`, а
> `PostgresSchemaState::load()` вызывает `psql --file=...`.
>
> Суффикс `.reference` выводит файл из-под auto-detect, сохраняя его как
> справочник. **Не переименовывай обратно в `pgsql-schema.sql`** до
> выполнения полноценного squash (раздел "Процедура post-dump patching").
>
> Для справки: `backend/laravel/Dockerfile` содержит `postgresql-client`
> в apt-install — когда squash будет выполнен корректно, `psql --file`
> уже будет доступен.

---

## Инвентарь TimescaleDB-артефактов

Перед squash-патчингом нужно зафиксировать полный список:

### Hypertables
```sql
-- Run in hydro_dev:
SELECT hypertable_schema, hypertable_name, num_dimensions
FROM timescaledb_information.hypertables;
```

По состоянию на 2026-04-18 ожидаем (из миграций):
- `telemetry_samples` (time-partition by `ts`)
- `telemetry_agg_1m` (time-partition by `bucket_start`)
- `telemetry_agg_1h` (time-partition by `bucket_start`)
- `commands` (time-partition by `created_at`, native partitions + hypertable)
- `zone_events` (time-partition by `created_at`, native partitions + hypertable)

### Retention policies
```sql
SELECT * FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention';
```

### Continuous aggregates
```sql
SELECT view_name FROM timescaledb_information.continuous_aggregates;
```

### pg_cron jobs
```sql
SELECT jobname, schedule, command FROM cron.job;
```

---

## Процедура post-dump patching (план B)

Если понадобится полный squash с TimescaleDB:

```bash
# 1. Очистить тестовую БД и применить все миграции с нуля
make test-db-reset

# 2. Снять актуальный inventory TimescaleDB-артефактов
docker compose -f backend/docker-compose.dev.yml exec -T db psql -U hydro hydro_test \
  -c "SELECT hypertable_name, num_dimensions FROM timescaledb_information.hypertables;"

# 3. Снять schema dump
# ВАЖНО: --data-only на migrations таблице, иначе после load'а Laravel
# не будет знать какие миграции считать применёнными и перезапустит их все.
docker compose -f backend/docker-compose.dev.yml exec -T db \
  pg_dump --schema-only --no-owner --no-acl --no-comments -U hydro hydro_test \
  > backend/laravel/database/schema/pgsql-schema.sql
docker compose -f backend/docker-compose.dev.yml exec -T db \
  pg_dump -t public.migrations --data-only --no-owner --no-acl -U hydro hydro_test \
  >> backend/laravel/database/schema/pgsql-schema.sql

# 4. PATCH: добавить в конец pgsql-schema.sql TimescaleDB setup
cat <<'TSDB_PATCH' >> backend/laravel/database/schema/pgsql-schema.sql

-- =========================================================================
-- TimescaleDB post-dump patch (pg_dump не дампит hypertables автоматически)
-- =========================================================================

-- Преобразуем таблицы в hypertables (если ещё не сделано).
SELECT create_hypertable('telemetry_samples', 'ts',
    chunk_time_interval => interval '1 day', if_not_exists => TRUE);
SELECT create_hypertable('telemetry_agg_1m', 'bucket_start',
    chunk_time_interval => interval '7 days', if_not_exists => TRUE);
SELECT create_hypertable('telemetry_agg_1h', 'bucket_start',
    chunk_time_interval => interval '30 days', if_not_exists => TRUE);
-- commands + zone_events partitioned natively, hypertable на native partitions:
SELECT create_hypertable('commands', 'created_at',
    chunk_time_interval => interval '7 days', if_not_exists => TRUE,
    migrate_data => TRUE);
SELECT create_hypertable('zone_events', 'created_at',
    chunk_time_interval => interval '7 days', if_not_exists => TRUE,
    migrate_data => TRUE);

-- Retention policies (значения нужно сверить с миграциями):
SELECT add_retention_policy('telemetry_samples', interval '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('telemetry_agg_1m', interval '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('telemetry_agg_1h', interval '365 days', if_not_exists => TRUE);
SELECT add_retention_policy('commands', interval '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('zone_events', interval '180 days', if_not_exists => TRUE);

-- pg_cron jobs (если используются — сверить с миграциями 2025_12_25 и далее):
-- SELECT cron.schedule('telemetry_refresh', '*/1 * * * *', ...);

TSDB_PATCH

# 5. Удалить миграции ДО cutoff даты
# (пример: всё до 2026_01_01)
CUTOFF="2026_01_01"
cd backend/laravel/database/migrations/
for f in *; do
  if [[ "$f" < "$CUTOFF" ]]; then rm -v "$f"; fi
done
cd -

# 6. КРИТИЧЕСКАЯ ПРОВЕРКА: migrate:fresh должен поднять систему с нуля
make test-db-reset  # пересоздаёт hydro_test через schema.sql + оставшиеся migrations
make test-ae        # automation-engine tests
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test  # PHPUnit

# 7. Sanity check hypertables:
docker compose -f backend/docker-compose.dev.yml exec -T db psql -U hydro hydro_test \
  -c "SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;"
# Ожидается: 5 hypertables, num_chunks >= 0

# 8. Если всё зелёное — commit + PR с явной пометкой breaking change
#    (coord'я со всеми разработчиками, которые держат локальные hydro_dev БД)
```

---

## Риски и почему отложено

1. **pg_dump circular FK warnings** (`hypertable`, `chunk`, `continuous_agg`) —
   pg_dump предупреждает о невозможности консистентного dump'а внутренних
   таблиц TimescaleDB. На практике схема dump'ится без ошибок, но
   **hypertable metadata** не восстанавливается через psql-replay.

2. **pg_cron jobs** — хранятся в cron-схеме, не в public. Не попадают в
   обычный pg_dump без дополнительных флагов.

3. **Continuous aggregates** — требуют recreate через
   `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)`. pg_dump
   выдаёт их как обычные materialized views — после replay теряется TimescaleDB
   refresh policy.

4. **Coordinated rollout** — разработчики с локальными `hydro_dev` БД
   получают сломанные pg_cron/hypertables после pull. Нужен явный
   `docker compose down -v` + `make up`.

5. **Prod migration strategy** — на prod БД миграции уже применены.
   Добавление baseline schema.sql **не заменяет** историю в
   `migrations` таблице. Нужно вручную prepopulate `migrations` записями
   удалённых файлов, либо очистить таблицу и передоверить записям из schema.

6. **Laravel auto-loadSchemaState ловушка** (обнаружено 2026-04-23) —
   Laravel при `php artisan migrate` автоматически проверяет путь
   `database/schema/{connection}-schema.{sql,dump}` и, если файл есть,
   вызывает `psql --file=...`. Если dump не содержит `INSERT INTO
   migrations` (как у нас — только `--schema-only`), Laravel после load'а
   запускает ВСЕ файлы миграций заново → `relation "users" already exists`.
   Поэтому справочный dump храним под именем
   `pgsql-schema.reference.sql` (суффикс `.reference` выводит из-под
   auto-detect). При реальном squash dump переименовывается в `pgsql-schema.sql`
   и обязательно дополняется `pg_dump -t migrations --data-only`.

---

## Критерии того, что squash стоит делать

Отложенная работа станет оправданной когда:

- **Количество миграций превышает 400** (сейчас 199) — локальный reset
  заметно замедляется.
- **Нет активных breaking changes в телеметрии** — добавление новых
  hypertables/retention policies в миграциях усложняет post-dump patching.
- **Есть staging-окружение** для coord'ной проверки squash-флоу.

---

## Связанные документы

- [ci.yml: Drop Timescale hypertables workaround](../../.github/workflows/ci.yml) — пример обхода для CI
- [doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md](../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md)
- Laravel официальная документация по squashing: https://laravel.com/docs/12.x/migrations#squashing-migrations
