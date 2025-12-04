# Аудит цепочки MQTT команд

## Проблема
Команды не приходят на ESP32 ноду через MQTT.

## Цепочка передачи команд

### 1. Laravel → mqtt-bridge
**Файл:** `backend/laravel/app/Services/PythonBridgeService.php`
- Отправляет HTTP POST на `{baseUrl}/bridge/zones/{zone_id}/commands`
- Передает: `greenhouse_uid`, `node_uid`, `channel`, `type`, `params`, `cmd_id`
- ✅ Работает корректно

### 2. mqtt-bridge → MQTT Broker
**Файл:** `backend/services/mqtt-bridge/publisher.py`
- Публикует в топик: `hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command`
- `zone_segment = f"zn-{zone_id}"` (по умолчанию, т.к. `MQTT_ZONE_FORMAT=id`)
- Payload: `{"cmd": "...", "cmd_id": "...", "params": {...}}`
- QoS: 1, Retain: false
- ⚠️ **ПРОБЛЕМА:** Не публикует на временный топик для нод с временными идентификаторами

### 3. MQTT Broker → ESP32
**Файл:** `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`
- Подписывается на: `hydro/{gh_uid}/{zone_uid}/{node_uid}/+/command`
- ⚠️ **ПРОБЛЕМА:** Не подписывается на временный топик команд
- ⚠️ **ПРОБЛЕМА:** Если нода использует временные идентификаторы (`gh-temp`, `zn-temp`, `node-temp`), а команда публикуется с реальными идентификаторами, нода не получит команду

## Найденные проблемы

### Проблема 1: Несоответствие формата zone_segment
- **mqtt-bridge публикует:** `hydro/{gh_uid}/zn-{zone_id}/{node_uid}/{channel}/command`
- **ESP32 подписывается:** `hydro/{gh_uid}/{zone_uid}/{node_uid}/+/command`
- Если `zn-{zone_id} != {zone_uid}`, команда не дойдет

### Проблема 2: Отсутствие временного топика для команд
- Для конфига есть временный топик: `hydro/gh-temp/zn-temp/{hardware_id}/config`
- Для команд временного топика нет
- Нода с временными идентификаторами не получит команды

### Проблема 3: Недостаточное логирование
- Нет логирования публикации команд в mqtt-bridge
- Нет логирования подписки на команды в ESP32 (есть только общее логирование)

## Решения (ВЫПОЛНЕНО)

### ✅ Решение 1: Добавить публикацию на временный топик команд
В `backend/services/mqtt-bridge/publisher.py`:
- ✅ Публикует команды также на временный топик: `hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command`
- ✅ Использует `hardware_id` для уникальности (как для конфига)
- ✅ Добавлено логирование публикации команд

### ✅ Решение 2: Добавить подписку на временный топик команд
В `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`:
- ✅ Подписывается на временный топик: `hydro/gh-temp/zn-temp/{hardware_id}/+/command`
- ✅ Использует `hardware_id` для уникальности
- ✅ Fallback на `node_uid`, если MAC не получен

### ✅ Решение 3: Улучшить логирование
- ✅ Добавлено логирование публикации команд в mqtt-bridge
- ✅ Добавлено логирование подписки на команды в ESP32
- ✅ Логирование приема команд в ESP32 уже было

### ✅ Решение 4: Исправить ACL
**Файл:** `backend/services/mqtt-bridge/acl`
- ✅ Добавлено: `topic read hydro/+/+/+/command` для `esp32_node`
- ✅ Добавлено: `topic read hydro/gh-temp/zn-temp/+/+/command` для временных топиков

### ✅ Решение 5: Передача hardware_id через цепочку
- ✅ Добавлено поле `hardware_id` в `CommandRequest` схему
- ✅ Laravel передает `hardware_id` в mqtt-bridge
- ✅ mqtt-bridge передает `hardware_id` в `publish_command`

## Итоговая цепочка

1. **Laravel** → получает `hardware_id` из `DeviceNode` → передает в mqtt-bridge
2. **mqtt-bridge** → публикует на два топика:
   - Основной: `hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command`
   - Временный: `hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command`
3. **ESP32** → подписывается на два топика:
   - Основной: `hydro/{gh_uid}/{zone_uid}/{node_uid}/+/command`
   - Временный: `hydro/gh-temp/zn-temp/{hardware_id}/+/command`
4. **MQTT Broker** → доставляет команды на оба топика
5. **ESP32** → получает команду и вызывает callback

## Проверка
После перепрошивки ноды и перезапуска сервисов команды должны приходить на ноду.

