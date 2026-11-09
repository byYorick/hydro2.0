# COMMAND_VALIDATION_ENGINE.md
# Полная система проверки команд в 2.0
# HMAC • Timestamp • Limits • Safety • Restrictions • Node-level Validation

Документ описывает полную архитектуру проверки команд (Command Validation)
в системе 2.0. Это критический слой безопасности на пути **backend/Python-сервисы → MQTT → ESP32**.

**Дата сверки с кодом:** 2026-11-07 (`command_service.py`, `commands/validation.py`, node-specific handlers).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Основная концепция

Любая команда, отправляемая узлу ESP32, должна пройти три уровня валидации:

```
Laravel (и/или automation-engine) → history-logger → MQTT → ESP32 Firmware
```

Каноническая публикация в MQTT — только через **history-logger** (см. `../04_BACKEND_CORE/HISTORY_LOGGER_API.md`, `../ARCHITECTURE_FLOWS.md`). Каждый уровень выполняет свои проверки.

---

# 2. Формат команды

Команда, отправляемая в MQTT:

```json
{
 "cmd": "dose",
 "params": { "ml": 1.2 },
 "cmd_id": "cmd-abc123",
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

Обязательные поля:

| Поле | Описание |
|------|----------|
| cmd | действие (string) |
| params | аргументы команды (object, обязательное поле, может быть пустым) |
| cmd_id | уникальный ID (string) |
| ts | Unix timestamp в секундах (number, int64) |
| sig | HMAC-SHA256 подпись в hex формате, 64 символа (string) |

**Примечание:** Поля `ts` и `sig` обязательны. При отсутствии любого поля команда отклоняется.

---

# 3. Уровень 1 — Laravel Validation

Laravel проверяет:

1. **Права пользователя**
2. **role permissions** (Sanctum + middleware `role:operator,admin,agronomist,engineer`)
3. **zone_id / node_id корректны** (FK + ZoneAccess policy)
4. **channel принадлежит node** (lookup в `node_channels`)
5. **params валидны** (Form Request — see `app/Http/Requests/`)
6. **нет активных блокировок safety на уровне UI/API** (ZonePolicy)

Централизованного whitelist допустимых `cmd` в Laravel и history-logger нет. `StoreNodeCommandRequest` проверяет форму запроса и наличие `state` для `set_state`/`set_relay`; `commands/validation.py` в HL требует `cmd` и отвергает legacy `type`. HL не гарантирует поддержку произвольного `cmd` прошивкой: конечный набор задаётся регистрациями обработчиков конкретной ноды. Любой код, добавляющий новый `cmd`, должен синхронно расширить backend и firmware.

Laravel НЕ публикует команду напрямую в MQTT. Laravel вызывает `PythonBridgeService::sendZoneCommand(...) / sendNodeCommand(...)` → `POST {history-logger}/zones/{zone_id}/commands` (или `/nodes/{node_uid}/commands` для node-level), и история lifecycle ведётся в таблице `commands` через history-logger.

---

# 4. Уровень 2 — валидация в Python-сервисе (history-logger)

Перед публикацией в MQTT **history-logger** выполняет валидацию sanity caps в `backend/services/history-logger/command_service.py::_validate_command_params`. Это runaway-protection; доменные ограничения задаёт AE3 planner. HL проверяет числовые `ml`/`duration_ms`, если они переданы, и параметры `set_position`. Обязательность и типы остальных параметров нужно проверять по API и обработчику конкретной ноды.

## 4.1. Проверка срока годности команды

```
abs(now - ts) <= 10 секунд
```

`now` и `ts` — Unix timestamp в секундах. Реализация: `command_service.py` (`_MAX_COMMAND_TS_OFFSET_SEC = 10`); firmware: `node_command_handler.c` (`HMAC_TIMESTAMP_TOLERANCE_SEC 10`). HL подставляет текущее время, если caller не передал `ts`; переданную caller-подпись игнорирует и подписывает payload заново серверным секретом ноды.

## 4.2. Sanity caps на параметры (history-logger)

Это safety-runaway пределы. Точные agronomy-границы задаются authority bundle (`zone.correction.resolved_config.controllers.*` + `pump_calibration`) и проверяются AE3 `correction_planner`.

### Команда dose:
```
0 < ml <= _MAX_DOSE_ML_SANITY (500)
```
Доменный cap задаётся `controllers.{ec,ph}.max_dose_ml` в resolved zone correction config. Текущие base defaults `ZoneCorrectionConfigCatalog` — pH **35 ml**, EC **80 ml**; phase overrides и длительность дозы могут ограничить их сильнее. Диапазон `0.05..50 ml` не является общим production-контрактом.

### Команда run_pump:
```
1 <= duration_ms <= _MAX_DURATION_MS_SANITY (300_000)
```
HL ограничивает числовой `duration_ms` пятью минутами (`_MAX_DURATION_MS_SANITY`). AE3 planner для pH/EC dose использует default `pump_calibration.max_dose_ms=60_000` ms (firmware ph/ec node). На `timeout_ms` timed-start IRR (`pump_main/set_relay {state,timeout_ms,stage}`) этот HL cap **не распространяется**: параметры проверяют planner и IRR firmware.

### Команда set_position (roof vent / greenhouse climate):
```
0 <= position_pct <= 100
max_step_pct optional, 0..100
```
Валидация в `history-logger` `POST /commands` (см. `HISTORY_LOGGER_API.md`, `GREENHOUSE_CLIMATE_CONTROL_SPEC.md`).

### Команда set_relay:
```
params.state ∈ {true,false}
params.duration_ms optional (см. §8.6 MQTT_SPEC_FULL.md для diagnostic auto-stop)
params.timeout_ms + params.stage для timed-start IRR (только pump_main, stage ∈ {solution_fill, prepare_recirculation})
```

### Команда set_pwm:

Канонический параметр — `params.duty` в процентах `0..100`. AE3 формирует его, а текущие `climate_node` и `test_node` принимают через общий `node_pwm_decode` (`node_utils/node_pwm_command.h`). Нечисловые, не конечные и выходящие за диапазон значения отклоняются; при одновременных `duty` и `value` приоритет имеет `duty`.

Для совместимости сохранён `params.value`:

- `climate_node`: целая часть `0..100` — проценты; выше `100` — шкала `0..255` с ограничением сверху;
- `test_node`: шкала `0..255` с ограничением границ;
- `light_node` остаётся сенсорной нодой без `set_pwm`.

HL передаёт параметры без преобразования и не проверяет PWM-диапазон. Исправление совместимости находится в прошивках; уже установленные старые бинарники требуют обновления. Host regression проверяет обе шкалы, границы, NaN/Infinity и приоритет OFF.

## 4.3. Проверка состояния зоны

Это AE3-уровень, не history-logger. AE3 `planner` обязан вернуть `PlannerConfigurationError` или fail-closed task если:

- low water level (`level_solution_min=false`)
- stale telemetry (`telemetry_max_age_sec` exceeded)
- EC/pH out of sanity bounds (pH ∉ [0,14], EC ∉ [0,20] mS/cm)
- controller cooldown (`min_interval_sec`)

History-logger такие проверки не делает — он публикует команду как есть, если payload прошёл sanity caps.

## 4.4. Проверка частоты команд

Status: **planned / not enforced by history-logger**. В текущей реализации `min_interval_sec` между дозами pH/EC обеспечивается AE3 `correction_planner.py` через `pid_state.last_dose_at` и `controllers.{ec,ph}.min_interval_sec` из authority bundle.

Текущие base defaults `ZoneCorrectionConfigCatalog` (конфигурируемо per controller/phase): pH — **20 сек**, EC — **25 сек**. Фактическое значение нужно брать из pinned bundle активного цикла. Диапазон `60..120 сек` не является фиксированным runtime-default.

## 4.5. HMAC Sign

Python вычисляет подпись по каноническому JSON команды:

```
sig = HMAC_SHA256(node_secret, canonical_json(command_without_sig))
```

Где `canonical_json`:
- удаляет поле `sig`,
- сортирует ключи объектов лексикографически,
- сохраняет порядок массивов,
- сериализует без пробелов,
- формат чисел как в cJSON (`int` если целое, иначе 15/17 значащих).

---

# 5. Уровень 3 — ESP32 Firmware Validation

Прошивка проверяет:

## 5.1. Timestamp

```
abs(now - ts) <= 10 секунд
```

Где `now` и `ts` — Unix timestamp в секундах.

При провале проверки firmware отвечает `command_response` со **`status=ERROR`**, `error_code=timestamp_expired` (не `INVALID`). См. `node_command_handler.c`, `MQTT_SPEC_FULL.md` §8.2.1.

## 5.2. HMAC-подпись

```
sig == HMAC_SHA256(node_secret, canonical_json(command_without_sig))
```

Где:
- `node_secret` — секрет ноды из NVS; доставка в NodeConfig выполняется через `node_secret_enc`, plaintext в MQTT не публикуется. Production HL требует per-node secret из БД; `NODE_DEFAULT_SECRET` разрешён только вне production и не заменяет настройку секрета на устройстве.
- `canonical_json` — каноническая JSON-строка команды без `sig` (см. выше)
- Подпись в hex формате (64 символа, нижний регистр)
- Сравнение регистронезависимое

При провале проверки firmware отвечает `command_response` со **`status=ERROR`**, `error_code=invalid_signature` (не `INVALID`). См. `node_command_handler.c`, `MQTT_SPEC_FULL.md` §8.2.1.

## 5.3. Параметры

Проверка диапазонов на firmware (`node_command_handler.c` + node-specific validators):

| Команда | Sanity-проверка прошивки | Дополнительно из NodeConfig |
|---------|--------------------------|------------------------------|
| dose | `params.ml > 0`, тип number | `safe_limits.max_duration_ms` per pump channel; нода считает duration из `ml_per_second`, при превышении cap — `details.duration_limited=true` |
| run_pump | `params.duration_ms >= 1`, integer | `safe_limits.max_duration_ms`, `safe_limits.min_off_ms` |
| set_relay | `params.state ∈ {true,false}`; для timed-start IRR ноды поддерживается `duration_ms`/`timeout_ms+stage` | interlock checks для `pump_main` |
| set_pwm | `params.duty` number `0..100` в `climate_node` / `test_node`; legacy `value` имеет разные шкалы (§4.2) | firmware проверяет finite/range; HL не преобразует params |
| calibrate | `params.type ∈ {PH_4, PH_7, PH_10, EC_DRY, EC_84, EC_1413, ...}` (зависит от sensor type) | — |
| test_sensor | `params={}` | — |
| restart, state | `params={}` | — |

## 5.4. Защита двигателя

Если команда пытается запустить насос дольше max_time:

```
stop after auto_cutoff
emit error
```

## 5.5. Защита от конфликтов

Например:

- нельзя выполнить `run` пока насос уже работает 
- нельзя выполнять две команды одновременно на один pump 

## 5.6. Watchdog Recovery

Если команда зависла:

- задача перезагружается 
- команда помечается как error 

---

# 6. Командные статусы (canonical)

ESP32 отвечает `command_response` (см. `MQTT_SPEC_FULL.md` §8). **Каноничные статусы (UPPERCASE):**

- `ACK` — команда принята и будет выполнена;
- `DONE` — команда выполнена успешно (terminal success);
- `ERROR` — команда не выполнена / выполнена с ошибкой; также HMAC/timestamp fail на firmware (`error_code`: `invalid_signature`, `timestamp_expired`);
- `INVALID` — команда невалидна по params / неподдерживаемый канал/`cmd` (не HMAC и не timestamp — те идут как `ERROR`);
- `BUSY` — узел занят, команда не может быть выполнена сейчас;
- `NO_EFFECT` — команда не оказала эффекта (idempotent skip);
- `TIMEOUT` — device-level timeout на стороне ноды.

Статусы `ok`, `error`, `accepted`, `failed` (в нижнем регистре или legacy форме) **запрещены** в канонических `command_response`. `SEND_FAILED` — backend-layer статус, в `command_response` от ноды не используется.

`ts` в `command_response` — Unix timestamp в **миллисекундах** (не секундах, как у telemetry). Это намеренное расхождение для точности измерения latency `ack_received_at - sent_at`.

Пример успешного ответа:

```json
{
  "cmd_id": "cmd-abc",
  "status": "DONE",
  "details": {"duration_ms": 8000},
  "ts": 1737355120123
}
```

Пример ошибки:

```json
{
  "cmd_id": "cmd-abc",
  "status": "ERROR",
  "error_code": "current_not_detected",
  "error_message": "No current on pump_in channel after switching on",
  "details": {"measured_current_ma": 5, "expected_min_current_ma": 80},
  "ts": 1737355120123
}
```

History-logger обновляет таблицу `commands` со следующими переходами `status`:

```
QUEUED → SENT → ACK → DONE
                    → NO_EFFECT
                    → ERROR / INVALID / BUSY / TIMEOUT
              → SEND_FAILED (publish failure без ACK от ноды)
