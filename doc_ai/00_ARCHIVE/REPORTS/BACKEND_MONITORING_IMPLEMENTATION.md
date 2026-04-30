# Реализация системы мониторинга для history-logger и automation-engine

## Обзор

Полностью реализована система мониторинга и логирования для сервисов `history-logger` и `automation-engine` согласно документации в `../../doc_ai/08_SECURITY_AND_OPS/LOGGING_AND_MONITORING.md`.

## Выполненные задачи

### 1. ✅ Экспорт метрик Prometheus в history-logger

**Файл:** `backend/services/history-logger/main.py`

- Добавлен endpoint `/metrics` для экспорта метрик Prometheus
- Используется `prometheus_client.generate_latest()` для генерации метрик
- Метрики доступны на том же порту, что и API (9300)

**Доступные метрики:**
- `telemetry_received_total` - количество полученных сообщений
- `telemetry_processed_total` - количество обработанных сообщений
- `telemetry_queue_size` - размер очереди Redis
- `telemetry_queue_age_seconds` - возраст самого старого элемента
- `telemetry_processing_duration_seconds` - время обработки батча
- `telemetry_dropped_total` - потерянные сообщения (по причинам)
- `database_errors_total` - ошибки БД (по типам)
- `node_hello_received_total`, `node_hello_registered_total`, `node_hello_errors_total` - регистрация узлов
- `heartbeat_received_total` - heartbeat сообщения
- И другие...

### 2. ✅ Grafana Dashboards

#### History Logger Dashboard
**Файлы:**
- `backend/configs/dev/grafana/dashboards/history-logger.json`
- `backend/configs/prod/grafana/dashboards/history-logger.json`

**Панели:**
1. Обзор сервиса (статус, размер очереди, возраст элементов, скорость обработки)
2. Поток телеметрии (получено/обработано)
3. Распределение размера батчей
4. Время обработки (p50, p95, p99)
5. Время операций Redis
6. Потерянные сообщения (по причинам)
7. Ошибки БД
8. Регистрация узлов (node_hello)
9. Ошибки регистрации узлов
10. Heartbeat сообщения
11. Время запросов к Laravel API

#### Automation Engine Dashboard
**Файлы:**
- `backend/configs/dev/grafana/dashboards/automation-engine.json`
- `backend/configs/prod/grafana/dashboards/automation-engine.json`

**Панели:**
1. Обзор сервиса (статус, скорость проверок зон, команды, успешность загрузки конфигурации)
2. Время обработки зон (p50, p95, p99)
3. Команды по зонам
4. Команды по типам метрик (pH, EC, irrigation, climate, light)
5. Статус загрузки конфигурации
6. Ошибки публикации MQTT
7. Ошибки в цикле автоматизации
8. Ошибки обработки (по зонам и типам)
9. Общая статистика (проверки, команды, ошибки)
10. Эффективность обработки

### 3. ✅ Prometheus Alert Rules

**Файлы:**
- `backend/configs/dev/prometheus/alerts.yml`
- `backend/configs/prod/prometheus/alerts.yml`

#### Алерты для History Logger:
1. **HistoryLoggerQueueOverflow** - очередь переполнена (>10000 элементов)
2. **HistoryLoggerQueueStale** - элементы задерживаются в очереди (>300 сек)
3. **HistoryLoggerDroppingMessages** - потеря сообщений из-за ошибок очереди
4. **HistoryLoggerDatabaseErrors** - высокий уровень ошибок БД
5. **HistoryLoggerSlowProcessing** - медленная обработка (P99 > 5 сек)
6. **HistoryLoggerNoProcessing** - отсутствие обработки сообщений

#### Алерты для Automation Engine:
1. **AutomationEngineLoopErrors** - ошибки в основном цикле (>5/сек)
2. **AutomationEngineConfigFetchErrors** - ошибки загрузки конфигурации (>3/сек)
3. **AutomationEngineMQTTPublishErrors** - ошибки публикации команд (>10/сек)
4. **AutomationEngineSlowZoneProcessing** - медленная обработка зон (P99 > 30 сек)
5. **AutomationEngineNoZoneChecks** - отсутствие проверок зон
6. **AutomationEngineHighErrorRate** - высокий общий уровень ошибок (>20/сек)

### 4. ✅ Обновление конфигурации Prometheus

**Файлы:**
- `backend/configs/dev/prometheus.yml`
- `backend/configs/prod/prometheus.yml`

- Добавлен job `history-logger` с правильным портом (9300)
- Обновлен alert `ServiceDown` для включения `history-logger`

## Использование

### Доступ к метрикам

**History Logger:**
```bash
curl http://history-logger:9300/metrics
```

**Automation Engine:**
```bash
curl http://automation-engine:9401/metrics
```

### Импорт Dashboards в Grafana

1. Откройте Grafana UI
2. Перейдите в Configuration → Data Sources → убедитесь, что Prometheus настроен
3. Перейдите в Dashboards → Import
4. Загрузите JSON файлы из `backend/configs/{env}/grafana/dashboards/`

Или используйте автоматический импорт через provisioning (если настроено).

### Просмотр алертов

1. Откройте Prometheus UI: `http://prometheus:9090`
2. Перейдите в Alerts для просмотра активных алертов
3. Настройте Alertmanager для отправки уведомлений (email, Telegram и т.д.)

## Проверка работоспособности

### Проверка метрик history-logger:
```bash
# Проверка health endpoint
curl http://localhost:9300/health

# Проверка метрик
curl http://localhost:9300/metrics | grep telemetry_received_total
```

### Проверка метрик automation-engine:
```bash
# Проверка метрик
curl http://localhost:9401/metrics | grep zone_checks_total
```

### Проверка Prometheus:
```bash
# Проверка targets
curl http://localhost:9090/api/v1/targets

# Проверка правил алертов
curl http://localhost:9090/api/v1/rules
```

## Следующие шаги

1. Настроить Alertmanager для отправки уведомлений
2. Добавить дополнительные метрики при необходимости
3. Настроить retention политики для метрик
4. Создать дополнительные dashboards для специфичных сценариев
5. Настроить автоматический импорт dashboards через Grafana provisioning

## Ссылки

- Документация по мониторингу: `../../doc_ai/08_SECURITY_AND_OPS/LOGGING_AND_MONITORING.md`
- Prometheus документация: https://prometheus.io/docs/
- Grafana документация: https://grafana.com/docs/
