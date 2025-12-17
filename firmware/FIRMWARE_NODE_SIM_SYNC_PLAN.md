# План синхронизации прошивок с эталоном node-sim

**ВАЖНО:** Эталонная документация находится в `doc_ai/`.  
Эталонный протокол MQTT описан в `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` и `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`.

## Цель

Синхронизировать все типы прошивок (ph, ec, climate, pump, relay, light) с эталонным протоколом node-sim, который успешно проходит E2E тесты. Это обеспечит совместимость прошивок с backend и гарантирует корректную работу всей системы.

## Этап 1: Фиксация эталонного протокола node-sim

### 1.1 Спецификация топиков

**Формат топиков:**
- Телеметрия: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry`
- Ошибки: `hydro/{gh_uid}/{zone_uid}/{node_uid}/error`
- Статус: `hydro/{gh_uid}/{zone_uid}/{node_uid}/status`
- Heartbeat: `hydro/{gh_uid}/{zone_uid}/{node_uid}/heartbeat`
- Команды: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command`
- Ответы на команды: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command_response`

**Временные топики (preconfig режим):**
- `hydro/gh-temp/zn-temp/{hardware_id}/{channel}/telemetry`
- `hydro/gh-temp/zn-temp/{hardware_id}/error`
- `hydro/gh-temp/zn-temp/{hardware_id}/status`
- `hydro/gh-temp/zn-temp/{hardware_id}/heartbeat`
- `hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command`
- `hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command_response`

### 1.2 Формат сообщений телеметрии

**Эталон (node-sim):**
```json
{
  "metric_type": "ph",           // обязательное, lowercase (ph, ec, air_temp_c, air_rh, co2_ppm, ina209_ma, flow_present)
  "value": 6.5,                  // обязательное, число (float)
  "ts": 1234567890               // обязательное, UTC timestamp в секундах (int)
}
```

**Требования:**
- `metric_type` должен соответствовать каналу (ph_sensor → "ph", ec_sensor → "ec", air_temp_c → "air_temp_c")
- `ts` в секундах UTC (Unix timestamp), тип int
- QoS = 1, Retain = false
- Допустимый drift ts: ±5 минут от текущего времени
- Stale данные (>5 минут) помечаются как критично

**Маппинг каналов → metric_type:**
- `ph_sensor` → `"ph"`
- `ec_sensor` → `"ec"`
- `air_temp_c` → `"air_temp_c"`
- `air_rh` → `"air_rh"`
- `co2_ppm` → `"co2_ppm"`
- `ina209` → `"ina209_ma"`
- `flow_present` → `"flow_present"`

### 1.3 Формат сообщений ошибок

**Эталон (node-sim):**
```json
{
  "level": "ERROR",              // обязательное: "ERROR" | "WARNING" | "INFO"
  "component": "node-sim",       // обязательное, источник ошибки
  "error_code": "infra_overcurrent",  // обязательное, код ошибки
  "message": "Current exceeded threshold",  // обязательное, описание
  "details": {                   // опциональное, дополнительные данные
    "current_ma": 550.0,
    "threshold_ma": 500.0,
    "actuator": "pump_acid"
  },
  "ts": 1234567890123            // опциональное, UTC timestamp в миллисекундах (int64)
}
```

**Требования:**
- QoS = 1, Retain = false
- `level` маппится из severity: critical/high → "ERROR", medium → "WARNING", low → "INFO"
- `ts` в миллисекундах UTC (если указан)

**Типовые error_code:**
- `infra_overcurrent` - перегрузка по току
- `infra_sensor_stuck_i2c` - застрявший I2C сенсор
- `infra_mqtt_reconnect` - переподключение MQTT
- `biz_no_flow` - отсутствие потока
- `biz_temp_out_of_range` - температура вне диапазона

### 1.4 Формат команд

**Входящая команда:**
```json
{
  "cmd_id": "cmd-12345",         // обязательное, уникальный ID команды
  "cmd": "set_relay_state",      // обязательное, имя команды
  "params": {                     // обязательное, параметры команды
    "state": true,
    "channel": "pump_acid"
  },
  "exec_time_ms": 100            // опциональное, ожидаемое время выполнения в мс
}
```

**Поддерживаемые команды:**
- `set_relay_state` / `set_relay` - установка состояния реле
- `run` / `run_pump` - запуск насоса
- `stop` / `stop_pump` - остановка насоса
- `set_pwm` - установка PWM значения (0-255)
- `hil_set_sensor` - HIL инжект телеметрии (для тестирования)
- `hil_raise_error` - HIL инжект ошибки
- `hil_clear_error` - HIL очистка ошибки
- `hil_set_flow` - HIL установка потока
- `hil_set_current` - HIL установка тока
- `hil_request_telemetry` - HIL запрос телеметрии on-demand

### 1.5 Формат ответов на команды

**Эталон (node-sim):**
```json
{
  "cmd_id": "cmd-12345",         // обязательное, echo из команды
  "status": "DONE",              // обязательное: "ACK" | "DONE" | "ERROR" | "INVALID" | "BUSY" | "NO_EFFECT"
  "details": "OK",               // опциональное, детали выполнения
  "ts": 1234567890123            // обязательное, UTC timestamp в миллисекундах (int64)
}
```

**Требования:**
- QoS = 1, Retain = false
- `cmd_id` должен точно соответствовать входящей команде
- `status`:
  - `ACK` - команда принята к выполнению (отправляется сразу)
  - `DONE` - команда выполнена успешно (финальный статус)
  - `ERROR` - ошибка выполнения
  - `INVALID` - невалидная команда/параметры
  - `BUSY` - устройство занято
  - `NO_EFFECT` - команда не оказала эффекта (например, насос уже остановлен)

### 1.6 Формат статуса и heartbeat

**Status (эталон):**
```json
{
  "status": "ONLINE",            // обязательное: "ONLINE" | "OFFLINE"
  "ts": 1234567890               // обязательное, UTC timestamp в секундах (int)
}
```

**Heartbeat (эталон):**
```json
{
  "uptime": 3600,                // обязательное, uptime в секундах (int)
  "free_heap": 200000,           // обязательное, свободная память в байтах (int)
  "rssi": -65                    // опциональное, RSSI WiFi (int)
}
```

**Требования:**
- Status: QoS = 1, Retain = true
- Heartbeat: QoS = 1, Retain = false
- Status публикуется при старте и периодически (интервал ~60 сек)
- Heartbeat публикуется периодически (интервал ~15-30 сек)

### 1.7 MQTT параметры

- **QoS:** Все сообщения используют QoS = 1 (кроме heartbeat в некоторых реализациях, но эталон использует QoS=1)
- **Retain:** 
  - Status: retain = true
  - Остальные: retain = false
- **Инициализация:** gh_uid, zone_uid, node_uid читаются из конфигурации (config_storage)

## Этап 2: Аудит и сопоставление прошивок

### 2.1 Текущее состояние прошивок

**Проанализированные типы:**
- ph_node
- ec_node
- climate_node
- pump_node
- relay_node
- light_node

### 2.2 Карта расхождений

#### 2.2.1 Телеметрия

**Текущий формат (firmware):**
```json
{
  "node_id": "nd-ph-esp32una",   // ❌ ЛИШНЕЕ - не должно быть в payload
  "channel": "ph_sensor",         // ❌ ЛИШНЕЕ - уже есть в топике
  "metric_type": "PH",            // ❌ НЕПРАВИЛЬНЫЙ РЕГИСТР - должно быть "ph" (lowercase)
  "value": 6.5,                   // ✅ OK
  "ts": 1234567890.0,             // ⚠️ DOUBLE вместо INT - должно быть int
  "unit": "pH",                   // ⚠️ ОПЦИОНАЛЬНОЕ - не в эталоне, но допустимо
  "raw": 1234,                    // ⚠️ ОПЦИОНАЛЬНОЕ - не в эталоне, но допустимо
  "stub": false,                  // ⚠️ ОПЦИОНАЛЬНОЕ - не в эталоне, но допустимо
  "stable": true                  // ⚠️ ОПЦИОНАЛЬНОЕ - не в эталоне, но допустимо
}
```

**Как должно быть:**
```json
{
  "metric_type": "ph",            // lowercase, соответствует каналу
  "value": 6.5,
  "ts": 1234567890                // int, секунды UTC
}
```

**Проблемы:**
1. ❌ Лишнее поле `node_id` - удалить
2. ❌ Лишнее поле `channel` - удалить (уже есть в топике)
3. ❌ `metric_type` в верхнем регистре - исправить на lowercase
4. ⚠️ `ts` как double - исправить на int
5. ⚠️ Опциональные поля (`unit`, `raw`, `stub`, `stable`) - можно оставить для совместимости, но не обязательны

**Файлы для исправления:**
- `firmware/nodes/common/components/node_framework/node_telemetry_engine.c` (строки 119-142)

#### 2.2.2 Команды и ответы

**Текущий формат ответа (firmware):**
```json
{
  "cmd_id": "cmd-12345",          // ✅ OK
  "status": "DONE",               // ✅ OK
  "details": "OK",                // ✅ OK
  "ts": 1234567890123             // ⚠️ Проверить формат (должен быть int64, миллисекунды)
}
```

**Проблемы:**
1. ⚠️ Нужно проверить, что `ts` в миллисекундах (не секундах)
2. ⚠️ Нужно убедиться, что `cmd_id` точно echo из команды

**Файлы для проверки:**
- `firmware/nodes/common/components/node_framework/node_command_handler.c`

#### 2.2.3 Ошибки

**Текущее состояние:**
- ❓ Нужно проверить, публикуются ли ошибки в правильном формате
- ❓ Есть ли публикация ошибок в прошивках

**Файлы для проверки:**
- Поиск по `mqtt_manager_publish_error` или аналогичным функциям

#### 2.2.4 Статус и Heartbeat

**Текущее состояние:**
- ✅ Heartbeat публикуется через компонент `heartbeat_task`
- ⚠️ Нужно проверить формат payload
- ⚠️ Нужно проверить QoS (должен быть 1 для heartbeat)

**Файлы для проверки:**
- `firmware/nodes/common/components/heartbeat_task/`
- `firmware/nodes/common/components/node_framework/node_state_manager.c`

### 2.3 Чек-лист для каждого типа прошивки

Для каждой прошивки проверить:

- [ ] **Топики:**
  - [ ] Формат топиков соответствует эталону
  - [ ] Используются gh_uid/zone_uid/node_uid из config_storage
  - [ ] Поддержка preconfig режима (gh-temp/zn-temp)

- [ ] **Телеметрия:**
  - [ ] Формат JSON соответствует эталону (только metric_type, value, ts)
  - [ ] metric_type в lowercase
  - [ ] ts в секундах UTC (int)
  - [ ] QoS = 1, Retain = false
  - [ ] Маппинг каналов → metric_type корректен

- [ ] **Ошибки:**
  - [ ] Формат JSON соответствует эталону (level, component, error_code, message, details?, ts?)
  - [ ] ts в миллисекундах UTC (если указан)
  - [ ] QoS = 1, Retain = false

- [ ] **Команды:**
  - [ ] Подписка на правильные топики
  - [ ] Парсинг cmd_id, cmd, params
  - [ ] Поддержка всех команд из эталона

- [ ] **Ответы на команды:**
  - [ ] Формат JSON соответствует эталону (cmd_id, status, details?, ts)
  - [ ] cmd_id точно echo из команды
  - [ ] ts в миллисекундах UTC
  - [ ] QoS = 1, Retain = false

- [ ] **Статус:**
  - [ ] Формат JSON соответствует эталону (status, ts)
  - [ ] ts в секундах UTC (int)
  - [ ] QoS = 1, Retain = true
  - [ ] Публикация при старте и периодически

- [ ] **Heartbeat:**
  - [ ] Формат JSON соответствует эталону (uptime, free_heap, rssi?)
  - [ ] QoS = 1, Retain = false
  - [ ] Публикация периодически

## Этап 3: План внедрения совместимости

### 3.1 Исправления в прошивках

#### 3.1.1 Исправление формата телеметрии

**Файл:** `firmware/nodes/common/components/node_framework/node_telemetry_engine.c`

**Изменения:**
1. Удалить поле `node_id` из JSON (строка 121)
2. Удалить поле `channel` из JSON (строка 122)
3. Исправить `metric_type` на lowercase:
   - Изменить функцию `metric_type_to_string()` (строки 60-70)
   - Или создать новую функцию для маппинга в lowercase формат эталона
4. Исправить `ts` на int (строка 125): `cJSON_AddNumberToObject(telemetry, "ts", (double)item->ts)` → `cJSON_AddNumberToObject(telemetry, "ts", (int)item->ts)`

**Маппинг metric_type:**
```c
static const char *metric_type_to_ethernet_string(metric_type_t type) {
    switch (type) {
        case METRIC_TYPE_PH: return "ph";
        case METRIC_TYPE_EC: return "ec";
        case METRIC_TYPE_TEMPERATURE: return "air_temp_c";  // или по контексту канала
        case METRIC_TYPE_HUMIDITY: return "air_rh";
        case METRIC_TYPE_CURRENT: return "ina209_ma";
        case METRIC_TYPE_PUMP_STATE: return "pump_state";
        default: return "unknown";
    }
}
```

**Проблема:** Нужен контекст канала для правильного маппинга (например, `air_temp_c` vs `solution_temp_c`). Решение: использовать имя канала для определения metric_type.

**Предлагаемое решение:**
- Использовать имя канала напрямую как metric_type (если оно соответствует эталону)
- Или создать маппинг канал → metric_type

#### 3.1.2 Исправление формата ответов на команды

**Файл:** `firmware/nodes/common/components/node_framework/node_command_handler.c`

**Проверить:**
1. Формат `ts` в ответах - должен быть в миллисекундах (int64)
2. `cmd_id` точно echo из команды

#### 3.1.3 Добавление публикации ошибок (если отсутствует)

**Требуется:**
- Функция `mqtt_manager_publish_error()` или аналогичная
- Формат JSON согласно эталону

#### 3.1.4 Исправление heartbeat

**Файл:** `firmware/nodes/common/components/heartbeat_task/`

**Проверить:**
1. Формат payload соответствует эталону
2. QoS = 1 (не 0)

### 3.2 Автотесты прошивок

#### 3.2.1 Структура тестов

Создать директорию `firmware/tests/` с тестами для каждого типа прошивки:

```
firmware/tests/
├── test_telemetry_format.c      # Тест формата телеметрии
├── test_command_response.c       # Тест ответов на команды
├── test_error_format.c           # Тест формата ошибок
├── test_status_heartbeat.c       # Тест статуса и heartbeat
└── test_mqtt_topics.c            # Тест формата топиков
```

#### 3.2.2 Smoke-тесты

Для каждого типа сообщения создать smoke-тест:

1. **Телеметрия:**
   - Публикация телеметрии с валидным JSON
   - Проверка наличия обязательных полей (metric_type, value, ts)
   - Проверка типов данных (metric_type - string, value - number, ts - int)
   - Проверка формата metric_type (lowercase)

2. **Команды:**
   - Отправка команды через локальный MQTT брокер
   - Проверка получения команды прошивкой
   - Проверка формата ответа (cmd_id, status, ts)

3. **Ошибки:**
   - Генерация ошибки
   - Проверка формата публикации (level, component, error_code, message)

4. **Статус и Heartbeat:**
   - Проверка формата при публикации

#### 3.2.3 JSON Schema валидация

Создать JSON схемы для каждого типа сообщения:

```json
// schemas/telemetry.schema.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["metric_type", "value", "ts"],
  "properties": {
    "metric_type": {
      "type": "string",
      "enum": ["ph", "ec", "air_temp_c", "air_rh", "co2_ppm", "ina209_ma", "flow_present"]
    },
    "value": {"type": "number"},
    "ts": {"type": "integer"}
  }
}
```

Использовать библиотеку для валидации JSON схемы в тестах.

### 3.3 Документация протокола

#### 3.3.1 Создать документ `firmware/PROTOCOL_V1.md`

Содержание:
- Спецификация топиков
- Форматы всех типов сообщений
- Требования по времени (ts, drift, stale)
- MQTT параметры (QoS, Retain)
- Примеры сообщений

#### 3.3.2 Чек-лист для разработчиков прошивок

Создать `firmware/FIRMWARE_COMPATIBILITY_CHECKLIST.md`:
- Чек-лист из раздела 2.3
- Примеры кода
- Типичные ошибки и как их избежать

### 3.4 CI проверки

#### 3.4.1 JSON Schema валидация в CI

Добавить в CI pipeline:
1. Запуск автотестов прошивок
2. Валидация JSON схемы для логов симуляции/прошивки
3. Проверка формата топиков

#### 3.4.2 Firmware compatibility job

Создать отдельный CI job `firmware_compatibility`:
1. Запуск node-sim с эталонными публикациями
2. Запуск прошивки (симуляция или реальное устройство)
3. Сравнение форматов сообщений
4. Проверка совместимости

### 3.5 Интеграция с E2E тестами

После исправлений:
1. Прогнать E2E тесты (E6x, E2x сценарии)
2. Убедиться, что все тесты проходят
3. Добавить новые E2E тесты для проверки совместимости прошивок

## Этап 4: План выполнения

### 4.1 Приоритеты

1. **Высокий приоритет:**
   - Исправление формата телеметрии (удаление node_id, channel, исправление metric_type, ts)
   - Исправление формата ответов на команды (ts в миллисекундах)
   - Проверка формата heartbeat и status

2. **Средний приоритет:**
   - Добавление публикации ошибок (если отсутствует)
   - Создание автотестов
   - Документация протокола

3. **Низкий приоритет:**
   - CI проверки
   - Расширенные тесты совместимости

### 4.2 Порядок выполнения

1. **Неделя 1: Фиксация эталона**
   - Задокументировать эталонный протокол (этот документ)
   - Создать JSON схемы

2. **Неделя 2: Аудит прошивок**
   - Пройти все типы прошивок
   - Составить детальную карту расхождений
   - Приоритизировать исправления

3. **Неделя 3-4: Исправления**
   - Исправить формат телеметрии
   - Исправить формат ответов на команды
   - Исправить heartbeat/status
   - Добавить публикацию ошибок (если нужно)

4. **Неделя 5: Тестирование**
   - Создать автотесты
   - Прогнать E2E тесты
   - Проверить совместимость

5. **Неделя 6: Документация и CI**
   - Завершить документацию
   - Добавить CI проверки
   - Финальная проверка

## Этап 5: Критерии успеха

### 5.1 Функциональные критерии

- ✅ Все типы прошивок публикуют телеметрию в формате эталона
- ✅ Все прошивки корректно отвечают на команды в формате эталона
- ✅ Все E2E тесты проходят
- ✅ Прошивки могут быть заменены на node-sim без изменения backend кода

### 5.2 Технические критерии

- ✅ JSON схема валидация проходит для всех типов сообщений
- ✅ Автотесты прошивок проходят
- ✅ CI проверки включены и работают
- ✅ Документация протокола актуальна

### 5.3 Метрики

- Количество типов прошивок, прошедших проверку совместимости: 6/6
- Процент E2E тестов, проходящих с прошивками: 100%
- Время выполнения команды от отправки до получения ответа: < 5 сек

## Приложение A: Примеры эталонных сообщений

### A.1 Телеметрия pH

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/ph_sensor/telemetry`

