# CORRECTION_CYCLE_SPEC.md
# Спецификация циклов коррекции раствора

Документ описывает state machine, режимы коррекции и логику управления измерением pH/EC с учетом необходимости наличия потока раствора.

**Дата создания:** 2026-02-14
**Дата обновления:** 2026-07-09 (PR8+; §6.2 MVP: `EC_BATCH_PARTIAL_FAILURE` + fail window, без auto-recovery)
**Статус:** Рабочий документ (требует валидации)

---

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

Актуализация authority / AE3 (2026-03-24):
- команды к нодам идут только через `history-logger /commands`;
- запуск цикла автоматики выполняется через `POST /zones/{id}/start-cycle`;
- runtime-резолв target/config выполняется через SQL read-model (effective-targets API не используется в runtime path).

### Authority matrix (correction / PID, 2026-07-20)

| Параметр | Source of truth |
|----------|-----------------|
| target pH/EC | recipe phase only |
| kp/ki/kd, dead/close/far zones | `zone.pid.{ph,ec}` |
| min_interval_sec, max_dose_ml, **max_integral**, derivative_filter_alpha, observe | `zone.correction.controllers.*` |
| process gains, transport_delay, settle | `zone.process_calibration.*` |
| min/max_dose_ms, ml_per_sec | pump_calibration |

- `targets.*.controller` в effective-targets — **не** AE3 authority;
- discard дозы (`below_min_dose_ms`, saturation clamp, sensor OOB) ≠
  `CORRECTION_SKIPPED_DEAD_ZONE` (gap внутри deadband / нет needs_*);
- dead code `DosePlan.deferred_action` / `CORRECTION_ACTION_DEFERRED` удалён
  из planner/handler (исторические UI labels событий могут оставаться).

Актуализация per-phase EC и day/night (2026-04-13):
- EC target в correction теперь зависит от текущей фазы workflow: для `solution_fill`/`tank_recirc` используется prepare-target (доля NPK от полного EC), для `irrigation`/`irrig_recirc` — полный EC;
- handler-уровневые accessors `_effective_ec_target/min/max` и `_effective_ph_target/min/max` (`backend/services/automation-engine/ae3lite/application/handlers/base.py:1107,1129,1143,1157,1161,1167`) выбирают значение по фазе и применяют day/night override (если `day_night_enabled=true` на phase snapshot);
- `build_dose_plan` / `is_within_tolerance` / `_targets_reached` / `_workflow_ready_values_match` обязаны вызывать только эти effective accessors, без чтения сырого `runtime["target_ec"]`;
- полный контракт runtime spec (`target_ec_prepare`, `npk_ec_share`, `day_night_config`) и валидация — см. `EFFECTIVE_TARGETS_SPEC.md` §9 / §10.

Актуализация AE3 in-flow correction (2026-03-15):
- correction decision больше не строится по одному `telemetry_last` sample;
- для `EC` и `pH` используется модель `dose -> hold -> observe -> decide`;
- окно наблюдения собирается из `telemetry_samples`, а не из одного текущего значения;
- на входе в correction-window planner может одновременно определить потребность и в `EC`, и в `pH`;
- выполнение доз остаётся последовательным: между `EC` и `pH` обязателен повторный `observe-step`;
- если planner видит одновременно `EC` и `pH`, обе потребности остаются в одном correction-window и не требуют повторного входа parent-stage;
- `3` consecutive `no-effect` для одного `pid_type` дают alert и fail-closed ветку correction window;
- обычные correction attempts и `no-effect` attempts — независимые лимиты.

Актуализация partial EC batch failure MVP (2026-07-09):
- при ошибке компонента `N` после успешных `0..N-1` в `multi_sequential` / `multi_parallel` эмитится `EC_BATCH_PARTIAL_FAILURE` (`status=degraded`), correction window закрывается fail-closed;
- метрика `ae3_correction_ec_batch_partial_failure_total{mode=...}`;
- auto-enqueue `irrigation_recovery` и infra-alert компенсации — **не в MVP** (см. §6.2).

