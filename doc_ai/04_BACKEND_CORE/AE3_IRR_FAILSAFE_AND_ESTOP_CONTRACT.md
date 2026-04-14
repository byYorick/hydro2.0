# AE3 IRR Fail-Safe And E-Stop Contract

**Версия:** 1.0
**Дата:** 2026-04-09
**Статус:** Детализирующий контракт для AE3 / Laravel / firmware mirror

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Зафиксировать единый контракт защитной логики для production `storage_irrigation_node`
и правила, по которым эта логика должна дублироваться в AE3.

Документ описывает:
- где лежит source of truth для настраиваемых fail-safe guard'ов;
- как frontend сохраняет их в `zone.logic_profile`;
- как backend зеркалирует их в `NodeConfig`;
- какие локальные stop/action правила обязана выполнять прошивка;
- как AE3 обязан дублировать те же guards на своём runtime path;
- как трактуется физический `E-Stop`.

Документ не заменяет:
- `ae3lite.md` как канонический runtime-spec;
- `../02_HARDWARE_FIRMWARE/STORAGE_IRRIGATION_NODE_PROD_SPEC.md` как hardware/firmware-spec;
- `../03_TRANSPORT_MQTT/*` как transport source of truth.

---

## 2. Источники истины

Source of truth для editable guard-настроек:

```text
zone.logic_profile.active_profile.subsystems.diagnostics.execution.fail_safe_guards
```

Firmware mirror:

```text
NodeConfig.fail_safe_guards
```

Инварианты:
- frontend редактирует только `zone.logic_profile`;
- AE3 читает guard-конфиг из compiled runtime bundle;
- firmware guard-конфиг приходит только через `NodeConfig`;
- backend обязан зеркалировать zone-level guard-поля в `NodeConfig` всех `type=irrig` нод зоны;
- direct MQTT publish из AE3 для guard-логики запрещён.

---

## 3. Конфигурационный контракт

### 3.1. Zone logic_profile

Канонические поля:

```json
{
  "subsystems": {
    "diagnostics": {
      "execution": {
        "fail_safe_guards": {
          "clean_fill_min_check_delay_ms": 5000,
          "solution_fill_clean_min_check_delay_ms": 5000,
          "solution_fill_solution_min_check_delay_ms": 15000,
          "recirculation_stop_on_solution_min": true,
          "irrigation_stop_on_solution_min": true,
          "estop_debounce_ms": 80
        }
      }
    }
  }
}
```

Смысл полей:
- `clean_fill_min_check_delay_ms` — задержка перед проверкой `level_clean_min` после старта `clean_fill`;
- `solution_fill_clean_min_check_delay_ms` — задержка перед проверкой `level_clean_min` после старта `solution_fill`;
- `solution_fill_solution_min_check_delay_ms` — задержка перед leak-check по `level_solution_min` после старта `solution_fill`;
- `recirculation_stop_on_solution_min` — включать ли stop-guard `prepare_recirculation` по `level_solution_min=0`;
- `irrigation_stop_on_solution_min` — включать ли stop-guard `irrigation` по `level_solution_min=0`;
- `estop_debounce_ms` — debounce физической кнопки `E-Stop`.

### 3.2. NodeConfig mirror

Backend зеркалирует те же значения в `NodeConfig.fail_safe_guards`:

```json
{
  "fail_safe_guards": {
    "clean_fill_min_check_delay_ms": 5000,
    "solution_fill_clean_min_check_delay_ms": 5000,
    "solution_fill_solution_min_check_delay_ms": 15000,
    "recirculation_solution_min_guard_enabled": true,
    "irrigation_solution_min_guard_enabled": true,
    "estop_debounce_ms": 80
  }
}
```

Правила mapping:
- `recirculation_stop_on_solution_min` -> `recirculation_solution_min_guard_enabled`
- `irrigation_stop_on_solution_min` -> `irrigation_solution_min_guard_enabled`

Границы значений:
- `*_delay_ms`: `0..3600000`
- `estop_debounce_ms`: `20..5000`

