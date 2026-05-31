# HISTORY_LOGGER_API.md
# REST API спецификация для history-logger сервиса

Документ описывает REST API endpoints history-logger сервиса — **единственной точки публикации команд в MQTT** в архитектуре hydro2.0.

**Дата обновления:** 2026-05-28 (sync с FastAPI routes: добавлены `/zones/.../commands`, `/nodes/.../commands`, `/nodes/.../config`, `/ingest/telemetry`, DLQ endpoints, webhook callback; порт `/metrics` исправлен на 9300; canonical имена метрик).

**Связанные документы:**
- `PYTHON_SERVICES_ARCH.md` — общая архитектура Python-сервисов
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол и форматы сообщений
- `../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md` — контракт между backend и нодами

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 1. Общая информация

**Base URL:** `http://history-logger:9300` (внутри Docker сети)
**External URL (dev):** `http://localhost:9300`

**Порты:**
- **9300**: REST API **+** Prometheus metrics (`/metrics` mount на тот же FastAPI app, не отдельный порт)

Status: **historical** — README/часть документации упоминала «metrics на :9301». Это устарело: uvicorn слушает только `SERVICE_PORT=9300`, Prometheus scrape настроен на `history-logger:9300/metrics` (`configs/dev/prometheus.yml`). Порт 9301 в коде не открывается.

**Назначение:**
- Централизованная публикация команд в MQTT
- Логирование всех отправленных команд
- Валидация команд перед публикацией
- Единая точка мониторинга команд
- Transport/observer ingest для MQTT-событий нод без владения bind/rebind state machine

**Архитектурный принцип:**
```
Automation-Engine → REST (9300) → History-Logger → MQTT → Узлы
Laravel scheduler-dispatch → REST (9405) → Automation-Engine → REST (9300) → History-Logger → MQTT → Узлы
```

`history-logger` не является owner-слоем для bind/rebind нод и не выполняет zone-level orchestration (`fill`, `drain`, `calibrate-flow`). Эти сценарии либо закрыты fail-closed, либо принадлежат canonical owner в Laravel/AE3.

---

## 2. Endpoints

### Полный список endpoints (sync с кодом 2026-05-28)

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/commands` | Универсальная публикация команды (см. §2.1) |
| POST | `/zones/{zone_id}/commands` | Zone-scoped публикация команды (см. §2.1.1) — используется Laravel `PythonBridgeService` |
| POST | `/nodes/{node_uid}/commands` | Node-scoped публикация команды (см. §2.1.2) |
| POST | `/nodes/{node_uid}/config` | Push NodeConfig в MQTT (см. §2.1.3) |
| POST | `/ingest/telemetry` | HTTP-ingest телеметрии (для нод без MQTT, см. §2.1.4) |
| GET | `/health` | Health check (см. §2.2) |
| GET | `/metrics` | Prometheus metrics (см. §6.1) |
| POST | `/internal/metrics/command-latency` | Internal metrics ingest (см. §2.3) |
| POST | `/internal/metrics/error-delivery-latency` | Internal metrics ingest (см. §2.6) |
| POST | `/internal/metrics/ws-broadcast` | WebSocket broadcast metrics |
| POST | `/internal/metrics/ws-auth` | WebSocket auth metrics |
| POST | `/internal/metrics/ws-event` | WebSocket event metrics |
| GET | `/api/dlq/alerts` | DLQ alerts list (см. §2.5) |
| POST | `/api/dlq/alerts/replay` | Replay alerts из DLQ |
| DELETE | `/api/dlq/alerts/{id}` | Удаление alert из DLQ |
| GET | `/api/dlq/status-updates` | DLQ status updates list |
| POST | `/api/dlq/status-updates/replay` | Replay status updates |
| DELETE | `/api/dlq/status-updates/{id}` | Удаление status update из DLQ |
| GET | `/api/dlq/metrics` | DLQ summary metrics |

Webhook callback (HL → Laravel): `POST {LARAVEL_URL}/api/internal/webhooks/history-logger/execution-event` с HMAC-подписью (`HISTORY_LOGGER_WEBHOOK_SECRET`). Используется для Scheduler Cockpit causal chain. См. §2.7.

### 2.1. POST /commands

**Описание:** Универсальный endpoint для отправки команд. Публикует команду в MQTT и логирует её в БД.

**URL:** `POST /commands`

**Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{
  "greenhouse_uid": "gh-1",
  "zone_id": 1,
  "node_uid": "nd-pump-1",
  "channel": "pump_in",
  "cmd": "run_pump",
  "params": {
    "duration_ms": 5000
  },
  "source": "automation-engine"
}
```

