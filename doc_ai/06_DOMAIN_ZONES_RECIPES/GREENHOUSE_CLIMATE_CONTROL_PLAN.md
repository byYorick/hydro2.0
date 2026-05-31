# GREENHOUSE_CLIMATE_CONTROL_PLAN.md
# План реализации общего управления климатом теплицы

**Версия:** 0.3-agent-ready  
**Дата:** 2026-05-14  
**Статус:** Draft / agent-ready план; design decisions зафиксированы, перед кодом нужен Stage 1 spec sync

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Связанные документы

- `doc_ai/SYSTEM_ARCH_FULL.md` — greenhouse-level climate decisions принадлежат уровню теплицы.
- `doc_ai/ARCHITECTURE_FLOWS.md` — protected command pipeline и single-writer invariants.
- `doc_ai/04_BACKEND_CORE/ae3lite.md` — canonical AE3 task types и ingress endpoints.
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — роли `automation-engine` и `history-logger`.
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` — единственный REST-контракт публикации команд в MQTT.
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` — canonical tables/read-models.
- `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md` — формат `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`.
- `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — каналы сенсоров и actuator-ов.
- `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md` — Laravel scheduler-dispatch.
- `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` — AE3 dispatch света и greenhouse climate.

## 1. Цель

Реализовать greenhouse-level систему управления климатом теплицы, которая управляет
двумя roof-форточками:

- `roof_vent_left` — левая длинная форточка крыши;
- `roof_vent_right` — правая длинная форточка крыши.

Система должна принимать решение о проценте открытия `0..100%` по:

- расписанию и времени суток;
- освещенности;
- внутренним датчикам температуры/влажности/давления;
- внешней метеостанции;
- ветру, направлению ветра и дождю;
- целям активных рецептов или greenhouse-level target policy;
- настройкам оператора из frontend;
- режимам `auto|semi|manual`;
- временным ручным override с TTL.

Команды к приводам идут только через защищенный pipeline:

```text
Laravel scheduler-dispatch -> automation-engine -> history-logger -> MQTT -> ESP32
```

Прямой MQTT publish из Laravel или `automation-engine` запрещен.

---

## 2. Scope

### 2.1. V1: реализовать

V1 должен быть детерминированным rule-based controller без адаптивного ML.

Входит в V1:

1. Greenhouse-owned runtime task `greenhouse_climate_tick`.
2. Single-writer на уровне `greenhouse`.
3. Две roof-форточки с actuator command `set_position`.
4. Внутренняя агрегация нескольких climate-нод.
5. Внешняя метеостанция:
   - температура;
   - влажность;
   - давление;
   - ветер;
   - направление ветра;
   - дождь;
   - освещенность.
6. Расписание день/ночь + корректировка по освещенности.
7. Temperature/humidity correction.
8. Wind clamp:
   - `>= wind_reduce_threshold_ms` — прикрыть;
   - `>= wind_close_threshold_ms` — закрыть/сильно ограничить.
9. Direction-aware logic для наветренной/подветренной стороны.
10. Rain clamp:
    - наветренную сторону закрыть;
    - подветренную ограничить настраиваемым процентом.
11. `max_step_pct`, default `25`, редактируется на frontend.
12. `position_deadband_pct` и `min_command_interval_sec`, чтобы не дергать приводы.
13. Fallback при stale sensors.
14. Emergency overheat mode.
15. Режимы `auto|semi|manual`.
16. Temporary manual override: “открыть на X% на N минут, затем вернуть mode”.
17. Decision snapshot/state для UI.
18. Alerts/events/metrics.
19. Тесты алгоритма, API и command pipeline.

### 2.2. V2: спроектировать, но не реализовывать в V1

V2 items можно учитывать в структуре state/debug payload, но нельзя делать их runtime
критической зависимостью V1:

1. Absolute humidity как обязательный фактор принятия решения.
2. Dew point и condensation risk.
3. VPD.
4. Weighted policy по нескольким зонам.
5. Адаптивная настройка порогов по истории.
6. AI/digital twin recommendations.
7. Учет прогноза погоды.

### 2.3. Future: только отметить

Зональная система климата остается future subsystem `zone_climate`.
В этом плане она только фиксируется как будущий контур телеметрии:

- температура воздуха;
- влажность воздуха;
- CO2;
- температура прикорневой зоны;
- температура почвы;
- температура раствора полива.

Зональные actuator-ы (`CO2`, вентиляторы зоны, root-zone heating/cooling,
solution heating/cooling) не входят в V1 greenhouse climate.

---

## 3. Design Decisions Required Before Implementation

Решения DD-1..DD-9 зафиксированы в таблице ниже; новая реализация должна им соответствовать.

| ID | Решение | Статус по умолчанию для плана |
|---|---|---|
| DD-1 | Расширять существующие AE3 tables через `owner_type`, или создать отдельные greenhouse runtime tables | **Утверждено:** отдельные таблицы `greenhouse_automation_*` / `greenhouse_manual_overrides` (Option A) |
| DD-2 | Runtime `greenhouse.logic_profile`: raw document или compiled bundle | **Утверждено:** compiled bundle в `automation_effective_bundles` (`scope_type=greenhouse`, `scope_id=greenhouse_id`), путь `greenhouse.logic_profile` внутри `config` |
| DD-3 | Semantics `wind_direction`: meteorological degrees, откуда дует ветер | Зафиксировать как обязательное |
| DD-4 | Ориентация теплицы: нормали левой/правой roof-стороны или азимут конька | **Утверждено:** поля `greenhouse_orientation_deg`, `left_roof_normal_deg`, `right_roof_normal_deg` в `execution` (nullable); direction-aware выключается, если нормали не заданы |
| DD-5 | Default target policy: `greenhouse_targets` или `primary_zone`/`active_zones_strictest` | **Утверждено:** `greenhouse_targets` по умолчанию |
| DD-6 | Emergency behavior в `manual`: запрещать команды полностью или разрешать аварийный override | **Утверждено:** флаг `manual_emergency_override_enabled` в execution (как в примере JSON §7.2) |
| DD-7 | Nodes type для метеостанции/приводов: новые `weather|vent` или существующие `climate|relay` + bindings | **Утверждено:** существующие `climate` / `relay` + `channel_bindings` с ролями из §6.2 |
| DD-8 | Фактическая позиция actuator: нода публикует position telemetry или runtime доверяет actuator controller | **Утверждено:** V1 — **trust controller** + `last_sent_*` в state; если нода публикует позицию в телеметрии, runtime может обновлять фактическую позицию в будущем без breaking change |
| DD-9 | Сегмент `{zone}` в MQTT для приводов, привязанных к теплице, но без «логической» зоны | **Утверждено:** узел **обязан** иметь непустой `nodes.zone_id` (anchor-зона в той же теплице); сегмент `{zone}` в топике = `zones.uid` этой зоны. Отдельный synthetic `zone_uid` в V1 не вводится. |

Если решения нет, реализация должна остановиться на spec/update stage и зафиксировать blocker.
На момент версии `0.3-agent-ready` все обязательные DD-1..DD-9 зафиксированы; новый
blocker появляется только если связанная layer-spec противоречит этим решениям.

---

## 4. Архитектурные ограничения

### 4.1. Расширение текущего AE3 scope

Текущий `doc_ai/04_BACKEND_CORE/ae3lite.md` жестко ограничивает canonical task types
и endpoint-ы. Поэтому `greenhouse_climate_tick` нельзя добавлять в runtime-код, пока
не синхронизированы:

1. `doc_ai/04_BACKEND_CORE/ae3lite.md`;
2. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`;
3. `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`;
4. `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md`;
5. API docs и data model docs.

