# Чек-лист совместимости прошивок с эталоном node-sim

Этот чек-лист предназначен для разработчиков прошивок и помогает убедиться, что прошивка соответствует эталонному протоколу node-sim.

## Быстрая проверка

Перед отправкой прошивки на тестирование убедитесь, что выполнены все пункты этого чек-листа.

## 1. Топики MQTT

### 1.1 Формат топиков

- [ ] Телеметрия: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/telemetry`
- [ ] Ошибки: `hydro/{gh_uid}/{zone_uid}/{node_uid}/error`
- [ ] Статус: `hydro/{gh_uid}/{zone_uid}/{node_uid}/status`
- [ ] Heartbeat: `hydro/{gh_uid}/{zone_uid}/{node_uid}/heartbeat`
- [ ] Команды: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command`
- [ ] Ответы: `hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command_response`

### 1.2 Инициализация идентификаторов

- [ ] `gh_uid` читается из `config_storage_get_gh_uid()`
- [ ] `zone_uid` читается из `config_storage_get_zone_uid()`
- [ ] `node_uid` читается из `config_storage_get_node_id()`
- [ ] Поддержка preconfig режима (gh-temp/zn-temp) для временных топиков

### 1.3 MQTT параметры

- [ ] Телеметрия: QoS = 1, Retain = false
- [ ] Ошибки: QoS = 1, Retain = false
- [ ] Статус: QoS = 1, Retain = true
- [ ] Heartbeat: QoS = 1, Retain = false
- [ ] Команды: подписка с QoS = 1
- [ ] Ответы: QoS = 1, Retain = false

## 2. Телеметрия

### 2.1 Формат JSON

**Обязательные поля:**
- [ ] `metric_type` (string, lowercase)
- [ ] `value` (number)
- [ ] `ts` (integer, секунды UTC)

**Запрещенные поля:**
- [ ] НЕТ поля `node_id` в payload
- [ ] НЕТ поля `channel` в payload (уже есть в топике)

**Опциональные поля (можно оставить):**
- [ ] `unit` (string)
- [ ] `raw` (integer)
- [ ] `stub` (boolean)
- [ ] `stable` (boolean)

### 2.2 Типы метрик

- [ ] `metric_type` в lowercase (не "PH", а "ph")
- [ ] Маппинг каналов → metric_type корректен:
  - [ ] `ph_sensor` → `"ph"`
  - [ ] `ec_sensor` → `"ec"`
  - [ ] `air_temp_c` → `"air_temp_c"`
  - [ ] `air_rh` → `"air_rh"`
  - [ ] `co2_ppm` → `"co2_ppm"`
  - [ ] `ina209` → `"ina209_ma"`
  - [ ] `flow_present` → `"flow_present"`

### 2.3 Временные метки

- [ ] `ts` в секундах UTC (Unix timestamp)
- [ ] Тип `ts`: integer (не double/float)
- [ ] Допустимый drift: ±5 минут от текущего времени
- [ ] Stale данные (>5 минут) помечаются как критично

### 2.4 Пример правильного формата

```json
{
  "metric_type": "ph",
  "value": 6.5,
  "ts": 1704067200
}
```

## 3. Ошибки

### 3.1 Формат JSON

**Обязательные поля:**
- [ ] `level` (string: "ERROR" | "WARNING" | "INFO")
- [ ] `component` (string)
- [ ] `error_code` (string, формат: `infra_*` или `biz_*`)
- [ ] `message` (string)

**Опциональные поля:**
- [ ] `details` (object)
- [ ] `ts` (integer, миллисекунды UTC)

### 3.2 Маппинг severity → level

- [ ] critical/high → "ERROR"
- [ ] medium → "WARNING"
- [ ] low → "INFO"

### 3.3 Пример правильного формата

```json
{
  "level": "ERROR",
  "component": "ph_node",
  "error_code": "infra_overcurrent",
  "message": "Current exceeded threshold",
  "details": {
    "current_ma": 550.0,
    "threshold_ma": 500.0
  },
  "ts": 1704067200123
}
```

## 4. Команды

### 4.1 Подписка на команды

- [ ] Подписка на топики команд для всех каналов
- [ ] QoS = 1 для подписки
- [ ] Обработка команд в правильном формате

### 4.2 Парсинг команды

**Обязательные поля:**
- [ ] `cmd_id` (string)
- [ ] `cmd` (string)
- [ ] `params` (object)

