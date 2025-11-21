# Исправление метрик Prometheus для Automation Engine и History Logger

## Проблема

Нет данных в dashboards:
- **Automation Engine Service** - использует Prometheus
- **History Logger Service** - использует Prometheus

## Найденные проблемы

### 1. History Logger - неправильный порт в Prometheus

В `prometheus.yml` был указан порт **9301**, но сервис работает на порту **9300**.

**Исправлено:**
- ✅ `backend/configs/dev/prometheus.yml` - изменен порт с `9301` на `9300`
- ✅ `backend/configs/prod/prometheus.yml` - порт уже был правильный (`9300`)

### 2. Automation Engine

✅ Работает правильно:
- Порт: `automation-engine:9401`
- Статус в Prometheus: **UP**

## Исправления

1. ✅ Исправлен порт для `history-logger` в `prometheus.yml` (dev)
2. ✅ Перезапущен Prometheus для применения изменений

## Проверка статуса

После перезапуска Prometheus:

1. **Подождите 15-30 секунд** для первого сбора метрик
2. **Проверьте статус targets в Prometheus:**
   - Откройте: `http://localhost:9090/targets`
   - Должны быть:
     - `automation-engine:9401` - **UP** ✅
     - `history-logger:9300` - **UP** ✅

3. **Проверьте метрики через API:**
   ```bash
   # History Logger
   docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up{job=\"history-logger\"}"
   
   # Automation Engine
   docker exec prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up{job=\"automation-engine\"}"
   ```

4. **Проверьте dashboards в Grafana:**
   - **Automation Engine Service** - должны появиться метрики
   - **History Logger Service** - должны появиться метрики

## Доступные метрики

### Automation Engine

- `up{job="automation-engine"}` - статус сервиса (1 = UP, 0 = DOWN)
- `zone_checks_total` - количество проверок зон
- `automation_commands_sent_total` - отправленные команды
- `automation_errors_total` - ошибки

### History Logger

- `up{job="history-logger"}` - статус сервиса (1 = UP, 0 = DOWN)
- `telemetry_received_total` - полученная телеметрия
- `telemetry_processed_total` - обработанная телеметрия
- `telemetry_queue_size` - размер очереди Redis
- `telemetry_queue_age_seconds` - возраст очереди

## Если метрики все еще не появляются

### Проверка доступности метрик напрямую

```bash
# History Logger - проверка /metrics endpoint
docker exec backend-history-logger-1 python -c "import httpx; r = httpx.get('http://localhost:9300/metrics'); print(r.status_code, r.text[:200])"

# Automation Engine - проверка /metrics endpoint
docker exec backend-automation-engine-1 python -c "import httpx; r = httpx.get('http://localhost:9401/metrics'); print(r.status_code, r.text[:200])"
```

### Проверка Prometheus targets

```bash
# Через API
docker exec prometheus wget -qO- http://localhost:9090/api/v1/targets | grep -A 5 "history-logger\|automation-engine"
```

### Проверка логов Prometheus

```bash
docker logs prometheus --tail 50 | grep -i "history-logger\|automation-engine\|error"
```

### Проверка подключения из Prometheus

```bash
# Проверка доступности history-logger из Prometheus
docker exec prometheus wget -qO- http://history-logger:9300/metrics

# Проверка доступности automation-engine из Prometheus
docker exec prometheus wget -qO- http://automation-engine:9401/metrics
```

## Примечание

Dashboards Automation Engine и History Logger используют **Prometheus**, а не PostgreSQL. Поэтому данные появляются только если:

1. ✅ Сервисы запущены
2. ✅ Метрики экспортируются на правильных портах (9300 для history-logger, 9401 для automation-engine)
3. ✅ Prometheus собирает метрики (проверьте targets)
4. ✅ Prometheus datasource правильно настроен в Grafana (должен быть дефолтным)

## Следующие шаги

1. Проверьте targets в Prometheus: `http://localhost:9090/targets`
2. Если history-logger все еще DOWN, проверьте:
   - Доступность порта 9300 из контейнера Prometheus
   - Логи history-logger на наличие ошибок
   - Правильность монтирования конфига Prometheus