Это изменение является осознанным расширением runtime scope, а не “малой правкой”.
Если часть документов уже обновлена, Stage 1 обязан проверить их на согласованность с
DD-1..DD-9 и этим планом, а не считать синхронизацию завершенной автоматически.

### 4.2. Runtime ownership

Общие форточки принадлежат `greenhouse`, не `zone`.
Запрещено запускать управление общими форточками через:

```text
POST /zones/{id}/start-cycle
```

Нужен отдельный greenhouse writer:

```text
POST /greenhouses/{id}/start-climate-tick
```

и single-writer lease на `greenhouse_id`.

### 4.3. Protected command pipeline

`automation-engine` отправляет actuator-команды только через:

```text
POST http://history-logger:9300/commands
```

`history-logger` остается единственной точкой MQTT publish.

---

## 5. Runtime Flow

Целевой поток:

```text
Laravel scheduler
  -> greenhouse automation intent в PostgreSQL
  -> POST /greenhouses/{id}/start-climate-tick
  -> automation-engine GreenhouseClimateRunner
  -> direct SQL read-model
  -> decision snapshot
  -> history-logger POST /commands
  -> MQTT hydro/{gh}/{zone_or_gh}/{node}/{channel}/command
  -> ESP32 actuator node
  -> command_response
  -> history-logger commands/status
  -> AE reconcile
  -> greenhouse automation state
```

До отдельного greenhouse MQTT namespace все команды должны оставаться совместимыми с
`hydro/{gh}/{zone}/{node}/{channel}/{message_type}`. Сегмент `{zone}` для приводов теплицы:
см. **DD-9** (anchor-зона через `nodes.zone_id` и `zones.uid`).

---

## 6. Hardware и Bindings

### 6.1. Ноды

V1 предполагает:

1. Внешняя метеостанция.
2. Одна или несколько внутренних climate-нод.
3. Actuator-нода приводов roof-форточек.

### 6.2. Bindings

Использовать greenhouse-owned bindings:

```text
infrastructure_instances.owner_type = 'greenhouse'
channel_bindings.role in (
  'climate_sensor',
  'weather_station_sensor',
  'vent_actuator',
  'fan_actuator'
)
```

Для roof-форточек binding metadata:

```json
{
  "role": "vent_actuator",
  "placement": "roof_left",
  "side": "left",
  "position_feedback": "closed_limit_only"
}
```

```json
{
  "role": "vent_actuator",
  "placement": "roof_right",
  "side": "right",
  "position_feedback": "closed_limit_only"
}
```

