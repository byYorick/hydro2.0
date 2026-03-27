# CORRECTION_CYCLE_SPEC.md
# Спецификация циклов коррекции раствора

Документ описывает state machine, режимы коррекции и логику управления измерением pH/EC с учетом необходимости наличия потока раствора.

**Дата создания:** 2026-02-14
**Статус:** Рабочий документ (требует валидации)

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

Актуализация authority / AE3 (2026-03-24):
- команды к нодам идут только через `history-logger /commands`;
- запуск цикла автоматики выполняется через `POST /zones/{id}/start-cycle`;
- runtime-резолв target/config выполняется через SQL read-model (effective-targets API не используется в runtime path).

Актуализация AE3 in-flow correction (2026-03-15):
- correction decision больше не строится по одному `telemetry_last` sample;
- для `EC` и `pH` используется модель `dose -> hold -> observe -> decide`;
- окно наблюдения собирается из `telemetry_samples`, а не из одного текущего значения;
- на входе в correction-window planner может одновременно определить потребность и в `EC`, и в `pH`;
- выполнение доз остаётся последовательным: между `EC` и `pH` обязателен повторный `observe-step`;
- если planner видит одновременно `EC` и `pH`, обе потребности остаются в одном correction-window и не требуют повторного входа parent-stage;
- `3` consecutive `no-effect` для одного `pid_type` дают alert и fail-closed ветку correction window;
- обычные correction attempts и `no-effect` attempts — независимые лимиты.

---

## 1. Проблема и решение

### 1.1. Проблема

**Измерения pH и EC достоверны только при наличии потока раствора через датчики.**

Без потока:
- Датчики измеряют стоячий раствор
- Показания могут быть неточными
- Стратификация раствора в баке
- Коррекция на основе таких данных приводит к ошибкам

### 1.2. Решение

**Ноды pH и EC работают в двух режимах:**

1. **IDLE (ожидание)** — без активации
   - Отправляют только heartbeat и LWT
   - НЕ отправляют telemetry сенсоров
   - НЕ принимают команды коррекции

2. **ACTIVE (активный)** — после активации
   - Сразу начинают отправлять telemetry
   - После стабилизации разрешают коррекцию
   - Automation-engine управляет активацией

**Активация нод происходит когда:**
- Включается поток раствора (pump_in или circulation_pump)
- Начинается режим коррекции

**Деактивация нод происходит когда:**
- Поток останавливается
- Режим коррекции завершен

---

## 2. State Machine зоны коррекции

### 2.1. Состояния (Zone Correction States)

```
┌──────────────┐
│   IDLE       │  ◄─── Начальное состояние
│              │       Нет потока, датчики неактивны
└──────┬───────┘
       │ start_tank_fill
       │
       ▼
┌──────────────┐
│ TANK_FILLING │  ◄─── Набор бака с раствором
│              │       Поток активен, NPK + pH коррекция
└──────┬───────┘
       │ targets_not_achieved
       │
       ▼
┌──────────────┐
│ TANK_RECIRC  │  ◄─── Рециркуляция бака
│              │       До достижения целевых NPK + pH
└──────┬───────┘
       │ targets_achieved
       │
       ▼
┌──────────────┐
│  READY       │  ◄─── Раствор готов
│              │       Ожидание полива
└──────┬───────┘
       │ start_irrigation
       │
       ▼
┌──────────────┐
│ IRRIGATING   │  ◄─── Полив зоны
│              │       Ca/Mg/микро + pH коррекция
└──────┬───────┘
       │ targets_not_achieved OR need_correction
       │
       ▼
┌──────────────┐
│ IRRIG_RECIRC │  ◄─── Рециркуляция при поливе
│              │       До достижения Ca/Mg/микро + pH
└──────┬───────┘
       │ targets_achieved OR irrigation_complete
       │
       ▼
     IDLE или READY
```

### 2.2. Описание состояний

| Состояние | Поток | pH/EC активны | Коррекция | Типы корр-и |
|-----------|-------|---------------|-----------|-------------|
| **IDLE** | ❌ Нет | ❌ Нет | ❌ Нет | - |
| **TANK_FILLING** | ✅ Да | ✅ Да | ✅ Да | NPK, pH |
| **TANK_RECIRC** | ✅ Да | ✅ Да | ✅ Да | NPK, pH |
| **READY** | ❌ Нет | ❌ Нет | ❌ Нет | - |
| **IRRIGATING** | ✅ Да | ✅ Да | ✅ Да | Ca/Mg/микро, pH |
| **IRRIG_RECIRC** | ✅ Да | ✅ Да | ✅ Да | Ca/Mg/микро, pH |

### 2.3. События (Triggers)

