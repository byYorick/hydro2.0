# План доработок для запуска в production (Задачи 1-3)

> Приоритет: безопасность растений → надёжность автоматизации

---

## Задача 1: Блокировка коррекции при stub-значениях сенсоров

### Проблема

Если pH/EC зонд отвалился (обрыв I2C, физическая поломка), прошивка переключается на fallback-значения (`pH=6.5`, `EC=1400`). Эти значения попадают в `telemetry_last`, а automation-engine принимает их за реальные и начинает дозирование — **на основе фиктивных данных**.

Это может привести к передозировке кислоты/щёлочи/удобрений и гибели растений.

### Текущий пайплайн (где разрыв)

```
ESP32 прошивка                    History-Logger               Automation-Engine
─────────────────                 ──────────────               ─────────────────
trema_ph.c:                       telemetry_processing.py:     correction_controller_check_core.py:
  use_stub_values = true            quality = "GOOD" ← БАГ      current = telemetry.get("PH")
  stub_ph = 6.5                     is_stub НЕ пишется          if current is None: skip ← НЕ ДОСТАТОЧНО
  → telemetry { stub: true }        → telemetry_last             → дозирует на stub!
```

**Разрыв:** History-logger получает `stub: true` из MQTT, но при записи в `telemetry_last` всегда ставит `quality = "GOOD"` (строка 1592). Automation-engine не видит stub-флаг.

### Файлы и изменения

#### 1.1 Миграция БД — добавить `is_stub` в `telemetry_last`

**Файл:** `backend/laravel/database/migrations/2026_02_25_000001_add_is_stub_to_telemetry_last.php`

Текущая схема (`2025_12_25_151720_create_telemetry_last_table.php`):
```
telemetry_last (sensor_id PK, last_value, last_ts, last_quality ENUM, updated_at)
```

Добавить:
```sql
ALTER TABLE telemetry_last ADD COLUMN is_stub BOOLEAN NOT NULL DEFAULT FALSE;
```

Обратная совместимость: `DEFAULT FALSE` — старые записи не ломаются.

#### 1.2 History-Logger — писать `is_stub` при upsert

**Файл:** `backend/services/history-logger/telemetry_processing.py`

**Строки 1589-1594** — формирование `telemetry_last_updates`:
```python
# БЫЛО:
telemetry_last_updates[sensor_id] = {
    "value": sample.value,
    "ts": sample_ts,
    "quality": "GOOD",
    "updated_at": sample_ts,
}

# СТАЛО:
raw_data = item.get("raw_data") or {}
is_stub = bool(raw_data.get("stub", False))
telemetry_last_updates[sensor_id] = {
    "value": sample.value,
    "ts": sample_ts,
    "quality": "BAD" if is_stub else "GOOD",
    "is_stub": is_stub,
    "updated_at": sample_ts,
}
```

**Строки 1596-1646** — SQL upsert:
Добавить `$6::boolean[]` (`is_stub`) в UNNEST, INSERT и ON CONFLICT DO UPDATE.

**Контекст:** `raw_data` доступен через `item["sample"]` → нужно проверить как `stub` попадает в item. Поле `stub` включено в `allowed_raw_fields` (`utils.py:38`), значит оно сохраняется в `metadata.raw` и доступно.

#### 1.3 Recipe Repository — читать `is_stub` из БД

**Файл:** `backend/services/automation-engine/repositories/recipe_repository_zone_single.py`

**SQL (строки 27-40)** — CTE `telemetry_data`:
```sql
-- БЫЛО:
SELECT DISTINCT ON (s.type)
    s.type as metric_type,
    tl.last_value as value,
    tl.last_ts as updated_at
FROM telemetry_last tl ...

-- СТАЛО:
SELECT DISTINCT ON (s.type)
    s.type as metric_type,
    tl.last_value as value,
    tl.last_ts as updated_at,
    COALESCE(tl.is_stub, FALSE) as is_stub
FROM telemetry_last tl ...
```