### 6.3. Sensor channels

Нужно обновить `NODE_CHANNELS_REFERENCE.md`, `MQTT_NAMESPACE.md`,
`MQTT_SPEC_FULL.md`, `BACKEND_NODE_CONTRACT_FULL.md`, `DATA_MODEL_REFERENCE.md`.

| Канал | Metric | Unit | Scope | V1 |
|---|---|---:|---|---|
| `outside_temp` | `OUTSIDE_TEMP` | C | outside | required |
| `outside_humidity` | `OUTSIDE_HUMIDITY` | % | outside | required |
| `outside_pressure` | `OUTSIDE_PRESSURE` | hPa | outside | optional |
| `wind_speed` | `WIND_SPEED` | m/s | outside | required |
| `wind_direction` | `WIND_DIRECTION` | degrees | outside | required for direction-aware |
| `rain_detected` | `RAIN_DETECTED` | bool | outside | required |
| `outside_light` | `OUTSIDE_LIGHT` | lux или PPFD | outside | required |
| `temperature` | `TEMPERATURE` | C | inside | required |
| `humidity` | `HUMIDITY` | % | inside | required |
| `pressure` | `PRESSURE` | hPa | inside | optional |

`wind_direction` must be meteorological direction: degrees from which wind blows.

### 6.4. Actuator channels

| Канал | Назначение | V1 |
|---|---|---|
| `roof_vent_left` | левая roof-форточка | required |
| `roof_vent_right` | правая roof-форточка | required |

Каноническая команда V1:

```json
{
  "cmd_id": "cmd-...",
  "cmd": "set_position",
  "params": {
    "position_pct": 40,
    "max_step_pct": 25,
    "reason": "temp_high_humidity_high_wind_safe"
  }
}
```

Обязательный response lifecycle:

```text
ACK -> DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT
```

### 6.5. Actuator calibration и homing

Так как есть только концевик полного закрытия, но нет обязательного датчика промежуточной
позиции, V1 должен явно описать actuator semantics:

1. После boot/reconnect actuator-нода должна выполнить или запросить homing до концевика закрытия.
2. `position_pct=0` считается достигнутой только после подтверждения closed limit.
3. Промежуточная позиция `1..100` считается по actuator controller, если нет position telemetry.
4. Нода должна иметь max movement timeout.
5. Если закрытие не достигло концевика за timeout, вернуть `ERROR` и event `VENT_HOMING_FAILED`.
6. Runtime не должен считать target достигнутым без terminal `DONE`.
7. Нужна сервисная команда, если firmware поддерживает ее:

```json
{
  "cmd": "home_closed",
  "params": {
    "timeout_ms": 120000
  }
}
```

Если `home_closed` не поддерживается, homing остается внутренней процедурой actuator-ноды и
должен быть описан в NodeConfig/firmware spec.

---

## 7. Authority Config

### 7.1. Namespace

Основной документ:

```text
automation_config_documents(
  namespace='greenhouse.logic_profile',
  scope_type='greenhouse',
  scope_id={greenhouse_id}
)
```

Для V1 обязательный runtime path: compiled bundle для `scope_type='greenhouse'`.
Raw document read-path в `automation-engine` запрещен. Если это решение будет изменено,
нужно сначала обновить DD-2 и `AUTOMATION_CONFIG_AUTHORITY.md`, затем пересмотреть
runtime tests.

### 7.2. Минимальный payload V1

```json
{
  "active_mode": "working",
  "profiles": {
    "working": {
      "subsystems": {
        "climate": {
          "enabled": true,
          "control_mode": "auto",
          "execution": {
            "decision_interval_sec": 900,
            "emergency_decision_interval_sec": 60,
            "min_command_interval_sec": 300,
            "max_step_pct": 25,
            "position_deadband_pct": 5,
            "min_safe_open_pct": 5,
            "fallback_open_pct": 5,
            "weather_stale_max_open_pct": 20,
            "emergency_open_pct": 100,
            "day_schedule": {
              "start_local": "08:00",
              "end_local": "20:00"
            },
            "daylight_lux_threshold": 15000,
            "night_base_open_pct": 0,
            "night_min_open_pct": 0,
            "night_max_open_pct": 20,
            "day_base_open_pct": 10,
            "day_min_open_pct": 0,
            "day_max_open_pct": 100,
            "temp_full_open_delta_c": 6,
            "rh_full_open_delta_pct": 20,
            "inside_temp_spread_alert_c": 4,
            "inside_rh_spread_alert_pct": 15,
            "cold_guard_margin_c": 1,
            "cold_guard_max_open_pct": 10,
            "outside_hotter_gain": 1.0,
            "outside_wetter_gain": 1.0,
            "wind_reduce_threshold_ms": 8,
            "wind_close_threshold_ms": 12,
            "wind_reduce_windward_max_pct": 25,
            "wind_reduce_leeward_max_pct": 50,
            "wind_storm_windward_max_pct": 0,
            "wind_storm_leeward_max_pct": 10,
            "rain_windward_position_pct": 0,
            "rain_leeward_position_pct": 10,
            "rain_unknown_direction_max_pct": 5,
            "overheat_emergency_temp_c": 38,
            "sensor_freshness_sec": 1200,
            "greenhouse_orientation_deg": null,
            "left_roof_normal_deg": null,
            "right_roof_normal_deg": null,
            "target_policy": "greenhouse_targets",
            "primary_zone_id": null,
            "greenhouse_targets": {
              "temp_min_c": 18,
              "temp_max_c": 28,
              "humidity_min_pct": 50,
              "humidity_max_pct": 75
            },
            "manual_emergency_override_enabled": false,
            "manual_override_max_sec": 86400
          }
        }
      }
    }
  }
}
```

