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
- Публикация конфига с новыми WiFi/MQTT настройками **НЕ происходит**
- Событие `NodeConfigUpdated` **НЕ срабатывает** для новых узлов без zone_id/pending_zone_id

**Лог:**
```
DeviceNode: Skipping config publish for new node without zone assignment
{
  "reason": "Node sent node_hello, already has working WiFi/MQTT config"
}
```

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

**⚡ Триггер публикации конфига:**

При установке `pending_zone_id` срабатывает событие `NodeConfigUpdated` (в `DeviceNode::saved`):

```php
// Условие в DeviceNode модели:
$needsConfigPublish = $node->pending_zone_id && !$node->zone_id;

if (!$skipNewNodeWithoutZone && ($hasChanges || $needsConfigPublish)) {
    event(new NodeConfigUpdated($node));
}
```

**Listener запускает Job:**
```php
PublishNodeConfigJob::dispatch($node->id);
```

**Job публикует конфигурацию через History Logger:**
```
POST http://history-logger:9300/nodes/{node_uid}/config
Authorization: Bearer {HISTORY_LOGGER_API_TOKEN}

{
  "node_id": "nd-clim-esp32new",
  "zone_id": 6,
  "greenhouse_uid": "gh-temp",
  "hardware_id": "esp32-newnode123",
  "config": {
    "node_id": "nd-clim-esp32new",
    "version": 1,
    "type": "climate",
    "gh_uid": "gh-temp",
    "zone_uid": "zn-temp",
    "channels": [...],
    "wifi": {
      "ssid": "HydroFarm",
      "password": "..."
    },
    "mqtt": {
      "host": "192.168.1.100",
      "port": 1883,
      "username": "...",
      "password": "..."
    }
  }
}
```

**ВАЖНО:** Теперь конфиг публикуется **ТОЛЬКО** при привязке к зоне (установке pending_zone_id), а не при первой регистрации!

### 5️⃣ History Logger публикует конфиг в MQTT

**Python код:** `POST /nodes/{node_uid}/config` endpoint

**MQTT топики:**
1. `hydro/{gh_uid}/zn-{zone_id}/{node_uid}/config` - основной топик
2. `hydro/{gh_uid}/{zone_uid}/{hardware_id}/config` - временный топик (до получения config_response)

**Логи:**
```
[PUBLISH_CONFIG] Publishing config for node nd-clim-esp3278e, zone_id: 6
[PUBLISH_CONFIG_MQTT] Config published successfully to hydro/gh-temp/zn-6/nd-clim-esp3278e/config
[PUBLISH_CONFIG_MQTT] Config published to temp topic: hydro/gh-temp/zn-temp/esp32-78e36ddde468/config
```

### 6️⃣ ESP32 получает конфигурацию

**Узел подписан на:**
- Основной топик с zone_id (когда знает свой uid)
- Временный топик с zone_uid (при первой настройке)

**Действия узла:**
1. Получает конфигурацию
2. Сохраняет её в NVS (энергонезависимую память)
3. Применяет настройки (Wi-Fi, MQTT, каналы)
4. Отправляет подтверждение

**config_response:**
```json
{
  "status": "ACK",
  "config_version": "1",
  "cmd_id": "..."
}
```

**MQTT топик:** `hydro/{gh_uid}/{zone_uid}/{node_uid}/config_response`

### 7️⃣ History Logger завершает привязку

**Python код:** `handle_config_response()` в `main.py`

**Действия (ДЛЯ REGISTERED_BACKEND узлов с pending_zone_id):**

**Step 1:** Обновляет `zone_id` из `pending_zone_id`
```
PATCH http://laravel/api/nodes/{node_id}/service-update
Authorization: Bearer {PY_INGEST_TOKEN}

{
  "zone_id": 6,
  "pending_zone_id": null
}
```

**Step 2:** Переводит узел в ASSIGNED_TO_ZONE
```
POST http://laravel/api/nodes/{node_id}/lifecycle/service-transition
Authorization: Bearer {PY_INGEST_TOKEN}

{
  "target_state": "ASSIGNED_TO_ZONE",
  "reason": "Config successfully installed and confirmed by node"
}
```