**SQL (строка 141)** — JSON aggregation:
```sql
-- БЫЛО:
json_build_object('value', value, 'updated_at', updated_at)

-- СТАЛО:
json_build_object('value', value, 'updated_at', updated_at, 'is_stub', is_stub)
```

**Строки 180-187** — обработка результата:
```python
# БЫЛО:
telemetry: Dict[str, Optional[float]] = {}
telemetry_timestamps: Dict[str, Any] = {}
for metric_type, metric_data in telemetry_raw.items():
    if isinstance(metric_data, dict):
        telemetry[metric_type] = metric_data.get("value")
        telemetry_timestamps[metric_type] = metric_data.get("updated_at")

# СТАЛО:
telemetry: Dict[str, Optional[float]] = {}
telemetry_timestamps: Dict[str, Any] = {}
telemetry_stub_flags: Dict[str, bool] = {}
for metric_type, metric_data in telemetry_raw.items():
    if isinstance(metric_data, dict):
        telemetry[metric_type] = metric_data.get("value")
        telemetry_timestamps[metric_type] = metric_data.get("updated_at")
        telemetry_stub_flags[metric_type] = bool(metric_data.get("is_stub", False))
    else:
        telemetry[metric_type] = metric_data
```

**Строка 214** — добавить в return:
```python
return {
    ...
    "telemetry_stub_flags": telemetry_stub_flags,  # НОВОЕ
}
```

#### 1.4 Zone Process Cycle — прокинуть stub_flags

**Файл:** `backend/services/automation-engine/services/zone_process_cycle.py`

**Строка 71:**
```python
telemetry_stub_flags = zone_data.get("telemetry_stub_flags", {})
```

Передать в `process_correction_controllers_fn` (строка 175) или напрямую добавить в `telemetry` dict через специальный ключ.

**Самый простой путь:** добавить stub_flags в сигнатуру `process_correction_controllers` и прокинуть в `check_and_correct_core`.

Альтернативный (минимально инвазивный) путь: вложить в `telemetry` dict:
```python
telemetry["_stub_flags"] = telemetry_stub_flags
```

#### 1.5 Correction Core — проверка stub перед коррекцией

**Файл:** `backend/services/automation-engine/correction_controller_check_core.py`

**После строки 46** (получение `current`), **перед строкой 52** (проверка `current is None`):

```python
# Проверка stub: если сенсор использует fallback значения, коррекция запрещена
stub_flags = telemetry.get("_stub_flags") or {}
metric_is_stub = stub_flags.get(controller.metric_name) or stub_flags.get(target_key)
if metric_is_stub:
    await state_machine.transition(
        "cooldown",
        "sense_sensor_stub_detected",
        {"metric": controller.metric_name, "stub": True},
    )
    logger.warning(
        "Zone %s: %s correction BLOCKED — sensor using stub/fallback values",
        zone_id,
        controller.metric_name,
        extra={"zone_id": zone_id, "metric": controller.metric_name},
    )
    return None
```

#### 1.6 Алерт SENSOR_STUB_DETECTED

**Файл:** `backend/services/common/alerts.py`

Добавить в `AlertCode`:
```python
BIZ_SENSOR_STUB = "biz_sensor_stub"  # Сенсор использует fallback значения
```

Создать алерт в `correction_controller_check_core.py` (опционально — можно создавать из оркестратора).

#### 1.7 Тесты

- **Unit-тест AE:** подать `telemetry = {"PH": 6.5, "_stub_flags": {"PH": True}}` → `check_and_correct_core` возвращает `None`
- **Unit-тест history-logger:** `sample.stub=True` → `is_stub=True` в SQL upsert
- **Интеграционный:** отключить pH-зонд → проверить что коррекция не запускается

### Верификация

1. Отключить pH-зонд (или эмулировать через test_node с `stub: true`)
2. Убедиться: `telemetry_last.is_stub = TRUE` для данного sensor_id
3. Убедиться: `correction_controller_check_core` возвращает `None` с reason `sense_sensor_stub_detected`
4. Убедиться: алерт `biz_sensor_stub` создан
5. Подключить зонд обратно → `is_stub = FALSE` → коррекция возобновляется