| Событие | Описание | Откуда |
|---------|----------|--------|
| `start_tank_fill` | Начать набор бака | Scheduler / Manual |
| `start_irrigation` | Начать полив | Scheduler / Manual |
| `targets_achieved` | Целевые значения достигнуты | Automation-engine |
| `targets_not_achieved` | Целевые значения НЕ достигнуты | Automation-engine |
| `need_correction` | Нужна коррекция во время полива | Automation-engine |
| `irrigation_complete` | Полив завершен | Pump node |
| `timeout` | Таймаут режима | Automation-engine |
| `error` | Ошибка (нет данных, нет нод) | Automation-engine |

---

## 3. Режимы коррекции

### 3.0. Базовый runtime-контракт correction sub-machine

Для `EC` и `pH` действует единая семантика:

1. `dose` — отправляется одна доза;
2. `hold` — до `hold_until` новые решения запрещены;
3. `observe` — после `transport_delay_sec` собирается окно samples из `telemetry_samples`;
4. `decide` — по агрегированному отклику (`median`/устойчивое окно), а не по одному sample,
   принимается решение `done / next dose / no-effect / exhausted`.

Обязательные правила:
- `transport_delay_sec` и `settle_sec` берутся из authority-документов `zone.process_calibration.*`;
- runtime phase нормализуется к canonical process-calibration key:
  `tank_filling -> solution_fill`,
  `prepare_recirculation -> tank_recirc`,
  `irrigating|irrig_recirc -> irrigation`;
- если process calibration отсутствует, новый in-flow correction path идёт fail-closed;
- `zone.correction.payload.resolved_config` считается полным runtime-контрактом:
  если обязательный correction/runtime/tolerance/controller parameter отсутствует,
  correction path идёт fail-closed и не добирает значение из seed/default или
  legacy `diagnostics.execution.*`;
- `telemetry_max_age_sec` должен быть согласован с фактической частотой telemetry;
- для production in-flow режима ожидается telemetry cadence порядка `2 сек`;
- если в `corr_check` или `corr_wait_{ec|ph}` telemetry временно stale/unavailable,
  correction path не падает сразу, а перепланирует тот же шаг с retry delay
  `retry.telemetry_stale_retry_sec`;
- если decision-window ещё не готово (`insufficient_samples` / `unstable`) или пришло non-finite значение,
  correction path перепланирует повторную проверку в рамках текущего stage/window
  через `retry.decision_window_retry_sec`, без silent success;
- если correction временно заблокирован по low-water guard, повторная проверка идёт через
  `retry.low_water_retry_sec`;
- retry из `min_interval_sec`, stale telemetry и unready decision-window не образует автономный бесконечный loop:
  correction sub-machine всегда ограничен parent stage deadline, а для `prepare_recirculation`
  ещё и `prepare_recirculation_max_attempts` на уровне окон;
- `EC` и `pH` имеют отдельные `no_effect_count`, отдельные process gains и отдельные observation thresholds.
- В `prepare_recirculation` EC-планирование консервативно: learned `pid_state`
  может улучшать оценку, но не может опускать `EC gain` ниже authoritative
  `process_calibrations.tank_recirc.ec_gain_per_ml` floor.
- если planner одновременно вернул `needs_ec=true` и `needs_ph_{up|down}=true`, runtime обязан сохранить оба действия
  в `CorrectionState`; первым исполняется ближайший шаг sub-machine, а второй остаётся в том же correction-window
  до следующего `corr_check` после обязательного `observe-step`.
- каждый ready `observe` шаг обязан писать zone-event с `baseline_value`, `observed_value`,
  `actual_effect`, `expected_effect`, `threshold_effect` и итогом `is_no_effect`, чтобы
  exhaustion/no-effect диагностика была читаема без ручного анализа telemetry SQL.
- runtime PID-тюнинг использует zoned PID-профили из `zone.pid.{ph|ec}`:
  `dead_zone` задаёт deadband, а `zone_coeffs.close|far` выбираются по величине текущего gap
  (`<= close_zone` -> close, `> close_zone` -> far), чтобы далеко от target дозы были грубее,
  а при приближении к target — мягче.
- `zone.pid.*` не содержит target, `max_output` или `min_interval_ms`:
  target берётся только из recipe phase, а дозовые лимиты/интервалы — только из
  `zone.correction.resolved_config.controllers.*`.
- `cycle.phase_overrides`, `cycle.manual_overrides` и `zone.logic_profile` не могут менять
  canonical `target_ph/target_ec` и их windows; runtime допускает из них только execution/config
  параметры, не chemical setpoints.
- `no-effect` определяется по факту наблюдаемой реакции на дозу (`peak_effect` в observe-window),
  а не только по tail-median; это нужно для проточных систем, где отклик может быть волнообразным.
- learned runtime metrics (`gain_ema`, `retention_ema`, `wave_score_ema`, learned timing) сохраняются
  в `pid_state.stats` и переживают рестарт automation-engine.

### 3.1. Режим 1: TANK_FILLING (Набор бака)

**Цель:** Набрать бак с раствором; пока бак не полон, выполнять in-flow коррекцию NPK + pH.
Если к моменту заполнения бака targets не достигнуты, переводить зону в `TANK_RECIRC`.

