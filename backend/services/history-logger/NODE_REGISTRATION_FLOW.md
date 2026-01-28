# Процесс автоматической регистрации узлов через History Logger

## Обзор

Все узлы ESP32 регистрируются и обновляются **только через History Logger**. Прямое общение узлов с Laravel API **не используется**.

## Архитектура

```
ESP32 Node
    ↓ MQTT
MQTT Broker (Mosquitto)
    ↓ MQTT Subscribe  
History Logger (Python)
    ↓ HTTP API
Laravel Backend (PHP)
    ↓ WebSocket/HTTP
Frontend (Vue/Inertia)
```

## Полный цикл регистрации узла

### 1️⃣ Узел отправляет node_hello при старте

**ESP32 Firmware:**
```c
// В climate_node_mqtt_connection_cb() при подключении к MQTT
void climate_node_publish_hello(void) {
    // Формирует JSON с hardware_id, node_type, fw_version, capabilities
    mqtt_manager_publish_raw("hydro/node_hello", json_str, 1, 0);
}
```

**MQTT топик:** `hydro/node_hello`

**Payload пример:**
```json
{
  "message_type": "node_hello",
  "hardware_id": "esp32-78e36ddde468",
  "node_type": "climate",
  "fw_version": "v5.2",
  "capabilities": ["temperature", "humidity", "co2"]
}
```

### 2️⃣ History Logger получает node_hello

**Python код:** `handle_node_hello()` в `main.py`

**Действия:**
1. Получает сообщение через MQTT подписку `hydro/node_hello`
2. Парсит JSON
3. Извлекает `hardware_id`, `node_type`, `capabilities`
4. Отправляет POST запрос в Laravel API

**HTTP запрос:**
```
POST http://laravel/api/nodes/register
Authorization: Bearer {PY_INGEST_TOKEN или HISTORY_LOGGER_API_TOKEN}
Content-Type: application/json

{
  "message_type": "node_hello",
  "hardware_id": "esp32-78e36ddde468",
  "node_type": "climate",
  "fw_version": "v5.2",
  "capabilities": ["temperature", "humidity", "co2"]
}
```

**Логи:**
```
[NODE_HELLO] Processing node_hello from hardware_id: esp32-testnode999
HTTP Request: POST http://laravel/api/nodes/register "HTTP/1.1 201 Created"
[NODE_HELLO] Node registered successfully: node_uid=nd-clim-esp32tes-1
```

### 3️⃣ Laravel регистрирует узел

**Controller:** `NodeController::register()`

**Service:** `NodeRegistryService::registerNodeFromHello()`

**Действия:**
1. Проверяет, существует ли узел с таким `hardware_id`
2. Если нет - создаёт новый узел:
   - Генерирует уникальный `uid` (например: `nd-clim-esp32tes`)
   - Устанавливает `lifecycle_state = REGISTERED_BACKEND`
   - Сохраняет `hardware_id`, `type`, `fw_version`, `capabilities`
3. Если да - обновляет существующий узел (fw_version, capabilities и т.д.)

**ВАЖНО:** 🔐 **WiFi и MQTT настройки НЕ обновляются!**

**Логика:**
- Если нода отправила `node_hello`, значит она **уже подключена** к WiFi и MQTT с правильными настройками
- Сервер не публикует NodeConfig, конфиг приходит только через `config_report`

**Состояние узла после регистрации:**
```sql
uid: nd-clim-esp32tes
type: climate
hardware_id: esp32-78e36ddde468
zone_id: NULL
pending_zone_id: NULL
lifecycle_state: REGISTERED_BACKEND
config: NULL  -- Конфиг НЕ создан!
```

### 4️⃣ Привязка узла к зоне (через UI или API)

**Пользователь в UI:**
1. Видит список незарегистрированных узлов (lifecycle_state = REGISTERED_BACKEND)
2. Выбирает узел и зону для привязки
3. Нажимает "Assign to Zone"

**Laravel обновляет узел:**
```sql
UPDATE nodes
SET pending_zone_id = 6
WHERE id = 7;
```

**⚡ Нода отправляет config_report:**

После установки `pending_zone_id` сервер **не публикует** конфиг. При подключении к MQTT нода отправляет `config_report` со своим актуальным NodeConfig.

**MQTT топик:**
- `hydro/{gh_uid}/{zone_uid}/{node_uid}/config_report`

**Пример payload:**
```json
{
  "node_id": "nd-clim-esp32new",
  "version": 1,
  "type": "climate",
  "channels": [
    { "name": "temp_air", "type": "SENSOR", "metric": "TEMPERATURE" }
  ],
  "wifi": { "ssid": "HydroFarm", "password": "***" },
  "mqtt": { "host": "192.168.1.100", "port": 1883 }
}
```

### 5️⃣ History Logger сохраняет config_report

**Python код:** `handle_config_report()` в `mqtt_handlers.py`

