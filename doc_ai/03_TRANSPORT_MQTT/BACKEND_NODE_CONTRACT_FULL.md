# BACKEND_NODE_CONTRACT_FULL.md
# Полный детальный контракт между Backend и ESP32 узлами (2.0)

Документ формализует ВСЁ взаимодействие между Backend и узлами ESP32:
протоколы, структуры JSON, ответственность сторон, гарантии доставки,
обработку ошибок, синхронизацию состояний и правила безопасности.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Общие принципы контракта

Backend — единственный источник бизнес‑логики и решений. 
Node — исполнитель и источник телеметрии.

Контракт гарантирует:

- предсказуемое, строго определённое API между сторонами,
- совместимость прошивок узлов и backend,
- отсутствие скрытой логики в узлах,
- ясность форматов данных,
- безопасность и fault-tolerance.

---

# 2. Структура взаимодействия

Backend ⇄ MQTT Broker ⇄ ESP32 Nodes

Типы обмена:

1. **Telemetry** (node → backend)
2. **Status / LWT** (node → backend)
3. **Heartbeat** (node → backend)
4. **Command** (backend → node)
5. **Command Response** (node → backend)
6. **NodeConfig** (backend → node)
7. **Config Response** (node → backend)

---

# 3. Ответственность сторон

## 3.1. Backend отвечает за:
- расчёты pH/EC/климата,
- принятие решений,
- определение расписаний,
- хранение NodeConfig, присланного нодой,
- генерацию команд,
- контроль выполнения команд,
- обработку telemetry,
- генерацию ALERTS/EVENTS.

## 3.2. Узел отвечает за:
- чтение сенсоров,
- исправное выполнение команд,
- соблюдение безопасных таймеров,
- формирование NodeConfig в прошивке,
- корректную публикацию telemetry,
- сохранение NodeConfig в NVS,
- локальный SAFE MODE.

---

# 4. MQTT топики контракта

```
hydro/{gh}/{zone}/{node}/status
hydro/{gh}/{zone}/{node}/lwt
hydro/{gh}/{zone}/{node}/heartbeat
hydro/{gh}/{zone}/{node}/error
hydro/{gh}/{zone}/{node}/config_report
hydro/{gh}/{zone}/{node}/{channel}/telemetry
hydro/{gh}/{zone}/{node}/{channel}/command
hydro/{gh}/{zone}/{node}/{channel}/command_response
```

---

# 5. NodeConfig Contract

NodeConfig формируется на стороне ноды (прошивка/NVS) и отправляется на сервер в `config_report`.

## 5.1. Payload

```json
{
 "node_id": "nd-ph-1",
 "version": 3,
 "channels": [
 {
 "name": "ph_sensor",
 "type": "SENSOR",
 "metric": "PH",
 "poll_interval_ms": 3000
 },
 {
 "name": "pump_acid",
 "type": "ACTUATOR",
 "actuator_type": "PUMP",
 "safe_limits": {
 "max_duration_ms": 5000,
 "min_off_ms": 3000
 }
 }
 ],
 "wifi": {
 "ssid": "FarmWiFi",
 "pass": "12345678"
 },
 "mqtt": {
 "host": "192.168.1.50",
 "port": 1883,
 "keepalive": 30
 },
 "node_secret": "unique-secret-key-for-this-node"
}
```

**Примечание:** Поле `node_secret` обязательно для всех узлов.

## 5.2. Требования
- Узел обязан валидировать весь конфиг.
- Версия `version` используется для контроля конфигурации и обновлений.
- Узел обязан сохранять конфиг в NVS.
- Узел обязан перезапускать каналы после применения.
- Узел обязан отправлять `config_report` при подключении.

---

# 6. Config Report Contract

## 6.1. Payload
```json
{
 "node_id": "nd-ph-1",
 "version": 3,
 "channels": [
  {
   "name": "ph_sensor",
   "type": "SENSOR",
   "metric": "PH",
   "poll_interval_ms": 3000
  }
 ],
 "wifi": {
  "ssid": "FarmWiFi",
  "pass": "12345678"
 },
 "mqtt": {
  "host": "192.168.1.50",
  "port": 1883,
  "keepalive": 30
 }
}
```

## 6.2. Обработка на backend

Backend подписывается на топик `hydro/+/+/+/config_report` через сервис `history-logger` и обрабатывает сообщения:

- Сохраняет `nodes.config` и синхронизирует `node_channels`
- Если нода в `REGISTERED_BACKEND` и имеет `zone_id`/`pending_zone_id`, переводит в `ASSIGNED_TO_ZONE`

