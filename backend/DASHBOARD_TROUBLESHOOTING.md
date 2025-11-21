# Устранение проблем с Grafana Dashboards

## Проблема: "Данных нет" в dashboards

### Проверка данных в БД

```bash
# Проверка алертов
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT status, COUNT(*) FROM alerts GROUP BY status;"

# Проверка команд
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT status, COUNT(*) FROM commands GROUP BY status;"

# Проверка телеметрии
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT COUNT(*) FROM telemetry_samples WHERE ts >= NOW() - INTERVAL '24 hours';"
```

### Проверка подключения PostgreSQL в Grafana

1. Откройте Grafana: `http://localhost:3000`
2. Перейдите в **Configuration** → **Data Sources**
3. Проверьте, что **PostgreSQL** datasource настроен:
   - **Host:** `db:5432`
   - **Database:** `hydro_dev` (dev) или `hydro` (prod)
   - **User:** `hydro`
   - **Password:** `hydro` (dev) или из переменной окружения (prod)
4. Нажмите **Test** для проверки подключения

### Исправление запросов в dashboards

Если данные есть в БД, но не отображаются:

1. **Проверьте регистр статусов:**
   - В БД могут быть `ACTIVE` и `active`
   - Запросы используют `UPPER(status) = 'ACTIVE'` для универсальности

2. **Проверьте временной диапазон:**
   - Убедитесь, что выбран правильный период (Last 6 hours, Last 24 hours и т.д.)
   - Некоторые запросы используют `$__timeFrom()` и `$__timeTo()`

3. **Проверьте формат данных:**
   - Для time_series нужны поля `time` и `value`
   - Для table нужны все необходимые колонки

### Унификация статусов в БД

Если статусы в разных регистрах:

```bash
# Унифицировать статусы алертов
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "UPDATE alerts SET status = UPPER(status);"
```

### Проверка конкретных dashboards

#### Alerts Dashboard
```sql
-- Должно вернуть активные алерты
SELECT COUNT(*) FROM alerts WHERE UPPER(status) = 'ACTIVE';
```

#### Commands & Automation
```sql
-- Должно вернуть команды
SELECT COUNT(*) FROM commands;
SELECT status, COUNT(*) FROM commands GROUP BY status;
```

#### Node Status
```sql
-- Должно вернуть узлы
SELECT COUNT(*) FROM nodes;
SELECT status, COUNT(*) FROM nodes GROUP BY status;
```

#### Zone Telemetry
```sql
-- Должно вернуть события
SELECT COUNT(*) FROM zone_events;
SELECT COUNT(*) FROM zone_events WHERE created_at >= NOW() - INTERVAL '24 hours';
```

#### History Logger
```sql
-- Должно вернуть телеметрию
SELECT COUNT(*) FROM telemetry_samples;
SELECT COUNT(*) FROM telemetry_last;
```

### Перезапуск Grafana

После исправления dashboards:

```bash
docker-compose -f backend/docker-compose.dev.yml restart grafana
```

### Ручная проверка запросов

1. Откройте dashboard в Grafana
2. Нажмите на панель → **Edit**
3. Проверьте запрос SQL
4. Нажмите **Query Inspector** для просмотра результатов
5. Проверьте ошибки в консоли браузера (F12)

### Частые проблемы

1. **PostgreSQL datasource не подключен:**
   - Проверьте настройки в `backend/configs/dev/grafana/datasources.yml`
   - Перезапустите Grafana

2. **Неправильный UID datasource:**
   - В dashboards должен быть `"uid": "PostgreSQL"`
   - Проверьте в Data Sources → PostgreSQL → UID

3. **Неправильная база данных:**
   - Dev: `hydro_dev`
   - Prod: `hydro`

4. **Временной диапазон:**
   - Убедитесь, что выбран период, в котором есть данные
   - Данные создаются за последние 7-30 дней

### Тестирование запросов напрямую

```bash
# Тест запроса для Alerts Dashboard
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT id, zone_id, type, status, details, created_at FROM alerts WHERE UPPER(status) = 'ACTIVE' ORDER BY created_at DESC LIMIT 10;"

# Тест запроса для Commands
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT cmd, status, COUNT(*) as count FROM commands WHERE created_at >= NOW() - INTERVAL '24 hours' GROUP BY cmd, status;"
```

### Если ничего не помогает

1. Проверьте логи Grafana:
```bash
docker logs grafana --tail 100 | Select-String -Pattern "error|postgres|datasource" -CaseSensitive:$false
```

2. Проверьте логи БД:
```bash
docker logs backend-db-1 --tail 50
```

3. Пересоздайте dashboards:
   - Удалите dashboard в Grafana
   - Импортируйте заново из JSON файлов