**Опциональные поля:**
- [ ] `exec_time_ms` (integer)

### 4.3 Поддерживаемые команды

- [ ] `set_relay_state` / `set_relay`
- [ ] `run` / `run_pump`
- [ ] `stop` / `stop_pump`
- [ ] `set_pwm`
- [ ] `hil_set_sensor`
- [ ] `hil_raise_error`
- [ ] `hil_clear_error`
- [ ] `hil_set_flow`
- [ ] `hil_set_current`
- [ ] `hil_request_telemetry`

## 5. Ответы на команды

### 5.1 Формат JSON

**Обязательные поля:**
- [ ] `cmd_id` (string, точно echo из команды)
- [ ] `status` (string: "ACK" | "DONE" | "ERROR" | "INVALID" | "BUSY" | "NO_EFFECT")
- [ ] `ts` (integer, миллисекунды UTC)

**Опциональные поля:**
- [ ] `details` (string)

### 5.2 Статусы команд

- [ ] `ACK` - отправляется сразу при принятии команды
- [ ] `DONE` - финальный статус успешного выполнения
- [ ] `ERROR` - ошибка выполнения
- [ ] `INVALID` - невалидная команда/параметры
- [ ] `BUSY` - устройство занято
- [ ] `NO_EFFECT` - команда не оказала эффекта

### 5.3 Пример правильного формата

```json
{
  "cmd_id": "cmd-12345",
  "status": "DONE",
  "details": "OK",
  "ts": 1704067200123
}
```

## 6. Статус

### 6.1 Формат JSON

**Обязательные поля:**
- [ ] `status` (string: "ONLINE" | "OFFLINE")
- [ ] `ts` (integer, секунды UTC)

### 6.2 Публикация

- [ ] Публикация при старте узла
- [ ] Периодическая публикация (интервал ~60 сек)
- [ ] QoS = 1, Retain = true

### 6.3 Пример правильного формата

```json
{
  "status": "ONLINE",
  "ts": 1704067200
}
```

## 7. Heartbeat

### 7.1 Формат JSON

**Обязательные поля:**
- [ ] `uptime` (integer, секунды)
- [ ] `free_heap` (integer, байты)

**Опциональные поля:**
- [ ] `rssi` (integer, -100 до 0)

### 7.2 Публикация

- [ ] Периодическая публикация (интервал ~15-30 сек)
- [ ] QoS = 1, Retain = false

### 7.3 Пример правильного формата

```json
{
  "uptime": 3600,
  "free_heap": 200000,
  "rssi": -65
}
```

## 8. Тестирование

### 8.1 Локальное тестирование

- [ ] Запуск прошивки с локальным MQTT брокером
- [ ] Проверка публикации телеметрии
- [ ] Проверка ответов на команды
- [ ] Проверка публикации ошибок (если применимо)

### 8.2 Валидация JSON

- [ ] Использование JSON схем для валидации
- [ ] Все сообщения проходят валидацию схемы
- [ ] Нет лишних полей в сообщениях

### 8.3 Совместимость с node-sim

- [ ] Прошивка может быть заменена на node-sim без изменения backend
- [ ] Форматы сообщений идентичны эталону

## 9. Типичные ошибки

### ❌ Неправильно

```json
// Телеметрия с лишними полями
{
  "node_id": "nd-ph-esp32una",  // ❌ ЛИШНЕЕ
  "channel": "ph_sensor",        // ❌ ЛИШНЕЕ
  "metric_type": "PH",           // ❌ ВЕРХНИЙ РЕГИСТР
  "value": 6.5,
  "ts": 1704067200.0             // ❌ DOUBLE вместо INT
}
```

### ✅ Правильно

```json
{
  "metric_type": "ph",
  "value": 6.5,
  "ts": 1704067200
}
```

## 10. Полезные ссылки

- [План синхронизации](../FIRMWARE_NODE_SIM_SYNC_PLAN.md)
- [JSON схемы](../schemas/)
- [Эталонный код node-sim](../../tests/node_sim/)
- [E2E тесты](../../tests/e2e/scenarios/)

## 11. Контрольный список перед коммитом

Перед коммитом изменений в прошивку:

- [ ] Все пункты чек-листа выполнены
- [ ] Код компилируется без ошибок
- [ ] Локальное тестирование пройдено
- [ ] JSON валидация проходит
- [ ] Документация обновлена (если нужно)

---

**Версия:** 1.0  
**Дата:** 2024-01-XX