Observability (UI/Grafana, 2026-07-09):
- панель «Коррекция / дозирование» в AutomationObservabilityPanel показывает причину пропуска дозы, шаг `corr_step`, последнюю дозу и `targets_in_tolerance` / `workflow_ready`;
- `latest_skip` / readiness фильтруются по `task_id` активной задачи и TTL (~30 мин); карточка не открывается на idle только из‑за старых событий;
- приоритет причины: hard-fail skip → активное дозирование → `control_mode` → soft skip;
- Grafana dashboard `automation-engine` — rate/sum для `dose_clamped`, `observe_out_of_bounds`, `no_effect`, `estop_interrupt`, `control_mode_blocked`, `ec_batch_partial_failure`.

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
| `start_tank_fill` | Начать набор бака | Laravel dispatch / Manual |
| `start_irrigation` | Начать полив | Laravel dispatch / Manual |
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
  устаревшие `diagnostics.execution.*`;
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
- `expected_effect` считается как `effective_process_gain * amount_ml`, где
  `effective_process_gain` — тот же auth⊕learned blend (с clamps / tank_recirc EC floor),
  что использует `CorrectionPlanner` при расчёте дозы. Порог no-effect и sizing дозы
  не должны расходиться по источнику gain.
- Adaptive stats (`pid_state.stats.adaptive`): gain / effectiveness / retention / wave
  observations инкрементируются только при валидном learning update
  (`dose_amount_ml > 0` и `learning_effect > 0`); timing EMA — отдельно (audit B10).
- Integral PID: накопление `gap×dt` только на active measurement ticks; hold/observe
  dead time не раздувает I. При saturation дозы (`gap/gain`, `max_dose_ml`,
  `clamped_to_max_dose_ms`) ΔI тика не персистится (conditional integration).
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
- correction success (`CorrectionPlanner.is_within_tolerance`, `_targets_reached`) = canonical `target_ph/target_ec` ± `prepare_tolerance`;
- `workflow_ready` (`_workflow_ready_reached`, переходы `*_stop_to_ready`) может быть **строже** correction-success:
  если runtime уже имеет явные `target_*_min/max`, именно они используются как explicit ready band;
- fallback на `prepare_tolerance` для `workflow_ready` допустим только если explicit ready band отсутствует;
- `target_*_min/max` не считаются ранним success сами по себе внутри correction sub-machine:
  они используются только для финального решения о `workflow_ready`.
- события `CORRECTION_COMPLETE`, `CORRECTION_INTERRUPTED_STAGE_COMPLETE` и успешный
  `CORRECTION_SKIPPED_DEAD_ZONE` публикуют явные флаги `targets_in_tolerance` и `workflow_ready`
  (legacy alias `targets_reached` = `workflow_ready` для solution_fill routing).
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
   - wall-clock deadline = `solution_fill_timeout_sec + solution_fill_correction_slack_sec`
     (аналогично `prepare_recirculation_*` и `irrigation_recovery.timeout_sec + irrigation_recovery_correction_slack_sec`)
     (оба поля из zone correction config; slack default `900`);
    - attempt-based exhaustion внутри `solution_fill` не должна останавливать коррекцию раньше времени:
      stage остаётся в одном correction window до этого deadline либо до fail-closed по `no-effect`;
    - fail-closed по `no-effect` в `solution_fill` реализуется как переход в `solution_fill_timeout_stop`,
      а не как silent poll без новой correction window.
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

### 3.5. Ограничения дозы (dose limits)

Контракт ограничений per dose реализован в `backend/services/automation-engine/ae3lite/domain/services/correction_planner.py::_dose_ml_to_ms` и `_resolve_dose_duration`.

**Из `pump_calibration` (zone policy, `system.pump_calibration_policy`):**
- `pump_calibration.max_dose_ms` — **runaway guard** и согласование с firmware: hard cap длительности одной дозы на стороне AE3. Default `60_000` ms (60 с — совпадает с `CORRECTION_NODE_ACTUATOR_MAX_DURATION_MS` / `safe_limits.max_duration_ms` ph_node/ec_node). Если расчётный `duration_ms` больше, длительность **clamps** до cap, а объём пересчитывается: `effective_ml = ml_per_sec * clamped_ms / 1000`. В MQTT-команде `params.ml` = `effective_ml`; в zone events `EC_DOSING` / `PH_CORRECTED` публикуются **оба** поля: `effective_ml` и `requested_ml` (исходный объём до clamp). PID/attempt-логика оперирует `effective_ml`. Для зон с увеличенным NodeConfig cap задайте `max_dose_ms` явно (≤ `_MAX_DURATION_MS_SANITY` history-logger = 300_000).
- `pump_calibration.min_dose_ms` — **нижний порог**. Если расчётный `duration_ms` ниже — доза **discarded** с reason `below_min_dose_ms` (без публикации команды). Это защита от микро-доз ниже физического разрешения насоса.
- **Discard ≠ deadband:** `CORRECTION_SKIPPED_DOSE_DISCARDED` — доза отброшена (ниже min / partial multi-component и т.п.), targets могут оставаться out of tolerance. Runtime **не** эмитит `CORRECTION_SKIPPED_DEAD_ZONE` и **не** завершает окно как `success=True`; вместо этого retry `corr_check` с backoff (`decision_window_retry_sec` или `level_poll_interval_sec` в prepare) и инкрементом `attempt` (включая prepare), плюс clock-touch `last_measurement_at` без commit plan integral.
- **Clamp ≠ discard:** `clamped_to_max_dose_ms` пишется в `dose_clamped_*` и эмитит `CORRECTION_DOSE_CLAMPED` (доза всё ещё уходит). Не маскируется под `CORRECTION_SKIPPED_DOSE_DISCARDED`.
- **True deadband:** `CORRECTION_SKIPPED_DEAD_ZONE` + `success=True` — только когда planner не видит дозы вне deadband **и** нет `dose_discarded_reason`.
- **PID persist timing:** plan updates (`integral` / `prev_*`) персистятся только после подтверждения маршрута дозы (не на flow_hold / discard / cooldown). При dual EC+PH commit I только для controller, чья dose уходит сейчас; peer — clock-touch без ΔI. `last_dose_at` — только после terminal `DONE`.