---

## Задача 2: activate/deactivate_sensor_mode в прошивках pH/EC

### Проблема

Automation-engine реализует Correction Cycle State Machine и отправляет команды `activate_sensor_mode` / `deactivate_sensor_mode` pH/EC нодам через `zone_sensor_mode_orchestrator.py`. Однако **реальные прошивки ph_node и ec_node не обрабатывают эти команды** — обработчик реализован только в test_node.

Без этого:
- AE не получает подтверждения что нода готова к коррекции
- Нет информации о стабилизации сенсора после включения потока
- Correction flags `flow_active`, `stable`, `corrections_allowed` не приходят из реальных нод

### Спецификация

Из `CORRECTION_CYCLE_SPEC.md:240-288`:

**Команда activate:**
```json
{
  "cmd": "activate_sensor_mode",
  "params": { "stabilization_time_sec": 60 },
  "cmd_id": "cmd-activate-123",
  "ts": 1710001234,
  "sig": "a1b2c3..."
}
```

**Расширенная телеметрия при active mode:**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001234,
  "flow_active": true,
  "stable": false,
  "stabilization_progress_sec": 15
}
```

После стабилизации: `stable: true`, `corrections_allowed: true`.

**Команда deactivate:**
```json
{ "cmd": "deactivate_sensor_mode", "params": {} }
```

### Файлы и изменения

#### 2.1 Общий компонент sensor_mode_handler

**Новые файлы:**
- `firmware/common/components/node_framework/sensor_mode_handler.h`
- `firmware/common/components/node_framework/sensor_mode_handler.c`

```c
// sensor_mode_handler.h
typedef enum {
    SENSOR_MODE_IDLE = 0,
    SENSOR_MODE_STABILIZING,
    SENSOR_MODE_ACTIVE,
} sensor_mode_t;

typedef struct {
    sensor_mode_t mode;
    bool corrections_allowed;
    bool stable;
    bool flow_active;
    int64_t stabilization_start_ms;
    uint32_t stabilization_time_sec;  // из params команды
} sensor_mode_state_t;

void sensor_mode_init(sensor_mode_state_t *state);
void sensor_mode_activate(sensor_mode_state_t *state, uint32_t stabilization_time_sec);
void sensor_mode_deactivate(sensor_mode_state_t *state);
void sensor_mode_tick(sensor_mode_state_t *state);  // вызывать из основного loop
bool sensor_mode_is_active(const sensor_mode_state_t *state);
```

**Логика `sensor_mode_tick`:**
- Если `mode == STABILIZING` и прошло `stabilization_time_sec`:
  - `mode = ACTIVE`, `stable = true`, `corrections_allowed = true`

#### 2.2 Обработчик в ph_node

**Файл:** `firmware/nodes/ph_node/main/ph_node_framework_integration.c`

В command handler (где обрабатываются команды типа `dose_acid`, `dose_base`, `calibrate`) добавить:

```c
if (strcmp(cmd, "activate_sensor_mode") == 0) {
    uint32_t stab_time = 60;  // default
    cJSON *params_stab = cJSON_GetObjectItem(params, "stabilization_time_sec");
    if (params_stab && cJSON_IsNumber(params_stab)) {
        stab_time = (uint32_t)params_stab->valuedouble;
    }
    sensor_mode_activate(&g_sensor_mode, stab_time);
    // send ACK
    return NODE_CMD_OK;
}