**Действия (ДЛЯ REGISTERED_BACKEND узлов с pending_zone_id):**

**Step 1:** Сохраняет `nodes.config` и синхронизирует `node_channels`

**Step 2:** Обновляет `zone_id` из `pending_zone_id` и переводит узел в ASSIGNED_TO_ZONE
```
PATCH http://laravel/api/nodes/{node_id}/service-update
Authorization: Bearer {PY_INGEST_TOKEN}

{
  "zone_id": 6,
  "pending_zone_id": null
}
```

```
POST http://laravel/api/nodes/{node_id}/lifecycle/service-transition
Authorization: Bearer {PY_INGEST_TOKEN}

{
  "target_state": "ASSIGNED_TO_ZONE",
  "reason": "Config report received from node"
}
```

**Логи:**
```
[CONFIG_REPORT] Config stored for node nd-clim-esp3278e
[CONFIG_REPORT] Synced 3 channel(s) for node nd-clim-esp3278e
```

**Итоговое состояние:**
```sql
uid: nd-clim-esp3278e
zone_id: 6
pending_zone_id: NULL
lifecycle_state: ASSIGNED_TO_ZONE
```

### 8️⃣ Узел работает и отправляет данные

**MQTT топики:**
- `hydro/{gh_uid}/{zone_uid}/{node_uid}/temperature/telemetry`
- `hydro/{gh_uid}/{zone_uid}/{node_uid}/humidity/telemetry`
- `hydro/{gh_uid}/{zone_uid}/{node_uid}/heartbeat`

**History Logger обрабатывает:**
- Телеметрию → записывает в `telemetry_samples`
- Heartbeat → обновляет `nodes.last_heartbeat_at`, `uptime_seconds`, `rssi`, `free_heap_bytes`

## Lifecycle States (Состояния жизненного цикла)

| State | Описание | zone_id | Действия |
|-------|----------|---------|----------|
| `REGISTERED_BACKEND` | Узел зарегистрирован, но не привязан к зоне | NULL | Ждёт привязки |
| `ASSIGNED_TO_ZONE` | Узел привязан к зоне и получил конфигурацию | SET | Работает, отправляет данные |
| `ACTIVE` | Узел активен и полностью настроен | SET | Нормальная работа |
| `OFFLINE` | Узел не отвечает | SET | Ждёт reconnect |

## Важные особенности архитектуры

### 🔐 Конфиг всегда firmware-defined

**Ранее:** сервер публиковал конфиг и мог перезаписывать рабочие WiFi/MQTT настройки.

**Сейчас:**
- ✅ Узел отправляет `node_hello`
- ✅ Laravel регистрирует узел без zone_id
- ✅ Сервер **не публикует** NodeConfig
- ✅ Нода использует конфиг из прошивки/NVS и отправляет `config_report`

## Проблемы и решения

### ❌ Проблема: 401 Unauthorized при завершении привязки

**Причина:** 
- History Logger использовал неправильную переменную `laravel_api_token` вместо `history_logger_api_token`
- PATCH маршрут `api/nodes/{node}` был защищён middleware `auth`, который требовал Sanctum аутентификацию

**Решение:**
1. ✅ Создан отдельный маршрут `/api/nodes/{node}/service-update` без auth middleware
2. ✅ Создан отдельный маршрут `/api/nodes/{node}/lifecycle/service-transition` без auth middleware
3. ✅ History Logger обновлён для использования `history_logger_api_token` вместо `laravel_api_token`
4. ✅ NodeController::update добавлена проверка всех токенов: `PY_API_TOKEN`, `PY_INGEST_TOKEN`, `HISTORY_LOGGER_API_TOKEN`

**Файлы изменены:**
- `backend/services/history-logger/main.py` - исправлена переменная токена
- `backend/laravel/routes/api.php` - добавлены service маршруты
- `backend/laravel/app/Http/Controllers/NodeController.php` - улучшена проверка токенов

### ✅ Проверка работоспособности

**Тест 1: Регистрация нового узла**
```bash
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_pub -h localhost \
  -t 'hydro/node_hello' \
  -m '{"message_type":"node_hello","hardware_id":"esp32-test999","node_type":"climate","fw_version":"v5.2","capabilities":["temperature","humidity"]}'
```

**Ожидаемый результат:**
- ✅ History Logger получает сообщение
- ✅ Отправляет POST в Laravel /api/nodes/register
- ✅ Laravel создаёт узел с lifecycle_state = REGISTERED_BACKEND
- ✅ Узел появляется в UI

**Тест 2: Завершение привязки**
```bash
# После привязки узла к зоне через UI, узел отправляет config_report:
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_pub -h localhost \
  -t 'hydro/gh-temp/zn-temp/nd-clim-esp3278e/config_report' \
  -m '{"node_id":"nd-clim-esp3278e","version":1,"channels":[{"name":"temp_air","type":"SENSOR","metric":"TEMPERATURE"}]}'
```