**Важно:** Переход в `ASSIGNED_TO_ZONE` происходит только после получения `config_report` от ноды. Это обеспечивает надежность привязки и гарантирует, что сервер использует актуальный конфиг.

**Примечание:** Если `config_report` пришёл в temp‑namespace до регистрации узла, History Logger буферизует его на короткое время и обрабатывает сразу после успешной регистрации. Параметры буфера задаются переменными `CONFIG_REPORT_BUFFER_TTL_SEC` и `CONFIG_REPORT_BUFFER_MAX`.

# 7. Telemetry Contract

## 7.1. Payload
```json
{
 "metric_type": "PH",
 "value": 5.83,
 "ts": 1710012345
}
```

**Обязательные поля:**
- `metric_type` (string, UPPERCASE) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY` и т.д.
- `value` (number) — значение метрики
- `ts` (integer) — UTC timestamp в секундах

**Опциональные поля:**
- `unit` (string) — единица измерения
- `raw` (integer) — сырое значение сенсора
- `stub` (boolean) — флаг симулированного значения
- `stable` (boolean) — флаг стабильности значения

> **Важно:** Формат соответствует эталону node-sim. Поля `node_id` и `channel` не включаются в JSON, так как они уже есть в топике.

## 7.2. Требования
- QoS=1
- Retain=false
- Узел обязан публиковать telemetry регулярно.
- Узел обязан фильтровать шумы (медиана/усреднение).
- Backend обязан сохранять sample в TSDB и кэшировать.

---

# 8. Status / LWT Contract

## 8.1. ONLINE

**ОБЯЗАТЕЛЬНО:** Узел **ОБЯЗАН** опубликовать status топик **немедленно** после успешного подключения к MQTT брокеру (событие `MQTT_EVENT_CONNECTED`).

**Топик:**
```
hydro/{gh}/{zone}/{node}/status
```

**Payload:**
```json
{
 "status": "ONLINE",
 "ts": 1710012000
}
```

**Требования:**
- QoS = 1
- Retain = true
- Публикация выполняется **до** подписки на command топики
- Поле `ts` содержит Unix timestamp в секундах

**Последовательность при подключении:**
1. Установка LWT при инициализации MQTT клиента
2. Подключение к брокеру
3. **Публикация status с "ONLINE"** ← ОБЯЗАТЕЛЬНО
4. Подписка на command топики (config — опционально)
5. Вызов connection callback (если зарегистрирован)

**Backend обязан:**
- обновить `nodes.status = 'ONLINE'`
- обновить `nodes.last_seen_at = NOW()`
- обработать статус для мониторинга зон

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (mqtt_manager.c, строки 370-374)

## 8.2. OFFLINE (LWT)

Payload:
```
"offline"
```

**Требования:**
- LWT настраивается при инициализации MQTT клиента
- Брокер автоматически публикует LWT при неожиданном отключении узла
- QoS = 1, Retain = true
- Для node-sim в режиме preconfig допустим temp-namespace:
  `hydro/gh-temp/zn-temp/{node_uid_or_hw}/lwt`

**Backend обязан:**
- отметить node OFFLINE,
- создать ALERT,
- переключить зоны в WARNING/ALARM.

---

# 9. Heartbeat Contract

## 9.1. Payload
```json
{
 "uptime": 3600,
 "free_heap": 102300,
 "rssi": -56
}
```

**Обязательные поля:**
- `uptime` (integer) — время работы узла в секундах
- `free_heap` (integer) — свободная память в байтах

**Опциональные поля:**
- `rssi` (integer) — сила сигнала Wi-Fi в dBm

> **Важно:** Поле `ts` **не включается** в heartbeat согласно эталону node-sim.

Backend обязан сохранять heartbeat для диагностики.

---

# 10. Command Contract

Backend → Node

## 10.1. Payload
```json
{
 "cmd_id": "cmd-9123",
 "cmd": "run_pump",
 "params": {
   "duration_ms": 2500
 },
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

**Тест сенсора канала:**
- `cmd`: `test_sensor`
- `params`: `{}` (канал определяется из MQTT топика)
**Правило (для всех нод):** команда `test_sensor` обязательна для любых узлов, у которых есть
каналы типа `SENSOR`. Узел выполняет разовое чтение датчика для канала из топика
`.../{channel}/command` и отвечает:
- при успехе: `command_response` содержит `details.value`, `details.unit`, `details.metric_type`
  (доп. поля допустимы);
- при ошибке чтения/инициализации или если канал не является `SENSOR`: `status=ERROR`/`INVALID`
  и `error_code`/`error_message`.

**Перезапуск ноды:**
- `cmd`: `restart`
- `params`: `{}`
**Правило (для всех нод):** узел обязан отправить `command_response` со статусом `DONE`,
после чего выполнить перезагрузку.

## 10.2. Требования
- Узел обязан:
 - валидировать команду (HMAC подпись, timestamp, параметры),
 - учитывать safe_limits,
 - выполнить действие,
 - отправить command_response.

## 10.3. HMAC проверка команд

**Формат подписи:**
```
sig = HMAC_SHA256(node_secret, canonical_json(command_without_sig))
```

`canonical_json` — каноническая JSON-строка команды без `sig`:
- ключи объектов отсортированы лексикографически,
- порядок массивов сохраняется,
- сериализация без пробелов,
- числа форматируются как в cJSON (int если целое, иначе 15/17 значащих),
- строки JSON-экранируются, UTF-8, слэши не экранируются.

**Проверки на узле:**
1. **Timestamp проверка:**
   - `abs(now - ts) < 10 секунд`
   - Если timestamp истек, команда отклоняется с ошибкой `timestamp_expired`

2. **HMAC подпись проверка:**
   - Узел получает `node_secret` из NodeConfig (поле `node_secret`)
   - Вычисляется ожидаемая подпись: `HMAC_SHA256(node_secret, canonical_json(command_without_sig))`
   - Сравнивается с полученной подписью `sig` (константное время)
   - Если подписи не совпадают, команда отклоняется с ошибкой `invalid_signature`

3. **Требования к полям:**
   - `ts` и `sig` обязательны. При отсутствии любого из полей команда отклоняется с ошибкой `invalid_hmac_format`.

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (node_command_handler.c)

---

# 11. Command Response Contract

## 11.1. Успех
```json
{
 "cmd_id": "cmd-9123",
 "status": "ACK",
 "ts": 1710012930123
}
```

## 11.2. Ошибка
```json
{
 "cmd_id": "cmd-9123",
 "status": "ERROR",
 "details": "Pump is in cooldown period",
 "ts": 1710012930123
}
```

**Важно:** Поле `ts` содержит UTC timestamp в **миллисекундах** (не секундах).

## 11.3. Ошибки валидации HMAC

Если команда отклонена из-за невалидной HMAC подписи:
```json
{
 "cmd_id": "cmd-9123",
 "status": "ERROR",
 "details": "Command HMAC signature verification failed",
 "ts": 1710012930123
}
```

Если команда отклонена из-за истекшего timestamp:
```json
{
 "cmd_id": "cmd-9123",
 "status": "ERROR",
 "details": "Command timestamp is outside acceptable range",
 "ts": 1710012930123
}
```

---

# 12. Error Contract

Типы ошибок:

- invalid_json
- invalid_channel
- invalid_command
- cooldown_active
- duration_exceeds_safe_limits
- config_invalid
- wifi_error
- mqtt_error
- sensor_error
- actuator_error

Backend обязан логировать.

---

# 13. Safety Contract

Узел обязан:

- ограничивать max_duration насосов,
- соблюдать min_off_time,
- предотвращать повторные команды,
- безопасно завершать действие при потере MQTT.

Backend обязан:
- учитывать время выполнения команды,
- отслеживать TIMEOUT,
- переводить команду в ERROR при отсутствии ответа.

---

# 14. Synchronization Contract

## Узел обязан:
- публиковать config_report при подключении,
- подтверждать command_response,
- публиковать status/heartbeat,
- хранить version NodeConfig.

## Backend обязан:
- хранить NodeConfig от ноды и использовать его в сервисах,
- синхронизировать состояния зон,
- не пересылать конфиги на ноды.

---

# 15. Контракт совместимости

- Если backend повышает version → узлы должны уметь игнорировать неизвестные поля.
- Если узлы повышают version → backend валидирует node_type/hw_version.
- `node_type` в payload-ах (`node_hello`, registration, config-report metadata) допускает только канонические
  значения: `ph|ec|climate|irrig|light|relay|water_sensor|recirculation|unknown`.
- Legacy-алиасы `node_type` (`pump_node`, `irrigation`, `climate_node`, `lighting_node` и т.п.) не поддерживаются.

---

# Конец файла BACKEND_NODE_CONTRACT_FULL.md
