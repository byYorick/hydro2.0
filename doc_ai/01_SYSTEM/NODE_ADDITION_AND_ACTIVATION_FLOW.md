# Полная цепочка добавления новой ноды и выход в рабочий режим

**Дата:** 2025-01-27


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## Обзор

Документ описывает **полный жизненный цикл** добавления новой ноды ESP32 в систему, от первого включения до выхода в рабочий режим.

---

## Архитектура взаимодействия

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

**Важно:** Все общение с нодами происходит **только через History Logger**. Прямое общение нод с Laravel API **не используется**.

---

## Состояния жизненного цикла ноды

| Состояние | Описание | zone_id | Может принимать телеметрию |
|-----------|----------|---------|---------------------------|
| `MANUFACTURED` | Узел произведён, прошивка записана | NULL | ❌ |
| `UNPROVISIONED` | Нет Wi-Fi/привязки, узел в режиме AP | NULL | ❌ |
| `PROVISIONED_WIFI` | Wi-Fi настроен, но узел ещё не зарегистрирован в backend | NULL | ❌ |
| `REGISTERED_BACKEND` | Узел известен backend (есть запись DeviceNode) | NULL | ✅ |
| `ASSIGNED_TO_ZONE` | Узел привязан к зоне и получил конфигурацию | SET | ✅ |
| `ACTIVE` | Узел активен и полностью настроен | SET | ✅ |
| `DEGRADED` | Узел работает, но с проблемами | SET | ✅ |
| `MAINTENANCE` | Узел переведён в режим обслуживания | SET | ❌ |
| `DECOMMISSIONED` | Узел списан | SET | ❌ |

---

## Полная цепочка добавления ноды

### Этап 1: Первое включение и настройка Wi-Fi (UNPROVISIONED → PROVISIONED_WIFI)

**Файлы прошивки:**
- `firmware/nodes/*/main/*_node_init.c` - инициализация компонентов
- `firmware/common/wifi_manager/` - менеджер Wi-Fi

**Процесс:**

1. **Узел включается** и запускает прошивку
2. **Проверка конфигурации Wi-Fi** в NVS (Non-Volatile Storage)
3. **Если Wi-Fi конфиг отсутствует:**
   - Узел переходит в режим Access Point (AP)
   - Создаётся точка доступа для первоначальной настройки
   - Оператор подключается через Android-приложение или веб-интерфейс
   - Вводит SSID и пароль Wi-Fi сети
   - Конфигурация сохраняется в NVS
   - Узел перезагружается

4. **После перезагрузки:**
   - Узел загружает Wi-Fi конфиг из NVS
   - Подключается к Wi-Fi сети
   - Состояние: `PROVISIONED_WIFI`

**Код инициализации:**
```c
// Пример из climate_node_init.c
err = climate_node_init_step_wifi(&init_ctx, &step_result);
if (err == ESP_ERR_NOT_FOUND) {
    // WiFi не настроен - запускаем setup mode
    ESP_LOGW(TAG, "WiFi config not found, starting setup mode...");
    climate_node_run_setup_mode();
    return ESP_ERR_NOT_FOUND; // setup mode will reboot device
}
```

---

### Этап 2: Подключение к MQTT и отправка node_hello (PROVISIONED_WIFI → REGISTERED_BACKEND)

**Файлы:**
- `firmware/common/mqtt_manager/` - менеджер MQTT
- `backend/services/history-logger/main.py` - обработчик node_hello
- `backend/laravel/app/Services/NodeRegistryService.php` - регистрация ноды

**Процесс:**

1. **Узел подключается к MQTT брокеру**
   - Использует временные настройки MQTT (если есть) или настройки из NVS
   - Подписывается на топики конфигурации

2. **Узел публикует `node_hello` сообщение:**
   - **MQTT топик:** `hydro/node_hello`
   - **Payload:**
   ```json
   {
     "message_type": "node_hello",
     "hardware_id": "esp32-78e36ddde468",
     "node_type": "climate",
     "fw_version": "v5.2",
     "capabilities": ["temperature", "humidity", "co2"]
   }
   ```

3. **History Logger получает сообщение:**
   - Подписан на топик `hydro/node_hello`
   - Функция: `handle_node_hello()` в `main.py`
   - Парсит JSON и извлекает данные