**Ожидаемый результат:**
- ✅ History Logger получает config_report
- ✅ Обновляет zone_id из pending_zone_id (PATCH /service-update)
- ✅ Переводит в ASSIGNED_TO_ZONE (POST /lifecycle/service-transition)
- ✅ Узел полностью настроен

## Переменные окружения

| Переменная | Где используется | Описание |
|------------|------------------|----------|
| `PY_INGEST_TOKEN` | History Logger → Laravel | Токен для регистрации и обновления узлов |
| `HISTORY_LOGGER_API_TOKEN` | Laravel → History Logger | Токен для публикации команд |
| `LARAVEL_API_URL` | History Logger | URL Laravel API (http://laravel) |

## Мониторинг

**History Logger метрики (Prometheus):**
- `node_hello_received_total` - количество полученных node_hello
- `node_hello_errors_total{error_type}` - ошибки при обработке
- `config_report_received_total` - количество config_report
- `config_report_processed_total` - количество успешно сохранённых config_report
- `config_report_error_total{node_uid}` - ошибки обработки config_report

**Endpoint:** http://localhost:9301/metrics

## Текущее состояние системы

**Зарегистрированные узлы:**
```sql
SELECT id, uid, type, zone_id, lifecycle_state 
FROM nodes 
ORDER BY id;
```

| ID | UID | Type | Zone | State |
|----|-----|------|------|-------|
| 1 | nd-ph-001-1 | sensor | 1 | ACTIVE |
| 2 | node-temp | sensor | 6 | REGISTERED_BACKEND |
| 3 | nd-clim-esp32tes | climate | NULL | REGISTERED_BACKEND |
| 4 | nd-clim-esp3278e | climate | 6 | ASSIGNED_TO_ZONE |
| 5 | nd-clim-esp32tes-1 | climate | NULL | REGISTERED_BACKEND |

## Команды для отладки

### Просмотр логов History Logger
```bash
docker compose -f docker-compose.dev.yml logs history-logger -f
```

### Фильтр по событиям
```bash
# Только node_hello
docker compose -f docker-compose.dev.yml logs history-logger | grep NODE_HELLO

# Только config_report
docker compose -f docker-compose.dev.yml logs history-logger | grep CONFIG_REPORT

# Только ошибки
docker compose -f docker-compose.dev.yml logs history-logger | grep ERROR
```

### Мониторинг MQTT топиков
```bash
# Все сообщения
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/#' -v

# Только node_hello
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/node_hello' -v

# Только config_report
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/+/+/+/config_report' -v
```

### Проверка узлов в базе
```bash
docker compose -f docker-compose.dev.yml exec db psql -U hydro -d hydro_dev -c "
SELECT 
    n.id, 
    n.uid, 
    n.type,
    n.hardware_id,
    n.zone_id,
    n.pending_zone_id,
    n.lifecycle_state,
    z.name as zone_name,
    g.name as greenhouse_name
FROM nodes n
LEFT JOIN zones z ON n.zone_id = z.id
LEFT JOIN greenhouses g ON z.greenhouse_id = g.id
ORDER BY n.id;
"
```

## Troubleshooting

### Узел не регистрируется автоматически

**Симптомы:** Узел отправляет телеметрию, но не появляется в UI

**Проверка:**
1. Проверьте логи History Logger: `docker compose logs history-logger | grep NODE_HELLO`
2. Если нет логов node_hello - узел не отправляет сообщение при старте
3. **Решение:** Перезагрузите ESP32, чтобы он отправил node_hello

### Config_report получен, но привязка не завершена

**Симптомы:** Узел в ASSIGNED_TO_ZONE, но zone_id = NULL

**Проверка:**
```bash
docker compose logs history-logger | grep "Failed to update zone_id"
```

**Решение:** Проверьте токены в docker-compose.dev.yml:
```yaml
environment:
  - PY_INGEST_TOKEN=dev-token-12345
  - HISTORY_LOGGER_API_TOKEN=dev-token-12345
```

### Узел отправляет данные, но они не записываются

**Симптомы:** В логах "Zone not found" или "Node not found"

**Причина:** Узел не зарегистрирован в базе или zone/greenhouse не существуют

**Решение:**
1. Убедитесь, что узел отправил node_hello
2. Проверьте, что теплица и зона существуют с правильными uid
3. Перезагрузите узел для повторной отправки node_hello

## Итоги

✅ **Автоматическая регистрация работает!**
- Узел отправляет node_hello → автоматически регистрируется в REGISTERED_BACKEND
- Пользователь привязывает к зоне → узел получает конфиг
- Узел подтверждает → автоматически переходит в ASSIGNED_TO_ZONE
- Узел начинает работу → данные записываются в базу

✅ **Все общение через History Logger**
- ESP32 ↔ MQTT ↔ History Logger ↔ Laravel
- Никаких прямых подключений узлов к Laravel API
- Централизованная обработка всех сообщений
