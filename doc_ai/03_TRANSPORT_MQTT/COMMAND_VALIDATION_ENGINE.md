# COMMAND_VALIDATION_ENGINE.md
# Полная система проверки команд в 2.0
# HMAC • Timestamp • Limits • Safety • Restrictions • Node-level Validation

Документ описывает полную архитектуру проверки команд (Command Validation)
в системе 2.0. Это критический слой безопасности на пути **backend/Python-сервисы → MQTT → ESP32**.

**Дата обновления:** 2026-05-28 (sync с кодом: реальные bounds, canonical статусы ACK/DONE, intervals из controllers config).

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

Status: **planned / not implemented** — централизованный whitelist допустимых `cmd` значений на стороне Laravel. Сейчас проверка `cmd` делается per-controller (например, `ZoneCommandController`, `NodeCommandController`) или дальше в history-logger (`backend/services/history-logger/commands/command_service.py`). Любой код, добавляющий новый `cmd`, должен синхронно расширить и backend, и firmware.

Laravel НЕ публикует команду напрямую в MQTT. Laravel вызывает `PythonBridgeService::sendCommand(...)` → `POST {history-logger}/zones/{zone_id}/commands` (или `/nodes/{node_uid}/commands` для node-level), и история lifecycle ведётся в таблице `commands` через history-logger.

---

# 4. Уровень 2 — валидация в Python-сервисе (history-logger)

Перед публикацией в MQTT **history-logger** выполняет валидацию sanity caps в `commands/command_service.py`. Это runaway-protection, а не agrobusiness-логика (которая живёт в AE3 planner).

## 4.1. Проверка срока годности команды

```
abs(now - ts) < 10 секунд
```

`now` и `ts` — Unix timestamp в секундах. Реализация: `command_service.py` (`_MAX_TIMESTAMP_SKEW_SEC = 10`); firmware: `node_command_handler.c` (`HMAC_TIMESTAMP_TOLERANCE_SEC 10`).

## 4.2. Sanity caps на параметры (history-logger)

Это safety-runaway пределы. Точные agronomy-границы задаются authority bundle (`zone.correction.resolved_config.controllers.*` + `pump_calibration`) и проверяются AE3 `correction_planner`.

### Команда dose:
```
0 < ml <= _MAX_DOSE_ML_SANITY (500)
```
Реальный production-диапазон: 0.05..50 ml per dose, ограничивается `controllers.{ec,ph}.max_dose_ml` в zone correction config.

### Команда run_pump:
```
1 <= duration_ms <= _MAX_DURATION_MS_SANITY (300_000)
```
Hard cap = 5 минут на одну команду. Совпадает с дефолтом `pump_calibration.max_dose_ms`. Для timed-start IRR (`pump_main/set_relay {state,timeout_ms,stage}`) cap применяется к `timeout_ms`.

### Команда set_position (roof vent / greenhouse climate):
```
0 <= position_pct <= 100
max_step_pct optional, 0..100
```
Валидация в `history-logger` `POST /commands` (см. `HISTORY_LOGGER_API.md`, `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`).

### Команда set_relay:
```
params.state ∈ {true,false}
params.duration_ms optional (см. §8.6 MQTT_SPEC_FULL.md для diagnostic auto-stop)
params.timeout_ms + params.stage для timed-start IRR (только pump_main, stage ∈ {solution_fill, prepare_recirculation})
```

### Команда set_pwm:
```
0 <= value <= 255 (или 0..100% в зависимости от nodeConfig)
```

## 4.3. Проверка состояния зоны

Это AE3-уровень, не history-logger. AE3 `planner` обязан вернуть `PlannerConfigurationError` или fail-closed task если:

- low water level (`level_solution_min=false`)
- stale telemetry (`telemetry_max_age_sec` exceeded)
- EC/pH out of sanity bounds (pH ∉ [0,14], EC ∉ [0,20] mS/cm)
- controller cooldown (`min_interval_sec`)

History-logger такие проверки не делает — он публикует команду как есть, если payload прошёл sanity caps.

## 4.4. Проверка частоты команд

Status: **planned / not enforced by history-logger**. В текущей реализации `min_interval_sec` между дозами pH/EC обеспечивается AE3 `correction_planner.py` через `pid_state.last_dose_at` и `controllers.{ec,ph}.min_interval_sec` из authority bundle.

Типовые production-значения (конфигурируемо per controller):
- pH: 60..120 сек
- EC: 60..120 сек

Старые значения «pH ≥ 20 сек, EC ≥ 10 сек» устарели и не должны использоваться как контракт.

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
abs(now - ts) < 10 секунд
```

Где `now` и `ts` — Unix timestamp в секундах.

## 5.2. HMAC-подпись

```
sig == HMAC_SHA256(node_secret, canonical_json(command_without_sig))
```

Где:
- `node_secret` — секретный ключ из NodeConfig (поле `node_secret`) или дефолтный
- `canonical_json` — каноническая JSON-строка команды без `sig` (см. выше)
- Подпись в hex формате (64 символа, нижний регистр)
- Сравнение регистронезависимое

## 5.3. Параметры

Проверка диапазонов на firmware (`node_command_handler.c` + node-specific validators):

| Команда | Sanity-проверка прошивки | Дополнительно из NodeConfig |
|---------|--------------------------|------------------------------|
| dose | `params.ml > 0`, тип number | `safe_limits.max_duration_ms` per pump channel |
| run_pump | `params.duration_ms >= 1`, integer | `safe_limits.max_duration_ms`, `safe_limits.min_off_ms` |
| set_relay | `params.state ∈ {true,false}`; для timed-start IRR ноды поддерживается `duration_ms`/`timeout_ms+stage` | interlock checks для `pump_main` |
| set_pwm | `params.value` integer/number | per-channel range |
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
- `ERROR` — команда не выполнена / выполнена с ошибкой;
- `INVALID` — команда невалидна (params, HMAC, timestamp);
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
| pH-pump dose min interval | AE3 `correction_planner.py` | `zone.correction.resolved_config.controllers.ph.min_interval_sec` (typical 60..120s) |
| EC-pump dose min interval | AE3 `correction_planner.py` | `zone.correction.resolved_config.controllers.ec.min_interval_sec` (typical 60..120s) |
| pH-pump max dose per shot | AE3 + sanity cap HL | `controllers.ph.max_dose_ml` + HL `_MAX_DOSE_ML_SANITY=500` |
| EC-pump max dose per shot | AE3 + sanity cap HL | `controllers.ec.max_dose_ml` + HL `_MAX_DOSE_ML_SANITY=500` |
| pump max duration per command | HL + firmware NodeConfig | HL `_MAX_DURATION_MS_SANITY=300_000`, NodeConfig `safe_limits.max_duration_ms` |
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

# 10. Автоматический rollback

Если команда вызывает ошибку:

- pH дозировка отменяется
- насос останавливается
- valve сбрасывается в idle
- создаётся alert

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
