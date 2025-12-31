# History Logger Service

Сервис для записи телеметрии в PostgreSQL/TimescaleDB из MQTT.

## Описание

History Logger — критически важный сервис в системе Hydro 2.0, отвечающий за:
- Прием телеметрии из MQTT
- Буферизацию данных в Redis
- Батчевую запись в PostgreSQL/TimescaleDB
- Регистрацию новых узлов через Laravel API
- Обновление heartbeat статусов узлов
- Обработку статусов/диагностики/ошибок и ответов на команды
- Сохранение `config_report` от нод

## Архитектура

### Поток данных

```
MQTT Topics → handle_telemetry() → Redis Queue → process_telemetry_queue() → PostgreSQL/TimescaleDB
```

1. **MQTT Handler** (`handle_telemetry`) - получает сообщения из MQTT, валидирует через Pydantic, добавляет в Redis queue
2. **Redis Queue** - буферизует телеметрию для батчевой обработки
3. **Queue Processor** (`process_telemetry_queue`) - извлекает батчи из очереди и записывает в БД
4. **Batch Writer** (`process_telemetry_batch`) - нормализует метрику, резолвит/создает `sensors`, пишет в `telemetry_samples` и делает upsert в `telemetry_last`

### Технологический стек

- **FastAPI** (0.115.4) — веб-фреймворк
- **Uvicorn** (0.32.0) — ASGI сервер
- **asyncpg** (0.29.0) — асинхронный PostgreSQL драйвер
- **redis** (5.0.1) — Redis клиент для буферизации
- **paho-mqtt** (1.6.1) — MQTT клиент
- **httpx** (0.27.2) — HTTP клиент для Laravel API
- **Prometheus** (0.20.0) — метрики
- **Pydantic** (2.9.2) — валидация данных

## Конфигурация

### Переменные окружения

#### MQTT
- `MQTT_HOST` - хост MQTT брокера (по умолчанию: `mqtt`)
- `MQTT_PORT` - порт MQTT брокера (по умолчанию: `1883`)
- `MQTT_TLS` - использовать TLS (по умолчанию: `0`)
- `MQTT_CLIENT_ID` - базовый client_id (по умолчанию: `hydro-core`)

**Примечание:** при запуске нескольких history-logger инстансов одновременно
нужно задавать уникальный `MQTT_CLIENT_ID`, иначе брокер будет закрывать
предыдущее соединение.

#### PostgreSQL
- `PG_HOST` - хост PostgreSQL (по умолчанию: `db`)
- `PG_PORT` - порт PostgreSQL (по умолчанию: `5432`)
- `PG_DB` - имя базы данных (по умолчанию: `hydro_dev`)
- `PG_USER` - пользователь БД (по умолчанию: `hydro`)
- `PG_PASS` - пароль БД (обязателен в production)

#### Redis
- `REDIS_HOST` - хост Redis (по умолчанию: `redis`)
- `REDIS_PORT` - порт Redis (по умолчанию: `6379`)

#### Laravel API
- `LARAVEL_API_URL` - URL Laravel API (по умолчанию: `http://laravel`)
- `LARAVEL_API_TOKEN` - токен для Laravel API (опционален)

#### History Logger специфичные настройки
- `TELEMETRY_BATCH_SIZE` - размер батча для записи в БД (по умолчанию: `1000`)
- `TELEMETRY_FLUSH_MS` - интервал принудительного flush в мс (по умолчанию: `200`)
- `REALTIME_QUEUE_MAX_SIZE` - лимит очереди realtime обновлений (по умолчанию: `5000`)
- `REALTIME_FLUSH_MS` - интервал flush realtime обновлений в мс (по умолчанию: `500`)
- `REALTIME_BATCH_MAX_UPDATES` - максимум realtime обновлений в одном запросе (по умолчанию: `200`)
- `SHUTDOWN_WAIT_SEC` - время ожидания перед закрытием Redis (по умолчанию: `2`)
- `SHUTDOWN_TIMEOUT_SEC` - таймаут graceful shutdown в секундах (по умолчанию: `30.0`)
- `FINAL_BATCH_MULTIPLIER` - множитель для финального батча при shutdown (по умолчанию: `10`)
- `QUEUE_CHECK_INTERVAL_SEC` - интервал проверки очереди в секундах (по умолчанию: `0.05`)
- `QUEUE_ERROR_RETRY_DELAY_SEC` - задержка при ошибке обработки очереди (по умолчанию: `1.0`)
- `LARAVEL_API_TIMEOUT_SEC` - таймаут для Laravel API в секундах (по умолчанию: `10.0`)
- `SERVICE_PORT` - порт для HTTP API (по умолчанию: `9300`)

## Тесты

### Локальный прогон

1. Поднимите инфраструктуру:
   ```bash
   docker compose -f backend/docker-compose.dev.yml up -d db redis laravel
   ```