Если zone-level поле отсутствует:
- backend обязан использовать system defaults / contract defaults;
- firmware не должна домысливать значения вне `NodeConfig` и compile-time defaults.

---

## 4. Локальная логика firmware

### 4.1. Clean fill

Условие активности:
- `valve_clean_fill == ON`

Правила:
1. После `clean_fill_min_check_delay_ms` прошивка обязана проверить `level_clean_min`.
2. Если `level_clean_min == 0`, прошивка обязана:
   - выключить `valve_clean_fill`;
   - опубликовать `clean_fill_source_empty`.
3. Если `level_clean_max == 1`, прошивка обязана:
   - выключить `valve_clean_fill`;
   - опубликовать `clean_fill_completed`.

### 4.2. Solution fill

Условие активности:
- `pump_main == ON`
- `valve_clean_supply == ON`
- `valve_solution_fill == ON`

Правила:
1. После `solution_fill_clean_min_check_delay_ms` прошивка обязана проверить `level_clean_min`.
2. Если `level_clean_min == 0`, прошивка обязана:
   - выключить `pump_main`, `valve_clean_supply`, `valve_solution_fill`;
   - опубликовать `solution_fill_source_empty`.
3. После `solution_fill_solution_min_check_delay_ms` прошивка обязана проверить `level_solution_min`.
4. Если `level_solution_min == 0`, прошивка обязана:
   - выключить `pump_main`, `valve_clean_supply`, `valve_solution_fill`;
   - опубликовать `solution_fill_leak_detected`.
5. Если `level_solution_max == 1`, прошивка обязана:
   - выключить `pump_main`, `valve_clean_supply`, `valve_solution_fill`;
   - опубликовать `solution_fill_completed`.

### 4.3. Prepare recirculation

Условие активности:
- `pump_main == ON`
- `valve_solution_supply == ON`
- `valve_solution_fill == ON`

Если `recirculation_solution_min_guard_enabled == true` и `level_solution_min == 0`,
прошивка обязана:
- выключить `pump_main`, `valve_solution_supply`, `valve_solution_fill`;
- опубликовать `recirculation_solution_low`.

### 4.4. Irrigation

Условие активности:
- `pump_main == ON`
- `valve_solution_supply == ON`
- `valve_irrigation == ON`

Если `irrigation_solution_min_guard_enabled == true` и `level_solution_min == 0`,
прошивка обязана:
- выключить `pump_main`, `valve_solution_supply`, `valve_irrigation`;
- опубликовать `irrigation_solution_low`.

### 4.5. Physical E-Stop

Аппаратный контракт firmware:
- выделенный вход `GPIO23`;
- `active_low=true`;
- `pull-up`;
- `debounce_ms` берётся из `fail_safe_guards.estop_debounce_ms`.

Семантика:
- пока кнопка нажата, нода обязана удерживать все 6 актуаторов в `OFF`;
- на фронт нажатия нода публикует `emergency_stop_activated`;
- после отпускания нода восстанавливает snapshot actuator-state, который был до нажатия;
- release не публикует отдельный domain event по умолчанию.

---

## 5. Контракт дублирования в AE3

AE3 обязан дублировать те же stop-решения на уровне runtime state machine.

Это означает:
- channel-level и aggregate node events могут ускорять реакцию;
- но даже без них AE3 должен уметь прийти к тем же stop/outcome через DB-first reconcile.

### 5.1. Что именно должен дублировать AE3

AE3 обязан знать те же guard-конфиги:
- `clean_fill_min_check_delay_ms`
- `solution_fill_clean_min_check_delay_ms`
- `solution_fill_solution_min_check_delay_ms`
- `recirculation_stop_on_solution_min`
- `irrigation_stop_on_solution_min`

AE3 обязан применять те же бизнес-решения:
- `clean_fill_source_empty`
- `clean_fill_completed`
- `solution_fill_source_empty`
- `solution_fill_leak_detected`
- `solution_fill_completed`
- `recirculation_solution_low`
- `irrigation_solution_low`
- `emergency_stop_activated`

### 5.2. Допустимое использование node events