Все поля `execution.*` должны валидироваться backend-ом и редактироваться во frontend.

### 7.3. Минимальные validation rules

Backend registry для `greenhouse.logic_profile` обязан отклонять невалидные документы до
попадания в compiled bundle.

| Поле | Правило V1 |
|---|---|
| `control_mode` | только `auto|semi|manual` |
| все `*_pct` | `0..100` |
| `max_step_pct` | `1..100` |
| `position_deadband_pct` | `0..50`, не больше `max_step_pct` |
| `decision_interval_sec` | `60..3600` |
| `emergency_decision_interval_sec` | `10..decision_interval_sec` |
| `min_command_interval_sec` | `0..3600` |
| `sensor_freshness_sec` | `60..86400` |
| `manual_override_max_sec` | `60..86400` |
| `day_schedule.*_local` | формат `HH:MM`, timezone берется из greenhouse/site config |
| `daylight_lux_threshold` | `0..200000` |
| `wind_close_threshold_ms` | `>= wind_reduce_threshold_ms` |
| `wind_*_max_pct`, `rain_*_pct` | `0..100` |
| `left_roof_normal_deg`, `right_roof_normal_deg`, `greenhouse_orientation_deg` | `null` или `0 <= value < 360` |
| `target_policy` | только `greenhouse_targets|primary_zone|active_zones_strictest` |
| `primary_zone_id` | required только при `target_policy=primary_zone`; зона должна принадлежать этой greenhouse |
| `greenhouse_targets.*` | `temp_min_c <= temp_max_c`, `humidity_min_pct <= humidity_max_pct` |

Если validation не может доказать принадлежность binding/zone к greenhouse, setup считается
неполным и runtime должен fail-closed до публикации команд.

---

## 8. Decision Algorithm V1

### 8.1. Входные данные

Runtime читает напрямую из PostgreSQL:

- greenhouse profile / bundle;
- greenhouse-owned bindings;
- `sensors`;
- `telemetry_last`;
- короткое окно `telemetry_samples` для сглаживания;
- active grow cycles, если target policy использует зоны;
- последнюю greenhouse automation state;
- command statuses.

Runtime не читает hot-path данные через Laravel API.

### 8.2. Freshness

Sensor fresh, если:

```text
effective_ts = COALESCE(telemetry_last.last_ts, telemetry_last.updated_at)
now - effective_ts <= sensor_freshness_sec
last_quality != BAD
```

Если sensor stale, его нельзя использовать для safety clamp, кроме явно разрешенного
last-known fallback. Last-known rain/wind запрещено использовать как hard truth после stale.

### 8.3. Aggregation

Для внутренних датчиков:

1. Отбросить stale/`BAD`/inactive.
2. Считать:
   - `inside_temp_median`;
   - `inside_temp_max`;
   - `inside_temp_min`;
   - `inside_temp_spread`;
   - `inside_rh_median`;
   - `inside_rh_max`;
   - `inside_rh_min`;
   - `inside_rh_spread`.
3. Safety uses max:
   - перегрев по `inside_temp_max`;
   - влажность по `inside_rh_max`.
4. Smooth control uses median.

Если `inside_temp_spread > inside_temp_spread_alert_c` или
`inside_rh_spread > inside_rh_spread_alert_pct`, создать alert
`GREENHOUSE_CLIMATE_SENSOR_SPREAD_HIGH`, но продолжать решение по safety values.

### 8.4. Target policy

V1 default:

```text
target_policy = greenhouse_targets
```

Это снижает риск конфликтов между культурами в разных зонах.

Допустимые V1 policies:

| Policy | Поведение |
|---|---|
| `greenhouse_targets` | цели берутся из `greenhouse.logic_profile.execution.greenhouse_targets` |
| `primary_zone` | цели берутся из активной фазы зоны `primary_zone_id` |
| `active_zones_strictest` | цели считаются пересечением активных зон; если пересечения нет, fallback на greenhouse_targets |

Если `target_policy=primary_zone`, но `primary_zone_id` не задан, зона не принадлежит
greenhouse или активная фаза не дает climate targets, runtime:

1. пишет alert `GREENHOUSE_TARGET_POLICY_INVALID`;
2. использует `greenhouse_targets`;
3. не блокирует emergency overheat.

Для `active_zones_strictest`:

```text
temp_min = max(active_zone.temp_min)
temp_max = min(active_zone.temp_max)
humidity_min = max(active_zone.humidity_min)
humidity_max = min(active_zone.humidity_max)
```