**Последовательность:**
```
1. Automation-engine → MQTT: activate ph_node, ec_node
2. Automation-engine → MQTT: start pump_in (набор бака)
3. Ожидание стабилизации (60-120 сек, настраиваемо)
4. pH/EC ноды → MQTT: telemetry с flow_active: true, stable: false
5. После стабилизации: stable: true
6. Пока `solution_max` ещё не сработал, Automation-engine:
   - читает observation window для EC/pH;
   - в рамках одного correction-window может одновременно держать план и по `EC`, и по `pH`;
   - исполняет дозы последовательно: сначала ближайший шаг correction sub-machine, затем `observe`, затем следующий химический шаг;
   - parent-stage не создаёт новое correction-window на каждом таком шаге: весь fill-stage работает в одном окне коррекции.
7. Возврат correction в `solution_fill_check` не открывает новый timeout-window:
   - действует исходный `solution_fill_timeout_sec` для всего stage целиком.
   - attempt-based exhaustion внутри `solution_fill` не должна останавливать коррекцию раньше времени:
     stage остаётся в одном correction window до `solution_fill_timeout_sec` либо до fail-closed по `no-effect`.
8. Когда `solution_max` сработал:
   - если targets достигнуты → `READY`, stop fill, deactivate sensors;
   - если targets НЕ достигнуты → stop fill и переход в `TANK_RECIRC`.
```

**Коррекция:**
- NPK (EC): in-flow дозирование на этапе набора раствора через `dose -> hold -> observe -> decide`
- pH: pH+ или pH- через тот же observation-driven цикл
- После достижения `solution_max` дополнительная коррекция в `TANK_FILLING` не продолжается:
  дальнейшее доведение до targets происходит только в `TANK_RECIRC`

### 3.2. Режим 2: TANK_RECIRC (Рециркуляция бака)

**Цель:** Циркулировать раствор до достижения целевых NPK + pH.

**Последовательность:**
```
1. pH/EC ноды уже активны (из TANK_FILLING)
2. Automation-engine → MQTT: start circulation_pump (рециркуляция)
3. Ожидание стабилизации (30 сек, короче чем при filling)
4. Повторение шагов 6-7 из TANK_FILLING
   - внутри одного `prepare_recirculation` correction-window planner так же может одновременно держать потребность
     и в `EC`, и в `pH`;
   - runtime не разводит их по разным recirculation windows: химические шаги идут последовательно
     (`EC -> observe -> pH` или `pH -> observe -> EC`) в рамках того же окна, пока не сработает
     success / no-effect fail-closed / deadline текущего recirculation window
5. Если targets достигнуты после N timeout-window:
   - → Состояние READY
   - Automation-engine → MQTT: stop circulation_pump
   - Automation-engine → MQTT: deactivate ph_node, ec_node
6. Внутри каждого window используются независимые лимиты `max_ec_correction_attempts` и `max_ph_correction_attempts`
   плюс верхний guard `prepare_recirculation_max_correction_attempts`;
   если верхний guard не задан, runtime использует `max(max_ec_correction_attempts, max_ph_correction_attempts)`,
   но никогда не превышает соответствующие per-PID лимиты
7. Если текущий window исчерпан без достижения targets:
   - остановить recirculation
   - перезапустить следующий window, пока не исчерпан `prepare_recirculation_max_attempts`
   - timeout window ограничивает не только `corr_check`, но и весь активный correction sub-machine;
     при истечении deadline текущий correction window должен быть немедленно прерван
8. Если targets НЕ достигнуты после исчерпания `prepare_recirculation_max_attempts`:
   - → Состояние IDLE (с ошибкой)
   - terminal error: `prepare_recirculation_attempt_limit_reached`
   - alert code: `biz_prepare_recirculation_retry_exhausted`
```

Дополнение по fail-closed:
- если один и тот же `EC` или `pH` contour трижды подряд не даёт наблюдаемого отклика,
  correction window завершается alert-ом `no-effect`;
- `no-effect` не равен обычной недокоррекции: при наличии физического отклика correction может
  продолжаться большим числом малых доз до общего attempt/time limit.

**Макс timeout-window:** 5
**Интервал между попытками:** 2 мин

### 3.3. Режим 3: IRRIGATING (Полив)

**Цель:** Поливать зону и корректировать Ca/Mg/микро + pH по необходимости.

**Последовательность:**
```
1. Automation-engine → MQTT: activate ph_node, ec_node
2. Automation-engine → MQTT: start pump_in (полив)
3. Ожидание стабилизации (30 сек, быстрая)
4. pH/EC ноды → MQTT: telemetry с flow_active: true
5. Automation-engine: проверка pH во время полива
   - Если pH вне диапазона: дозирование pH+/pH-
   - Минимальный интервал между дозами: 5 мин
6. Automation-engine: проверка Ca/Mg/микро (optional)
   - Если EC ниже нормы: дозирование Ca/Mg
7. Полив продолжается до завершения (по volume_ml или duration_sec)
8. После завершения полива:
   - Если pH/EC в норме:
     - → Состояние IDLE
     - Automation-engine → MQTT: deactivate ph_node, ec_node
   - Если pH/EC вне нормы:
     - → Состояние IRRIG_RECIRC
```