Node events разрешено использовать как:
- fast-path wake-up;
- explainability / timeline сигнал;
- shortcut для раннего reconcile.

Node events запрещено использовать как единственный source of truth для:
- terminal transition без DB confirmation;
- mutation `zone_workflow_state`;
- обхода `commands` / `telemetry_last` / `zone_events` reconcile;
- direct MQTT-side effects.

### 5.3. Каноническое поведение AE3

После получения `LEVEL_SWITCH_CHANGED` или guard-event AE3 обязан:
1. перечитать read-model зоны;
2. подтвердить, что stage всё ещё активен;
3. подтвердить состояние релевантных датчиков/событий;
4. выполнить тот же fail-closed outcome, который выполнила бы firmware.

Примеры:
- если runtime видит, что `solution_fill` активен, прошло окно `solution_fill_clean_min_check_delay_ms`,
  а `level_clean_min` подтверждённо `0`, AE3 обязан трактовать stage как fail-closed источник пустой воды;
- если runtime видит `prepare_recirculation` и `level_solution_min=0` при включённом guard,
  AE3 обязан остановить stage и не пытаться продолжать подготовку.
- если runtime получает `clean_fill_source_empty`, он обязан идти в `clean_fill_retry_stop`,
  увеличить `clean_fill_cycle` и после двух повторов завершить stage через terminal `clean_fill_source_empty_stop`;
- если runtime получает `emergency_stop_activated`, он обязан сначала попытаться
  перепроверить ожидаемый `storage_state` и может продолжить stage только при восстановленном snapshot.

---

## 6. Event contract

Aggregate event-топик:

```text
hydro/{gh}/{zone}/{node}/storage_state/event
```

Коды:
- `clean_fill_source_empty`
- `clean_fill_completed`
- `solution_fill_source_empty`
- `solution_fill_leak_detected`
- `solution_fill_completed`
- `recirculation_solution_low`
- `irrigation_solution_low`
- `solution_fill_timeout`
- `prepare_recirculation_timeout`
- `emergency_stop_activated`

Channel-level event-топики:

```text
hydro/{gh}/{zone}/{node}/{level_channel}/event
```

Код:
- `level_switch_changed`

---

## 7. Laravel / frontend obligations

Laravel обязан:
1. сохранять editable guard-настройки в `zone.logic_profile`;
2. после изменения `zone.logic_profile` репаблишить `NodeConfig` всех `irrig`-нод зоны;
3. не публиковать device-команды напрямую в MQTT;
4. сохранять совместимость поля `subsystems.irrigation.safety.stop_on_solution_min`
   как fallback для irrigation guard, пока UI/runtime полностью не опираются только на `fail_safe_guards`.

Frontend обязан:
1. редактировать guard-поля только через UI automation profile;
2. явно показывать, что это fail-safe настройки водного контура;
3. не писать firmware mirror напрямую в `NodeConfig`.

---

## 7a. IRR state probe backoff (resilient probing для polling-stages)

`irrigation_check` и `irrigation_recovery_check` опрашивают IRR-ноду каждые
`level_poll_interval_sec` через `_probe_irr_state` (`storage_state` команда +
ожидание `IRR_STATE_SNAPSHOT` zone_event). На реальном железе нода может быть
временно недоступна (Wi-Fi/MQTT hiccup, reboot ESP32, OTA, кратковременный
power-glitch). Жёсткий fail-closed на каждом poll-итерации без backoff
приводит к ложным `irrigation_start` failure'ам и преждевременной эскалации
recovery, тогда как нода восстановится через 5-15 секунд.

### 7a.1. Backoff контракт

`BaseStageHandler._probe_irr_state_with_backoff()` оборачивает probe и
действует так:

1. **Pre-probe liveness check** (вариант C). Перед публикацией
   `storage_state` команды читается `nodes.status` и `nodes.last_heartbeat_at`
   через `runtime_monitor.read_node_liveness(node_uid)`. Если нода
   `status='offline'` или `heartbeat_age_sec >
   _IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC` (по умолчанию 30 s) —
   probe пропускается, инкрементируется streak, возвращается
   `StageOutcome(kind="poll")`. Экономит HL roundtrip и MQTT публикацию.
