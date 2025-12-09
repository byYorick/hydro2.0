# Баг: config_response не обрабатывается, нода не переходит в ASSIGNED_TO_ZONE

**Дата:** 2025-01-27

---

## Симптомы

1. Нода получает конфиг на временном топике `hydro/gh-temp/zn-temp/esp32-004b1237d568/config`
2. Нода отправляет `config_response` с `status: "ACK"` на правильный топик `hydro/gh-secondary-001/zone-Ka7g5OMXolE7lJA1/nd-node-esp32004/config_response`
3. **НО:** Нода не исчезает из списка новых нод
4. **НО:** Не приходит уведомление на фронт об успешном применении конфига
5. **НО:** Нода не переходит в состояние `ASSIGNED_TO_ZONE`

---

## Анализ проблемы

### Payload от ноды:
```json
{"status":"ACK","ts":4811}
```

**Отсутствуют:**
- `cmd_id` - не указан
- `config_version` - не указан

### Логика валидации в `handle_config_response`:

```python
# Строка 1692-1704
if cmd_id:
    last_cmd_id = node_config.get("last_cmd_id")
    if last_cmd_id and last_cmd_id != cmd_id:
        validation_passed = False
        # ...

if config_version is not None:
    stored_config_version = node_config.get("version")
    if stored_config_version is not None and stored_config_version != config_version:
        validation_passed = False
        # ...
```

**Проблема:** Если `config_version` не указан в payload, но в БД есть версия конфига, валидация должна пройти. Но если `node_config` пустой или не содержит нужных полей, может быть проблема.

### Возможные причины:

1. **`node_config` пустой или не содержит нужных полей**
   - Конфиг не был сохранен в БД при публикации
   - Поле `config` в таблице `nodes` пустое или NULL

2. **Ошибка при запросе к БД**
   - Узел не найден в БД
   - Ошибка при выполнении SQL запроса

3. **Проблема с извлечением `node_uid` из топика**
   - Функция `_extract_node_uid` не может извлечь `node_uid` из топика
   - Топик имеет неправильный формат

4. **Ошибка при обновлении `zone_id`**
   - API запрос к Laravel провалился
   - Токен аутентификации неверный

5. **Ошибка при переходе в `ASSIGNED_TO_ZONE`**
   - API запрос к Laravel провалился
   - Узел уже в другом состоянии

---

## Диагностика

### Шаг 1: Проверить логи History Logger

```bash
docker compose -f backend/docker-compose.dev.yml logs history-logger | grep -i "CONFIG_RESPONSE"
```

**Ожидаемые логи:**
```
[CONFIG_RESPONSE] Received message on topic hydro/gh-secondary-001/zone-Ka7g5OMXolE7lJA1/nd-node-esp32004/config_response
[CONFIG_RESPONSE] Config successfully installed for node nd-node-esp32004
[CONFIG_RESPONSE] Step 1/2: Updating zone_id from pending_zone_id=...
[CONFIG_RESPONSE] Step 1/2 SUCCESS: Node zone_id updated
[CONFIG_RESPONSE] Step 2/2: Transitioning to ASSIGNED_TO_ZONE
[CONFIG_RESPONSE] Node successfully transitioned to ASSIGNED_TO_ZONE
```

**Если логи отсутствуют или показывают ошибки:**
- Проверить, подписан ли History Logger на топик `hydro/+/+/+/config_response`
- Проверить, правильно ли извлекается `node_uid` из топика
- Проверить, найден ли узел в БД

### Шаг 2: Проверить состояние узла в БД

```sql
SELECT 
    id, 
    uid, 
    lifecycle_state, 
    zone_id, 
    pending_zone_id,
    config
FROM nodes 
WHERE uid = 'nd-node-esp32004';
```

**Ожидаемые значения:**
- `lifecycle_state` = `REGISTERED_BACKEND`
- `pending_zone_id` = `<zone_id>` (не NULL)
- `zone_id` = NULL (до обработки config_response)
- `config` = JSON с конфигом (не NULL, не пустой)

### Шаг 3: Проверить MQTT топик

```bash
docker compose -f backend/docker-compose.dev.yml exec mqtt mosquitto_sub -h localhost -t 'hydro/+/+/+/config_response' -v
```

**Ожидаемый результат:**
- Видны сообщения `config_response` от нод
- Топик имеет правильный формат: `hydro/{gh_uid}/{zone_uid}/{node_uid}/config_response`