**Коррекция:**
- Ca/Mg/микро: При необходимости (опционально)
- pH: При отклонении во время полива (приоритет)

### 3.4. Режим 4: IRRIG_RECIRC (Рециркуляция при поливе)

**Цель:** Быстро скорректировать pH и Ca/Mg после полива.

**Последовательность:**
```
1. pH/EC ноды уже активны (из IRRIGATING)
2. Automation-engine → MQTT: stop pump_in
3. Automation-engine → MQTT: start circulation_pump
4. Ожидание стабилизации (30 сек)
5. Коррекция pH (приоритет) и Ca/Mg если нужно
6. Максимум 2 попытки
7. После достижения targets или timeout:
   - → Состояние IDLE
   - Automation-engine → MQTT: stop circulation_pump
   - Automation-engine → MQTT: deactivate ph_node, ec_node
```

**Макс попытки:** 2
**Интервал:** 1 мин

---

## 4. Команды активации/деактивации нод

### 4.1. Команда ACTIVATE (для ph_node, ec_node)

**Topic:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload:**
```json
{
  "cmd": "activate_sensor_mode",
  "params": {
    "stabilization_time_sec": 60  // Время до stable: true
  },
  "cmd_id": "cmd-activate-123",
  "ts": 1710001234,
  "sig": "a1b2c3..."
}
```

**Действия ноды после получения:**
1. Переход в режим ACTIVE
2. Начать отправку telemetry каждые 5 сек
3. В первых сообщениях: `stable: false`
4. Через `stabilization_time_sec`: `stable: true`
5. Разрешить команды дозирования (если есть)

**Telemetry во время активации:**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001234,
  "flow_active": true,    // ← поток активен
  "stable": false,        // ← еще не стабилизировалось
  "stabilization_progress_sec": 15  // ← прогресс стабилизации
}
```

После стабилизации:
```json
{
  "metric_type": "PH",
  "value": 5.92,
  "ts": 1710001294,
  "flow_active": true,
  "stable": true,         // ← стабилизировалось!
  "corrections_allowed": true  // ← можно дозировать
}
```

### 4.2. Команда DEACTIVATE

**Topic:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload:**
```json
{
  "cmd": "deactivate_sensor_mode",
  "params": {},
  "cmd_id": "cmd-deactivate-456",
  "ts": 1710002000,
  "sig": "b2c3d4..."
}
```

**Действия ноды после получения:**
1. Переход в режим IDLE
2. Прекратить отправку telemetry сенсоров
3. Отправлять только heartbeat и LWT
4. Игнорировать команды дозирования (если будут)

### 4.3. Новый topic для system команд

Для команд управления режимом (не относятся к каналам):

**Format:** `hydro/{gh}/{zone}/{node}/system/command`

**Примеры:**
- `hydro/gh-1/zn-1/nd-ph-1/system/command`
- `hydro/gh-1/zn-1/nd-ec-1/system/command`

### 4.4. Диаграмма жизненного цикла сенсорной ноды

Визуализация переходов между режимами IDLE и ACTIVE для pH/EC нод:

```
         SENSOR NODE LIFECYCLE (pH/EC nodes)

              ┌────────────────────────┐
              │        IDLE            │
              │                        │
              │ Режим ожидания:        │
              │ • Нет измерений        │
              │ • Нет telemetry        │
              │ • Только heartbeat     │
              │ • LWT активен          │
              └───────────┬────────────┘
                          │
                          │ activate_sensor_mode
                          │ {stabilization_time_sec: 90}
                          │
                          ▼
              ┌────────────────────────┐
              │       ACTIVE           │
              │                        │
              │ ┌────────────────────┐ │
              │ │  Stabilizing       │ │
              │ │  (0-90 sec)        │ │
              │ │                    │ │
              │ │  • Измерения ON    │ │
              │ │  • Telemetry ON    │ │
              │ │  • flow_active:    │ │
              │ │    true            │ │
              │ │  • stable: false   │ │
              │ │  • corrections_    │ │
              │ │    allowed: false  │ │
              │ │                    │ │
              │ │  Прогресс:         │ │
              │ │  stabilization_    │ │
              │ │  progress_sec:     │ │
              │ │  0→15→30→60→90     │ │
              │ └──────┬─────────────┘ │
              │         │               │
              │         │ Время прошло  │
              │         │ (90 sec)      │
              │         │               │
              │         ▼               │
              │ ┌────────────────────┐ │
              │ │  Stable & Ready    │ │
              │ │  for corrections   │ │
              │ │                    │ │
              │ │  • Измерения ON    │ │
              │ │  • Telemetry ON    │ │
              │ │  • flow_active:    │ │
              │ │    true            │ │
              │ │  • stable: true    │ │
              │ │  • corrections_    │ │
              │ │    allowed: true   │ │
              │ │                    │ │
              │ │  Automation-engine │ │
              │ │  может дозировать! │ │
              │ └────────────────────┘ │
              └───────────┬────────────┘
                          │
                          │ deactivate_sensor_mode
                          │ {}
                          │
                          ▼
              ┌────────────────────────┐
              │        IDLE            │
              │                        │
              │ Возврат в ожидание:    │
              │ • Измерения OFF        │
              │ • Telemetry OFF        │
              │ • Только heartbeat     │
              └────────────────────────┘


      Управляющие команды:

      ┌─────────────────────────────────────────────────────┐
      │  MQTT Topic:                                        │
      │  hydro/{gh}/{zone}/{node}/system/command            │
      │                                                     │
      │  Commands:                                          │
      │  • activate_sensor_mode   → IDLE → ACTIVE          │
      │  • deactivate_sensor_mode → ACTIVE → IDLE          │
      └─────────────────────────────────────────────────────┘