**Dual calibration (AE3 ↔ firmware) — ops checklist:**
- AE3 планирует `params.ml` по DB `pump_calibrations.ml_per_sec`; ph_node/ec_node исполняют dose по NodeConfig `ml_per_second` и **игнорируют** `params.duration_ms` (если передан).
- `ml_per_sec` в БД **должен совпадать** с `ml_per_second` в NodeConfig actuator channel; иначе фактический объём на ноде расходится с планом AE3.
- Laravel `PublishNodeConfigJob` / apply channel config зеркалит `ml_per_second` → `pump_calibrations` (source `node_config_publish` / `node_channel_config_apply`).
- AE3 runtime: при наличии обоих источников сравнивает значения по `system.pump_calibration_policy.ml_per_sec_mismatch_pct` (default 10%); warn → `PUMP_CALIBRATION_MIRROR_MISMATCH` + metric, fail-closed → `pump_calibration_dual_source_mismatch` (policy flag).
- Per-pump cap: если в calibration actuator задан `max_duration_ms` (зеркало NodeConfig), AE3 берёт `min(zone.max_dose_ms, calibration.max_duration_ms)`.
- Firmware при превышении cap публикует в ACK `details.duration_limited=true` и фактический `details.duration_ms`.
- После terminal `DONE` correction handler читает `response_details` из batch result (`commands.duration_ms` + ACK-поля) и при `duration_limited` или `actual_duration_ms < planned` пересчитывает `effective_ml = ml_per_sec * actual_duration_ms / 1000` (DB calibration). Без details поведение прежнее: planned `effective_ml`.
- В `EC_DOSING` / `PH_CORRECTED` и `pid_state.last_output_ms` пишутся фактические значения после node feedback.

**Ops checklist (при смене калибровки или NodeConfig):**
1. Обновить `pump_calibrations.ml_per_sec` в БД (Laravel calibrate-pump flow).
2. Перепубликовать NodeConfig с тем же `ml_per_second` на соответствующем actuator channel.
3. Сверить `pump_calibration.max_dose_ms` (zone policy) с `safe_limits.max_duration_ms` в NodeConfig.
4. Smoke: одна тестовая `dose` с известным `ml`, сравнить фактический расход / ACK `details` с ожиданием.

**Из `dosing` / `correction_config`:**
- `solution_volume_l` — **обязателен** (fail-closed) для полноты zone config и UI/metadata (объём бака/контура). Отсутствие или неположительное значение → `PlannerConfigurationError` на этапе build плана. **Не участвует** в PID ml math (`_compute_amount_ml`); доза считается по process gain + controller caps, не как доля от литража.

**Из `controllers.{ec,ph}` (per controller):**
- `controllers.{ec,ph}.max_dose_ml` — controller-level cap per dose в мл (применяется до перевода в ms).
- `controllers.{ec,ph}.min_interval_sec` — минимальный интервал между дозами одного controller'а. Конфигурируемо per controller; типовые production-значения: pH 60–120 с, EC 60–120 с. Прежние комментарии «pH ≥ 20 с, EC ≥ 10 с» устарели — на них не опираться.
- `last_dose_at` в `pid_state` пишется **только после terminal `DONE`** дозирующей команды в correction handler (не на этапе планирования). Timestamp якорится на момент подтверждённого DONE (`utcnow` после успешного `run_batch`), а не на старт tick handler'а. Это предотвращает фантомный cooldown при fail/TIMEOUT дозы и ранний старт `min_interval_sec`.
- Plan `integral` / `prev_*` коммитятся в `_finalize_dose_plan_routing` **после** подтверждения dose routing (не до control_mode gate, не при discard/cooldown). Observe finalize трогает только `last_measurement_at` (без ΔI) — эквивалент `accumulate_integral=False`.