Если `temp_min > temp_max` или `humidity_min > humidity_max`, runtime:

1. пишет alert `GREENHOUSE_TARGET_CONFLICT`;
2. использует `greenhouse_targets`;
3. не блокирует emergency overheat.

### 8.5. Day/night base position

V1 определяет `daylight_mode` по расписанию и освещенности:

```text
schedule_day = local_time in day_schedule.start_local..day_schedule.end_local
daylight_mode = schedule_day OR outside_light >= daylight_lux_threshold
```

Базовая позиция:

```text
if daylight_mode:
  base_open_pct = day_base_open_pct
  min_open_pct = day_min_open_pct
  max_open_pct = day_max_open_pct
else:
  base_open_pct = night_base_open_pct
  min_open_pct = night_min_open_pct
  max_open_pct = night_max_open_pct
```

### 8.6. Temperature component

```text
temp_delta = inside_temp_median - temp_max_c

if temp_delta <= 0:
  temp_open_pct = 0
else:
  temp_open_pct = linear_map(temp_delta, 0..temp_full_open_delta_c, 0..100)
```

Если `outside_temp > inside_temp_median`, V1 все равно открывает форточки, но применяет
`outside_hotter_gain`:

```text
temp_open_pct = temp_open_pct * outside_hotter_gain
```

Default `outside_hotter_gain=1.0`, потому что пользователь явно требует “все равно открывать”.

### 8.7. Humidity component

```text
rh_delta = inside_rh_max - humidity_max_pct

if rh_delta <= 0:
  humidity_open_pct = 0
else:
  humidity_open_pct = linear_map(rh_delta, 0..rh_full_open_delta_pct, 0..100)
```

Если `outside_humidity > inside_rh_max`, V1 все равно открывает форточки, но применяет
`outside_wetter_gain`.

### 8.8. Combine climate demand

```text
requested_open_pct = max(base_open_pct, temp_open_pct, humidity_open_pct)
requested_open_pct = clamp(requested_open_pct, min_open_pct, max_open_pct)
```

Cold guard:

```text
if inside_temp_median <= temp_min_c + cold_guard_margin_c
   and not emergency_overheat:
  requested_open_pct = min(requested_open_pct, cold_guard_max_open_pct)
```

### 8.9. Wind side calculation

`wind_direction` is meteorological degrees: direction from which wind blows.

Для каждой стороны считать angular distance между `wind_direction` и `*_roof_normal_deg`.
Сторона с меньшей дистанцией — наветренная.

Если `left_roof_normal_deg` или `right_roof_normal_deg` не настроены, direction-aware
logic отключается, используется симметричный clamp.

### 8.10. Wind and rain clamps

Wind clamp:

```text
if wind_speed >= wind_close_threshold_ms:
  windward_max_pct = wind_storm_windward_max_pct
  leeward_max_pct = wind_storm_leeward_max_pct
elif wind_speed >= wind_reduce_threshold_ms:
  windward_max_pct = wind_reduce_windward_max_pct
  leeward_max_pct = wind_reduce_leeward_max_pct
else:
  windward_max_pct = 100
  leeward_max_pct = 100
```

Rain clamp:

```text
if rain_detected and direction_known:
  windward_max_pct = min(windward_max_pct, rain_windward_position_pct)
  leeward_max_pct = min(leeward_max_pct, rain_leeward_position_pct)
elif rain_detected:
  left_max_pct = min(left_max_pct, rain_unknown_direction_max_pct)
  right_max_pct = min(right_max_pct, rain_unknown_direction_max_pct)
```

`rain_leeward_position_pct` в V1 является upper bound для подветренной стороны, а не
обязательным minimum. Runtime не должен открывать подветренную форточку только из-за дождя,
если schedule/temp/humidity demand ниже этого значения. Отдельного rain-specific minimum
в V1 нет: минимальное открытие задается day/night min limits, но hard clamps по ветру/дождю
остаются сильнее.

### 8.11. Priority matrix

| Situation | Priority | V1 behavior |
|---|---:|---|
| Manual mode, no active manual override | 1 | Do not send actuator commands |
| Manual mode + `manual_emergency_override_enabled=false` | 1 | Emergency recommendations only, no commands |
| Manual mode + `manual_emergency_override_enabled=true` + overheat | 2 | Allow emergency open within wind/rain hard clamp |
| Command already active | 3 | Do not start parallel command; wait/reconcile |
| Storm wind `>= wind_close_threshold_ms` | 4 | Hard clamp windward/leeward max |
| Rain detected | 5 | Close/limit windward, cap leeward by configured safe maximum |
| Emergency overheat | 6 | Request `emergency_open_pct`, then apply hard clamps |
| Cold guard | 7 | Limit opening unless emergency overheat |
| High humidity | 8 | Increase opening within clamps |
| High temperature | 9 | Increase opening within clamps |
| Schedule/daylight | 10 | Base opening |
| Deadband/min interval | 11 | Suppress non-essential movement |

Lower number means stronger priority. Hard clamps are final upper bounds.

