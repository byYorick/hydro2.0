# TimescaleDB Partitioning Documentation

Этот документ описывает стратегию партиционирования временных рядов с использованием TimescaleDB.

## Обзор

TimescaleDB автоматически партиционирует таблицы временных рядов на chunks (чанки) по времени. Это обеспечивает:
- Быстрые запросы по времени (query pruning)
- Эффективное удаление старых данных (drop chunks вместо DELETE)
- Автоматическое управление индексами на уровне chunks

## Партиционированные таблицы

### 1. telemetry_samples

**Стратегия партиционирования:**
- **Chunk interval:** 1 день
- **Partitioning column:** `ts` (timestamp)
- **Retention policy:** 90 дней (автоматическое удаление старых chunks)

**Миграция:** `2025_11_16_184935_add_timescaledb_hypertable.php`

**Использование:**
```sql
-- TimescaleDB автоматически использует только релевантные chunks
SELECT * FROM telemetry_samples 
WHERE zone_id = ? AND ts >= ? AND ts <= ?;
```

**Преимущества:**
- Запросы по времени работают только с нужными chunks
- Удаление старых данных через `drop_chunks` вместо медленного `DELETE`
- Автоматическое создание новых chunks

### 2. telemetry_agg_1m

**Стратегия партиционирования:**
- **Chunk interval:** 7 дней
- **Partitioning column:** `ts` (timestamp)
- **Retention policy:** 30 дней

**Миграция:** `2025_11_16_184939_create_telemetry_aggregated_tables.php`

### 3. telemetry_agg_1h

**Стратегия партиционирования:**
- **Chunk interval:** 30 дней
- **Partitioning column:** `ts` (timestamp)
- **Retention policy:** 365 дней

**Миграция:** `2025_11_16_184939_create_telemetry_aggregated_tables.php`

## Retention Policies

Retention policies автоматически удаляют старые chunks через заданный интервал времени.

### Настройка retention policy

```sql
-- Добавить retention policy для telemetry_samples (90 дней)
SELECT add_retention_policy('telemetry_samples', INTERVAL '90 days');

-- Добавить retention policy для telemetry_agg_1m (30 дней)
SELECT add_retention_policy('telemetry_agg_1m', INTERVAL '30 days');

-- Добавить retention policy для telemetry_agg_1h (365 дней)
SELECT add_retention_policy('telemetry_agg_1h', INTERVAL '365 days');
```

### Просмотр retention policies

```sql
SELECT 
    hypertable_name,
    job_id,
    config->>'drop_after' as drop_after
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_retention';
```

### Удаление retention policy

```sql
SELECT remove_retention_policy('telemetry_samples');
```

## Управление chunks

### Просмотр chunks

```sql
-- Список всех chunks для hypertable
SELECT 
    chunk_name,
    range_start,
    range_end,
    pg_size_pretty(total_bytes) as size
FROM timescaledb_information.chunks
WHERE hypertable_name = 'telemetry_samples'
ORDER BY range_start DESC;
```

### Ручное удаление старых chunks

```sql
-- Удалить chunks старше 90 дней
SELECT drop_chunks('telemetry_samples', INTERVAL '90 days');
```

### Предварительное создание chunks

TimescaleDB автоматически создает chunks при вставке данных. Для предварительного создания:

```sql
-- Создать chunks на следующий месяц
SELECT create_chunk('telemetry_samples', '2025-02-01'::timestamp, '2025-03-01'::timestamp);
```

## Мониторинг

### Размер chunks

```sql
SELECT 
    chunk_name,
    range_start,
    range_end,
    pg_size_pretty(total_bytes) as size,
    pg_size_pretty(table_bytes) as table_size,
    pg_size_pretty(index_bytes) as index_size
FROM timescaledb_information.chunks
WHERE hypertable_name = 'telemetry_samples'
ORDER BY range_start DESC;
```

### Статистика использования chunks

```sql
SELECT 
    chunk_name,
    range_start,
    range_end,
    num_times_accessed,
    last_accessed
FROM timescaledb_information.chunk_stats
WHERE hypertable_name = 'telemetry_samples'
ORDER BY range_start DESC;
```

### Производительность запросов

```sql
-- EXPLAIN для проверки использования chunks
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM telemetry_samples 
WHERE zone_id = 1 AND ts >= NOW() - INTERVAL '7 days';
```

## Оптимизация

### Изменение chunk interval

```sql
-- Изменить chunk interval для telemetry_samples (требует пересоздания hypertable)
-- ВНИМАНИЕ: Это операция требует миграции данных!
SELECT set_chunk_time_interval('telemetry_samples', INTERVAL '1 day');
```

### Компрессия старых chunks

TimescaleDB поддерживает автоматическую компрессию старых chunks:

```sql
-- Включить компрессию для chunks старше 7 дней
ALTER TABLE telemetry_samples SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'zone_id, metric_type',
    timescaledb.compress_orderby = 'ts DESC'
);

-- Добавить политику компрессии
SELECT add_compression_policy('telemetry_samples', INTERVAL '7 days');
```

## Best Practices

1. **Chunk interval:**
   - Для высокочастотных данных (telemetry_samples): 1 день
   - Для агрегированных данных (agg_1m): 7 дней
   - Для долгосрочных агрегатов (agg_1h): 30 дней

2. **Retention policy:**
   - Настраивайте retention policy для автоматического удаления старых данных
   - Используйте `drop_chunks` вместо `DELETE` для лучшей производительности

3. **Мониторинг:**
   - Регулярно проверяйте размер chunks
   - Мониторьте использование chunks через `timescaledb_information.chunk_stats`

4. **Индексы:**
   - Индексы создаются автоматически на каждом chunk
   - Используйте составные индексы для оптимизации запросов

## Миграция

Партиционирование настроено через миграции:
- `2025_11_16_184935_add_timescaledb_hypertable.php` - создание hypertable для telemetry_samples
- `2025_11_16_184939_create_telemetry_aggregated_tables.php` - создание hypertables для агрегированных таблиц
- `2025_01_27_000007_optimize_timescaledb_partitioning.php` - оптимизация и retention policies

---

**Дата создания:** 2025-01-27  
**Версия:** 1.0