---

## Исправление

### Проблема 1: Валидация проваливается из-за отсутствия `config_version`

**Файл:** `backend/services/history-logger/main.py:1699-1704`

**Проблема:** Если `config_version` не указан в payload, но в БД есть версия, валидация должна пройти. Но текущая логика может быть слишком строгой.

**Исправление:**

```python
# Проверяем версию конфига если она указана
if config_version is not None:
    stored_config_version = node_config.get("version")
    if stored_config_version is not None and stored_config_version != config_version:
        validation_passed = False
        validation_errors.append(f"config_version mismatch: expected {stored_config_version}, got {config_version}")
```

**Текущая логика корректна** - проверка происходит только если `config_version` указан. Но нужно убедиться, что `node_config` не пустой.

### Проблема 2: `node_config` может быть пустым

**Файл:** `backend/services/history-logger/main.py:1690`

**Проблема:** Если конфиг не был сохранен в БД, `node_config` будет пустым словарем, и валидация может провалиться.

**Исправление:**

Добавить проверку и логирование:
```python
node_config = node.get("config") or {}

# Логируем для диагностики
logger.debug(f"[CONFIG_RESPONSE] Node config: {node_config}, has_version: {'version' in node_config}")

# Если конфиг пустой, это может быть проблемой, но не критично для валидации
if not node_config:
    logger.warning(f"[CONFIG_RESPONSE] Node {node_uid} has empty config in database")
```

### Проблема 3: Улучшить логирование для диагностики

**Файл:** `backend/services/history-logger/main.py:1636`

**Исправление:**

Добавить более детальное логирование:
```python
async def handle_config_response(topic: str, payload: bytes):
    try:
        logger.info(f"[CONFIG_RESPONSE] ===== START processing config_response =====")
        logger.info(f"[CONFIG_RESPONSE] Topic: {topic}, payload length: {len(payload)}")
        
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[CONFIG_RESPONSE] Invalid JSON in config_response from topic {topic}")
            CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()
            return
        
        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[CONFIG_RESPONSE] Could not extract node_uid from topic {topic}")
            logger.warning(f"[CONFIG_RESPONSE] Topic parts: {topic.split('/')}")
            CONFIG_RESPONSE_ERROR.labels(node_uid="unknown").inc()
            return
        
        logger.info(f"[CONFIG_RESPONSE] Extracted node_uid: {node_uid} from topic: {topic}")
        logger.info(f"[CONFIG_RESPONSE] Payload: {data}")
        
        # ... остальной код
```

### Проблема 4: Проверка существования узла в БД

**Файл:** `backend/services/history-logger/main.py:1684-1687`

**Исправление:**

Улучшить логирование при отсутствии узла:
```python
if not node_rows or len(node_rows) == 0:
    logger.warning(
        f"[CONFIG_RESPONSE] Node {node_uid} not found in database, ignoring ACK. "
        f"Topic: {topic}, Payload: {data}"
    )
    CONFIG_RESPONSE_ERROR.labels(node_uid=node_uid).inc()
    return
```

---

## Рекомендуемые изменения

1. **Добавить детальное логирование** на всех этапах обработки `config_response`
2. **Проверить, что конфиг сохраняется в БД** при публикации
3. **Улучшить обработку ошибок** с более информативными сообщениями
4. **Добавить метрики** для отслеживания проблемных случаев

---

## Тестирование

После исправления протестировать:

1. **Отправить config_response от ноды:**
   ```bash
   docker compose exec mqtt mosquitto_pub -h localhost \
     -t 'hydro/gh-secondary-001/zone-Ka7g5OMXolE7lJA1/nd-node-esp32004/config_response' \
     -m '{"status":"ACK","ts":4811}'
   ```

2. **Проверить логи History Logger:**
   ```bash
   docker compose logs history-logger | grep -i "CONFIG_RESPONSE"
   ```

3. **Проверить состояние узла в БД:**
   ```sql
   SELECT lifecycle_state, zone_id, pending_zone_id FROM nodes WHERE uid = 'nd-node-esp32004';
   ```

4. **Проверить уведомление на фронт:**
   - Нода должна исчезнуть из списка новых нод
   - Должно прийти уведомление об успешном применении конфига

---

## Связанные баги

- **БАГ #1**: Хардкод временного топика (может влиять на очистку retained сообщений)
- **БАГ #2**: Дублирование публикации конфига (может влиять на сохранение конфига в БД)

