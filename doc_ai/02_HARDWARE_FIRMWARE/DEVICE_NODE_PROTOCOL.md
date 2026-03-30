# DEVICE_NODE_PROTOCOL.md
# Полная спецификация протокола узлов ESP32 (2.0)
# Инструкция для ИИ-агентов и разработчиков прошивок

Этот документ описывает стандарты, обязательные правила и архитектуру прошивок узлов ESP32 для гидропонной системы 2.0. 
Цель — обеспечить абсолютную совместимость узлов с Python-сервисом, Laravel, MQTT-топиками и БД.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Основные принципы

Узел ESP32 обязан:

- идентифицировать себя по стандарту 2.0;
- публиковать telemetry, status, command_response;
- принимать команды «command» в одном формате;
- соблюдать топик-структуру;
- иметь устойчивую работу в условиях сетевых потерь;
- поддерживать OTA (опционально, позже);
- работать автономно с локальными тайм‑аутами.

ИИ-агенты **не имеют права менять** format, naming и структуру ключевых сообщений.

---

# 2. Иерархия идентификаторов узлов

Каждый ESP32 получает:

- `gh_uid` (например, `gh-1`)
- `zone_uid` (например, `zn-3`)
- `node_uid` (например, `nd-ph-1`, `nd-ec-2`, `nd-irrig-1`)

Правило:
- `node_uid` = тип + порядковый номер
 Примеры:
 - nd-ph-1 (pH сенсор)
 - nd-ec-1 (EC сенсор)
 - nd-irrig-1 (насосы/клапаны)
 - nd-climate-1 (датчики климата)

---

# 3. MQTT топики (обязательный формат)

```
hydro/{gh}/{zone}/{node}/{channel}/{type}
```

Пример:

```
hydro/gh-1/zn-2/nd-ph-1/ph_sensor/telemetry
```

**Менять формат запрещено.**

---

# 4. Сообщения от узла

## 4.1. Telemetry

**Topic:**
```
hydro/gh/zone/node/channel/telemetry
```

**Payload:**
```json
{
 "metric_type": "PH",
 "value": 6.42,
 "ts": 1737355600
}
```