**Payload:**
```json
{
  "metric_type": "ph",
  "value": 6.5,
  "ts": 1704067200
}
```

### A.2 Телеметрия температуры

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/air_temp_c/telemetry`

**Payload:**
```json
{
  "metric_type": "air_temp_c",
  "value": 24.5,
  "ts": 1704067200
}
```

### A.3 Ошибка перегрузки по току

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/error`

**Payload:**
```json
{
  "level": "ERROR",
  "component": "node-sim",
  "error_code": "infra_overcurrent",
  "message": "Current exceeded threshold",
  "details": {
    "current_ma": 550.0,
    "threshold_ma": 500.0,
    "actuator": "pump_acid"
  },
  "ts": 1704067200123
}
```

### A.4 Команда set_relay_state

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/pump_acid/command`

**Payload:**
```json
{
  "cmd_id": "cmd-12345",
  "cmd": "set_relay_state",
  "params": {
    "state": true,
    "channel": "pump_acid"
  },
  "exec_time_ms": 100
}
```

### A.5 Ответ на команду

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/pump_acid/command_response`

**Payload:**
```json
{
  "cmd_id": "cmd-12345",
  "status": "DONE",
  "details": "OK",
  "ts": 1704067200123
}
```

### A.6 Статус

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/status`

**Payload:**
```json
{
  "status": "ONLINE",
  "ts": 1704067200
}
```

### A.7 Heartbeat

**Топик:** `hydro/gh-test-1/zn-test-1/nd-ph-esp32una/heartbeat`

**Payload:**
```json
{
  "uptime": 3600,
  "free_heap": 200000,
  "rssi": -65
}
```

## Приложение B: Ссылки на код эталона

- **Топики:** `tests/node_sim/node_sim/topics.py`
- **Телеметрия:** `tests/node_sim/node_sim/telemetry.py`
- **Ошибки:** `tests/node_sim/node_sim/errors.py`
- **Команды:** `tests/node_sim/node_sim/commands.py`
- **Статус:** `tests/node_sim/node_sim/status.py`
- **E2E тесты:** `tests/e2e/scenarios/`

## Приложение C: Контакты и ответственные

- **Архитектор протокола:** [TBD]
- **Разработчик прошивок:** [TBD]
- **QA/Тестирование:** [TBD]

---

**Версия документа:** 1.0  
**Дата создания:** 2024-01-XX  
**Последнее обновление:** 2024-01-XX