### 8.12. Final target and step limiting

```text
left_raw = requested_open_pct
right_raw = requested_open_pct

left_min_pct = min_open_pct
right_min_pct = min_open_pct
left_max_pct = max_open_pct
right_max_pct = max_open_pct

apply wind/rain side-specific max clamps to left_max_pct/right_max_pct

left_target = clamp(left_raw, left_min_pct, left_max_pct)
right_target = clamp(right_raw, right_min_pct, right_max_pct)

left_next = limit_step(current_left_position_pct, left_target, max_step_pct)
right_next = limit_step(current_right_position_pct, right_target, max_step_pct)

if abs(left_next - current_left_position_pct) < position_deadband_pct:
  suppress left command

if abs(right_next - current_right_position_pct) < position_deadband_pct:
  suppress right command

if now - last_command_at < min_command_interval_sec and not emergency_overheat:
  suppress commands
```

Runtime must write decision snapshot even when commands are suppressed.

---

## 9. Control Modes

### 9.1. `auto`

Runtime calculates recommendation and sends commands.

### 9.2. `semi`

V1 behavior:

- calculate recommendation;
- write state/event;
- do not send commands automatically;
- operator can apply recommendation through manual override/API.

### 9.3. `manual`

V1 behavior:

- automation does not send commands;
- runtime still calculates recommendations and alerts;
- active temporary override may send its explicit command;
- emergency command in manual is allowed only if `manual_emergency_override_enabled=true`.

### 9.4. Temporary manual override

API:

```text
POST /greenhouses/{id}/climate/manual-override
```

Payload:

```json
{
  "left_position_pct": 40,
  "right_position_pct": 40,
  "ttl_sec": 1800,
  "return_mode": "auto",
  "reason": "operator_request"
}
```

Requirements:

1. Persist override in DB.
2. Survive service restart.
3. Write audit trail.
4. Enforce `manual_override_max_sec`.
5. Expire automatically and restore `return_mode`.
6. Commands still go through `history-logger`.

---

## 10. Fallback и аварии

### 10.1. Weather station stale

If external weather stale:

1. Alert `GREENHOUSE_WEATHER_STATION_STALE`.
2. Disable wind/rain direction-aware hard logic.
3. Use schedule + inside climate.
4. Apply conservative max opening `weather_stale_max_open_pct`.
5. If inside sensors also stale, use fallback position.

### 10.2. Inside climate stale

If all inside climate sensors stale:

1. Alert `GREENHOUSE_INSIDE_CLIMATE_STALE`.
2. Use `fallback_open_pct`, capped by current day/night max and by weather stale cap if weather is stale too.
3. Do not execute temp/humidity correction.
4. Do not infer emergency overheat.

### 10.3. Emergency overheat

If `inside_temp_max >= overheat_emergency_temp_c`:

1. Set `emergency_overheat=true`.
2. Request `emergency_open_pct`.
3. Apply wind/rain hard clamps.
4. Use `emergency_decision_interval_sec` for next tick.
5. Alert `GREENHOUSE_OVERHEAT_EMERGENCY`.

### 10.4. Actuator command failure

On `ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED`:

1. Do not update actual position as reached.
2. Write `GREENHOUSE_VENT_COMMAND_FAILED`.
3. Allow no more than one transient retry to `history-logger` on transport error/HTTP 5xx.
4. Fail task closed after retry.
5. Never publish MQTT directly.

---

## 11. Data Model

V1 реализует только DD-1 Option A: отдельные greenhouse runtime tables.
Расширение существующих AE3 tables через `owner_type` в V1 запрещено, чтобы не повышать
риск регрессий в zonal AE3.

### 11.1. Dedicated greenhouse tables

```text
greenhouse_automation_intents
greenhouse_automation_tasks
greenhouse_automation_leases
greenhouse_automation_state
greenhouse_manual_overrides
```

Минимальная ответственность таблиц:

| Таблица | Ответственность |
|---|---|
| `greenhouse_automation_intents` | scheduler/API intent, idempotency, lifecycle `pending|claimed|running|terminal` |
| `greenhouse_automation_tasks` | runtime task, stage, decision snapshot, command refs, terminal outcome |
| `greenhouse_automation_leases` | single-writer lease на `greenhouse_id` |
| `greenhouse_automation_state` | read-model для UI и следующего scheduler tick |
| `greenhouse_manual_overrides` | persistent override с TTL, audit fields и return mode |

Обязательные constraints:

1. Не больше одного active intent/task на `greenhouse_id`.
2. Не больше одной active lease на `greenhouse_id`.
3. `greenhouse_manual_overrides.expires_at` обязателен.
4. `greenhouse_manual_overrides.return_mode` только `auto|semi|manual`.
5. `greenhouse_automation_tasks.task_type` только `greenhouse_climate_tick`.
6. `greenhouse_automation_tasks.status` должен иметь terminal states, совместимые с AE3 status semantics.
7. Все FK должны ссылаться на существующую greenhouse; каскадное удаление runtime history запрещено без явной retention policy.

### 11.2. Rejected for V1: generalized AE owner

