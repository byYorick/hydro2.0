# Тесты протокола для production IRR node

Набор `firmware/tests` проверяет MQTT-контракт прошивки `storage_irrigation_node`:
форматы `telemetry`, `command_response`, `heartbeat`, `status` и базовый command lifecycle.

## Доступные тесты

### 1. test_node_compatibility.py

Комплексный тест совместимости, проверяющий:
- ✅ Формат телеметрии
- ✅ Формат ответов на команды
- ✅ Формат heartbeat
- ✅ Формат статуса
- ✅ Валидация по JSON схемам

### 2. test_telemetry_format.py

Тест формата телеметрии (может использоваться отдельно).

### 3. test_command_response_format.py

Тест формата ответов на команды (может использоваться отдельно).

### 4. test_command_ack_terminal_timing.py

HIL/интеграционный тест таймингов command lifecycle:
- ✅ Проверяет сценарий `ACK -> terminal`, если нода отвечает асинхронно
- ✅ Проверяет immediate terminal path, если `ACK` не используется
- ✅ Валидирует допустимое окно задержки terminal-ответа

### 5. test_storage_state_contract.py

HIL/интеграционный тест контракта `storage_state/state`:
- ✅ Проверяет `DONE`-ответ на сервисный канал `storage_state`
- ✅ Проверяет `details.snapshot`, `details.state` и freshness-поля
- ✅ Проверяет, что в snapshot присутствуют все канонические IRR-ключи

### 6. test_pump_main_interlock.py

HIL/интеграционный тест блокировки `pump_main`:
- ✅ Отправляет `pump_main/set_relay {state:true}` без открытого flow path
- ✅ Ожидает terminal `ERROR`
- ✅ Проверяет `error_code=pump_interlock_blocked`

### 7. test_actuator_cooldown.py

HIL/интеграционный тест enforcement `min_off_ms`:
- ✅ Выполняет последовательность `ON -> OFF -> ON` на actuator-канале
- ✅ Проверяет отказ повторного включения до истечения cooldown
- ✅ Проверяет `error_code=cooldown_active` и `cooldown_remaining_ms`

### 8. test_actuator_max_duration.py

HIL/интеграционный тест latched `set_relay`:
- ✅ Включает actuator через `set_relay {state:true}`
- ✅ Держит канал включённым дольше старого `max_duration_ms`
- ✅ Проверяет через `storage_state/state`, что канал всё ещё включён до явного `OFF`

### 9. test_storage_events.py

HIL/интеграционный тест `storage_state/event`:
- ✅ Поднимает нужный fill-path для `clean_fill_completed` или `solution_fill_completed`
- ✅ Ждёт событие на `storage_state/event`
- ✅ Проверяет `event_code`, `snapshot`, `state` и факт сработавшего `*_max`

### 10. test_stage_timeout_guard.py

HIL/интеграционный тест stage-level timeout guard:
- ✅ Поднимает flow-path для `solution_fill` или `prepare_recirculation`
- ✅ Отправляет `pump_main/set_relay {state:true, timeout_ms, stage}`
- ✅ Проверяет lifecycle `ACK -> ERROR(stage_timeout) -> storage_state/event`
- ✅ Проверяет через `storage_state/state`, что flow-path локально остановлен нодой

## Граница ответственности набора firmware/tests

Текущий набор `firmware/tests/*` проверяет совместимость протокола и таймингов command lifecycle
(`telemetry/command_response/heartbeat/status`, а также `ACK -> terminal`), но не валидирует
бизнес-процессы 2-бакового цикла (`startup/clean_fill/solution_fill/prepare_recirculation`).

Проверка согласованности автоматики с реальной IRR-нодой остаётся в e2e/HIL-наборах
верхних слоёв. Этот каталог не подменяет интеграционные сценарии automation-engine.

## Быстрый старт

```bash
# Запуск всех тестов совместимости
./firmware/tests/run_compatibility_tests.sh

# С параметрами
MQTT_HOST=192.168.1.100 MQTT_PORT=1883 \
./firmware/tests/run_compatibility_tests.sh

# С включённым HIL тайминг-тестом command lifecycle
RUN_HIL_TIMING=1 HIL_CHANNEL=valve_clean_fill HIL_PARAMS_JSON='{"state":true}' \
./firmware/tests/run_compatibility_tests.sh

# С HIL-проверками service state, interlock, cooldown, latched set_relay и storage events
RUN_HIL_STORAGE_STATE=1 RUN_HIL_INTERLOCK=1 RUN_HIL_COOLDOWN=1 RUN_HIL_MAX_DURATION=1 RUN_HIL_STORAGE_EVENTS=1 \
./firmware/tests/run_compatibility_tests.sh

# С HIL-проверкой stage timeout guard
RUN_HIL_STAGE_TIMEOUT=1 HIL_STAGE=solution_fill HIL_STAGE_TIMEOUT_MS=5000 \
./firmware/tests/run_compatibility_tests.sh

# Прямой запуск Python скрипта
python3 firmware/tests/test_node_compatibility.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1 \
    --telemetry-channel level_clean_min \
    --command-channel valve_clean_fill \
    --command set_relay \
    --command-params-json '{"state":true}'
```

## Требования

- Python 3.6+
- paho-mqtt: `pip install paho-mqtt`
- jsonschema: `pip install jsonschema`

Скрипт `run_compatibility_tests.sh` автоматически проверяет и устанавливает зависимости.

