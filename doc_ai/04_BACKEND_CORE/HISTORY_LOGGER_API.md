# HISTORY_LOGGER_API.md
# REST API спецификация для history-logger сервиса

Документ описывает REST API endpoints history-logger сервиса — **единственной точки публикации команд в MQTT** в архитектуре hydro2.0.

**Связанные документы:**
- `PYTHON_SERVICES_ARCH.md` — общая архитектура Python-сервисов
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол и форматы сообщений
- `../03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md` — контракт между backend и нодами

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общая информация

**Base URL:** `http://history-logger:9300` (внутри Docker сети)
**External URL (dev):** `http://localhost:9300`

**Порты:**
- **9300**: REST API (команды)
- **9301**: Prometheus metrics (`/metrics`)

**Назначение:**
- Централизованная публикация команд в MQTT
- Логирование всех отправленных команд
- Валидация команд перед публикацией
- Единая точка мониторинга команд

**Архитектурный принцип:**
```
Automation-Engine → REST (9300) → History-Logger → MQTT → Узлы
Scheduler → REST (9405) → Automation-Engine → REST (9300) → History-Logger → MQTT → Узлы
```

---

## 2. Endpoints

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
- `source` (string, optional) — источник команды (`automation`, `scheduler`, `api`)

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
  "detail": "Field 'cmd' is required; legacy field 'type' is not supported"
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

### 2.2. POST /zones/{zone_id}/commands

**Описание:** Отправка команды для конкретной зоны. Упрощенный endpoint для zone-level команд.

**URL:** `POST /zones/{zone_id}/commands`

**Path Parameters:**
- `zone_id` (integer) — ID зоны

**Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{
  "cmd": "run_pump",
  "params": {
    "duration_ms": 5000
  },
  "greenhouse_uid": "gh-1",
  "node_uid": "nd-pump-1",
  "channel": "pump_in"
}
```

**Поля:**
- `cmd` (string, required) — команда
- `params` (object, required) — параметры команды
- `greenhouse_uid` (string, required) — UID теплицы
- `node_uid` (string, required) — UID ноды
- `channel` (string, required) — канал ноды

**Response:** Аналогично `/commands`

**Пример:**
```bash
curl -X POST http://localhost:9300/zones/1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "run_pump",
    "params": {"duration_ms": 5000},
    "greenhouse_uid": "gh-1",
    "node_uid": "nd-pump-1",
    "channel": "pump_in"
  }'
```

---

### 2.3. POST /nodes/{node_uid}/commands

**Описание:** Отправка команды для конкретной ноды. Упрощенный endpoint для node-level команд.

**URL:** `POST /nodes/{node_uid}/commands`

**Path Parameters:**
- `node_uid` (string) — UID ноды

**Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{
  "cmd": "set_config",
  "params": {
    "key": "ph_calibration_offset",
    "value": 0.15
  },
  "greenhouse_uid": "gh-1",
  "channel": "ph_main"
}
```

**Поля:**
- `cmd` (string, required) — команда
- `params` (object, required) — параметры команды
- `greenhouse_uid` (string, required) — UID теплицы
- `channel` (string, required) — канал ноды

**Response:** Аналогично `/commands`

**Пример:**
```bash
curl -X POST http://localhost:9300/nodes/nd-ph-1/commands \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "set_config",
    "params": {"key": "calibration_offset", "value": 0.15},
    "greenhouse_uid": "gh-1",
    "channel": "ph_main"
  }'
```

---

### 2.4. GET /health

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

---

## 4. Валидация команд

History-logger выполняет следующую валидацию перед публикацией команды:

1. **Проверка структуры:**
   - Наличие обязательных полей (`greenhouse_uid`, `node_uid`, `channel`, `cmd`, `params`)
   - Поле `type` отклоняется (strict policy, legacy alias не поддерживается)
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
  command_id VARCHAR(255) UNIQUE NOT NULL,
  greenhouse_uid VARCHAR(50) NOT NULL,
  zone_id INTEGER,
  node_uid VARCHAR(50) NOT NULL,
  channel VARCHAR(50) NOT NULL,
  command_type VARCHAR(50) NOT NULL,
  params JSONB NOT NULL,
  context JSONB,
  mqtt_topic VARCHAR(255) NOT NULL,
  status VARCHAR(20) NOT NULL, -- published, failed
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  published_at TIMESTAMP
);
```

**Индексы:**
- `idx_commands_node_uid` на `node_uid`
- `idx_commands_zone_id` на `zone_id`
- `idx_commands_created_at` на `created_at`

---

## 6. Мониторинг

### 6.1. Prometheus метрики (порт 9301)

**Endpoint:** `GET /metrics`

**Метрики:**
```
# Команды
history_logger_commands_published_total{command_type="FORCE_IRRIGATION", zone_id="1"} 123
history_logger_commands_failed_total{command_type="FORCE_IRRIGATION", reason="validation_error"} 5

# Телеметрия
history_logger_telemetry_received_total{node_uid="nd-ph-1", channel="ph_main"} 45678
history_logger_telemetry_processing_duration_seconds{quantile="0.5"} 0.001
history_logger_telemetry_batch_size{quantile="0.95"} 150

# MQTT
history_logger_mqtt_connected{} 1
history_logger_mqtt_messages_received_total{} 123456
history_logger_mqtt_reconnects_total{} 3

# База данных
history_logger_db_operations_total{operation="insert", table="telemetry_samples"} 45000
history_logger_db_errors_total{operation="insert", table="telemetry_samples"} 2
```

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

### 8.2. Scheduler отправляет команду полива

```python
# Scheduler через automation-engine отправляет команду полива
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
    "http://history-logger:9300/zones/1/commands",
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
1. Для `POST /commands`, `POST /zones/{zone_id}/commands`, `POST /nodes/{node_uid}/commands` поле `cmd` обязательно.
2. Legacy поле `type` отклоняется с `400`.

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
