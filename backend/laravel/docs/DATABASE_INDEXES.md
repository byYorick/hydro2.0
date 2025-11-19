# Database Indexes Documentation

Этот документ описывает индексы базы данных и их назначение для оптимизации запросов.

## Обзор

Индексы созданы для оптимизации наиболее частых запросов к базе данных. Все индексы используют B-tree структуру (по умолчанию в PostgreSQL).

## Таблицы и индексы

### 1. telemetry_samples

**Существующие индексы:**
- `telemetry_samples_zone_metric_ts_idx` - `(zone_id, metric_type, ts)` - для запросов по зоне и метрике
- `telemetry_samples_node_ts_idx` - `(node_id, ts DESC)` - для запросов по узлу (из TimescaleDB миграции)
- `telemetry_samples_metric_ts_idx` - `(metric_type, ts DESC)` - для запросов по типу метрики (из TimescaleDB миграции)
- `ts` - индекс на timestamp для временных запросов

**Добавленные индексы:**
- `telemetry_samples_node_channel_ts_idx` - `(node_id, channel, ts DESC)` - для запросов по узлу и каналу (partial index, только для NOT NULL значений)
- `telemetry_samples_created_at_idx` - `(created_at)` - для cleanup операций и архивации

**Использование:**
- Запросы истории телеметрии по зоне: `WHERE zone_id = ? AND metric_type = ? AND ts >= ? AND ts <= ?`
- Запросы по узлу: `WHERE node_id = ? AND ts >= ?`
- Cleanup старых данных: `WHERE created_at < ?`

### 2. commands

**Существующие индексы:**
- `commands_status_idx` - `(status)` - для фильтрации по статусу
- `commands_cmd_id_idx` - `(cmd_id)` - для поиска по ID команды (unique)

**Добавленные индексы:**
- `commands_zone_status_idx` - `(zone_id, status)` - для запросов команд зоны по статусу
- `commands_node_status_idx` - `(node_id, status)` - для запросов команд узла по статусу
- `commands_created_at_idx` - `(created_at)` - для архивации и cleanup
- `commands_sent_at_idx` - `(sent_at)` - для обработки таймаутов команд

**Использование:**
- Поиск команд зоны: `WHERE zone_id = ? AND status = ?`
- Поиск команд узла: `WHERE node_id = ? AND status = ?`
- Архивация старых команд: `WHERE created_at < ? AND status != 'pending'`
- Обработка таймаутов: `WHERE sent_at < ? AND status IN ('pending', 'sent')`

### 3. alerts

**Существующие индексы:**
- `alerts_zone_status_idx` - `(zone_id, status)` - для запросов активных алертов зоны

**Добавленные индексы:**
- `alerts_type_idx` - `(type)` - для фильтрации по типу алерта
- `alerts_source_code_idx` - `(source, code)` - для запросов по source и code (новые поля)
- `alerts_created_at_idx` - `(created_at)` - для фильтрации по времени создания
- `alerts_resolved_at_idx` - `(resolved_at)` - для фильтрации разрешенных алертов
- `alerts_zone_type_status_idx` - `(zone_id, type, status)` - для комбинированных запросов

**Использование:**
- Поиск активных алертов: `WHERE zone_id = ? AND type = ? AND status = 'ACTIVE'`
- Фильтрация по типу: `WHERE type = ?`
- Поиск по source и code: `WHERE source = ? AND code = ?`
- Фильтрация по времени: `WHERE created_at >= ? AND created_at <= ?`
- Поиск разрешенных: `WHERE resolved_at IS NOT NULL`

### 4. zone_events

**Существующие индексы:**
- `zone_events_zone_id_created_at_idx` - `(zone_id, created_at)` - для запросов событий зоны
- `zone_events_type_idx` - `(type)` - для фильтрации по типу события

**Добавленные индексы:**
- `zone_events_zone_type_created_idx` - `(zone_id, type, created_at)` - для комбинированных запросов
- `zone_events_created_at_idx` - `(created_at)` - для cleanup и архивации

**Использование:**
- Поиск событий зоны: `WHERE zone_id = ? AND type = ? ORDER BY created_at DESC`
- Поиск последних событий: `WHERE zone_id = ? AND type IN (?) ORDER BY created_at DESC LIMIT 1`
- Архивация старых событий: `WHERE created_at < ?`

## Частые паттерны запросов

### Запросы телеметрии

```sql
-- История по зоне и метрике
SELECT * FROM telemetry_samples 
WHERE zone_id = ? AND metric_type = ? AND ts >= ? AND ts <= ?
ORDER BY ts ASC;
-- Использует: telemetry_samples_zone_metric_ts_idx

-- История по узлу
SELECT * FROM telemetry_samples 
WHERE node_id = ? AND ts >= ?
ORDER BY ts DESC;
-- Использует: telemetry_samples_node_ts_idx
```

### Запросы команд

```sql
-- Команды зоны по статусу
SELECT * FROM commands 
WHERE zone_id = ? AND status = ?
ORDER BY created_at DESC;
-- Использует: commands_zone_status_idx

-- Таймауты команд
SELECT * FROM commands 
WHERE sent_at < ? AND status IN ('pending', 'sent');
-- Использует: commands_sent_at_idx
```

### Запросы алертов

```sql
-- Активные алерты зоны по типу
SELECT * FROM alerts 
WHERE zone_id = ? AND type = ? AND status = 'ACTIVE';
-- Использует: alerts_zone_type_status_idx

-- Алерты по source и code
SELECT * FROM alerts 
WHERE source = ? AND code = ? AND status = 'ACTIVE';
-- Использует: alerts_source_code_idx
```

### Запросы событий

```sql
-- Последнее событие зоны по типу
SELECT * FROM zone_events 
WHERE zone_id = ? AND type = ? 
ORDER BY created_at DESC 
LIMIT 1;
-- Использует: zone_events_zone_type_created_idx
```

## Мониторинг индексов

### Проверка использования индексов

```sql
-- Статистика использования индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

### Размер индексов

```sql
-- Размер индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Неиспользуемые индексы

```sql
-- Индексы, которые не используются (idx_scan = 0)
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public' AND idx_scan = 0
ORDER BY tablename, indexname;
```

## Рекомендации

1. **Мониторинг**: Регулярно проверяйте использование индексов через `pg_stat_user_indexes`
2. **Оптимизация**: Удаляйте неиспользуемые индексы для экономии места и ускорения INSERT/UPDATE
3. **Анализ**: Используйте `EXPLAIN ANALYZE` для проверки использования индексов в запросах
4. **Обслуживание**: Периодически запускайте `VACUUM ANALYZE` для обновления статистики

## Миграция

Индексы добавлены через миграцию: `2025_01_27_000006_add_missing_indexes.php`

Для отката:
```bash
php artisan migrate:rollback --step=1
```

---

**Дата создания:** 2025-01-27  
**Версия:** 1.0