**Из `pid_configs.{ec,ph}`:**
- `close_zone` / `far_zone` — зоны PID-коэффициентов. При `far_zone <= close_zone` → `PlannerConfigurationError` на этапе build плана.

**Sanity bounds decision/observation windows (`metric_window_validator`):**
- Единый валидатор: `ae3lite/domain/services/metric_window_validator.py` (используется в `DecisionWindowReader`, `BaseStageHandler._read_target_metric_window` и observe finalize в `CorrectionHandler._read_observation_window_or_interrupt`).
- pH ∈ `[0, 14]`, EC ∈ `[0, 20]` mS/cm.
- Выход за пределы (error code типа `-1` / `999`, NaN, inf) → reason `sensor_out_of_bounds`, окно не ready, PID-state не обновляется, доза не публикуется.

**Alert-block retry cap:**
- При `safety.block_on_active_no_effect_alert=true` и активном no-effect alert handler retry'ит `corr_check` с backoff 60 с, но не более `AE_CORRECTION_ALERT_BLOCK_MAX_RETRIES` (default `10`). По исчерпании — terminal fail с кодом `correction_blocked_by_no_effect_alert`.

**No-effect лимит:**
- `3` consecutive `no-effect` для одного `pid_type` → alert + fail-closed correction window. Обычные attempts и `no-effect` attempts считаются отдельно.

### 3.6. `ec_dosing_mode` для EC контура

Параметр `correction_config.ec_dosing_mode` управляет тем, как `correction_planner` распределяет gap EC по компонентам (NPK / Ca / Mg / Micro). Реализация — `correction_planner.py::_assert_distinct_parallel_actuators` и связанные функции.

Допустимые значения:
- `single` (default) — один pump на весь EC контур (legacy / SUBSTRATE без компонентов).
- `multi_sequential` — gap делится на компоненты по `ec_component_ratios`, дозируется **последовательностью импульсов** на разные насосы в рамках одного `corr_dose_ec`. Защита от runaway — каждый импульс ограничен `max_dose_ms`.
- `multi_parallel` — gap делится по `ec_component_ratios` и компоненты дозируются **одним batch** через `history-logger`. Каждая команда batch несёт согласованную пару `params.ml` + `params.duration_ms` из плана (после clamp — `effective_ml`). **Fail-closed правило:** все компоненты обязаны иметь distinct `(node_uid, channel)` — иначе суперпозиция команд на один насос даст неверные дозы; `_assert_distinct_parallel_actuators` raise'ит `PlannerConfigurationError`.

**`ec_excluded_components`:**
- Для стадии `irrigation_check` обычно `["npk"]` — NPK уже добавлен в `solution_fill`, во время полива дозируется только Ca/Mg/Micro. Оставшиеся компоненты перенормируются (сумма ratios → 1.0).

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

### 6.2. Политика partial EC batch failure (обновление 2026-07-09)

**Status: MVP implemented (detect + event + fail window).** Полный компенсационный путь (enqueue `irrigation_recovery`) — **out-of-scope MVP / v2+**.

Для EC-коррекции, где дозирование идет батчем по компонентам (`npk -> calcium -> magnesium -> micro` в `multi_sequential`, либо параллельный `multi_parallel`), действует fail-safe правило:

1. Если компонент `N` завершился ошибкой после успешной дозировки предыдущих компонентов (`0..N-1`):
   - batch немедленно прерывается;
   - correction window закрывается как **fail** (`outcome_success=false`); EC-target **не** считается достигнутым;
   - фиксируется событие `EC_BATCH_PARTIAL_FAILURE` с деталями:
     - `successful_components`
     - `failed_component`
     - `remaining_components`
     - `target_ec` / `current_ec`
     - `status=degraded`
     - `mode` (`multi_sequential` | `multi_parallel`), `error_code`, `failed_index`;
   - метрика: `ae3_correction_ec_batch_partial_failure_total{mode=...}`.
2. **MVP не делает** auto-enqueue diagnostics workflow (`irrigation_recovery`) и не шлёт infra-alert `infra_ec_batch_partial_failure_compensation_enqueue_failed` — это целевой контракт v2+.
3. Ошибка на **первом** компоненте batch (нет prior success) остаётся обычным fail-closed `TaskExecutionError` без события partial failure.

**Тестовое покрытие MVP (§6.2):**