if (strcmp(cmd, "deactivate_sensor_mode") == 0) {
    sensor_mode_deactivate(&g_sensor_mode);
    return NODE_CMD_OK;
}
```

В telemetry loop — добавить поля при active mode:
```c
if (sensor_mode_is_active(&g_sensor_mode)) {
    // Добавить в JSON: flow_active, stable, corrections_allowed,
    // stabilization_progress_sec
}
```

#### 2.3 Обработчик в ec_node

**Файл:** `firmware/nodes/ec_node/main/ec_node_framework_integration.c`

Аналогично ph_node.

#### 2.4 Обновить CMakeLists.txt

Добавить `sensor_mode_handler.c` в SRCS компонента `node_framework`.

#### 2.5 Тесты

- **На реальном оборудовании:** отправить `activate_sensor_mode` → проверить телеметрию → `stable: true` через N секунд
- **Через node_sim:** test_node уже реализует — проверить интеграцию с AE

### Верификация

1. Отправить `activate_sensor_mode {stabilization_time_sec: 30}` на pH ноду
2. Нода отвечает ACK (command response `status: "ok"`)
3. Телеметрия содержит `flow_active: true, stable: false`
4. Через 30 сек: `stable: true, corrections_allowed: true`
5. Automation-engine видит correction_flags и разрешает коррекцию
6. `deactivate_sensor_mode` → `corrections_allowed: false`, `stable: false`

---

## Задача 3: Надёжность Scheduler (recovery + lighting watchdog)

### Проблема

Scheduler перенесён в automation-engine (`scheduler_internal_enqueue.py`, `scheduler_task_executor.py`). При перезапуске AE задачи со статусом `accepted` теряются — asyncio таймеры не переживают restart.

Для освещения это критично: photoperiod 16/8 для салата — сбой на 2 часа = стрелкование (растение начинает цвести вместо наращивания зелёной массы).

### Текущая архитектура

```
Laravel (SchedulerTaskController)     Automation-Engine
────────────────────────────────      ──────────────────
LaravelSchedulerActiveTask:           scheduler_internal_enqueue.py:
  task_id, zone_id, task_type           SUPPORTED_TYPES = {irrigation, lighting, ...}
  status: pending|accepted|...          _INTERNAL_ENQUEUE_DUE_SEC = 60
  due_at, expires_at                    _schedule_runtime_dispatch_if_possible()
  accepted_at, terminal_at                  ↓
                                      scheduler_task_executor.py:
                                        execute(zone_id, task_type, payload)
```

**Проблема:** Между `due_at` и `terminal_at` задача живёт в памяти AE (asyncio.sleep). При restart — потеряна.

### Файлы и изменения

#### 3.1 Recovery при старте AE

**Новый файл:** `backend/services/automation-engine/scheduler_recovery.py`

```python
async def recover_pending_tasks(laravel_client, runtime_scheduler):
    """
    При старте AE: запросить из Laravel все задачи, которые нужно восстановить.
    """
    response = await laravel_client.get("/api/scheduler-tasks/recoverable")
    tasks = response.json().get("data", [])

    for task in tasks:
        if task["status"] in ("pending", "accepted"):
            if task["expires_at"] > utcnow():
                if task["due_at"] <= utcnow():
                    # Задача просрочена но не expired — выполнить немедленно
                    await runtime_scheduler.execute_immediately(task)
                else:
                    # Задача ещё не наступила — перепланировать
                    await runtime_scheduler.reschedule(task)

    logger.info("Recovered %d scheduler tasks after restart", len(tasks))
```

**Интеграция:** Вызвать `recover_pending_tasks()` при инициализации AE в текущем runtime entrypoint.

#### 3.2 Laravel endpoint для recovery

**Файл:** `backend/laravel/app/Http/Controllers/SchedulerTaskController.php`

Добавить метод:
```php
public function recoverable(Request $request)
{
    $tasks = LaravelSchedulerActiveTask::whereIn('status', ['pending', 'accepted'])
        ->where('expires_at', '>', now())
        ->get();

    return response()->json(['data' => $tasks]);
}
```

**Маршрут:** `backend/laravel/routes/api.php` или `web.php`:
```php
Route::get('/api/scheduler-tasks/recoverable', [SchedulerTaskController::class, 'recoverable']);
```

#### 3.3 Lighting Watchdog

**Новый файл:** `backend/services/automation-engine/scheduler_lighting_watchdog.py`

```python
WATCHDOG_CHECK_DELAY_SEC = 30
MAX_RETRIES = 3