Option B (`owner_type='zone'|'greenhouse'`, `owner_id`) остается возможным future
refactor, но не входит в V1. Нельзя частично смешивать Option A и Option B.

### 11.3. State minimum

Read-model для UI должен содержать:

- `greenhouse_id`;
- `control_mode`;
- `left_position_pct`;
- `right_position_pct`;
- `recommended_left_position_pct`;
- `recommended_right_position_pct`;
- `last_sent_left_position_pct`;
- `last_sent_right_position_pct`;
- `decision_reason`;
- `decision_factors` JSON;
- `weather_fresh`;
- `inside_climate_fresh`;
- `active_manual_override_id`;
- `next_scheduled_tick_at`;
- `last_task_id`;
- `last_error_code`;
- `last_error_message`;
- `active_alerts_summary`;
- `last_decision_at`;
- `last_command_at`;
- `updated_at`.

---

## 12. API и Frontend

### 12.1. API V1

Нужны endpoints:

```text
GET /api/greenhouses/{id}/climate/state
POST /api/greenhouses/{id}/climate/control-mode
POST /api/greenhouses/{id}/climate/manual-override
DELETE /api/greenhouses/{id}/climate/manual-override
```

Authority config остается через:

```text
GET /api/automation-configs/greenhouse/{id}/greenhouse.logic_profile
PUT /api/automation-configs/greenhouse/{id}/greenhouse.logic_profile
```

Automation-engine internal endpoint:

```text
POST /greenhouses/{id}/start-climate-tick
```

### 12.2. Frontend V1

Frontend должен дать оператору:

1. Enable/disable greenhouse climate.
2. Control mode `auto|semi|manual`.
3. Decision interval, default `900s`.
4. Emergency interval.
5. `max_step_pct`, default `25`.
6. Deadband and min command interval.
7. Day/night base/min/max positions.
8. Daylight lux threshold.
9. Wind thresholds and wind clamp values.
10. Rain clamp values.
11. Emergency overheat threshold.
12. Sensor freshness and stale fallback caps.
13. Sensor spread alert thresholds.
14. Greenhouse orientation / left-right roof normals.
15. Target policy, `primary_zone_id` and greenhouse-level targets.
16. Manual override with TTL.
17. Current state and decision reasons.

UI должен показывать reason в операторском виде, например:

```text
Температура высокая + влажность высокая + ветер 6.2 м/с, дождя нет.
Рекомендация: левая 55%, правая 55%.
Команда ограничена max_step_pct: отправлено 35%.
```

---

## 13. Events, Alerts, Metrics

Events:

- `GREENHOUSE_CLIMATE_TICK_STARTED`;
- `GREENHOUSE_CLIMATE_DECISION`;
- `GREENHOUSE_VENT_POSITION_CHANGED`;
- `GREENHOUSE_WEATHER_STATION_STALE`;
- `GREENHOUSE_INSIDE_CLIMATE_STALE`;
- `GREENHOUSE_CLIMATE_SENSOR_SPREAD_HIGH`;
- `GREENHOUSE_TARGET_CONFLICT`;
- `GREENHOUSE_TARGET_POLICY_INVALID`;
- `GREENHOUSE_OVERHEAT_EMERGENCY`;
- `GREENHOUSE_WIND_CLAMP_ACTIVE`;
- `GREENHOUSE_RAIN_CLAMP_ACTIVE`;
- `GREENHOUSE_VENT_COMMAND_FAILED`;
- `VENT_HOMING_FAILED`.

Metrics:

- `greenhouse_climate_tick_total`;
- `greenhouse_climate_command_total`;
- `greenhouse_climate_decision_duration_seconds`;
- `greenhouse_climate_sensor_stale_total`;
- `greenhouse_climate_wind_clamp_total`;
- `greenhouse_climate_rain_clamp_total`;
- `greenhouse_climate_command_failed_total`.

Alert lifecycle must follow Python/AE3 producer -> Laravel alert API, not direct DB writes
to lifecycle alert tables.

---

## 14. Implementation Order For AI Agent

ИИ-агент обязан выполнять этапы последовательно. Нельзя начинать следующий этап, если
предыдущий не закрыт тестом или явным documented blocker.

### Stage 0. Confirm design decisions

Deliverable:

- обновленный раздел `Design Decisions Required Before Implementation`;
- список выбранных решений DD-1..DD-9;
- явная отметка, что Option A является единственным вариантом data model для V1.

Stop condition:

- если хотя бы одно обязательное решение не принято или противоречит layer-spec,
  не писать код runtime.

### Stage 1. Spec updates

Синхронизировать и при необходимости обновить:

