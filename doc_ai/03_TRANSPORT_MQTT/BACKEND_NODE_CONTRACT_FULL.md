# BACKEND_NODE_CONTRACT_FULL.md
# Полный детальный контракт между Backend и ESP32 узлами (2.0)

Документ формализует ВСЁ взаимодействие между Backend и узлами ESP32:
протоколы, структуры JSON, ответственность сторон, гарантии доставки,
обработку ошибок, синхронизацию состояний и правила безопасности.

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
- построение NodeConfig,
- генерацию команд,
- контроль выполнения команд,
- обработку telemetry,
- генерацию ALERTS/EVENTS.

## 3.2. Узел отвечает за:
- чтение сенсоров,
- исправное выполнение команд,
- соблюдение безопасных таймеров,
- корректную публикацию telemetry,
- сохранение NodeConfig в NVS,
- локальный SAFE MODE.

---

# 4. MQTT топики контракта

```
hydro/{gh}/{zone}/{node}/status
hydro/{gh}/{zone}/{node}/lwt
hydro/{gh}/{zone}/{node}/heartbeat
hydro/{gh}/{zone}/{node}/config
hydro/{gh}/{zone}/{node}/config_response
hydro/{gh}/{zone}/{node}/{channel}/telemetry
hydro/{gh}/{zone}/{node}/{channel}/command
hydro/{gh}/{zone}/{node}/{channel}/command_response
```

---

# 5. NodeConfig Contract

Backend формирует единственный источник конфигурации узла.

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
 }
}
```

## 5.2. Требования
- Узел обязан валидировать весь конфиг.
- При ошибке → config_response(ERROR).
- Версия `version` используется для совместимости.
- Узел обязан сохранять конфиг в NVS.
- Узел обязан перезапускать каналы после применения.

---

# 6. Config Response Contract

## 6.1. Успех
```json
{
 "status": "OK",
 "node_id": "nd-ph-1",
 "applied": true,
 "timestamp": 1710002222
}
```

## 6.2. Ошибка
```json
{
 "status": "ERROR",
 "error": "invalid channel pump_x",
 "timestamp": 1710002222
}
```

---

# 7. Telemetry Contract

## 7.1. Payload
```json
{
 "node_id": "nd-ph-1",
 "channel": "ph_sensor",
 "metric_type": "PH",
 "value": 5.83,
 "raw": 1460,
 "ts": 1710012345
}
```

## 7.2. Требования
- QoS=1
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
- Публикация выполняется **до** подписки на config/command топики
- Поле `ts` содержит Unix timestamp в секундах

**Последовательность при подключении:**
1. Установка LWT при инициализации MQTT клиента
2. Подключение к брокеру
3. **Публикация status с "ONLINE"** ← ОБЯЗАТЕЛЬНО
4. Подписка на config и command топики
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

**Backend обязан:**
- отметить node OFFLINE,
- создать ALERT,
- переключить зоны в WARNING/ALARM.

---

# 9. Heartbeat Contract

## 9.1. Payload
```json
{
 "uptime": 55100,
 "heap": 102300,
 "rssi": -56,
 "ts": 1710012900
}
```

Backend обязан сохранять heartbeat для диагностики.

---

# 10. Command Contract

Backend → Node

## 10.1. Payload
```json
{
 "cmd_id": "cmd-9123",
 "cmd": "run_pump",
 "duration_ms": 2500
}
```

## 10.2. Требования
- Узел обязан:
 - валидировать команду,
 - учитывать safe_limits,
 - выполнить действие,
 - отправить command_response.

---

# 11. Command Response Contract

## 11.1. Успех
```json
{
 "cmd_id": "cmd-9123",
 "status": "ACK",
 "ts": 1710012930
}
```

## 11.2. Ошибка
```json
{
 "cmd_id": "cmd-9123",
 "status": "ERROR",
 "error": "cooldown_active"
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
- подтверждать config_response,
- подтверждать command_response,
- публиковать status/heartbeat,
- хранить version NodeConfig.

## Backend обязан:
- держать NodeConfig как источник истины,
- синхронизировать состояния зон,
- пересылать config при обновлении рецептов/фаз.

---

# 15. Контракт совместимости

- Если backend повышает version → узлы должны уметь игнорировать неизвестные поля.
- Если узлы повышают version → backend валидирует node_type/hw_version.

---

# Конец файла BACKEND_NODE_CONTRACT_FULL.md