```

**Ключевые моменты:**

1. **IDLE режим:** Экономия ресурсов (нет измерений, нет MQTT трафика)
2. **Stabilizing период:** Сенсор адаптируется к потоку, измерения ещё неточные
3. **Stable режим:** Можно доверять измерениям и выполнять коррекции
4. **Переходы управляются automation-engine** через системные команды

**Применение в correction cycle:**

| Переход state machine | Команда ноде |
|-----------------------|--------------|
| IDLE → TANK_FILLING | `activate_sensor_mode` (90s) |
| TANK_FILLING → TANK_RECIRC | Нода остается ACTIVE (30s) |
| READY → IDLE | `deactivate_sensor_mode` |
| READY → IRRIGATING | `activate_sensor_mode` (30s) |
| IRRIG_RECIRC → IDLE | `deactivate_sensor_mode` |

---

## 5. Временные параметры (семантика effective-targets, источник runtime — authority bundle)

### 5.1. Параметры стабилизации

```typescript
interface CorrectionTimings {
  // Время стабилизации после активации
  tank_fill_stabilization_sec: number;     // По умолчанию: 90
  tank_recirc_stabilization_sec: number;   // По умолчанию: 30
  irrigation_stabilization_sec: number;    // По умолчанию: 30
  irrig_recirc_stabilization_sec: number;  // По умолчанию: 30

  // Время ожидания после дозирования
  npk_mix_time_sec: number;                // По умолчанию: 120
  ph_mix_time_sec: number;                 // По умолчанию: 60
  ca_mg_mix_time_sec: number;              // По умолчанию: 90

  // Интервалы коррекции
  min_correction_interval_sec: number;     // По умолчанию: 300 (5 мин)

  // Макс попытки
  max_tank_recirc_attempts: number;        // По умолчанию: 5
  max_irrig_recirc_attempts: number;       // По умолчанию: 2