4. **History Logger отправляет запрос в Laravel:**
   - **HTTP запрос:**
   ```
   POST http://laravel/api/nodes/register
   Authorization: Bearer {PY_INGEST_TOKEN}
   Content-Type: application/json
   
   {
     "message_type": "node_hello",
     "hardware_id": "esp32-78e36ddde468",
     "node_type": "climate",
     "fw_version": "v5.2",
     "capabilities": ["temperature", "humidity", "co2"]
   }
   ```

5. **Laravel регистрирует узел:**
   - **Controller:** `NodeController::register()`
   - **Service:** `NodeRegistryService::registerNodeFromHello()`
   - **Действия:**
     - Проверяет, существует ли узел с таким `hardware_id`
     - Если нет - создаёт новый узел:
       - Генерирует уникальный `uid` (например: `nd-clim-esp32tes-1`)
       - Устанавливает `lifecycle_state = REGISTERED_BACKEND`
       - Сохраняет `hardware_id`, `type`, `fw_version`, `capabilities`
     - Если да - обновляет существующий узел (fw_version, capabilities и т.д.)

**Важно:** 
- WiFi и MQTT настройки **НЕ обновляются** при регистрации
- Если нода отправила `node_hello`, значит она **уже подключена** к WiFi и MQTT с правильными настройками
- Публикация конфига с новыми WiFi/MQTT настройками **НЕ происходит**
- Событие `NodeConfigUpdated` **НЕ срабатывает** для новых узлов без zone_id/pending_zone_id

**Состояние узла после регистрации:**
```sql
uid: nd-clim-esp32tes-1
type: climate
hardware_id: esp32-78e36ddde468
zone_id: NULL
pending_zone_id: NULL
lifecycle_state: REGISTERED_BACKEND
config: NULL  -- Конфиг НЕ создан!
```

**Код регистрации:**
```php
// NodeRegistryService.php
$node = new DeviceNode();
$node->uid = $uid;
$node->hardware_id = $hardwareId;
$node->type = $nodeType;
$node->first_seen_at = now();
$node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
$node->save();
```

---

### Этап 3: Привязка узла к зоне через UI (REGISTERED_BACKEND → ожидание config_report)

> Важно: публикация конфигов с сервера отключена. Актуальный поток — нода отправляет `config_report`, сервер сохраняет конфиг и завершает привязку.

**Файлы:**
- `backend/laravel/app/Services/NodeService.php` - логика привязки
- `backend/laravel/app/Models/DeviceNode.php` - модель узла
- `backend/laravel/app/Jobs/PublishNodeConfigJob.php` - публикация конфига
- `backend/laravel/resources/js/Pages/Devices/Add.vue` - UI привязки

**Процесс:**

1. **Пользователь в UI:**
   - Видит список незарегистрированных узлов (`lifecycle_state = REGISTERED_BACKEND`)
   - Выбирает узел и зону для привязки
   - Нажимает "Assign to Zone" или "Привязать"

2. **Frontend отправляет запрос:**
   ```
   PATCH /api/nodes/{node_id}
   {
     "zone_id": 6
   }
   ```

3. **Laravel обрабатывает запрос:**
   - **Service:** `NodeService::update()`
   - **Логика:**
     - Определяет, что это запрос от UI (есть `zone_id`, но нет `pending_zone_id`)
     - Проверяет, что узел в допустимом состоянии (`REGISTERED_BACKEND`, `ASSIGNED_TO_ZONE`, или `ACTIVE`)
     - **КРИТИЧНО:** Устанавливает `pending_zone_id = 6`, `zone_id = NULL`
     - Узел **остаётся** в состоянии `REGISTERED_BACKEND`
     - НЕ переводит сразу в `ASSIGNED_TO_ZONE`!

**Код привязки:**
```php
// NodeService.php
if ($isAssignmentFromUI) {
    // ВСЕГДА сохраняем в pending_zone_id для получения подтверждения от ноды
    $data['pending_zone_id'] = $newZoneId;
    unset($data['zone_id']); // Удаляем zone_id из данных обновления!
    
    // Узел остается в REGISTERED_BACKEND
}
```

4. **Триггер публикации конфига:**
   - При установке `pending_zone_id` срабатывает событие `NodeConfigUpdated` (в `DeviceNode::saved`)
   - **Условие:**
   ```php
   $needsConfigPublish = $node->pending_zone_id && !$node->zone_id;
   
   if (!$skipNewNodeWithoutZone && ($hasChanges || $needsConfigPublish)) {
       event(new NodeConfigUpdated($node));
   }
   ```