async def lighting_watchdog(zone_id, expected_state, command_gateway, telemetry_repo):
    """
    После отправки команды set_light — проверить что свет реально включился/выключился.
    """
    await asyncio.sleep(WATCHDOG_CHECK_DELAY_SEC)

    for attempt in range(MAX_RETRIES):
        telemetry = await telemetry_repo.get_last_telemetry(zone_id)
        actual_light = telemetry.get("LIGHT_STATUS")

        if actual_light == expected_state:
            logger.info("Zone %s: lighting watchdog OK (attempt %d)", zone_id, attempt + 1)
            return True

        logger.warning(
            "Zone %s: lighting watchdog MISMATCH (expected=%s, actual=%s, attempt=%d/%d)",
            zone_id, expected_state, actual_light, attempt + 1, MAX_RETRIES,
        )

        if attempt < MAX_RETRIES - 1:
            # Повторить команду
            await command_gateway.send_light_command(zone_id, expected_state)
            await asyncio.sleep(WATCHDOG_CHECK_DELAY_SEC)

    # Все попытки исчерпаны
    await create_alert(
        zone_id=zone_id,
        source=AlertSource.BIZ.value,
        code=AlertCode.BIZ_LIGHT_FAILURE.value,
        type="LIGHTING_WATCHDOG_FAILED",
        details={
            "expected_state": expected_state,
            "retries": MAX_RETRIES,
        },
    )
    return False
```

**Интеграция:** Вызвать `asyncio.create_task(lighting_watchdog(...))` после отправки команды освещения в `scheduler_task_executor.py`.

#### 3.4 Heartbeat для lighting задач

Помимо watchdog, добавить периодическую проверку (каждые 5 минут) во время активного photoperiod:
- Если свет должен быть включён (по расписанию) и телеметрия показывает что он выключен → retry + алерт
- Это защищает от ситуации когда нода перезагрузилась и "забыла" что свет был включён

**Файл:** Добавить в `scheduler_task_executor.py` при обработке `task_type == "lighting"`.

#### 3.5 Тесты

- **Unit:** `test_scheduler_recovery.py` — mock Laravel API, проверить что задачи восстанавливаются
- **Unit:** `test_lighting_watchdog.py` — mock telemetry, проверить retry и алерт
- **Chaos:** `docker restart automation-engine` во время активной lighting фазы → задача восстановлена

### Верификация

1. Создать lighting задачу (photoperiod 16/8)
2. `docker restart automation-engine`
3. Убедиться: задача восстановлена, свет не погас
4. Эмулировать сбой ноды (свет не включился) → watchdog срабатывает → retry → алерт если не помогло

---

## Порядок реализации

```
Неделя 1:
├── Задача 1.1: Миграция БД (is_stub)
├── Задача 1.2: History-logger upsert
├── Задача 1.3: Recipe repository SQL
├── Задача 1.4: Zone process cycle прокидка
├── Задача 1.5: Correction core проверка
├── Задача 1.6: Алерт SENSOR_STUB
└── Задача 1.7: Тесты

Неделя 2 (параллельно):
├── Задача 3.1: scheduler_recovery.py
├── Задача 3.2: Laravel endpoint
├── Задача 3.3: Lighting watchdog
├── Задача 3.4: Heartbeat для lighting
└── Задача 3.5: Тесты

Неделя 3-4:
├── Задача 2.1: sensor_mode_handler.c/.h
├── Задача 2.2: ph_node обработчик
├── Задача 2.3: ec_node обработчик
├── Задача 2.4: CMakeLists.txt
└── Задача 2.5: Тесты на оборудовании
```

## Зависимости

- Задача 1 не зависит ни от чего — **начинать сразу**
- Задача 3 не зависит от задач 1 и 2 — **параллельно с задачей 1**
- Задача 2 не блокирует задачу 1 (stub-проверка работает независимо от sensor_mode)
- Задача 2 требует физического оборудования для тестирования

## TODO (отложено)

- [ ] Telegram-алерты (настройка Alertmanager + Telegram bot)
- [ ] MQTT auth + ACL (задача 4)
- [ ] OTA обновления прошивок (задача 5)
- [ ] TLS для MQTT
- [ ] Secrets vault
