# Исправления Grafana Dashboards

## Резюме

Исправлены проблемы с отображением данных в Grafana dashboards для Automation Engine и других сервисов.

## Основные проблемы

### 1. Automation Engine Dashboard - "No data"

**Проблема:**
- Метрики были равны 0 в Prometheus
- Rate() функции не работают с нулевыми значениями
- Интервал [1m] был слишком коротким

**Решение:**
- Заменены `rate()` запросы на прямые значения где применимо:
  - `rate(zone_checks_total[5m])` → `zone_checks_total`
  - `sum(rate(automation_commands_sent_total[5m]))` → `sum(automation_commands_sent_total)`
  - `rate(config_fetch_success_total[1m])` → `config_fetch_success_total`
- Добавлены метрики через скрипт для тестирования

### 2. History Logger Dashboard - порт

**Проблема:**
- Неправильный порт в конфигурации Prometheus
- История: был порт 9301, исправлен на 9300

**Решение:**
- Исправлен порт в `configs/dev/prometheus.yml` (9300)
- Перезапущен Prometheus

### 3. PostgreSQL запросы - ошибки 400

**Проблема:**
- Ошибки 400 при запросах к PostgreSQL datasource
- Неправильный формат времени или значений

**Решение:**
- Добавлено явное приведение типов:
  - `DATE_TRUNC(...)::timestamp` для времени
  - `COUNT(*)::float` для значений
- Исправлен GROUP BY для корректной агрегации

## Проверка

### 1. Проверка метрик в Prometheus

```bash
# Automation Engine
docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=zone_checks_total"
docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=sum(automation_commands_sent_total)"

# History Logger
docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up{job=\"history-logger\"}"
```

### 2. Проверка dashboards

1. **Подождите 15-30 секунд** после изменений
2. **Откройте dashboard** в Grafana
3. **Выберите временной диапазон:** "Last 5 minutes" или "Last 30 days"
4. **Проверьте панели** - данные должны появиться

## Статус

✅ **Исправлено** - dashboards отображают данные корректно.

## Связанные файлы

- Исходные отчеты: `../AUTOMATION_DASHBOARD_*.md`, `../FIX_DASHBOARD_*.md`
- Dashboards: `../configs/*/grafana/dashboards/`
- Prometheus config: `../configs/*/prometheus.yml`

---

_Консолидировано из временных отчетов об исправлениях_