**Обязательные поля:**
- `metric_type` (string, UPPERCASE) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY`, `CO2`, `LIGHT_INTENSITY`, `WATER_LEVEL`, `FLOW_RATE`, `PUMP_CURRENT` и т.д.
- `value` (float или int) — значение метрики
- `ts` (integer) — timestamp в секундах (после синхронизации времени — Unix timestamp)

**Опциональные поля:**
- `unit` (string) — единица измерения
- `raw` (integer) — сырое значение сенсора
- `stub` (boolean) — флаг симулированного значения
- `stable` (boolean) — флаг стабильности значения

> **Важно:** поля `node_uid` и `channel` не включаются в JSON, так как они уже есть в топике.
> До синхронизации времени (`set_time`) `ts` может отражать uptime-секунды; после синхронизации — Unix time.

Каналы (channel в топике):
- `ph_sensor` → `metric_type: "PH"`
- `ec_sensor` → `metric_type: "EC"`
- `temperature` (или `air_temp_c` в test-node) → `metric_type: "TEMPERATURE"`
- `humidity` (или `air_rh` в test-node) → `metric_type: "HUMIDITY"`
- `co2` → `metric_type: "CO2"`
- `pump_bus_current` → `metric_type: "PUMP_CURRENT"`
- `flow_present` → `metric_type: "FLOW_RATE"`
- `light`/`light_level` → `metric_type: "LIGHT_INTENSITY"`
- и другие

## 4.2. Status (жизненный статус узла)

**Topic:**
```
hydro/gh/zone/node/status
```

**Payload (канонический минимальный профиль):**
```json
{
 "status": "ONLINE",
 "ts": 1737355600
}
```

**Payload (расширенный профиль):**
```json
{
 "status": "ONLINE",
 "online": true,
 "ip": "192.168.1.55",
 "rssi": -58,
 "fw": "v5.2.1",
 "ts": 1737355600
}
```

**Обязательные поля (для прод-готового формата):**
- `status` (string) — человекочитаемый статус (`ONLINE`/`OFFLINE`/`SAFE_MODE` и т.д.)
- `ts` (integer) — UTC timestamp в секундах

**Опционально:**
- `online` (boolean) — бинарный статус (`true`/`false`) для быстрого парсинга
- `ip` (string), `rssi` (number), `fw` (string) — диагностические поля
- `state` (string), `reason` (string) — служебные поля для safe-mode/status events

**Требования:**
- QoS = 1
- Retain = true
- Публикация выполняется сразу после успешного подключения к MQTT брокеру
- Для production-ready профиля рекомендуется периодическая публикация (например, каждые 60 секунд) или по изменению состояния.

**Runtime-совместимость (переходный период):**
- На части real-node пока встречается сокращённый payload без `ts` и/или без `status` (только `online` + диагностика).
- Для production-режима это считается техническим долгом: целевой формат — `status` + `ts` (остальные поля опциональны).
- На отдельных прошивках периодическая `status`-публикация может отсутствовать; тогда источником liveliness остаётся `heartbeat`.

## 4.3. command_response

Узел обязан отвечать на команду Python‑сервиса.

**Topic:**
```
hydro/gh/zone/node/channel/command_response
```

**Payload:**
```json
{
 "cmd_id": "cmd-91ab23",
 "status": "DONE",
 "details": {
  "result": "ok"
 },
 "ts": 1737355600123
}
```

**Обязательные поля:**
- `cmd_id` (string) — идентификатор команды, точно соответствующий `cmd_id` из команды
- `status` (string) — статус выполнения: `ACK`, `DONE`, `ERROR`, `INVALID`, `BUSY`, `NO_EFFECT`
- `ts` (integer) — UTC timestamp в миллисекундах

**Опциональные поля:**
- `details` (object) — структурированные детали выполнения команды
- `error_code` (string) — машинночитаемый код ошибки для `status=ERROR`
- `error_message` (string) — человекочитаемое пояснение для `status=ERROR`
- `message` (string) — краткое top-level сообщение; backend может использовать как fallback для `error_message`

Временной SLA `command_response` зависит от типа команды и runtime (длительность исполнения, очередь, retry).
Для long-running команд рекомендуется схема:
- быстрый `ACK` после приёма;
- terminal статус (`DONE`/`ERROR`/`INVALID`/`BUSY`/`NO_EFFECT`) после завершения.

---

# 5. Сообщения к узлу (команды)

Python-сервис отправляет команды:

**Topic:**
```
hydro/gh/zone/node/channel/command
```

**Payload:**
```json
{
 "cmd_id": "cmd-123abc",
 "cmd": "dose",
 "params": {
  "ml": 0.5
 },
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

Обязательные поля:
- cmd_id — строка UUID/HEX
- cmd — имя команды
- params — JSON-объект (может быть пустым)
- ts — Unix timestamp (секунды)
- sig — HMAC-SHA256 подпись

Узел обязан:

1. принять команду;
2. выполнить её (или отказать корректно);
3. вернуть command_response с тем же cmd_id.

Важно: поддержка конкретной команды зависит от типа ноды и зарегистрированных handler'ов
в прошивке (`node_command_handler_register`). Неизвестные команды должны возвращать
ошибку выполнения, а не игнорироваться silently.

---

# 6. Типы каналов узла

Узел формируется из **каналов** — логических единиц.

## 6.1. SENSOR каналы:

| Канал | Тип значения | Связь с БД |
|----------------|--------------|------------|
| ph_sensor | float | metric=PH |
| ec_sensor | float | metric=EC |
| temperature / air_temp_c | float | TEMPERATURE |
| humidity / air_rh | float | HUMIDITY |
| solution_temp_c | float | TEMPERATURE |
| water_level | float/int | LEVEL |
| light / light_level | float/int | LIGHT |

Сенсоры публикуют telemetry.

## 6.2. ACTUATOR каналы:

| Канал | Тип действия |
|------------------|--------------|
| ph_doser_up / ph_doser_down (alias: pump_base / pump_acid) | дозирование pH-корректора |
| pump_a / pump_b / pump_c / pump_d | внесение удобрений (NPK / Ca / Mg / Micro) |
| pump_irrigation | полив |
| valve_irrigation | клапан |
| fan_air | вентилятор |
| heater / heater_air | подогрев |
| white_light | освещение |
| uv_light | УФ-лампы |

Актуация идёт только через `command`.

## Обязательная отчётность об исполнении команд

Любая команда, пришедшая на узел в топик `.../{channel}/command`, должна быть:

1. Провалидирована (формат JSON, допустимый канал, допустимые параметры).
2. Либо выполнена, либо отклонена с чётким кодом ошибки.
3. Во всех случаях порождает `command_response` с указанием `cmd_id` и статуса
   (`ACK`, `DONE`, `ERROR`, `INVALID`, `BUSY`, `NO_EFFECT`).

Backend никогда не должен “догадываться”, выполнилась ли команда — он всегда сверяет
состояние по `command_response` и дополнительной telemetry.

## Особые правила для насосов и INA209 (один датчик на ноду)

Для насосов (`pump_acid`, `pump_base`, `pump_a`, `pump_b`, `pump_c`, `pump_d`, `pump_in` и др.) протокол
усилён контролем по суммарному току через INA209 по шине I²C. Архитектура ноды:

- у всех насосов общий плюс питания;
- каждый насос включается по минусу через MOSFET, управляемый через оптопару;
- INA209 включён в цепь общего плюса и измеряет суммарный ток всех насосов ноды.

### Алгоритм обработки команды к насосу

1. Команда на включение/дозирование насоса (`set_relay` / `dose` / `run_pump`) обрабатывается так:

   - узел переключает соответствующий MOSFET через оптопару;
   - ждёт небольшую паузу для стабилизации (100–300 ms, параметр `stabilization_delay_ms` в NodeConfig);
   - считывает суммарный ток `bus_current_ma` с INA209;
   - сопоставляет `bus_current_ma` с ожидаемыми порогами из NodeConfig.

2. NodeConfig содержит как минимум:

   - `min_bus_current_on` — минимальный ток, при котором считается, что хотя бы один насос реально включился;
   - опционально: ожидаемые диапазоны тока для сценариев “работает только один насос”.

3. Если `bus_current_ma < min_bus_current_on` (нет тока при ожидаемом включении):

   - узел формирует `command_response` со статусом `ERROR` и `error_code="current_not_detected"`;
   - в `details` может передаваться измеренный ток и пороги;
   - при необходимости публикуется диагностическая telemetry по каналу `pump_bus_current`.

4. Если ток аномально высокий относительно заданных лимитов:

   - узел формирует `command_response` со статусом `ERROR` и `error_code="overcurrent"`;
   - по возможности отключает все насосы на ноде;
   - публикует диагностическую telemetry.

5. Если ток в заданных пределах:

   - узел формирует `command_response` со статусом `ACK`;
   - опционально прикладывает `bus_current_ma` в `details` и публикует telemetry по `pump_bus_current`.

6. При многократных ошибках по току (количество и окно наблюдения задаются в NodeConfig)
   узел переводит насосы или всю ноду в локальный SAFE_MODE, прекращает попытки включения
   и публикует соответствующий статус.


---

# 7. Жизненный цикл узла

1. **Boot** — узел подключается к Wi‑Fi.
2. **MQTT connect**
3. Публикация:
 - `status` (целевой формат: `status` + `ts`)
4. Загрузка локальной конфигурации.
5. Публикация первых telemetry.
6. Работа цикла:
 - сенсоры → telemetry каждые X секунд,
 - статус периодически (обычно около 60 секунд) или по изменению состояния,
 - выполнение команд,
 - command_response.

Если Wi‑Fi/MQTT пропадает, узел переходит в offline/reconnect режим; обязательный offline-buffer telemetry
в текущем production baseline не гарантирован и зависит от конкретной прошивки.

---

# 8. Ошибки и отказоустойчивость

Узел должен поддерживать:

- автоматический reconnect MQTT (esp-mqtt builtin);
- watchdog 5–10 секунд;
- локальные тайм-ауты для команд;
- защиту от двойных команд (idempotency по `cmd_id`, поведение дубликатов зависит от реализации хендлера/кеша).

---

# 9. Минимальные требования к прошивке

### Стэк:
- ESP-IDF (C, production baseline);
- mqtt client;
- json (cJSON);
- wifi reconnect логика.

### Память:
- heap min 80 KB free
- минимизация логирования

### Производительность:
- отправка telemetry не чаще чем 1 раз / 300 мс на канал (рекомендация)
- отправка status 1 раз в минуту

---

# 10. Правила для ИИ-агентов

ИИ-агент **может**:

- добавлять новые каналы (SENSOR/ACTUATOR);
- расширять NodeConfig и `config_report`;
- улучшать алгоритмы обработки команд;
- добавлять OTA-поддержку;
- добавлять калибровку.

ИИ-агент **не может**:

- менять формат MQTT-топиков,
- менять ключи telemetry (`value`, `ts`),
- менять структуру команд (`cmd_id`, `cmd`, `params`, `ts`, `sig`),
- менять command_response,
- менять обязательные каналы (ph_sensor, ec_sensor).

---

# 11. Чек-лист ИИ перед изменением протокола

1. Формат топиков не изменён?
2. Telemetry всё ещё `{value, ts}`?
3. Команда всё ещё `{cmd_id, cmd, params, ts, sig}`?
4. Ответ содержит `cmd_id`?
5. Python и Laravel смогут обработать новый канал/тип?
6. Узел не начнёт отправлять слишком частые сообщения?

---

# Конец файла DEVICE_NODE_PROTOCOL.md