```

Reconcile terminal статуса делается AE3 через polling `recover_waiting_command` (см. `PYTHON_SERVICES_ARCH.md` §3.3); Laravel Scheduler Cockpit получает обновления через `LISTEN ae_command_status`.

---

# 7. Таблица ограничений безопасности

Sanity-runaway пределы и source of truth:

| Контроль | Где enforced | Source of truth |
|----------|--------------|-----------------|
| pH-pump dose min interval | AE3 `correction_planner.py` | `zone.correction.resolved_config.controllers.ph.min_interval_sec` (base default 20s) |
| EC-pump dose min interval | AE3 `correction_planner.py` | `zone.correction.resolved_config.controllers.ec.min_interval_sec` (base default 25s) |
| pH-pump max dose per shot | AE3 + sanity cap HL | `controllers.ph.max_dose_ml` + HL `_MAX_DOSE_ML_SANITY=500` |
| EC-pump max dose per shot | AE3 + sanity cap HL | `controllers.ec.max_dose_ml` + HL `_MAX_DOSE_ML_SANITY=500` |
| pump max duration per command | AE3 planner + HL + firmware NodeConfig | AE3 default `pump_calibration.max_dose_ms=60_000` (firmware ph/ec), HL `_MAX_DURATION_MS_SANITY=300_000`, NodeConfig `safe_limits.max_duration_ms` |
| pump min off interval | firmware NodeConfig | `safe_limits.min_off_ms` |
| irrigation: low water guard | AE3 + IRR-node level switches | `level_solution_min` + `irrigation_solution_min_guard_enabled` |
| no-effect → fail-closed | AE3 `correction_planner` | 3 consecutive no-effect per pid_type → alert + fail-closed window |
| sensor out of bounds (no PID update) | AE3 `base._sensor_value_in_bounds` | pH ∈ [0,14], EC ∈ [0,20] mS/cm |

---

# 8. Анти-спам защита

Status: **planned / not implemented in history-logger**. Спам-защита command-уровня в текущем коде делается косвенно:

- AE3 `SequentialCommandGateway` исполняет команды строго последовательно (`send → await terminal → next`) для одной зоны;
- `min_interval_sec` controller'а блокирует частые дозы;
- partial unique index `ae_tasks_active_zone_unique` гарантирует одну active task на зону;
- `ZoneLease` обеспечивает single-writer.

Явная rate-limit таблица (`max 10 команд/мин/node`, `max 3 команды/10 сек`) в history-logger не реализована; добавлять только при появлении реальной проблемы и через config + metrics.

---

# 9. Командная очередь

Python создаёт очередь:

```
pending → sending → waiting_response → done
```

Dispatcher:

1. отсылает 1 команду
2. ждёт ответ
3. по тайм-ауту → retry (до 3 раз)
4. если нет ответа → error

---

# 10. Ошибки и безопасная остановка

Универсального rollback физического действия нет: уже внесённую дозу pH/EC программно отменить невозможно. Ограничение длительности, auto-stop и E-Stop выполняет прошивка соответствующего канала; AE3 обрабатывает terminal outcome и выбирает дальнейший переход FSM. Ошибка сама по себе не гарантирует возврат каждого клапана в idle или создание отдельного alert. Для IRR действуют `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` и `AE3_RUNTIME_EVENT_CONTRACT.md` из backend-слоя.

---

# 11. Логирование

Каждая команда логируется в events:

```
COMMAND_SENT
COMMAND_ACK
COMMAND_RETRY
COMMAND_TIMEOUT
COMMAND_ERROR
```

---

# 12. Правила для ИИ

ИИ может:

- ужесточить проверки,
- добавить новые командные лимиты,
- улучшить алгоритм retry,
- добавить контекстные проверки (например temp+humidity).

ИИ НЕ может:

- отключить HMAC,
- ослабить timestamp,
- убрать проверки безопасности,
- убрать ограничение частоты команд.

---

# 13. Чек‑лист перед релизом

1. Timestamp проверяется на всех уровнях? 
2. HMAC корректен? 
3. Ограничения команд соблюдаются? 
4. Защита dry-run работает? 
5. Нет двойных команд? 
6. ESP32 валидирует payload? 
7. Python валидирует params? 
8. Laravel валидирует доступ? 
9. Retry работает? 
10. Все статусы команд отображаются в UI? 

---

# Конец файла COMMAND_VALIDATION_ENGINE.md