  // Timeout режимов
  tank_fill_timeout_sec: number;           // По умолчанию: 1800 (30 мин)
  tank_recirc_timeout_sec: number;         // По умолчанию: 3600 (1 час)
  irrigation_timeout_sec: number;          // По умолчанию: 600 (10 мин)
}
```

### 5.2. Derived shape в effective-targets

Эти параметры могут публиковаться в derived `effective-targets` для диагностики и integration tooling.
В runtime automation-engine эквивалентные значения читаются из compiled authority bundle
(`zone.correction.resolved_config` + `zone.process_calibration.*`):

```json
{
  "cycle_id": 123,
  "targets": {
    "ph": {...},
    "ec": {...},
    "correction_timings": {
      "tank_fill_stabilization_sec": 90,
      "tank_recirc_stabilization_sec": 30,
      "irrigation_stabilization_sec": 30,
      "npk_mix_time_sec": 120,
      "ph_mix_time_sec": 60,
      "min_correction_interval_sec": 300,
      "max_tank_recirc_attempts": 5,
      "max_irrig_recirc_attempts": 2
    }
  }
}
```

---

## 6. Логика automation-engine

### 6.1. Новый компонент: CorrectionStateMachine

```python
class CorrectionStateMachine:
    """
    State machine для управления циклами коррекции зоны.
    """

    def __init__(self, zone_id: int):
        self.zone_id = zone_id
        self.state: CorrectionState = CorrectionState.IDLE
        self.attempt_count = 0
        self.last_correction_ts = None
        self.ph_ec_nodes_active = False

    async def transition(self, event: CorrectionEvent):
        """Обработка события и переход в новое состояние."""
        new_state = self._get_next_state(self.state, event)
        await self._on_exit_state(self.state)
        self.state = new_state
        await self._on_enter_state(new_state)

    async def _on_enter_state(self, state: CorrectionState):
        """Действия при входе в состояние."""
        if state == CorrectionState.TANK_FILLING:
            await self._activate_ph_ec_nodes()
            await self._start_pump("pump_in")
            await self._wait_stabilization("tank_fill")

        elif state == CorrectionState.TANK_RECIRC:
            await self._start_pump("circulation_pump")
            await self._wait_stabilization("tank_recirc")
            self.attempt_count = 0

        elif state == CorrectionState.READY:
            await self._deactivate_ph_ec_nodes()
            await self._stop_all_pumps()

        elif state == CorrectionState.IRRIGATING:
            await self._activate_ph_ec_nodes()
            await self._start_pump("pump_in")
            await self._wait_stabilization("irrigation")

        elif state == CorrectionState.IRRIG_RECIRC:
            await self._stop_pump("pump_in")
            await self._start_pump("circulation_pump")
            await self._wait_stabilization("irrig_recirc")
            self.attempt_count = 0

        elif state == CorrectionState.IDLE:
            await self._deactivate_ph_ec_nodes()
            await self._stop_all_pumps()

    async def _activate_ph_ec_nodes(self):
        """Активация pH и EC нод."""
        timings = await self._get_correction_timings()

        # Активировать pH ноду
        await send_command(
            node_uid="nd-ph-1",
            topic_suffix="system/command",
            cmd="activate_sensor_mode",
            params={
                "stabilization_time_sec": timings.get("tank_fill_stabilization_sec", 90)
            }
        )

        # Активировать EC ноду
        await send_command(
            node_uid="nd-ec-1",
            topic_suffix="system/command",
            cmd="activate_sensor_mode",
            params={
                "stabilization_time_sec": timings.get("tank_fill_stabilization_sec", 90)
            }
        )

        self.ph_ec_nodes_active = True

    async def _deactivate_ph_ec_nodes(self):
        """Деактивация pH и EC нод."""
        await send_command(
            node_uid="nd-ph-1",
            topic_suffix="system/command",
            cmd="deactivate_sensor_mode"
        )

        await send_command(
            node_uid="nd-ec-1",
            topic_suffix="system/command",
            cmd="deactivate_sensor_mode"
        )

        self.ph_ec_nodes_active = False

    async def check_and_correct(self):
        """Проверка и коррекция pH/EC в текущем состоянии."""
        if self.state == CorrectionState.TANK_FILLING:
            await self._correct_npk_and_ph()

        elif self.state == CorrectionState.TANK_RECIRC:
            success = await self._correct_npk_and_ph()
            self.attempt_count += 1

            if success:
                await self.transition(CorrectionEvent.TARGETS_ACHIEVED)
            elif self.attempt_count >= self._get_max_attempts("tank_recirc"):
                await self.transition(CorrectionEvent.TIMEOUT)

        elif self.state == CorrectionState.IRRIGATING:
            await self._correct_ph()  # Только pH во время полива
            # Ca/Mg опционально

        elif self.state == CorrectionState.IRRIG_RECIRC:
            success = await self._correct_ph()
            self.attempt_count += 1

            if success or self.attempt_count >= self._get_max_attempts("irrig_recirc"):
                await self.transition(CorrectionEvent.IRRIGATION_COMPLETE)

    async def _correct_npk_and_ph(self) -> bool:
        """Коррекция NPK (EC) и pH."""
        # Получить текущую телеметрию
        telemetry = await get_stable_telemetry(self.zone_id)
        if not telemetry or not telemetry.stable:
            return False

        targets = await get_effective_targets(self.zone_id)
        success = True

        # Коррекция EC (NPK)
        if telemetry.ec < targets.ec.min:
            dose_a, dose_b = calculate_npk_dose(telemetry.ec, targets.ec.target)
            await dose_npk(self.zone_id, dose_a, dose_b)
            await asyncio.sleep(targets.timings.npk_mix_time_sec)
            success = False  # Нужна повторная проверка

        # Коррекция pH
        if telemetry.ph < targets.ph.min:
            dose = calculate_ph_dose(telemetry.ph, targets.ph.target)
            await dose_ph_up(self.zone_id, dose)
            await asyncio.sleep(targets.timings.ph_mix_time_sec)
            success = False

        elif telemetry.ph > targets.ph.max:
            dose = calculate_ph_dose(telemetry.ph, targets.ph.target)
            await dose_ph_down(self.zone_id, dose)
            await asyncio.sleep(targets.timings.ph_mix_time_sec)
            success = False

        return success