2. **Resilient probe** (вариант B). Если нода кажется живой — выполняется
   обычный `_probe_irr_state`. На `irr_state_unavailable` или
   `irr_state_stale` `TaskExecutionError` НЕ пробрасывается: streak
   инкрементируется, эмитится zone-event `IRR_STATE_PROBE_DEFERRED`,
   возвращается `poll`.
3. **Streak limit / fail-closed**. При достижении
   `_IRR_PROBE_FAILURE_STREAK_LIMIT` (по умолчанию 5 подряд идущих
   deferred probes) handler возвращает `exhausted_outcome` (для
   `irrigation_check` — `transition: irrigation_stop_to_recovery`, для
   `irrigation_recovery_check` — `fail:
   irrigation_recovery_probe_exhausted`). Эмитится
   `IRR_STATE_PROBE_STREAK_EXHAUSTED` zone-event и
   `biz_irr_probe_streak_exhausted` alert (severity `warning`).
4. **Reset streak**. После успешного probe `ae_tasks.irr_probe_failure_streak`
   обнуляется (UPDATE с `WHERE streak <> 0`, чтобы не плодить лишние UPDATE).
5. **Hardware mismatch — без backoff**. `irr_state_mismatch` (snapshot
   получен, но valve/pump state не совпадает с `expected`) пробрасывается
   как TaskExecutionError немедленно. Это safety boundary: расхождение
   физического состояния — не transient ошибка, а потенциально опасное
   состояние, требующее fail-closed.

### 7a.2. Где применяется

| Stage | Backoff | Exhausted outcome |
|-------|---------|-------------------|
| `irrigation_check` | да | `transition: irrigation_stop_to_recovery` |
| `irrigation_recovery_check` | да | `fail: irrigation_recovery_probe_exhausted` |
| `startup`, `clean_fill`, `solution_fill`, `prepare_recirc`, `correction` | нет (strict `_probe_irr_state`) | TaskExecutionError fail-closed |

Полив (poll-based stages) работает в режиме deferred backoff. Setup-stages
(fill / startup / correction-window) сохраняют строгое поведение — там
nodes уже должны быть available, transient failure даёт реальные диагнозы,
а скрытие через streak усложнило бы расследование.

### 7a.3. Поля и события

- `ae_tasks.irr_probe_failure_streak` — счётчик подряд идущих deferred
  probes. Сбрасывается при успехе.
- `IRR_STATE_PROBE_DEFERRED` — zone-event на каждый отложенный probe;
  payload `{stage, workflow_phase, reason, streak, streak_limit, expected,
  node_uid, node_status, heartbeat_age_sec}`.
- `IRR_STATE_PROBE_STREAK_EXHAUSTED` — zone-event при достижении лимита.
- `biz_irr_probe_streak_exhausted` — biz alert (severity `warning`).

`reason` принимает значения: `node_unreachable`, `irr_state_unavailable`,
`irr_state_stale`.

---

## 8. Инварианты и fail-closed

1. Firmware и AE3 обязаны останавливаться в одну и ту же безопасную сторону: `OFF`, а не retry-first.
2. При расхождении `NodeConfig` и runtime bundle source of truth остаётся у `zone.logic_profile`,
   а backend обязан как можно быстрее переиздать mirror.
3. `E-Stop` всегда имеет приоритет над обычными workflow-stage и correction-переходами.
4. Отпускание `E-Stop` не отменяет общую обязанность AE3 перепроверить read-model до продолжения логики.
5. Новые event-коды и config-поля не должны ломать защищённый pipeline
   `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.
6. `irr_state_mismatch` — safety boundary, не оборачивается probe backoff'ом
   (см. §7a). `irr_state_unavailable` / `irr_state_stale` в polling-стейджах
   допускают отложенный retry до `_IRR_PROBE_FAILURE_STREAK_LIMIT`, после
   чего обязательно эскалируются (recovery transition или fail-closed).