5. **Listener запускает Job:**
   ```php
   PublishNodeConfigJob::dispatch($node->id);
   ```

---

### Этап 4: Нода отправляет config_report

**Файлы:**
- `firmware/nodes/common/components/node_utils` - публикация config_report
- `firmware/nodes/common/components/mqtt_manager` - публикация MQTT
- `backend/services/history-logger/mqtt_handlers.py` - обработчик config_report

**Процесс:**

1. **Нода подключается к MQTT** после provisioning или перезагрузки.
2. **Публикует текущий NodeConfig** в `hydro/{gh_uid}/{zone_uid}/{node_uid}/config_report`.
3. **History Logger сохраняет конфиг** и синхронизирует каналы.

**Важно:** конфиг формируется в прошивке и/или хранится в NVS, сервер его не публикует.

---

### Этап 5: Завершение привязки (REGISTERED_BACKEND → ASSIGNED_TO_ZONE)

**Файлы:**
- `backend/services/history-logger/mqtt_handlers.py` - обработчик config_report
- `backend/laravel/app/Http/Controllers/NodeController.php` - API endpoints

**Процесс:**

1. **History Logger получает config_report:**
   - Подписан на топик `hydro/+/+/+/config_report`
   - Функция: `handle_config_report()` в `mqtt_handlers.py`
   - Валидирует payload NodeConfig

2. **History Logger завершает привязку (для REGISTERED_BACKEND узлов с pending_zone_id):**

   **Step 1:** Обновляет `zone_id` из `pending_zone_id`
   ```
   PATCH http://laravel/api/nodes/{node_id}/service-update
   Authorization: Bearer {PY_INGEST_TOKEN}
   
   {
     "zone_id": 6,
     "pending_zone_id": null
   }
   ```

   **Step 2:** Переводит узел в `ASSIGNED_TO_ZONE`
   ```
   POST http://laravel/api/nodes/{node_id}/lifecycle/service-transition
   Authorization: Bearer {PY_INGEST_TOKEN}
   
   {
     "target_state": "ASSIGNED_TO_ZONE",
     "reason": "Config successfully installed and confirmed by node"
   }
   ```

3. **Laravel обрабатывает переход:**
   - **Service:** `NodeLifecycleService::transition()`
   - Проверяет, разрешён ли переход (из `REGISTERED_BACKEND` в `ASSIGNED_TO_ZONE`)
   - Обновляет `lifecycle_state`
   - Сохраняет узел

4. **Очистка retained сообщений:**
   - History Logger очищает retained сообщения на временном топике
   - Очищает retained на основном топике конфига

**Итоговое состояние:**
```sql
uid: nd-clim-esp3278e
zone_id: 6
pending_zone_id: NULL
lifecycle_state: ASSIGNED_TO_ZONE
```

**Код обработки:**
```python
# history-logger/main.py
if lifecycle_state == "REGISTERED_BACKEND" and target_zone_id:
    # Step 1: Обновляем zone_id
    if pending_zone_id and not zone_id:
        await client.patch(
            f"{laravel_url}/api/nodes/{node_id}/service-update",
            json={"zone_id": pending_zone_id, "pending_zone_id": None}
        )
    
    # Step 2: Переводим в ASSIGNED_TO_ZONE
    await client.post(
        f"{laravel_url}/api/nodes/{node_id}/lifecycle/service-transition",
        json={"target_state": "ASSIGNED_TO_ZONE", "reason": "..."}
    )
```

---

### Этап 7: Узел начинает работу и отправляет телеметрию

**Файлы:**
- `firmware/nodes/*/main/*_node_main.c` - основной цикл узла
- `backend/services/history-logger/main.py` - обработка телеметрии

**Процесс:**

1. **Узел работает в нормальном режиме:**
   - Собирает данные с сенсоров
   - Выполняет команды актуаторов
   - Отправляет телеметрию

2. **Узел отправляет телеметрию:**
   - **MQTT топики:**
     - `hydro/{gh_uid}/{zone_uid}/{node_uid}/temperature/telemetry`
     - `hydro/{gh_uid}/{zone_uid}/{node_uid}/humidity/telemetry`
     - `hydro/{gh_uid}/{zone_uid}/{node_uid}/heartbeat`