| Уровень | Файл | Кейсы |
|---------|------|-------|
| Unit (`_run_dose_ec`) | `backend/services/automation-engine/test_ae3lite_correction_handler_multi_dose.py` | `test_corr_dose_ec_dispatches_sequence_ca_mg_micro`, `test_corr_dose_ec_partial_failure_emits_event_and_fails_window`, `test_corr_dose_ec_first_component_failure_raises` |
| Integration (`CorrectionHandler.run` + `CorrectionEventLogger` + gateway `command_statuses`) | `backend/services/automation-engine/test_ae3lite_correction_handler_multi_dose_integration.py` | happy path sequential; sequential/parallel partial (`status=degraded`, enrichment, metric, `current_ec`); first-fail sequential + parallel без partial event |

YAML E2E сценарий для partial failure **не добавлен**: полный two-tank/irrigation прогон хрупкий без node_sim; pytest AE3 даёт воспроизводимое покрытие без железа.

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
| `CORRECTION_DECISION_MADE`       | `corr_check`        | Когда planner/runtime выбрал следующий correction contour в окне     |
| `CORRECTION_COMPLETE`            | `corr_check`        | Когда `pH/EC` вошли в целевое окно                                   |
| `CORRECTION_SKIPPED_COOLDOWN`    | `corr_check`        | Когда PID-контур ещё в `min_interval_sec` и доза откладывается       |
| `CORRECTION_SKIPPED_DOSE_DISCARDED` | `corr_check`     | Доза discarded (`below_min_dose_ms` / partial multi-component и т.п.); не success |
| `CORRECTION_DOSE_CLAMPED`         | `corr_check`        | Saturation clamp (`clamped_to_max_dose_ms`); доза уходит, не discard |
| `CORRECTION_SKIPPED_DEAD_ZONE`   | `corr_check`        | Истинный deadband (нет `dose_discarded_reason`); success=True        |
| `CORRECTION_NO_EFFECT_RESET_FAILED` | `corr_check`    | Fail-closed: не удалось сбросить `no_effect_count` после success     |
| `CORRECTION_LIMIT_POLICY_APPLIED` | `corr_check` / fill-start | Когда `solution_fill` запускает continuous correction без attempt caps |
| `CORRECTION_ATTEMPT_CAP_IGNORED` | `corr_check` / fill | Когда `solution_fill` сознательно игнорирует достигнутый attempt cap |
| `CORRECTION_SKIPPED_WATER_LEVEL` | `corr_check`        | Когда correction пропущен из-за низкого уровня воды                  |
| `CORRECTION_SKIPPED_FRESHNESS`   | `corr_check`/observe| Когда decision/observe window не может использовать свежую телеметрию |
| `CORRECTION_SKIPPED_WINDOW_NOT_READY` | `corr_check`/observe | Когда окно наблюдения ещё не прошло `window_min_samples/stability` |
| `CORRECTION_OBSERVATION_EVALUATED` | `corr_wait_ec/ph` | Когда observe-window оценён и runtime понял, есть ли реакция         |
| `CORRECTION_NO_EFFECT`           | `corr_wait_ec/ph`   | Когда достигнут `no_effect_consecutive_limit` и correction fail-closed |
| `CORRECTION_EXHAUSTED`           | любой correction    | Когда исчерпаны configured attempts и runtime уходит в fail-closed   |

### 9.2. Структура payload

