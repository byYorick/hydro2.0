# DATAFLOW_FULL.md
# Полный детальный документ потоков данных 2.0 (Data Flows)

Этот документ описывает ВСЕ потоки данных системы 2.0:
telemetry, commands, config, status/LWT, heartbeat, alerts, events,
и то, как Backend, MQTT, узлы ESP32, фронтенд и базы данных
обмениваются информацией в реальном времени.

---

# 1. Общая концепция потоков данных

Система 2.0 состоит из чётких каналов коммуникации:

1. **Telemetry Flow** — вверх (узлы → backend).
2. **Command Flow** — вниз (backend → узлы).
3. **Config Flow** — вниз (backend → узлы).
4. **Status/LWT Flow** — вверх (узлы → backend).
5. **Heartbeat Flow** — вверх (узлы → backend).
6. **Events Flow** — backend → frontend.
7. **Real-time WebSocket Flow** — backend → frontend.

У каждого потока есть строгие правила, форматы JSON, QoS, и конечные точки.

---

# 2. Общая схема потоков данных

```
 ┌───────────────────┐
 │ Frontend │
 │ Web/UI + WS/REST │
 └──────────┬────────┘
 │
 │ Websocket/REST
 ▼
 ┌─────────────────┐
 │ Backend │
 │ Logic + DB/TSDB │
 └───────┬─────────┘
 │
 │ MQTT publish/subscribe
 ▼
 ┌───────────────┐
 │ MQTT Broker │
 └───────┬──────┘
 │ Wi-Fi LAN
 ┌───────────────┼────────────────────────┬─────────────────────────┐
 │ │ │ │
┌───────▼───────┐ ┌───────▼───────┐ ┌───────▼───────┐ ┌───────▼───────┐
│ Node PH │ │ Node EC │ │ Node Climate │ │ Node Irrig │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘
```

---

# 3. TELEMETRY FLOW (узлы → backend)

## 3.1. Назначение
Telemetry — это поток измерений, поступающих от узлов:
pH, EC, t°, RH, LUX, CO₂, уровень, расход и т.п.

## 3.2. Шаги

1. Узел измеряет значение (по расписанию или вручную).
2. Формирует JSON.
3. Публикует MQTT telemetry-топик.
4. MQTT брокер доставляет backend.
5. Backend сохраняет:
 - sample в TSDB,
 - last_value в кэш,
 - возможный Alert.
6. Backend отправляет обновление frontend через WebSocket.

## 3.3. Формат топика
```
hydro/{gh}/{zone}/{node}/{channel}/telemetry
```

## 3.4. Пример JSON
```json
{
 "metric_type": "ph",
 "value": 5.81,
 "ts": 1710023000
}
```

> **Важно:** Формат соответствует эталону node-sim. Поля `node_id` и `channel` не включаются в JSON, так как они уже есть в топике. `metric_type` в lowercase, `ts` в секундах.

## 3.5. QoS = 1 
## Retain = false

---

# 4. COMMAND FLOW (backend → узлы)

## 4.1. Назначение
Backend отправляет команды:
- включить насос,
- открыть клапан,
- установить PWM,
- измерить сейчас,
- откалибровать.

## 4.2. Шаги

1. Backend создаёт Command.
2. Публикует MQTT → узел.
3. Узел исполняет команду.
4. Узел публикует command_response.
5. Backend обновляет статус команды.

## 4.3. Топик команды
```
hydro/{gh}/{zone}/{node}/{channel}/command
```

## 4.4. Пример JSON
```json
{
 "cmd_id": "cmd-88122",
 "cmd": "run_pump",
 "duration_ms": 2500
}
```

## 4.5. Ответ
```json
{
 "cmd_id": "cmd-88122",
 "status": "ACK",
 "ts": 1710023005
}
```

---

# 5. CONFIG FLOW (backend → узел)

## 5.1. Назначение
NodeConfig определяет:
- типы каналов (Sensor/Actuator),
- частоты опроса,
- безопасные лимиты,
- параметры Wi‑Fi/MQTT.

Узел не имеет своей логики — всё определяется этим файлом.

## 5.2. Шаги

1. Backend генерирует NodeConfig.
2. Публикует MQTT config в топик `hydro/{gh}/{zone}/{node}/config`.
3. Узел принимает config.
4. Валидирует.
5. Сохраняет в NVS.
6. Перезапускает каналы.
7. Отправляет config_response в топик `hydro/{gh}/{zone}/{node}/config_response`.
8. **Backend обрабатывает config_response:**
   - При `status: "OK"`: если нода в состоянии `REGISTERED_BACKEND` и имеет `zone_id`, переводит в `ASSIGNED_TO_ZONE`
   - При `status: "ERROR"`: логирует ошибку, нода остается в `REGISTERED_BACKEND`

## 5.3. Топик
```
hydro/{gh}/{zone}/{node}/config
```