**Логи:**
```
[CONFIG_RESPONSE] Config successfully installed for node nd-clim-esp3278e
[CONFIG_RESPONSE] Step 1/2: Updating zone_id from pending_zone_id=6
[CONFIG_RESPONSE] Step 1/2 SUCCESS: Node zone_id updated
[CONFIG_RESPONSE] Step 2/2: Transitioning to ASSIGNED_TO_ZONE
[CONFIG_RESPONSE] Node successfully transitioned to ASSIGNED_TO_ZONE
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

### 🔐 Не перезаписываем рабочие настройки WiFi/MQTT

**Проблема (было раньше):**
- Узел отправляет `node_hello` (значит уже подключен к WiFi и MQTT)
- Laravel регистрирует узел
- Автоматически публикуется конфиг с **дефолтными** WiFi/MQTT настройками
- Узел получает конфиг и **перезаписывает** свои рабочие настройки
- Узел может потерять подключение!

**Решение (сейчас):**
- ✅ Узел отправляет `node_hello`
- ✅ Laravel регистрирует узел без zone_id
- ✅ Конфиг **НЕ публикуется** автоматически
- ✅ Узел сохраняет свои рабочие WiFi/MQTT настройки
- ✅ Конфиг публикуется **только при привязке к зоне** (установке `pending_zone_id`)

**Логика в коде:**
```php
// DeviceNode::saved event
$skipNewNodeWithoutZone = $node->wasRecentlyCreated 
    && !$node->zone_id 
    && !$node->pending_zone_id;

if (!$skipNewNodeWithoutZone && ($hasChanges || $needsConfigPublish)) {
    event(new NodeConfigUpdated($node));
}
```

**Когда конфиг БУДЕТ опубликован:**
- ✅ При установке `pending_zone_id` (привязка к зоне)
- ✅ При изменении `zone_id`, `type`, `config`, `uid`
- ✅ При обновлении настроек через UI

**Когда конфиг НЕ публикуется:**
- ❌ При первой регистрации через `node_hello` (zone_id и pending_zone_id пустые)
- ❌ При обновлении только метаданных (`fw_version`, `last_heartbeat_at`, и т.д.)

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
# После привязки узла к зоне через UI, узел получает config и отправляет ACK:
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_pub -h localhost \
  -t 'hydro/gh-temp/zn-temp/nd-clim-esp3278e/config_response' \
  -m '{"status":"ACK","config_version":"1"}'
```

**Ожидаемый результат:**
- ✅ History Logger получает config_response
- ✅ Обновляет zone_id из pending_zone_id (PATCH /service-update)
- ✅ Переводит в ASSIGNED_TO_ZONE (POST /lifecycle/service-transition)
- ✅ Узел полностью настроен

## Переменные окружения

| Переменная | Где используется | Описание |
|------------|------------------|----------|
| `PY_INGEST_TOKEN` | History Logger → Laravel | Токен для регистрации и обновления узлов |
| `HISTORY_LOGGER_API_TOKEN` | Laravel → History Logger | Токен для публикации конфигурации |
| `LARAVEL_API_URL` | History Logger | URL Laravel API (http://laravel) |

## Мониторинг

**History Logger метрики (Prometheus):**
- `node_hello_received_total` - количество полученных node_hello
- `node_hello_errors_total{error_type}` - ошибки при обработке
- `config_response_received_total` - количество config_response
- `config_response_success_total{node_uid}` - успешные обработки
- `config_response_processed_total` - количество завершённых привязок

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

# Только config_response  
docker compose -f docker-compose.dev.yml logs history-logger | grep CONFIG_RESPONSE

# Только ошибки
docker compose -f docker-compose.dev.yml logs history-logger | grep ERROR
```

### Мониторинг MQTT топиков
```bash
# Все сообщения
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/#' -v

# Только node_hello
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/node_hello' -v

# Только config_response
docker compose -f docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/+/+/+/config_response' -v
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

### Config_response получен, но привязка не завершена

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