**EC_DOSING:**
```json
{
  "task_id": 73,
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "correction_window_id": "task:73:tank_filling:solution_fill_check",
  "corr_step": "corr_dose_ec",
  "observe_seq": 2,
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
  "task_id": 73,
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "correction_window_id": "task:73:tank_filling:solution_fill_check",
  "corr_step": "corr_dose_ph",
  "observe_seq": 2,
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

**CORRECTION_DECISION_MADE:**
```json
{
  "task_id": 73,
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "correction_window_id": "task:73:tank_filling:solution_fill_check",
  "corr_step": "corr_dose_ph",
  "selected_action": "ph_down",
  "decision_reason": "prioritize_pending_ph_after_ec_observe",
  "current_ph": 6.83,
  "current_ec": 0.52,
  "target_ph_min": 5.6,
  "target_ph_max": 6.0,
  "target_ec_min": 1.2,
  "target_ec_max": 1.6,
  "needs_ec": true,
  "needs_ph_up": false,
  "needs_ph_down": true
}
```

**CORRECTION_OBSERVATION_EVALUATED:**
```json
{
  "task_id": 73,
  "stage": "solution_fill_check",
  "workflow_phase": "tank_filling",
  "correction_window_id": "task:73:tank_filling:solution_fill_check",
  "corr_step": "corr_wait_ph",
  "pid_type": "ph",
  "observe_seq": 2,
  "baseline_value": 6.916,
  "observed_value": 6.832,
  "expected_effect": 0.15,
  "actual_effect": 0.084,
  "threshold_effect": 0.0375,
  "is_no_effect": false
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

### 9.6. Коррекция во время полива (inline irrigation correction)

AE3-Lite поддерживает вход в коррекцию **во время стадии** `irrigation_check` (фаза `irrigating`), без остановки гидравлики полива:
- стадия `irrigation_check` помечена `has_correction=true` и возвращается обратно в `irrigation_check`;
- вход в коррекцию контролируется флагом runtime `irrigation_execution.correction_during_irrigation`;
- чтобы избежать бесконечных циклов, при исчерпании попыток коррекции в `irrigation_check` увеличивается `stage_retry_count` и новые входы в коррекцию для этой стадии блокируются.

#### Multi-component EC (Ca/Mg/Micro)

Для стадии `irrigation_check` поддержан режим `ec_dosing_mode=multi_sequential`:
- EC gap вычисляется один раз (один PID выход);
- затем EC gap распределяется по `ec_component_ratios` полного рецепта (включая NPK, сумма=1.0);
- для полива NPK исключается через `ec_excluded_components=["npk"]`, а оставшиеся компоненты перенормируются (Ca/Mg/Micro);
- дозирование выполняется последовательностью импульсов (Ca → Mg → Micro) в рамках одного `corr_dose_ec`.

---

## 10. Полуавтоматическая подмена раствора (`solution_change` v1)

> **Этап D.1** из `doc_ai/AGRO_AUTONOMY_MASTER_PLAN.md`.  
> **Статус:** doc-first SPEC (реализация runtime — отдельный PR после принятия контракта).  
> **Связанные документы:** `doc_ai/04_BACKEND_CORE/ae3lite.md` §1 / §7.2.3, `WATER_FLOW_ENGINE.md` §19 (out-of-scope sibling `solution_topup`), `CONTROL_MODES_SPEC.md` §5.

### 10.1. Проблема и цель

Для длинных циклов плодовых раствор деградирует; штатный startup (`cycle_start`) покрывает только первичное наполнение, а не **полную замену** раствора в работающей зоне.

**Цель v1 (полуавтомат):** оператор инициирует подмену одной командой; AE3 проводит зону через drain → refill → recirc → `ready`, но **останавливается на явных точках подтверждения** перед сливом и после наполнения. Полный автомат без подтверждений и CIP — этап D.2.

### 10.2. Предусловия ingress

Подмена разрешена только если одновременно:

| Условие | Fail-closed code (черновик) |
|---------|----------------------------|
| `zone_workflow_state.workflow_phase = 'ready'` | `solution_change_zone_not_ready` |
| Нет active `ae_tasks` / active lease на зоне | `start_solution_change_zone_busy` |
| Нет активного полива (`irrigating` / `irrig_recirc`) | `solution_change_active_irrigation` |
| Two-tank topology (`tanks_count >= 2`, IRR-нода online) | `solution_change_topology_unsupported` |
| `subsystems.solution_change.enabled = true` в effective targets / zone bundle | `solution_change_disabled` |

Ingress (целевой контракт):

- **Ручной:** `POST /zones/{id}/start-solution-change` (`source`, `idempotency_key`, опционально `trigger=operator|scheduler`).
- **По расписанию:** Laravel `ScheduleDispatcher` создаёт intent `SOLUTION_CHANGE_TICK` и вызывает тот же endpoint; в v1 task **не начинает drain** до первого operator confirm (см. §10.4).

Команды на узлы — только через `history-logger` → MQTT (инвариант AE3).

### 10.3. Workflow (reuse two-tank stages)

Canonical business task: `task_type='solution_change'`.  
Внутри task переиспользуются существующие stage handlers two-tank контура; отличие — **prefixed drain-подконтур** и **operator gates**.

```
workflow_phase=ready
    │
    ▼
await_operator_drain_confirm          ◄── GATE 1 (UI confirm)
    │
    ▼
solution_drain_start → solution_drain_check
    │                      (до solution_min=false или timeout)
    ▼
clean_fill_start → clean_fill_check
    │
    ▼
solution_fill_start → solution_fill_check
    │                      (+ штатная EC/pH correction, prepare-targets)
    ▼
solution_fill_stop_to_refill_confirm  ◄── stop + sensor_mode_deactivate
    │                      (в т.ч. если solution_max сработал во время correction)
    ▼
await_operator_refill_confirm         ◄── GATE 2 (UI confirm)
    │
    ▼
prepare_recirculation_start → prepare_recirculation_check
    │                              (+ correction window)
    ▼
complete_ready  →  workflow_phase='ready'
```

**Семантика drain (новые stages, черновик):**

- `solution_drain_start` — открыть drain path (клапан слива / насос слива по topology IRR-ноды); зеркалит паттерн `clean_fill_start` / `solution_fill_start`.
- `solution_drain_check` — poll read-model до подтверждения опустошения бака раствора (`level_solution_min` **not triggered** / coarse percent ниже порога); fail-safe по `solution_drain_timeout_sec`.
- При `solution_drain_check` success AE3 **не** переводит зону в `idle/startup reset` — task продолжается в refill-ветку (в отличие от guard depletion в `ready`).

**Reuse без изменения контракта handlers:**

- `clean_fill_*`, `solution_fill_*`, `prepare_recirculation_*` — те же stage keys, correction sub-machine, terminal codes (`solution_fill_leak_stop`, `prepare_recirculation_attempt_limit_reached`, …) что и в `cycle_start`.
- `workflow_phase` во время task: `tank_filling` (drain+clean+solution fill) → `tank_recirc` (prepare recirc) → `ready`.

### 10.4. Точки подтверждения оператора

| Gate | Stage key | Когда | Действие оператора | Manual step (черновик) |
|------|-----------|-------|--------------------|------------------------|
| **G1 — перед drain** | `await_operator_drain_confirm` | Task создана, физическая подготовка (отключение полива, доступ к сливу) | Подтвердить начало слива | `solution_drain_confirm` |
| **G2 — после refill** | `await_operator_refill_confirm` | `solution_fill_check` успешно завершён (`solution_max`, targets в tolerance или operator override) | Подтвердить переход к перемешиванию/коррекции | `solution_refill_confirm` |

Поведение gates:

1. Task в gate-stage переводится в `poll` / `manual_hold` (аналог startup manual); **клапаны и насосы OFF** до confirm.
2. Таймаут ожидания: `solution_change_operator_confirm_timeout_sec` (default **3600**); истечение → `solution_change_operator_timeout` + fail-safe stop + task `failed`.
3. Оператор может отменить: `solution_change_abort` → `solution_change_aborted_by_operator`, workflow → `idle`, alert info.
4. В `control_mode='auto'` gates **не bypass** — semi-auto v1 всегда требует confirm (расписание только будит intent и показывает badge в UI).

Scheduler v1: intent `SOLUTION_CHANGE_TICK` переводится в «ожидает подтверждения»; автоматический drain **запрещён**.

### 10.5. UI flow (Vue, без реализации в этом PR)

Источник истины для кнопок: `allowed_manual_steps[]` из AE3 (`GET /api/zones/{id}/automation-state` → proxy AE3), **не** хардкод в UI (`CLAUDE.md`, `FRONTEND_UI_UX_SPEC.md`).

**Существующие компоненты (расширить, не дублировать):**

| Компонент / composable | Роль для `solution_change` |
|------------------------|----------------------------|
| `Pages/Zones/Tabs/ZoneAutomationTab.vue` | Контейнер вкладки «Автоматика»; прокидывает `allowedManualSteps`, `@run-manual-step` |
| `Components/ZoneAutomationOpsPanel.vue` | Кнопки manual steps + primary action «Подмена раствора» (новый emit `start-solution-change`) |
| `Components/ZoneAutomation/AutomationObservabilityPanel.vue` | Badge `pending_manual_step` / stage label на gate |
| `composables/useZoneAutomationScheduler.ts` | `runManualStep()` → `POST /api/zones/{id}/manual-step` |
| `composables/zoneAutomationUtils.ts` | Зеркало `manual_control_contract.py`; добавить mapping для gate stages |
| `types/Automation.ts` | Расширить union `AutomationManualStep` новыми step codes |
| `composables/useZoneScheduleWorkspace.ts` | Label `solution_change` уже есть («Смена раствора») |

**Целевой UX v1:**

1. В `ready` + `semi|manual`: кнопка **«Подмена раствора»** рядом с «Запустить полив» / «Диагностика» (`ZoneAutomationOpsPanel`).
2. Modal confirm для G1/G2 с checklist (слив подготовлен / уровень после refill OK); confirm отправляет соответствующий `manual_step`.
3. На gate stages в `allowed_manual_steps` только confirm/abort; на fill/recirc stages — существующие `*_stop` (как в startup).
4. Timeline / observability: события `SOLUTION_CHANGE_STARTED`, `SOLUTION_CHANGE_GATE_PASSED`, `SOLUTION_CHANGE_COMPLETED` (см. §10.7).
5. Schedule workspace: `task_type=solution_change` показывает «ожидает подтверждения оператора», если intent pending на G1.

**Новые manual steps (черновик, добавить в контракт AE3 + Vue union):**

| Step | Label (RU) | Stage |
|------|------------|-------|
| `solution_drain_confirm` | Подтвердить слив | `await_operator_drain_confirm` |
| `solution_refill_confirm` | Подтвердить наполнение | `await_operator_refill_confirm` |
| `solution_change_abort` | Отменить подмену | любой pre-terminal stage gate/fill |

Существующие steps (`clean_fill_start`, `solution_fill_stop`, …) остаются для `control_mode=manual` **внутри** fill-подконтура; в v1 полуавтомат fill-stages идут автоматически после G1, stop-кнопки доступны как emergency override.

### 10.6. Intent / task / API (черновик контракта)

| Поле | Значение |
|------|----------|
| Scheduler `task_type` | `solution_change` |
| DB `zone_automation_intents.intent_type` | `SOLUTION_CHANGE_TICK` (manual start — `SOLUTION_CHANGE_START`, опционально) |
| AE3 `ae_tasks.task_type` | `solution_change` (новое значение CHECK constraint — миграция Laravel) |
| Ingress endpoint | `POST /zones/{id}/start-solution-change` |
| Payload intent (optional) | `{ "trigger": "operator\|scheduler", "requested_by_user_id": … }` |
| Idempotency | `(zone_id, idempotency_key)` как у `start-irrigation` |

Recipe / effective targets (уже частично в UI):

```json
{
  "extensions": {
    "subsystems": {
      "solution_change": {
        "enabled": true,
        "execution": {
          "interval_sec": 10800,
          "duration_sec": 120
        }
      }
    }
  }
}
```

Парсер: `resources/js/services/automation/subsystemParsers/solutionChangeParser.ts`.  
Runtime bundle keys (черновик): `solution_drain_timeout_sec`, `solution_change_operator_confirm_timeout_sec`.

### 10.7. Error codes (черновик)

Добавить в `ERROR_CODE_CATALOG.md` после принятия SPEC:

| code | Домен | Когда |
|------|-------|-------|
| `start_solution_change_zone_busy` | `ae3_ingress` | Active task/lease при ingress |
| `solution_change_zone_not_ready` | `ae3_ingress` | `workflow_phase != ready` |
| `solution_change_active_irrigation` | `ae3_ingress` | Полив активен |
| `solution_change_disabled` | `ae3_config` | Subsystem disabled в bundle |
| `solution_change_topology_unsupported` | `ae3_config` | Не two-tank / нет IRR |
| `solution_drain_timeout_stop` | `solution_drain_check` | Слив не завершён за timeout |
| `solution_drain_incomplete_stop` | `solution_drain_check` | Уровень не подтверждён empty |
| `solution_change_operator_timeout` | `await_operator_*` | Истёк таймаут gate |
| `solution_change_aborted_by_operator` | `solution_change` | Cancel manual step |
| `solution_change_gate_invalid_step` | `ae3_manual` | Неверный manual step для stage |

Terminal failure обязан: fail-safe OFF актуаторов, sync `workflow_phase='idle'` (инвариант ae3lite §5.4.13).

### 10.8. Критерии приёмки D.1 (документ)

1. Оператор может инициировать подмену; SPEC фиксирует drain→refill→ready с двумя gates.
2. Переиспользованы two-tank stages и существующие fail-safe codes fill/recirc.
3. UI contract описан через `allowed_manual_steps` и существующие Vue-компоненты automation tab.
4. `solution_change` снят с out-of-scope AE3 v1 в `ae3lite.md` как **doc-first semi-auto v1**.

---

## 11. Связанные документы

- `ARCHITECTURE_FLOWS.md` — архитектурные схемы и пайплайны
- `EFFECTIVE_TARGETS_SPEC.md` — спецификация effective-targets
- `doc_ai/04_BACKEND_CORE/ae3lite.md` — runtime AE3, ingress `start-solution-change`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/WATER_FLOW_ENGINE.md` — гидравлические подсистемы
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CONTROL_MODES_SPEC.md` — manual steps baseline
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — MQTT протокол
- `../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` — каналы нод

---

**Документ создан после обсуждения логики коррекции 2026-02-14**
**Обновлён 2026-03-11: добавлен раздел 9 (логирование событий коррекции)**
**Обновлён 2026-07-08: добавлен раздел 10 (solution_change semi-auto v1, этап D.1)**