## 5.4. Пример payload
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
 ]
}
```

---

# 6. STATUS FLOW (узлы → backend)

## 6.1. Online

**ОБЯЗАТЕЛЬНО:** При успешном подключении к MQTT брокеру (событие `MQTT_EVENT_CONNECTED`) узел **ОБЯЗАН** немедленно опубликовать status топик.

**Топик:**
```
hydro/{gh}/{zone}/{node}/status
```

**Payload:**
```json
{
 "status": "ONLINE",
 "ts": 1710023101
}
```

**Последовательность при подключении:**
1. Установка LWT при инициализации MQTT клиента
2. Подключение к брокеру
3. **Публикация status с "ONLINE"** ← ОБЯЗАТЕЛЬНО (выполняется сразу после `MQTT_EVENT_CONNECTED`)
4. Подписка на config и command топики
5. Вызов connection callback (если зарегистрирован)

**Требования:**
- QoS = 1
- Retain = true
- Публикация выполняется **до** подписки на config/command топики
- Backend обновляет `nodes.status = 'ONLINE'` и `nodes.last_seen_at = NOW()`

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (mqtt_manager.c, строки 370-374)

## 6.2. Offline (LWT)

**Топик:**
```
hydro/{gh}/{zone}/{node}/lwt
```

**Payload:**
```
"offline"
```

**Требования:**
- LWT настраивается при инициализации MQTT клиента
- Брокер автоматически публикует LWT при неожиданном отключении узла
- QoS = 1, Retain = true

**Backend автоматически фиксирует:**
- узел OFFLINE,
- Alert,
- возможный ALARM зоны.

---

# 7. HEARTBEAT FLOW (узлы → backend)

Раз в 15 секунд узел публикует:
```
hydro/{gh}/{zone}/{node}/heartbeat
```

```json
{
 "uptime": 88000,
 "free_heap": 111000,
 "rssi": -55
}
```

---

# 8. EVENTS FLOW (backend → frontend)

Backend публикует в WebSocket:

- любые новые события,
- Alerts,
- ZoneEvents,
- Command updates.

Формат WebSocket события:
```json
{
 "type": "ZONE_EVENT",
 "zone": "zn-3",
 "event": "PH_CORRECTED",
 "details": {
 "delta": -0.2,
 "pump": "pump_acid"
 },
 "ts": 1710023110
}
```

---

# 9. WEBSOCKET FLOW (frontend ←→ backend)

Фронтенд получает real‑time:

- telemetry updates,
- alerts,
- zone status,
- node status,
- command statuses.

Также UI может отправлять:
- действия пользователя (manual irrigation),
- изменения рецептов,
- apply recipe,
- pause/resume зоны.

---

# 10. Механика хранения данных (DB & TSDB Flow)

## Telemetry
- Коротко хранится в Redis (последние значения),
- Долго хранится в TSDB (история для графиков).

## Commands / Events / Alerts
- Сохраняются в основной БД (PostgreSQL/MySQL).

## Zone state
- Основная БД хранит:
 - фазу,
 - статус,
 - активные циклы,
 - применённый рецепт.

---

# 11. Цепочка полного цикла pH коррекции

```
pH_sensor → telemetry
 ↓
 backend анализирует value
 ↓
 ZoneNutrientController решает → нужно корректировать
 ↓
 backend создаёт команду run_pump
 ↓
 mqtt publish → node pump_acid/command
 ↓
 node выполняет → pump ON
 ↓
 node → command_response (ACK)
 ↓
 backend обновляет состояние и пишет Event
 ↓
 frontend получает WS обновление
```

---

# 12. Цепочка полной смены фазы рецепта

1. Пользователь жмёт «Next Phase» 
2. Фронтенд → Backend (REST) 
3. Backend обновляет модель Zone 
4. Backend генерирует новый NodeConfig для всех узлов зоны 
5. MQTT → config 
6. Узлы применяют config 
7. Узлы → config_response 
8. Backend → Events → Фронтенд 

---

# 13. Fail-safe потоки

## Потеря Wi‑Fi
Узел пытается переподключаться в цикле.

## Потеря MQTT
Переподключение + offline → backend знает.

## Потеря Backend
- узлы продолжают безопасно работать (ничего опасного не делают), 
- backend после рестарта догоняет историю.

---

# 14. Диаграмма потоков данных (подробная)

```
[SENSOR]
 │ read
 ▼
[TELEMETRY MANAGER] → telemetry JSON → MQTT → backend → DB → WS → UI

[BACKEND CONTROLLER] → decision → command JSON → MQTT → node → execute → command_response → backend → UI

[BACKEND CONFIG MANAGER] → config JSON → MQTT → node → apply → config_response → backend

[NODE WIFI] → status/connectivity → status/LWT → MQTT → backend → alert

[NODE HEARTBEAT] → heartbeat → MQTT → backend → metrics / UI
```

---

# 15. Будущие расширения потоков

- групповые команды MQTT (multicast),
- ML‑события (AI triggers),
- автоматические фейзы на основе telemetry patterns,
- поток аварий через отдельный MQTT-топик,
- MQTT schema registry.

---

# Конец файла DATAFLOW_FULL.md