## Что проверяется

### Телеметрия
- ✅ Наличие обязательных полей: `metric_type`, `value`, `ts`
- ✅ Отсутствие запрещенных полей: `node_id`, `channel`
- ✅ `metric_type` в UPPERCASE
- ✅ `ts` в секундах (int)
- ✅ Соответствие JSON схеме

### Ответы на команды
- ✅ Наличие обязательных полей: `cmd_id`, `status`, `ts`
- ✅ `cmd_id` точно соответствует команде
- ✅ `ts` в миллисекундах
- ✅ Валидный статус: ACK, DONE, ERROR, и т.д.
- ✅ Соответствие JSON схеме

### Heartbeat
- ✅ Наличие обязательных полей: `uptime`, `free_heap`
- ✅ Отсутствие поля `ts`
- ✅ `uptime` в секундах
- ✅ Соответствие JSON схеме

### Статус
- ✅ Наличие обязательных полей: `status`, `ts`
- ✅ `status` в формате ONLINE/OFFLINE
- ✅ `ts` в секундах (int)
- ✅ Соответствие JSON схеме

## Использование отдельных тестов

### HIL тест ACK -> terminal таймингов

```bash
python3 firmware/tests/test_command_ack_terminal_timing.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1 \
    --channel valve_clean_fill \
    --cmd set_relay \
    --params-json '{"state":true}' \
    --expect-ack \
    --min-terminal-delay-ms 50 \
    --max-terminal-delay-ms 2000
```

Опциональные параметры:
- `--ack-timeout-sec`
- `--terminal-timeout-sec`
- `--min-terminal-delay-ms`
- `--max-terminal-delay-ms`

### HIL тест `storage_state/state`

```bash
python3 firmware/tests/test_storage_state_contract.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1
```

### HIL тест `pump_main` interlock

```bash
python3 firmware/tests/test_pump_main_interlock.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1
```

### HIL тест cooldown `set_relay`

```bash
python3 firmware/tests/test_actuator_cooldown.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1 \
    --channel valve_clean_fill
```

### HIL тест latched `set_relay`

```bash
python3 firmware/tests/test_actuator_max_duration.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1 \
    --channel valve_solution_supply
```

### HIL тест `storage_state/event`

```bash
python3 firmware/tests/test_storage_events.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1 \
    --event-code clean_fill_completed
```

### HIL тест stage timeout guard

```bash
python3 firmware/tests/test_stage_timeout_guard.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-irrig-1 \
    --stage solution_fill \
    --timeout-ms 5000
```

Примечание:
- для green-прохода этого теста соответствующий `level_*_max` датчик должен физически сработать во время активного fill-path;
- если бак не заполнен и датчик не переключился, тест завершится timeout'ом как корректной индикацией отсутствия события.

### Тест формата телеметрии

```bash
# Проверка файла
python3 firmware/tests/test_telemetry_format.py sample_telemetry.json

# Проверка через stdin (например, из MQTT)
mosquitto_sub -t 'hydro/+/+/+/+/telemetry' | python3 firmware/tests/test_telemetry_format.py -
```

### Тест формата ответов на команды

```bash
# Проверка файла
python3 firmware/tests/test_command_response_format.py sample_response.json

# Проверка через stdin
mosquitto_sub -t 'hydro/+/+/+/+/command_response' | python3 firmware/tests/test_command_response_format.py -
```

## Примеры валидных сообщений

### Телеметрия

```json
{
  "metric_type": "LEVEL_SWITCH",
  "value": 1,
  "ts": 1704067200
}
```

### Ответ на команду

```json
{
  "cmd_id": "cmd-12345",
  "status": "DONE",
  "details": {
    "result": "ok"
  },
  "ts": 1704067200123
}
```

`details` передается объектом с деталями выполнения:

```json
{
  "cmd_id": "cmd-12346",
  "status": "DONE",
  "details": {
    "channel": "valve_clean_fill",
    "state": true
  },
  "ts": 1704067201123
}
```

### Heartbeat

```json
{
  "uptime": 3600,
  "free_heap": 200000,
  "rssi": -65
}
```

### Статус

```json
{
  "status": "ONLINE",
  "ts": 1704067200
}
```

## Пример вывода

```
============================================================
ТЕСТИРОВАНИЕ PRODUCTION IRR NODE
============================================================

✅ Подключено к MQTT брокеру
  Подписка: hydro/gh-test-1/zn-test-1/nd-irrig-1/+/telemetry
  ...

📨 Получено: telemetry
   Топик: hydro/gh-test-1/zn-test-1/nd-irrig-1/level_clean_min/telemetry
   Payload: {
     "metric_type": "LEVEL_SWITCH",
     "value": 1,
     "ts": 1704067200
   }

============================================================
РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ
============================================================

✅ status_format: Формат статуса корректен
✅ telemetry_format: Формат телеметрии корректен
✅ command_response_format: Формат ответа на команду корректен
✅ heartbeat_format: Формат heartbeat корректен

============================================================
Успешно: 4
Ошибок: 0
============================================================
```

## Интеграция в CI

```yaml
# Пример для GitHub Actions
- name: Test IRR firmware protocol
  run: |
    # Запуск MQTT брокера
    docker run -d -p 1884:1883 eclipse-mosquitto
    
    # Запуск тестов
    ./firmware/tests/run_compatibility_tests.sh
```

---

**Версия:** 1.0