1. `doc_ai/04_BACKEND_CORE/ae3lite.md`;
2. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`;
3. `doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md`;
4. `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`;
5. `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`;
6. `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`;
7. `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`;
8. `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`;
9. `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`;
10. `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`;
11. `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`;
12. frontend docs.

Stage 1 считается закрытым только если в этих документах нет противоречий по:

1. task type `greenhouse_climate_tick`;
2. endpoint `POST /greenhouses/{id}/start-climate-tick`;
3. отдельным таблицам `greenhouse_automation_*`;
4. MQTT topic segment `{zone}` через anchor-zone из `nodes.zone_id`;
5. команде actuator-а `set_position`;
6. запрету direct MQTT publish из Laravel/AE.

### Stage 2. Database and authority

1. Laravel migrations only.
2. Registry schema for `greenhouse.logic_profile`.
3. Validation rules and config violations.
4. Manual override persistence.
5. State read-model.

### Stage 3. Backend API

1. Greenhouse climate state endpoint.
2. Control mode endpoint.
3. Manual override create/delete.
4. Setup validation for greenhouse climate bindings.
5. API tests.

### Stage 4. Automation-engine

1. `GreenhouseClimateRunner`.
2. `POST /greenhouses/{id}/start-climate-tick`.
3. Greenhouse single-writer lease.
4. DB-first read-model.
5. Decision algorithm V1.
6. Command gateway via `history-logger`.
7. Command reconcile.
8. Startup recovery.
9. Unit/integration tests.

### Stage 5. Scheduler dispatch

1. Laravel scheduler creates greenhouse climate intents.
2. Scheduler wakes AE endpoint.
3. Active greenhouse task backpressure is not operational failure.
4. Scheduler tests.

### Stage 6. Frontend

1. Config editor.
2. State view.
3. Manual override UI.
4. Validation and error display.
5. Frontend tests.

### Stage 7. End-to-end verification

1. Telemetry ingest -> decision -> command row.
2. `history-logger` publish path.
3. Command response reconcile.
4. UI state reflects decision and command result.

---

## 15. Test Matrix

### 15.1. Algorithm unit tests

Required cases:

1. Normal daytime schedule, no correction.
2. Night limits applied.
3. Light sensor forces daytime behavior.
4. High temperature opens.
5. High humidity opens.
6. High temp + outside hotter still opens.
7. High humidity + outside wetter still opens.
8. Cold guard limits opening.
9. Emergency overheat overrides cold guard.
10. Wind reduce threshold clamps.
11. Wind close threshold clamps.
12. Rain + known wind direction closes windward.
13. Rain + unknown direction applies symmetric clamp.
14. Stale weather disables wind/rain hard logic.
15. Stale inside sensors uses fallback.
16. Sensor spread high creates alert.
17. Target conflict falls back to greenhouse targets.
18. Invalid `primary_zone` policy falls back to greenhouse targets.
19. Weather stale applies `weather_stale_max_open_pct`.
20. `max_step_pct` limits movement.
21. Deadband suppresses small movement.
22. Min command interval suppresses non-emergency movement.
23. Manual mode sends no command.
24. Semi mode sends no command, writes recommendation.
25. Manual override sends explicit command.
26. Manual emergency override disabled sends no emergency command.
27. Manual emergency override enabled sends emergency command within clamps.

### 15.2. Integration tests

1. AE calls `history-logger POST /commands`, not MQTT.
2. `ACK` is non-terminal.
3. `DONE` updates state.
4. `ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED` fail task.
5. One transient retry only on `history-logger` transport error/HTTP 5xx.
6. Startup recovery handles running greenhouse task.
7. Single-writer prevents two active greenhouse climate ticks.

### 15.3. API tests

1. Config validation rejects invalid percentages.
2. Wind thresholds require `close >= reduce`.
3. Manual override TTL capped by `manual_override_max_sec`.
4. Unauthorized roles rejected.
5. State endpoint returns stale flags.
6. `primary_zone_id` validation rejects zone from another greenhouse.
7. Day schedule rejects invalid `HH:MM`.
8. Greenhouse setup validation fails without two required vent actuator bindings.

### 15.4. Frontend tests

1. Settings save through authority API.
2. Invalid settings show validation errors.
3. State view shows current/recommended/sent positions.
4. Manual override form sends TTL and target positions.
5. Semi mode shows recommendation without auto-command wording.

---

## 16. Acceptance Criteria

V1 считается готовой только если:

1. Все protocol/data/API/spec docs обновлены.
2. Нет прямого MQTT publish из Laravel или automation-engine.
3. Greenhouse climate не запускается через zone endpoint.
4. Single-writer на greenhouse level покрыт тестами.
5. V1 использует только dedicated tables `greenhouse_automation_*` / `greenhouse_manual_overrides`.
6. Algorithm unit tests покрывают test matrix.
7. Commands go through history-logger and reconcile terminal statuses.
8. Frontend позволяет редактировать все V1 thresholds.
9. UI показывает current/recommended/sent positions and reasons.
10. Manual override переживает restart и истекает по TTL.
11. Fallback/stale sensor behavior покрыт тестами.
12. Emergency overheat behavior покрыт тестами.

---

## 17. Explicit Non-Goals

1. Не реализовывать ML/AI adaptive control в V1.
2. Не реализовывать зональные climate actuator-ы в V1.
3. Не добавлять прямой MQTT publish.
4. Не использовать `POST /zones/{id}/start-cycle` для greenhouse climate.
5. Не читать hot-path runtime данные через Laravel API.
6. Не менять telemetry field types без синхронного обновления всех спецификаций.