```

### 6.2. Политика partial EC batch failure (обновление 2026-02-16)

Для EC-коррекции, где дозирование идет батчем по компонентам (`npk -> calcium -> magnesium -> micro`), действует fail-safe правило:

1. Если компонент `N` завершился ошибкой после успешной дозировки предыдущих компонентов:
   - batch немедленно прерывается;
   - результат маркируется как `degraded`;
   - фиксируется событие `EC_BATCH_PARTIAL_FAILURE` с деталями:
     - `successful_components`
     - `failed_component`
     - `remaining_components`
     - `target_ec` / `current_ec`
     - `status=degraded`.
2. Параллельно запускается компенсационный путь:
   - enqueue diagnostics workflow (`irrigation_recovery`) для повторной оценки и выравнивания раствора;
   - если enqueue недоступен — infra-alert `infra_ec_batch_partial_failure_compensation_enqueue_failed`.
3. До завершения компенсационного пути запрещено трактовать partial batch как успешное достижение EC-target.

---

## 7. Изменения в прошивках нод

### 7.1. pH node / EC node

**Новые состояния:**
```c
typedef enum {
    SENSOR_MODE_IDLE,      // Только heartbeat/LWT
    SENSOR_MODE_ACTIVE,    // Telemetry + corrections
} sensor_mode_t;
```

**Новая логика:**
```c
// В main loop ноды
void sensor_node_loop() {
    if (sensor_mode == SENSOR_MODE_IDLE) {
        // Отправлять только heartbeat каждые 60 сек
        send_heartbeat();
        vTaskDelay(60000 / portTICK_PERIOD_MS);
        return;
    }

    // SENSOR_MODE_ACTIVE
    if (!stable) {
        // Еще не стабилизировалось
        stabilization_elapsed_sec += 5;
        if (stabilization_elapsed_sec >= stabilization_target_sec) {
            stable = true;
        }
    }

    // Измерить и отправить telemetry
    float ph_value = read_ph_sensor();
    send_telemetry(ph_value, stable);

    vTaskDelay(5000 / portTICK_PERIOD_MS);  // Каждые 5 сек
}

// Command handler
void handle_system_command(const char* cmd, cJSON* params) {
    if (strcmp(cmd, "activate_sensor_mode") == 0) {
        sensor_mode = SENSOR_MODE_ACTIVE;
        stable = false;
        stabilization_elapsed_sec = 0;
        stabilization_target_sec = cJSON_GetNumberValue(cJSON_GetObjectItem(params, "stabilization_time_sec"));
        ESP_LOGI(TAG, "Sensor mode activated, stabilization: %d sec", stabilization_target_sec);

    } else if (strcmp(cmd, "deactivate_sensor_mode") == 0) {
        sensor_mode = SENSOR_MODE_IDLE;
        stable = false;
        ESP_LOGI(TAG, "Sensor mode deactivated");
    }
}
```

---

## 8. Frontend настройки

### 8.1. Секция "Коррекция" в Zone Settings

```vue
<template>
  <div class="correction-settings">
    <h3>Параметры коррекции раствора</h3>

    <div class="timing-group">
      <label>Время стабилизации (набор бака)</label>
      <input v-model="timings.tank_fill_stabilization_sec" type="number" />
      <span>секунд</span>
    </div>

    <div class="timing-group">
      <label>Время смешивания NPK</label>
      <input v-model="timings.npk_mix_time_sec" type="number" />
      <span>секунд</span>
    </div>

    <div class="timing-group">
      <label>Время смешивания pH</label>
      <input v-model="timings.ph_mix_time_sec" type="number" />
      <span>секунд</span>
    </div>

    <div class="timing-group">
      <label>Макс попыток рециркуляции бака</label>
      <input v-model="timings.max_tank_recirc_attempts" type="number" min="1" max="10" />
    </div>

    <button @click="saveTimings">Сохранить</button>
  </div>