2. Подготовьте venv и зависимости:
   ```bash
   python3 -m venv backend/services/.venv
   backend/services/.venv/bin/python -m pip install -r backend/services/history-logger/requirements.txt
   ```
3. Запустите тесты:
   ```bash
   backend/services/history-logger/scripts/run_tests.sh
   ```

Скрипт подхватывает `backend/services/history-logger/.env.test`. При необходимости
обновите там `PG_*`, `REDIS_*`, `LARAVEL_API_URL` и токены под свою среду.

## API Endpoints

### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "components": {
    "db": "ok",
    "mqtt": "ok",
    "queue_alerts": {
      "status": "ok",
      "size": 0,
      "oldest_age_seconds": 0,
      "dlq_size": 0,
      "success_rate": 1.0
    },
    "queue_status_updates": {
      "status": "ok",
      "size": 0,
      "oldest_age_seconds": 0,
      "dlq_size": 0,
      "success_rate": 1.0
    }
  }
}
```

### POST /commands
**Универсальный endpoint для публикации команд.**  
**Единственная точка публикации команд в MQTT для всех сервисов.**

**Request:**
```json
{
  "cmd": "irrigate",
  "greenhouse_uid": "gh-1",
  "zone_id": 1,
  "node_uid": "nd-irrig-1",
  "channel": "default",
  "params": {"duration_sec": 60},
  "trace_id": "trace-123"
}
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "command_id": "cmd-123"
  }
}
```

**Поддержка legacy формата:**
- Можно использовать `type` вместо `cmd` (legacy)

### POST /zones/{zone_id}/commands
Публикация команды для зоны.

**Request:** Аналогично `/commands`, но `zone_id` берется из URL.

### POST /nodes/{node_uid}/commands
Публикация команды для ноды.

**Request:** Аналогично `/commands`, но `node_uid` берется из URL.

### POST /ingest/telemetry
HTTP endpoint для приема телеметрии.

**Request:**
```json
{
  "samples": [
    {
      "node_uid": "nd-ph-1",
      "zone_uid": "zn-1",
      "zone_id": 1,
      "metric_type": "PH",
      "value": 6.5,
      "ts": "2025-01-27T10:00:00Z",
      "channel": "ph_sensor"
    }
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "count": 1
}
```

## MQTT Topics

Сервис подписывается на следующие топики:

- `hydro/+/+/+/+/telemetry` - телеметрия от узлов (формат: `hydro/{gh}/{zone}/{node}/{channel}/telemetry`)
- `hydro/+/+/+/heartbeat` - heartbeat сообщения от узлов
- `hydro/+/+/+/status` - статусы узлов
- `hydro/+/+/+/lwt` - LWT (last will) сообщения
- `hydro/+/+/+/diagnostics` - диагностические данные
- `hydro/+/+/+/error` - ошибки/алерты от узлов
- `hydro/node_hello` - регистрация новых узлов
- `hydro/+/+/+/node_hello` - регистрация новых узлов (альтернативный формат)
- `hydro/+/+/+/config_report` - конфигурация от ноды (firmware-defined)
- `hydro/+/+/+/+/command_response` - ответы на команды
- `hydro/time/request` - запрос синхронизации времени

### Формат топика телеметрии

```
hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry
```

Пример: `hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry`

**Примечание:** Формат синхронизирован с прошивками ESP32 согласно `MQTT_SPEC_FULL.md`.

### Формат payload телеметрии

```json
{
  "metric_type": "PH",
  "value": 6.5,
  "ts": 1737979.2,
  "channel": "ph_sensor",
  "node_id": "nd-ph-1",
  "raw": 1465,
  "stub": false,
  "stable": true
}
```

**Поля:**
- `metric_type` (обязательное) - тип метрики: PH, EC, TEMPERATURE, и т.д.
- `value` (обязательное) - значение метрики
- `ts` (опциональное) - timestamp в секундах (Unix timestamp) от прошивок
- `channel` (опциональное) - имя канала (может быть извлечено из топика)
- `node_id` (опциональное) - ID узла от прошивки
- `raw` (опциональное) - сырое значение сенсора
- `stub` (опциональное) - флаг, указывающий, что значение симулированное
- `stable` (опциональное) - флаг стабильности показаний сенсора

**Важно:** Legacy поле `timestamp` не поддерживается и будет отклонено.

## Метрики Prometheus

### Counter метрики
- `telemetry_received_total` - общее количество полученных сообщений
- `telemetry_processed_total` - общее количество обработанных сообщений
- `telemetry_dropped_total{reason}` - количество отброшенных сообщений
- `dropped_updates_count{reason}` - отброшенные realtime обновления
- `heartbeat_received_total{node_uid}` - heartbeat по узлам
- `status_received_total{node_uid,status}` - статусы узлов
- `diagnostics_received_total{node_uid}` - диагностика узлов
- `error_received_total{node_uid,level}` - ошибки узлов
- `node_hello_received_total` - количество node_hello
- `node_hello_registered_total` - количество зарегистрированных узлов
- `node_hello_errors_total{error_type}` - ошибки по типам
- `config_report_received_total` - количество config_report
- `config_report_processed_total` - количество успешно обработанных config_report
- `config_report_error_total{node_uid}` - ошибки обработки config_report
- `command_response_received_total` - ответы на команды
- `command_response_error_total` - ошибки обработки ответов на команды
- `commands_sent_total{zone_id,metric}` - отправлено команд через REST API
- `mqtt_publish_errors_total{error_type}` - ошибки публикации в MQTT
- `database_errors_total{error_type}` - ошибки БД
- `ingest_auth_failed_total` - ошибки авторизации ingest
- `ingest_rate_limited_total` - rate-limit на ingest
- `ingest_requests_total{status}` - запросы ingest по статусам

### Histogram метрики
- `telemetry_batch_size` - размер батчей
- `telemetry_processing_duration_seconds` - время обработки батча телеметрии
- `laravel_api_request_duration_seconds` - длительность запросов к Laravel API
- `redis_operation_duration_seconds` - длительность Redis операций
- `flush_latency_ms` - latency flush realtime обновлений

### Gauge метрики
- `telemetry_queue_size` - текущий размер очереди Redis
- `telemetry_queue_age_seconds` - возраст самого старого элемента в очереди
- `realtime_queue_len` - размер очереди realtime обновлений

### Histogram метрики (время обработки)
- `telemetry_processing_duration_seconds` - время обработки батча
- `laravel_api_request_duration_seconds` - время ответа Laravel API
- `redis_operation_duration_seconds` - время операций с Redis
- `command_rest_latency_seconds` - задержка обработки REST запросов команд

### Counter метрики (ошибки)
- `telemetry_dropped_total{reason}` - потерянные сообщения по причинам
- `database_errors_total{error_type}` - ошибки БД по типам

## Особенности реализации

### Retry логика

- **Redis push**: до 3 попыток с exponential backoff (2^attempt секунд)
- **Laravel API**: до 3 попыток для серверных ошибок (5xx), без retry для клиентских (4xx)

### Валидация данных

- Валидация размера payload (максимум 64KB)
- Валидация через Pydantic модели
- Проверка обязательных полей (metric_type, value)

### Batch обработка

- Группировка по идентичности сенсора `(zone_id, node_id, metric_type, channel)` для получения `sensor_id`
- Batch insert в `telemetry_samples` по `sensor_id`
- Batch upsert в `telemetry_last` по `sensor_id`
- Автоматический flush при достижении размера батча или интервала времени

### Graceful shutdown

- Отслеживание фоновых задач
- Таймаут 30 секунд на завершение
- Обработка оставшихся элементов в очереди

## Разработка

### Запуск локально

```bash
cd backend/services/history-logger
python -m pip install -r requirements.txt
python main.py
```

### Тестирование

```bash
# Все тесты
pytest history-logger/test_main.py -v

# Тесты критических исправлений
pytest history-logger/test_critical_fixes.py -v
```

### Docker

```bash
docker build -t history-logger -f Dockerfile .
docker run -p 9300:9300 history-logger
```

## Производительность

### Текущие настройки
- Размер батча: 200 элементов
- Интервал flush: 500 мс
- Максимальный размер очереди: 10000 элементов
- PostgreSQL pool: min_size=1, max_size=10

### Рекомендации по тюнингу
- Увеличить `TELEMETRY_BATCH_SIZE` для высокой нагрузки
- Уменьшить `TELEMETRY_FLUSH_MS` для более частой записи
- Настроить PostgreSQL pool в зависимости от нагрузки

## Безопасность

- Валидация размера payload (защита от DoS)
- Параметризованные SQL запросы (защита от SQL injection)
- Whitelist полей для обновления в heartbeat
- TLS для MQTT (по умолчанию включен)

## Мониторинг

Рекомендуется настроить алерты на:
- Размер очереди Redis (приближение к максимуму)
- Количество ошибок обработки
- Время обработки батчей
- Доступность сервиса (health endpoint)

## Troubleshooting

### Проблема: Потеря данных
- Проверить размер очереди Redis
- Проверить логи на ошибки записи в БД
- Проверить метрику `telemetry_dropped_total`

### Проблема: Медленная обработка
- Проверить размер батчей (`telemetry_batch_size`)
- Проверить производительность БД
- Проверить метрику `telemetry_processing_duration_seconds`

### Проблема: Ошибки регистрации узлов
- Проверить доступность Laravel API
- Проверить токен авторизации
- Проверить метрику `node_hello_errors_total`
### GET /metrics
Prometheus метрики.

### POST /nodes/{node_uid}/config
Публикация NodeConfig в MQTT (legacy/служебный сценарий).

**Примечание:** В актуальном флоу конфиг не пушится с сервера. Ноды отправляют
`config_report` при подключении, а history-logger сохраняет его в БД.