**Поля:**
- `greenhouse_uid` (string, required) — UID теплицы
- `zone_id` (integer, optional) — ID зоны (для контекста)
- `node_uid` (string, required) — UID ноды
- `channel` (string, required) — канал ноды
- `cmd` (string, required) — команда для ноды
- `params` (object, required) — параметры команды
- `source` (string, optional) — источник команды (`automation-engine`, `laravel_scheduler`, `api`, …)
- `cmd_id` (string, optional) — внешний command id, который будет сохранён в `commands.cmd_id`

Примечание:
- sensor calibration не имеет отдельного history-logger endpoint;
- backend публикует её через этот же `POST /commands` с `cmd="calibrate"`;
- для pH используются `params = { "stage": 1|2, "known_ph": number }`;
- для EC используются `params = { "stage": 1|2, "tds_value": integer }`.
- pump calibration также не имеет поддерживаемого orchestration endpoint в `history-logger`;
- canonical flow для pump calibration идёт через Laravel `POST /api/zones/{id}/calibrate-pump`,
  где backend/automation владеет `run_token`, `zone_events` и `pump_calibrations`;
- `history-logger` в этом сценарии принимает только transport publish на `POST /commands`;
- `POST /zones/{zone_id}/calibrate-pump` считается удалённым из контракта и возвращает `410 Gone`.
- **`set_position`** (roof vent, 0..100%): greenhouse climate tick; обязательный `params.position_pct`, опционально `params.max_step_pct` (см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`).

**Response (200 OK):**
```json
{
  "status": "ok",
  "data": {
    "command_id": "cmd-123456",
    "zone_id": 1,
    "node_uid": "nd-pump-1",
    "channel": "pump_in"
  }
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Field 'cmd' is required; field 'type' is not supported"
}
```

**Response (401 Unauthorized):**
```json
{
  "detail": "Unauthorized: invalid or missing token"
}
```

**Response (500 Internal Server Error):**
```json
{
  "status": "error",
  "error": "mqtt_publish_failed",
  "message": "Failed to publish to MQTT broker"
}
```

---

### 2.1.1. POST /zones/{zone_id}/commands

**Описание:** Zone-scoped публикация команды. Используется Laravel `PythonBridgeService` (`backend/laravel/app/Services/PythonBridgeService.php`) для всех команд, инициированных из Laravel.

**URL:** `POST /zones/{zone_id}/commands`

Поведение идентично `POST /commands`, но `zone_id` из URL автоматически подставляется в payload. Это разделение упрощает audit и применение per-zone rate limits.

**Request Body:** как для `POST /commands`, без `zone_id` (берётся из URL):
```json
{
  "greenhouse_uid": "gh-1",
  "node_uid": "nd-pump-1",
  "channel": "pump_in",
  "cmd": "run_pump",
  "params": {"duration_ms": 5000},
  "source": "laravel:manual",
  "cmd_id": "...",
  "ts": 1737355112,
  "sig": "...",
  "zone_uid": "zn-1",
  "hardware_id": "esp32-ABCD"
}
```

Дополнительные поля передаются Laravel:
- `ts`, `sig` — HMAC-подпись вычисляется `App\Services\CommandSignatureService` ещё в Laravel;
- `trace_id`, `request_id` — для audit;
- `zone_uid`, `hardware_id` — denormalized identifiers.

История-logger **всё равно пересчитывает** `sig` согласно своей policy (`command_service.py`: `Overriding provided command signature`) — Laravel-side подпись используется как best-effort baseline, canonical sign делает HL непосредственно перед публикацией в MQTT.

### 2.1.2. POST /nodes/{node_uid}/commands

**Описание:** Node-scoped публикация команды. Используется для node-level операций (например, `restart`, `state`, `system/command`).

**URL:** `POST /nodes/{node_uid}/commands`

Payload как у `POST /commands`, но `node_uid` берётся из URL. Если `channel` не указан, команда публикуется в node-level topic (`hydro/{gh}/{zone}/{node}/{type}` без сегмента channel) — это используется для `restart`, `state`, и system команд `activate_sensor_mode`/`deactivate_sensor_mode` (`channel="system"`).

### 2.1.3. POST /nodes/{node_uid}/config

**Описание:** Push NodeConfig в MQTT topic `hydro/{gh}/{zone}/{node}/config`. Используется Laravel `PublishNodeConfigJob` (`backend/laravel/app/Jobs/PublishNodeConfigJob.php`) при изменении конфигурации ноды.

**URL:** `POST /nodes/{node_uid}/config`

**Request Body:**
```json
{
  "greenhouse_uid": "gh-1",
  "zone_uid": "zn-1",
  "config": {
    "node_id": "nd-ph-1",
    "version": 3,
    "fw_version": "1.0.0",
    "channels": [...],
    "wifi": {...},
    "mqtt": {...}
  },
  "ts": 1737355112,
  "sig": "..."
}
```

Поведение:
- HL валидирует структуру NodeConfig;
- публикует в MQTT с QoS=1, Retain=false;
- логирует факт публикации в `nodes.config` (через Laravel API observed-факт).

### 2.1.4. POST /ingest/telemetry

**Описание:** HTTP fallback для приёма телеметрии от нод, у которых нет прямого MQTT-канала (например, тестовый прогон или edge-кейсы). Сохраняет в `telemetry_samples` и обновляет `telemetry_last`.

**URL:** `POST /ingest/telemetry`

**Request Body:**
```json
{
  "greenhouse_uid": "gh-1",
  "zone_id": 1,
  "node_uid": "nd-ph-1",
  "channel": "ph_sensor",
  "metric_type": "PH",
  "value": 6.2,
  "ts": 1737355112,
  "unit": "pH"
}
```

Внимание: `ts` декодируется как **секунды** через `datetime.fromtimestamp(ts_value)`. Не передавайте миллисекунды (известный edge-case, ts > 10^10 будет интерпретирован как далёкое будущее).

### 2.1.5. DLQ endpoints (`/api/dlq/*`)

Управление dead-letter queue для alerts и status updates:

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/api/dlq/alerts` | List failed alert ingest |
| POST | `/api/dlq/alerts/replay` | Перенос обратно в `pending_alerts` для повторной обработки |
| DELETE | `/api/dlq/alerts/{id}` | Hard delete из DLQ |
| GET | `/api/dlq/status-updates` | List failed status updates |
| POST | `/api/dlq/status-updates/replay` | Replay status updates |
| DELETE | `/api/dlq/status-updates/{id}` | Hard delete |
| GET | `/api/dlq/metrics` | Summary (queue depth, failure rate, oldest entry age) |

Аутентификация: те же правила, что у `/commands` (Bearer token + production-only enforcement).

### 2.2. GET /health

**Описание:** Health check endpoint для проверки работоспособности сервиса.

**URL:** `GET /health`

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "history-logger",
  "version": "3.0.0",
  "mqtt_connected": true,
  "db_connected": true,
  "uptime_seconds": 3600,
  "commands_published_total": 1234,
  "last_telemetry_received_ago_sec": 5
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "service": "history-logger",
  "mqtt_connected": false,
  "db_connected": true,
  "errors": [
    "MQTT broker connection lost"
  ]
}
```

**Пример:**
```bash
curl http://localhost:9300/health
```

---

### 2.3. POST /internal/metrics/command-latency

**Описание:** Internal endpoint для приёма latency-метрик команд от Laravel и обновления Prometheus histogram’ов.

**URL:** `POST /internal/metrics/command-latency`

**Request Body:**
```json
{
  "cmd_id": "cmd-123456",
  "metrics": {
    "sent_to_accepted_seconds": 1.2,
    "accepted_to_done_seconds": 0.8,
    "e2e_latency_seconds": 2.0
  }
}
```

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

---

### 2.6. POST /internal/metrics/error-delivery-latency

**Описание:** Internal endpoint для приёма latency-метрик доставки ошибок (MQTT -> Laravel -> WS).

**URL:** `POST /internal/metrics/error-delivery-latency`

**Request Body:**
```json
{
  "metrics": {
    "mqtt_to_laravel_seconds": 0.4,
    "laravel_to_ws_seconds": 0.2,
    "total_latency_seconds": 0.6
  }
}
```

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

---

### 2.7. Webhook callback (HL → Laravel)

**Описание:** History-logger вызывает Laravel webhook при terminal-статусе команды, чтобы Scheduler Cockpit получил causal chain update.

**Endpoint Laravel:** `POST {LARAVEL_URL}/api/internal/webhooks/history-logger/execution-event`

**HL config:**
- `LARAVEL_URL` — base URL Laravel (по умолчанию `http://laravel:8080`);
- `HISTORY_LOGGER_WEBHOOK_SECRET` — секрет HMAC-подписи;
- `HISTORY_LOGGER_WEBHOOK_DEBOUNCE_MS` — debounce окно (default 250 ms).

**Headers:**
- `X-HL-Signature: hmac-sha256=<hex>` — подпись body
- `X-HL-Timestamp: <unix>` — для replay-protection

**Body:**
```json
{
  "event_type": "command_terminal",
  "cmd_id": "cmd-123",
  "zone_id": 1,
  "task_id": 42,
  "terminal_status": "DONE",
  "ack_received_at": "2026-05-28T10:00:00Z",
  "terminal_at": "2026-05-28T10:00:05Z"
}
```

Laravel middleware: `VerifyHistoryLoggerWebhook` (alias `verify.history-logger.webhook`) проверяет HMAC и timestamp tolerance. После приёма Laravel эмитит broadcast event `ExecutionChainUpdated` на канал `hydro.zone.executions.{zoneId}`.

---

## 3. Типы команд

История-logger поддерживает все типы команд из MQTT спецификации. Основные типы:

### 3.1. Команды управления насосами

| Тип команды | Описание | Параметры |
|------------|----------|-----------|
| `FORCE_IRRIGATION` | Принудительный полив | `duration_sec`, `volume_ml` (optional) |
| `FORCE_PUMP_ON` | Включить насос | `duration_sec`, `target_ml_per_sec` (optional) |
| `FORCE_PUMP_OFF` | Выключить насос | - |
| `PUMP_CALIBRATE` | Калибровка насоса | `expected_ml`, `duration_sec` |

### 3.2. Команды управления дозированием

| Тип команды | Описание | Параметры |
|------------|----------|-----------|
| `DOSE_PH_UP` | Дозирование pH+ | `ml`, `duration_sec` (optional) |
| `DOSE_PH_DOWN` | Дозирование pH- | `ml`, `duration_sec` (optional) |
| `DOSE_EC_A` | Дозирование EC компонент A | `ml`, `duration_sec` (optional) |
| `DOSE_EC_B` | Дозирование EC компонент B | `ml`, `duration_sec` (optional) |

### 3.3. Команды управления освещением

| Тип команды | Описание | Параметры |
|------------|----------|-----------|
| `LIGHT_ON` | Включить освещение | `brightness` (0-100, optional) |
| `LIGHT_OFF` | Выключить освещение | - |
| `LIGHT_SET_BRIGHTNESS` | Установить яркость | `brightness` (0-100) |
| `LIGHT_SCHEDULE` | Установить расписание | `on_time`, `off_time` |

### 3.4. Команды управления климатом

| Тип команды | Описание | Параметры |
|------------|----------|-----------|
| `VENT_ON` | Включить вентиляцию | `speed` (0-100, optional) |
| `VENT_OFF` | Выключить вентиляцию | - |
| `HEATER_ON` | Включить обогрев | `target_temp` (optional) |
| `HEATER_OFF` | Выключить обогрев | - |

### 3.5. Системные команды

| Тип команды | Описание | Параметры |
|------------|----------|-----------|
| `SET_CONFIG` | Установить конфигурацию | `key`, `value` |
| `REBOOT` | Перезагрузка ноды | - |
| `SAFE_MODE` | Переход в safe mode | - |
| `GET_STATUS` | Запрос статуса | - |

### 3.6. Команды калибровки сенсоров

| Тип команды | Описание | Параметры |
|------------|----------|-----------|
| `calibrate` | Stage-based калибровка pH/EC сенсора | `stage`, `known_ph` или `tds_value` |

Контракт:
- `stage=1` и `stage=2` публикуются отдельными командами;
- `cmd_id` приходит из Laravel и затем используется в `POST /api/python/commands/ack`;
- terminal status `DONE` трактуется Laravel как успешное завершение этапа;
- terminal status `NO_EFFECT`, `ERROR`, `INVALID`, `BUSY`, `TIMEOUT`, `SEND_FAILED` трактуются как failed stage на стороне Laravel.

---

## 4. Валидация команд

History-logger выполняет следующую валидацию перед публикацией команды:

1. **Проверка структуры:**
   - Наличие обязательных полей (`greenhouse_uid`, `node_uid`, `channel`, `cmd`, `params`)
   - Поле `type` отклоняется (strict policy, алиас не поддерживается)
   - Корректность типов данных

2. **Проверка типа команды:**
   - Тип команды должен быть в списке поддерживаемых
   - Тип команды должен соответствовать каналу (например, `FORCE_IRRIGATION` только для `pump_*` каналов)

3. **Проверка параметров:**
   - Наличие обязательных параметров для данного типа команды
   - Валидация диапазонов значений (например, `brightness: 0-100`)
   - Проверка типов параметров

4. **Проверка MQTT топика:**
   - Топик должен соответствовать формату: `hydro/{gh}/{zone}/{node}/{channel}/command`
   - Ноды и каналы должны существовать в системе (опционально)

---

## 5. Логирование команд

Каждая команда логируется в БД в таблицу `commands`:

**Структура записи:**
```sql
CREATE TABLE commands (
  id BIGSERIAL PRIMARY KEY,
  zone_id BIGINT NULL,
  node_id BIGINT NULL,
  channel VARCHAR(50) NOT NULL,
  cmd VARCHAR(64) NOT NULL,
  params JSONB NOT NULL,
  status VARCHAR(20) NOT NULL, -- QUEUED|SENT|ACK|DONE|NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED
  cmd_id VARCHAR(128) UNIQUE NOT NULL,
  sent_at TIMESTAMPTZ NULL,
  ack_at TIMESTAMPTZ NULL,
  failed_at TIMESTAMPTZ NULL,
  source VARCHAR(64) NULL,
  error_code VARCHAR(64) NULL,
  error_message TEXT,
  result_code INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Индексы:**
- `idx_commands_node_uid` на `node_uid`
- `idx_commands_zone_id` на `zone_id`
- `idx_commands_created_at` на `created_at`

---

## 6. Мониторинг

### 6.1. Prometheus метрики (порт 9300, путь `/metrics`)

**Endpoint:** `GET http://history-logger:9300/metrics`

Канонические имена метрик (из `backend/services/history-logger/metrics.py`):

```
# Команды
commands_sent_total{cmd, zone_id, source}
commands_failed_total{cmd, reason}
commands_publish_duration_seconds{cmd, le}

# Телеметрия
telemetry_received_total{node_uid, channel}
telemetry_processed_total{result}
telemetry_processing_duration_seconds{le}
telemetry_batch_size{le}

# MQTT
mqtt_connected
mqtt_messages_received_total{topic_kind}
mqtt_reconnects_total

# База данных
db_operations_total{operation, table}
db_errors_total{operation, table}

# DLQ
dlq_size{queue}                              # pending_alerts, pending_status_updates
dlq_replay_total{queue, result}

# Webhook
hl_webhook_calls_total{event_type, result}
hl_webhook_duration_seconds{event_type, le}
```

Старый префикс `history_logger_*` (например `history_logger_commands_published_total`) **deprecated** — оставлен только в части legacy dashboards.

### 6.2. Логи

История-logger пишет структурированные логи в stdout:

**Формат:**
```json
{
  "timestamp": "2026-02-14T10:30:00Z",
  "level": "INFO",
  "service": "history-logger",
  "event": "command_published",
  "command_id": "cmd-123456",
  "node_uid": "nd-pump-1",
  "channel": "pump_in",
  "command_type": "FORCE_IRRIGATION",
  "mqtt_topic": "hydro/gh-1/zone-1/nd-pump-1/pump_in/command"
}
```

**Уровни логов:**
- `DEBUG` — детальная информация о работе
- `INFO` — успешные операции (команды, телеметрия)
- `WARNING` — предупреждения (валидация, ретраи)
- `ERROR` — ошибки (MQTT, БД, валидация)

---

## 7. Обработка ошибок

### 7.1. Коды ошибок

| Код | HTTP Status | Описание |
|-----|-------------|----------|
| `validation_failed` | 400 | Невалидные данные команды |
| `unknown_command_type` | 400 | Неизвестная команда `cmd` |
| `missing_required_params` | 400 | Отсутствуют обязательные параметры |
| `invalid_param_value` | 400 | Невалидное значение параметра |
| `unauthorized` | 401 | Отсутствует/некорректен токен |
| `mqtt_publish_failed` | 500 | Ошибка публикации в MQTT |
| `db_insert_failed` | 500 | Ошибка записи в БД |
| `service_unavailable` | 503 | Сервис недоступен |

### 7.2. Retry логика

History-logger использует retry логику для MQTT публикаций:
- Максимум 3 попытки
- Экспоненциальная задержка: 100ms, 200ms, 400ms
- После 3 неудачных попыток команда помечается как `failed` в БД

---

## 8. Примеры использования

### 8.1. Automation-Engine отправляет команду корректировки pH

```python
import httpx

# Automation-engine определил, что pH слишком низкий
command = {
    "greenhouse_uid": "gh-1",
    "zone_id": 1,
    "node_uid": "nd-ph-1",
    "channel": "pump_ph_up",
    "cmd": "dose_ph_up",
    "params": {
        "ml": 5.0
    },
    "source": "automation-engine"
}

response = httpx.post(
    "http://history-logger:9300/commands",
    json=command,
    timeout=5.0
)

print(response.json())
# {"status": "ok", "data": {"command_id": "cmd-123456", ...}}
```

### 8.2. Automation-engine публикует команду полива

```python
# Только automation-engine (после решения контроллера) вызывает history-logger; Laravel dispatch не пишет в MQTT напрямую.
command = {
    "cmd": "run_pump",
    "params": {
        "duration_ms": 60000
    },
    "greenhouse_uid": "gh-1",
    "node_uid": "nd-pump-1",
    "channel": "pump_in"
}

response = httpx.post(
    "http://history-logger:9300/commands",
    json=command,
    timeout=5.0
)
```

### 8.3. Laravel отправляет ручную команду

```php
// Laravel контроллер для ручных команд
$response = Http::timeout(5)->post('http://history-logger:9300/commands', [
    'greenhouse_uid' => 'gh-1',
    'zone_id' => $zone->id,
    'node_uid' => 'nd-pump-1',
    'channel' => 'pump_in',
    'cmd' => 'run_pump',
    'params' => [
        'duration_ms' => 30000
    ],
    'source' => 'manual',
]);
```

---

## 9. Security

**Strict policy (актуально):**
1. Для `POST /commands` поле `cmd` обязательно.
2. Поле `type` отклоняется с `400`.
3. `GROWTH_CYCLE_CONFIG` не является device-командой и не должен отправляться в `history-logger /commands`; эта команда завершается локально на backend как zone-level control-plane update.

**Аутентификация (фактическая модель):**
1. Если `HISTORY_LOGGER_API_TOKEN`/`PY_INGEST_TOKEN` задан, запрос должен содержать `Authorization: Bearer <token>`.
2. В production (`APP_ENV=production|prod`) токен обязателен всегда.
3. Без токена в dev допускаются только localhost-запросы; внешние запросы получают `401`.

---

## 10. Связанные документы

- `PYTHON_SERVICES_ARCH.md` — архитектура Python-сервисов
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол
- `../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md` — контракт backend↔nodes
- `REST_API_REFERENCE.md` — общий референс REST API