</template>
```

---

## 9. Логирование событий коррекции в zone_events

### 9.1. Создаваемые события

`CorrectionHandler` создаёт записи в `zone_events` как для дозирования, так и для fail-closed / retry наблюдаемости:

| Тип события                      | Шаг/контекст        | Когда создаётся                                                      |
|----------------------------------|---------------------|----------------------------------------------------------------------|
| `EC_DOSING`                      | `corr_dose_ec`      | После успешной отправки команды насосу EC                            |
| `PH_CORRECTED`                   | `corr_dose_ph`      | После успешной отправки команды насосу pH                            |
| `CORRECTION_COMPLETE`            | `corr_check`        | Когда `pH/EC` вошли в целевое окно                                   |
| `CORRECTION_SKIPPED_COOLDOWN`    | `corr_check`        | Когда PID-контур ещё в `min_interval_sec` и доза откладывается       |
| `CORRECTION_SKIPPED_DEAD_ZONE`   | `corr_check`        | Когда planner не видит допустимой дозы вне deadband                  |
| `CORRECTION_LIMIT_POLICY_APPLIED` | `corr_check` / fill-start | Когда `solution_fill` запускает continuous correction без attempt caps |
| `CORRECTION_ATTEMPT_CAP_IGNORED` | `corr_check` / fill | Когда `solution_fill` сознательно игнорирует достигнутый attempt cap |
| `CORRECTION_SKIPPED_WATER_LEVEL` | `corr_check`        | Когда correction пропущен из-за низкого уровня воды                  |
| `CORRECTION_SKIPPED_FRESHNESS`   | `corr_check`/observe| Когда decision/observe window не может использовать свежую телеметрию |
| `CORRECTION_SKIPPED_WINDOW_NOT_READY` | `corr_check`/observe | Когда окно наблюдения ещё не прошло `window_min_samples/stability` |
| `CORRECTION_NO_EFFECT`           | `corr_wait_ec/ph`   | Когда достигнут `no_effect_consecutive_limit` и correction fail-closed |
| `CORRECTION_EXHAUSTED`           | любой correction    | Когда исчерпаны configured attempts и runtime уходит в fail-closed   |

### 9.2. Структура payload

**EC_DOSING:**
```json
{
  "node_uid": "ec-node-uid",
  "channel": "ec_npk_pump",
  "amount_ml": 2.5,
  "duration_ms": 2500,
  "current_ec": 1.2,
  "target_ec": 1.5,
  "target_ec_min": 1.4,
  "target_ec_max": 1.6,
  "attempt": 1,
  "source": "correction_handler"
}
```

**PH_CORRECTED:**
```json
{
  "node_uid": "ph-node-uid",
  "channel": "ph_base_pump",
  "amount_ml": 1.2,
  "duration_ms": 1200,
  "direction": "up",
  "current_ph": 5.8,
  "target_ph": 6.2,
  "target_ph_min": 6.0,
  "target_ph_max": 6.5,
  "attempt": 1,
  "source": "correction_handler"
}
```

**CORRECTION_SKIPPED_FRESHNESS:**
```json
{
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "corr_step": "corr_check",
  "sensor_scope": "decision_window",
  "sensor_type": "EC",
  "reason": "EC telemetry stale/unavailable during observation window",
  "retry_after_sec": 30.0,
  "attempt": 2
}
```

**CORRECTION_LIMIT_POLICY_APPLIED:**
```json
{
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "corr_step": "corr_check",
  "attempt_caps_enforced": false,
  "stop_conditions": ["no_effect", "stage_timeout"],
  "stage_timeout_sec": 900,
  "policy": "fill_continuous_until_no_effect_or_timeout"
}
```

**CORRECTION_ATTEMPT_CAP_IGNORED:**
```json
{
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "corr_step": "corr_check",
  "cap_type": "overall",
  "current_value": 6,
  "limit_value": 5,
  "policy": "fill_continuous_until_no_effect_or_timeout"
}
```

**CORRECTION_SKIPPED_WATER_LEVEL:**
```json
{
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "corr_step": "corr_check",
  "water_level_pct": 12.0,
  "retry_after_sec": 60.0,
  "current_ph": 6.3,
  "current_ec": 1.1,
  "target_ph": 6.0,
  "target_ec": 2.0,
  "attempt": 2
}
```

**CORRECTION_NO_EFFECT:**
```json
{
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "corr_step": "corr_wait_ec",
  "pid_type": "ec",
  "baseline_value": 1.0,
  "observed_value": 1.02,
  "expected_effect": 0.4,
  "actual_effect": 0.02,
  "threshold_effect": 0.1,
  "no_effect_limit": 3,
  "attempt": 2
}
```

**CORRECTION_SKIPPED_WINDOW_NOT_READY:**
```json
{
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "corr_step": "corr_wait_ec",
  "sensor_scope": "observe_window",
  "sensor_type": "EC",
  "pid_type": "ec",
  "reason": "insufficient_samples",
  "sample_count": 2,
  "retry_after_sec": 2
}
```

### 9.3. Источник current_ph / current_ec

Значения `current_ph` и `current_ec` берутся **из таблицы `pid_state`** (метод `PgPidStateRepository.read_measured_value`), а не из `plan.runtime`.

**Причина:** `plan` не обновляется между шагами коррекции — `_run_check` и `_run_dose_ec`/`_run_dose_ph` выполняются в разных итерациях основного цикла executor'а. В `_run_check` выполняется `_persist_pid_state_updates`, который записывает `last_measured_value` в `pid_state`. Таким образом, чтение из `pid_state` гарантирует, что событие содержит актуальное измерение.

### 9.4. Обработка ошибок логирования

Ошибки создания событий логируются как WARNING (`_logger.warning`), но **не прерывают** выполнение шага коррекции. Это намеренно — ошибки логирования не должны влиять на бизнес-логику дозирования.

### 9.5. Канонический context payload

Для correction-runtime событий `payload_json` обязан по возможности включать:
- `stage`
- `workflow_phase`
- `corr_step`
- `attempt`
- `ec_attempt`
- `ph_attempt`

Это требуется для Laravel/UI diagnostics и для безопасной отладки fail-closed веток без чтения raw `ae_tasks`.

---

## 10. Связанные документы

- `ARCHITECTURE_FLOWS.md` — архитектурные схемы и пайплайны
- `EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол
- `../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — каналы нод

---

**Документ создан после обсуждения логики коррекции 2026-02-14**
**Обновлён 2026-03-11: добавлен раздел 9 (логирование событий коррекции)**
