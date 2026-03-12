# Тесты совместимости с эталоном node-sim

Набор тестов для проверки совместимости прошивок с эталонным протоколом node-sim.

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
- ✅ Подтверждает, что приходит `ACK`, затем terminal (`DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT`)
- ✅ Проверяет окно задержки `ACK -> terminal` относительно `sim_delay_ms`
- ✅ Поддерживает форс terminal-статуса через `sim_status`

## Граница ответственности набора firmware/tests

Текущий набор `firmware/tests/*` проверяет совместимость протокола и таймингов command lifecycle
(`telemetry/command_response/heartbeat/status`, а также `ACK -> terminal`), но не валидирует
бизнес-процессы 2-бакового цикла (`startup/clean_fill/solution_fill/prepare_recirculation`).

Проверка согласованности автоматики и `test_node` выполняется в e2e-наборе
`tests/e2e/scenarios/automation_engine/` (актуальный AE2-Lite subset: `E61`, `E64`, `E65`, `E74`).

## Быстрый старт

```bash
# Запуск всех тестов совместимости
./firmware/tests/run_compatibility_tests.sh

# С параметрами
MQTT_HOST=192.168.1.100 MQTT_PORT=1883 \
./firmware/tests/run_compatibility_tests.sh

# С включённым HIL тайминг-тестом ACK -> terminal
RUN_HIL_TIMING=1 HIL_SIM_DELAY_MS=1500 HIL_SIM_STATUS=DONE \
./firmware/tests/run_compatibility_tests.sh

# Прямой запуск Python скрипта
python3 firmware/tests/test_node_compatibility.py \
    --mqtt-host localhost \
    --mqtt-port 1884 \
    --gh-uid gh-test-1 \
    --zone-uid zn-test-1 \
    --node-uid nd-test-001
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
    --node-uid nd-test-001 \
    --channel ph_sensor \
    --cmd set_relay \
    --sim-delay-ms 1200 \
    --sim-status DONE
```

Опциональные параметры допуска:
- `--lower-jitter-ms` (по умолчанию `200`)
- `--upper-jitter-ms` (по умолчанию `1500`)

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
  "metric_type": "PH",
  "value": 6.5,
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
    "virtual": true,
    "channel": "ph_sensor",
    "note": "probe_complete"
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
ТЕСТИРОВАНИЕ СОВМЕСТИМОСТИ С ЭТАЛОНОМ NODE-SIM
============================================================

✅ Подключено к MQTT брокеру
  Подписка: hydro/gh-test-1/zn-test-1/nd-test-001/+/telemetry
  ...

📨 Получено: telemetry
   Топик: hydro/gh-test-1/zn-test-1/nd-test-001/ph_sensor/telemetry
   Payload: {
     "metric_type": "PH",
     "value": 6.5,
     "ts": 1704067200
   }

============================================================
РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ
============================================================

✅ status_format: Формат статуса соответствует эталону
✅ telemetry_format: Формат телеметрии соответствует эталону
✅ command_response_format: Формат ответа на команду соответствует эталону
✅ heartbeat_format: Формат heartbeat соответствует эталону

============================================================
Успешно: 4
Ошибок: 0
============================================================
```

## Интеграция в CI

```yaml
# Пример для GitHub Actions
- name: Test firmware compatibility
  run: |
    # Запуск MQTT брокера
    docker run -d -p 1884:1883 eclipse-mosquitto
    
    # Запуск тестов
    ./firmware/tests/run_compatibility_tests.sh
```

---

**Версия:** 1.0