3. **History Logger обрабатывает:**
   - Телеметрию → записывает в `telemetry_samples`
   - Heartbeat → обновляет `nodes.last_heartbeat_at`, `uptime_seconds`, `rssi`, `free_heap_bytes`, `status='online'`

4. **Узел участвует в зонной логике:**
   - После перехода в `ASSIGNED_TO_ZONE` узел участвует в автоматизации зоны
   - Получает команды от automation-engine
   - Выполняет рецепты

---

### Этап 8: Переход в ACTIVE (опционально)

**Важно:** `ASSIGNED_TO_ZONE` уже является **рабочим состоянием**. Узел может работать и отправлять телеметрию в этом состоянии.

Переход в `ACTIVE` может происходить:
- **Вручную** через UI (оператор переводит узел в активное состояние)
- **Автоматически** (если реализована логика автоматического перехода)

**Разрешенные переходы:**
```php
// NodeLifecycleService.php
NodeLifecycleState::ASSIGNED_TO_ZONE->value => [
    NodeLifecycleState::ACTIVE->value,
    NodeLifecycleState::MAINTENANCE->value,
    NodeLifecycleState::DECOMMISSIONED->value,
]
```

**Код перехода:**
```php
// NodeLifecycleService.php
public function transitionToActive(DeviceNode $node, ?string $reason = null): bool
{
    return $this->transition($node, NodeLifecycleState::ACTIVE, $reason);
}
```

При переходе в `ACTIVE`:
- `lifecycle_state = ACTIVE`
- `status = 'online'`

---

## Диаграмма состояний

```
MANUFACTURED
    ↓
UNPROVISIONED (Wi-Fi не настроен)
    ↓ (настройка Wi-Fi через AP)
PROVISIONED_WIFI (Wi-Fi настроен)
    ↓ (подключение к MQTT, отправка node_hello)
REGISTERED_BACKEND (зарегистрирован в backend)
    ↓ (привязка к зоне через UI)
    ↓ (публикация config_report)
ASSIGNED_TO_ZONE (привязан к зоне, работает)
    ↓ (опционально, вручную или автоматически)
ACTIVE (активен, полностью настроен)
    ↓ (при проблемах)
DEGRADED (работает с проблемами)
    ↓ (при обслуживании)
MAINTENANCE (обслуживание)
```

---

## Ключевые моменты

### 1. Двухэтапная привязка к зоне

Привязка происходит в два этапа:
1. **Установка `pending_zone_id`** - пользователь привязывает узел
2. **Подтверждение от узла** - узел отправляет `config_report`
3. **Завершение привязки** - `zone_id` устанавливается, `pending_zone_id` очищается, переход в `ASSIGNED_TO_ZONE`

Это гарантирует, что узел **реально получил и применил конфиг** перед началом работы.

### 2. Защита от перезаписи рабочих настроек

- Сервер не публикует конфиг на ноды
- Узел использует конфиг из прошивки/NVS
- Это предотвращает перезапись рабочих WiFi/MQTT настроек
- После успешной привязки временный топик очищается

### 4. Все общение через History Logger

- ESP32 ↔ MQTT ↔ History Logger ↔ Laravel
- Никаких прямых подключений узлов к Laravel API
- Централизованная обработка всех сообщений

---

## Логирование и отладка

### Просмотр логов History Logger
```bash
docker compose -f docker-compose.dev.yml logs history-logger -f
```

### Фильтр по событиям
```bash
# Только node_hello
docker compose logs history-logger | grep NODE_HELLO

# Только config_report
docker compose logs history-logger | grep CONFIG_REPORT

# Только ошибки
docker compose logs history-logger | grep ERROR
```

### Мониторинг MQTT топиков
```bash
# Все сообщения
docker compose exec mqtt mosquitto_sub -h localhost -t 'hydro/#' -v

# Только node_hello
docker compose exec mqtt mosquitto_sub -h localhost -t 'hydro/node_hello' -v

# Только config_report
docker compose exec mqtt mosquitto_sub -h localhost -t 'hydro/+/+/+/config_report' -v
```

### Проверка узлов в базе
```bash
docker compose exec db psql -U hydro -d hydro_dev -c "
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

---

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

---

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

✅ **Безопасная привязка**
- Двухэтапная привязка гарантирует получение конфига
- Защита от перезаписи рабочих настроек
- Временный топик для узлов без uid
