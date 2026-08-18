# HISTORY_LOGGER_API.md
# REST API спецификация для history-logger сервиса

Документ описывает REST API endpoints history-logger сервиса — **единственной точки публикации команд в MQTT** в архитектуре hydro2.0.

**Дата обновления:** 2026-08-02 (code-first audit: webhook HMAC/body, DLQ replay paths, `zone_id` required, health/ingest/metrics sync).

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

Status: **historical** — README/часть документации/`docker-compose` publish `9301:9301` упоминали «metrics на :9301». Это устарело: uvicorn слушает только `SERVICE_PORT=9300`, Prometheus scrape — `history-logger:9300/metrics` (`backend/configs/dev/prometheus.yml`). Отдельный metrics-порт в коде не открывается.

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

### Полный список endpoints (sync с кодом 2026-08-02)

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/commands` | Универсальная публикация команды (см. §2.1) |
| POST | `/zones/{zone_id}/commands` | Zone-scoped публикация команды (см. §2.1.1) — используется Laravel `PythonBridgeService` |
| POST | `/nodes/{node_uid}/commands` | Node-scoped публикация команды (см. §2.1.2) |
| POST | `/nodes/{node_uid}/config` | Push NodeConfig в MQTT (см. §2.1.3) |
| POST | `/ingest/telemetry` | HTTP-ingest телеметрии (batch, см. §2.1.4) |
| GET | `/health` | Health check (см. §2.2) |
| GET | `/metrics` | Prometheus metrics (см. §6.1) |
| POST | `/internal/metrics/command-latency` | Internal metrics ingest (см. §2.3) |
| POST | `/internal/metrics/error-delivery-latency` | Internal metrics ingest (см. §2.6) |
| POST | `/internal/metrics/ws-broadcast` | WebSocket broadcast metrics |
| POST | `/internal/metrics/ws-auth` | WebSocket auth metrics |
| POST | `/internal/metrics/ws-event` | WebSocket event metrics |
| GET | `/api/dlq/alerts` | DLQ alerts list (см. §2.1.5) |
| POST | `/api/dlq/alerts/{dlq_id}/replay` | Replay одного alert из DLQ |
| DELETE | `/api/dlq/alerts/{id}` | Удаление alert из DLQ |
| GET | `/api/dlq/status-updates` | DLQ status updates list |
| POST | `/api/dlq/status-updates/{dlq_id}/replay` | Replay одного status update |
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
- `zone_id` (integer, **required**) — ID зоны (без него HL отвечает `400`)
- `node_uid` (string, required) — UID ноды
- `channel` (string, required) — канал ноды (всегда сегмент topic; для system-команд — `"system"`)
- `cmd` (string, required) — device-level команда; HL проверяет наличие `cmd` и отвергает legacy `type`, **не** валидирует enum-каталог §3
- `params` (object, required) — параметры команды
- `source` (string, optional) — источник команды (`automation-engine`, `laravel`, `api`, …)
- `cmd_id` (string, optional) — внешний command id, который будет сохранён в `commands.cmd_id`

**AE3 lease gate:** если у `zone_id` есть активная запись в `ae_zone_leases` (`leased_until > now()`), HL отклоняет mutating ON-команды от источников, отличных от `automation-engine`, ответом `409` `ae3_zone_lease_held`. Разрешены:
- `source=automation-engine` (держатель lease);
- read-only `state` / `test_sensor`;
- fail-safe OFF (`set_relay`/`set_state` с `state=false|0`, `set_pwm` с duty ≤ 0);
- diagnostic `set_fault_mode` (только `test_node`: seed уровней / pH / EC / E-Stop для realhw e2e, без актуаторов).
Operator `FORCE_PH_CONTROL` / `FORCE_EC_CONTROL` / `FORCE_LIGHTING` / `FORCE_CLIMATE` и device-level `dose`/`run_pump`/`set_relay true` через Laravel при активной lease не публикуются. `FORCE_IRRIGATION` идёт в AE3 ingress (там свой `*_zone_busy`).

Примечание:
- sensor calibration не имеет отдельного history-logger endpoint;
- backend публикует её через этот же `POST /commands` с `cmd="calibrate"`;
- для pH используются `params = { "stage": 1|2, "known_ph": number }`;
- для EC используются `params = { "stage": 1|2, "tds_value": integer }`.
- pump calibration также не имеет orchestration endpoint в `history-logger`;
- canonical flow для pump calibration — Laravel `POST /api/zones/{id}/calibrate-pump`
  (backend/AE владеет `run_token`, `zone_events`, `pump_calibrations`); HL — только transport `POST /commands`;
- устаревший HL-path `POST /zones/{zone_id}/calibrate-pump` **удалён** (ответ `404`, не `410`);
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

**Response (409 Conflict — AE3 lease held):**
```json
{
  "detail": {
    "error": "ae3_zone_lease_held",
    "zone_id": 1
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

#### Идемпотентность по `cmd_id` (контракт PR5)

History-logger **идемпотентен по `cmd_id`** при повторной публикации (`history-logger/commands/lifecycle.py`, `REPUBLISH_ALLOWED_STATUSES`):
- новая команда создаётся со статусом **`QUEUED`** (не `PENDING`);
- если запись с тем же `cmd_id` уже существует и payload совпадает — повторный `POST /commands` **безопасен** (не создаёт вторую MQTT-публикацию для `SENT`/`ACK`/terminal);
- re-drive publish допускается **только** при `QUEUED` или `SEND_FAILED`;
- при коллизии `cmd_id` с другим `(zone_id, node_uid, channel, cmd, params)` — `409 Conflict`;
- AE3-Lite стабилизирует `cmd_id` через `ae_commands.planner_step` + переиспользование `step_no`, чтобы retry handler'а не приводил к повторной дозе.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

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

Payload как у `POST /commands`, но `node_uid` берётся из URL. Поле **`channel` обязательно** (HL topic всегда включает сегмент channel). Для `restart`/`state` и system-команд (`activate_sensor_mode` / `deactivate_sensor_mode`) передавайте `channel="system"` (или иной channel из NodeConfig), а не опускайте поле.

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

**Описание:** HTTP fallback для приёма телеметрии (batch). Валидирует samples, ставит в очередь записи; пишет в `telemetry_samples` / `telemetry_last` асинхронно.

**URL:** `POST /ingest/telemetry`

**Request Body:**
```json
{
  "samples": [
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
  ]
}
```

Ограничения: max **1000** samples за запрос; пустой `samples` → `200` `{status:"ok", count:0, dropped:0}`.

**Response (202 Accepted):**
```json
{
  "status": "accepted",
  "count": 1,
  "dropped": 0,
  "total": 1
}
```

Внимание: `ts` — **секунды** (`datetime.fromtimestamp`). Не передавайте миллисекунды.

### 2.1.5. DLQ endpoints (`/api/dlq/*`)

Управление dead-letter queue для alerts и status updates (`system_routes.py`):

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/api/dlq/alerts` | List failed alert ingest |
| POST | `/api/dlq/alerts/{dlq_id}/replay` | Replay **одного** alert обратно в обработку |
| DELETE | `/api/dlq/alerts/{id}` | Hard delete из DLQ |
| GET | `/api/dlq/status-updates` | List failed status updates |
| POST | `/api/dlq/status-updates/{dlq_id}/replay` | Replay **одного** status update |
| DELETE | `/api/dlq/status-updates/{id}` | Hard delete |
| GET | `/api/dlq/metrics` | Summary (queue depth, failure rate, oldest entry age) |

Аутентификация: те же правила, что у `/commands` (Bearer token + production-only enforcement).

### 2.2. GET /health

**Описание:** Health check с проверкой компонентов (`system_routes.health`).

**URL:** `GET /health`

**Response (200 OK):**
```json
{
  "status": "ok",
  "components": {
    "db": "ok",
    "mqtt": "ok",
    "redis": "ok",
    "queues": "ok"
  }
}
```

При сбое компонента `status` становится `"degraded"` (HTTP всё ещё 200 в текущей реализации). Поля `version` / `uptime_seconds` / `commands_published_total` **не** возвращаются.

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

**Описание:** History-logger шлёт в Laravel шаги causal chain (`chain_webhook.emit_execution_step`) — в т.ч. `DISPATCH` при publish, далее `RUNNING` / `COMPLETE` / `FAIL` и др. Нужен Scheduler Cockpit.

**Endpoint Laravel:** `POST {LARAVEL_URL}/api/internal/webhooks/history-logger/execution-event`

**HL config:**
- `LARAVEL_URL` — base URL Laravel (по умолчанию `http://laravel:8080`);
- `HISTORY_LOGGER_WEBHOOK_SECRET` — секрет HMAC-подписи;
- `HISTORY_LOGGER_WEBHOOK_DEBOUNCE_MS` — debounce окно (default 250 ms).

**Headers:**
- `X-Hydro-Signature: <hex>` — `hex(hmac_sha256(secret, "{timestamp}.{raw_body}"))`
- `X-Hydro-Timestamp: <unix>` — replay-protection

**Body:**
```json
{
  "zone_id": 1,
  "step": "DISPATCH",
  "ref": "cmd-123",
  "status": "ok",
  "cmd_id": "cmd-123",
  "detail": "",
  "at": "2026-08-02T10:00:00Z",
  "live": true
}
```

Обязательны `zone_id`, `step`, `ref`, `status`; плюс **либо** `execution_id` (= `ae_tasks.id`), **либо** `cmd_id`.  
`step` ∈ `SNAPSHOT|DECISION|TASK|DISPATCH|RUNNING|COMPLETE|FAIL|SKIP`; `status` ∈ `ok|err|skip|run|warn`.

Laravel middleware: `VerifyHistoryLoggerWebhook` (alias `verify.history-logger.webhook`) проверяет HMAC и timestamp. После приёма — broadcast `ExecutionChainUpdated` на `hydro.zone.executions.{zoneId}`.

---

## 3. Типы команд

В MQTT / `POST /commands` поле **`cmd`** — это **device-level** команда узла.
High-level product labels (`FORCE_IRRIGATION`, `LIGHT_ON`, `VENT_ON`, `REBOOT`, …)
**не** являются значениями `cmd` и не публикуются в MQTT как есть.

Канонический enum device `cmd` (см. MQTT/node contract, `command_service`):

| `cmd` | Назначение | Типичные `params` |
|-------|------------|-------------------|
| `run_pump` | Насос / полив / recirculation | `duration_ms`, опционально volume/flow hints |
| `dose` | Дозирование pH/EC | `ml` (доменный must — AE3/Laravel; HL sanity при наличии), `duration_ms` (optional) |
| `set_relay` | Реле on/off | `state` / `on` |
| `set_pwm` | PWM / яркость / скорость | `duty` / `brightness` / `percent` (по каналу) |
| `set_position` | Позиционный привод | позиция / угол (по каналу) |
| `calibrate` | Калибровка сенсора/насоса | `stage`, `known_ph` / `tds_value` / … |
| `test_sensor` | Тест SENSOR-канала | по контракту канала |
| `restart` | Перезагрузка ноды (device) | — |
| `state` | Запрос/установка state snapshot | по контракту узла |

### 3.1. Дозирование (AE3 → HL → MQTT)

Канон для pH/EC насосов — **`cmd: "dose"`** с **`params.ml`**.
Обязательность `ml` enforce на стороне AE3/Laravel; HL проверяет bounds **если** `ml` передан.
Прошивка ph_node/ec_node исполняет дозу по `ml`; `params.duration_ms` опционален
(observability / audit в `commands.duration_ms`).

| `cmd` | Канал | Обязательные `params` | Опциональные `params` |
|-------|-------|----------------------|------------------------|
| `dose` | actuator pump (pH+/pH-/EC) | `ml` (float, > 0) | `duration_ms` (int, > 0) |

Transport-layer sanity bounds (`command_service._validate_command_params`):
- `params.ml` ∈ `(0, 500]` — защита от интеграционных ошибок; доменные caps — в AE3 CorrectionPlanner.
- `params.duration_ms` ∈ `(0, 300_000]` — при наличии.

### 3.2. Калибровка сенсоров

| `cmd` | Описание | Параметры |
|-------|----------|-----------|
| `calibrate` | Stage-based калибровка pH/EC | `stage`, `known_ph` или `tds_value` |

Контракт:
- `stage=1` и `stage=2` публикуются отдельными командами;
- `cmd_id` приходит из Laravel и затем используется в `POST /api/python/commands/ack`;
- terminal `DONE` — успех этапа; `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` — fail stage.

### 3.3. Legacy high-level labels (не device `cmd`)

Status: **historical / non-normative** — product/intent labels старых черновиков.
В MQTT публикуется только device `cmd` из таблицы выше (+ корректный `channel`).

| Legacy label | Каноническая замена |
|--------------|---------------------|
| `FORCE_IRRIGATION` / `FORCE_PUMP_ON` / `FORCE_PUMP_OFF` | штатный полив — AE3 `start-irrigation`; device — `run_pump` на pump/irrig channel |
| `PUMP_CALIBRATE` | `calibrate` (или отдельный calibration flow Laravel → HL) |
| `DOSE_PH_UP` / `DOSE_PH_DOWN` / `DOSE_EC_*` | `cmd: "dose"` + actuator `channel` |
| `LIGHT_ON` / `LIGHT_OFF` / `LIGHT_SET_BRIGHTNESS` / `LIGHT_SCHEDULE` | lighting tick / AE3 → `set_pwm` (или реле) на light channel; расписание — Laravel scheduler, не MQTT `cmd` |
| `VENT_ON` / `VENT_OFF` / `HEATER_ON` / `HEATER_OFF` | climate tick → `set_pwm` / `set_relay` на соответствующий channel |
| `REBOOT` | device `cmd: "restart"` |
| `SET_CONFIG` / `SAFE_MODE` / `GET_STATUS` | не MQTT device `cmd` из этого каталога (`config` / `state` / node framework flows) |
| `duration_sec` в dose payload | не используется; AE3 передаёт `ml`, опционально `duration_ms` |

---

## 4. Валидация команд

History-logger выполняет следующую валидацию перед публикацией команды:

1. **Проверка структуры:**
   - Наличие обязательных полей (`greenhouse_uid`, `node_uid`, `channel`, `cmd`, `params`)
   - Поле `type` отклоняется (strict policy, алиас не поддерживается)
   - Корректность типов данных

2. **Проверка типа команды:**
   - `cmd` должен быть из канонического device-каталога (§3)
   - `cmd` должен соответствовать типу канала (например, `run_pump` / `dose` — для actuator pump-каналов)

3. **Проверка параметров:**
   - Наличие обязательных параметров для данного типа команды
   - Для `cmd="dose"`: обязателен `params.ml` (> 0, ≤ 500 sanity ceiling); `params.duration_ms` опционален (> 0, ≤ 300_000)
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

Канон имён — `backend/services/history-logger/metrics.py` (+ shared `common/pipeline_metrics` для части health). Ключевые:

```
# Команды / publish
commands_sent_total{zone_id, metric}
mqtt_publish_errors_total{error_type}
commands_published_unconfirmed_total
command_response_received_total
command_response_error_total
command_queue_drain_*_total
command_status_delivery_dropped_total
command_status_dlq_moved_total
command_status_dlq_size
alert_dlq_size

# Телеметрия / ingest
telemetry_received_total / telemetry_processed_total / telemetry_batch_size
telemetry_processing_duration_seconds
telemetry_dropped_total{reason}
ingest_requests_total / ingest_auth_failed_total / ingest_rate_limited_total

# Прочее
node_hello_* / config_report_* / heartbeat_received_total
database_errors_total
ws_broadcast_total / ws_auth_total
```

Отдельных `hl_webhook_*` Prometheus-метрик в коде нет. Старый префикс `history_logger_*` — только legacy dashboards.

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
  "cmd": "run_pump",
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
| `validation_failed` | 400 | Невалидные данные команды / отсутствует `cmd` / запрещён `type` |
| `missing_required_params` | 400 | Отсутствуют обязательные параметры (напр. `zone_id`, `channel`) |
| `invalid_param_value` | 400 | Невалидное значение параметра (sanity bounds) |
| `unauthorized` | 401 | Отсутствует/некорректен токен |
| `mqtt_publish_failed` | 500 | Ошибка публикации в MQTT |
| `db_insert_failed` | 500 | Ошибка записи в БД |
| `service_unavailable` | 503 | Сервис недоступен |

HL **не** возвращает `unknown_command_type` — enum `cmd` из §3 не enforce на транспорте (каталог — контракт AE3/firmware/MQTT).

### 7.2. Retry логика

History-logger использует retry для MQTT publish (`MQTT_PUBLISH_RETRY_DELAYS_SEC`, `MAX_PUBLISH_RETRIES=3`):
- максимум 3 попытки;
- задержки: **500ms / 1s / 2s**;
- после исчерпания — статус `SEND_FAILED` (lowercase `failed` запрещён).

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
    "cmd": "dose",
    "params": {
        "ml": 5.0,
        "duration_ms": 1200,
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
