# PID_CONFIG_REFERENCE.md
# Справочник по настройке PID контроллеров pH/EC

Документ описывает фактическую архитектуру PID-коррекции pH и EC в AE3-Lite,
структуру `correction_config` в БД, параметры насосов и калибровку.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

**Обновлено:** 2026-07-22 — sequential nutrient pipeline↔PID invariants (§11);
impulse model + PI assist; integral freeze на hold/observe; conditional-integration
anti-windup; `expected_effect` на `effective_process_gain`; порог дозы из
`pump_calibration.min_dose_ms`; legacy `AdaptivePid` / `pid_config_service` /
`correction_cooldown` **удалены**.

---

## 0. Authority matrix (канон AE3)

| Параметр | Source of truth |
|----------|-----------------|
| target pH/EC | recipe phase only |
| cumulative `T_*` / water baseline | `zone_prepare_baselines` + recipe ratios (см. `EFFECTIVE_TARGETS_SPEC.md` §9) |
| kp/ki/kd, dead/close/far zones | `zone.pid.{ph,ec}` |
| min_interval_sec, max_dose_ml, **max_integral**, derivative_filter_alpha, observe | `zone.correction.controllers.*` |
| process gains, transport_delay, settle | `zone.process_calibration.*` |
| per-component EC gains | `zone.process_calibration.*.ec_component_gains.{calcium\|magnesium\|npk\|micro}.ec_gain_per_ml` |
| dilute-on-overshoot | `zone.correction.recirc.ec_overshoot_dilute_*` |
| min/max_dose_ms, ml_per_sec | pump_calibration |

**Не AE3 authority:**
- `targets.*.controller` в effective-targets (legacy Laravel shape);
- `controllers.kp/ki/kd/deadband` при наличии `zone.pid` — fallback only;
  UI LiveEdit их не редактирует (редактор — `PidConfigForm` → `zone.pid.*`);
- `zone.pid.*.max_integral` — **deprecated / not used by AE3** (пишется UI для
  совместимости payload; runtime clamp читает `controllers.*.max_integral`);
- schema theatre (ignored-by-runtime): `controllers.*.mode`, `anti_windup.*`,
  `overshoot_guard.*`, `no_effect.enabled/max_count`, `safety.safe_mode_on_no_effect`.

---

## 1. Архитектура PID в AE3-Lite

### 1.1. Где живёт PID

**Канонический runtime** — импульсный observation-driven контур
`dose → hold → observe → decide` в AE3-Lite:

- планирование дозы / PID math: `ae3lite/domain/services/correction_planner.py`
  (`_next_pid_state`, `_compute_amount_ml`, `effective_process_gain`);
- observation / no-effect: `ae3lite/domain/services/observation_analyzer.py`;
- orchestration FSM: `ae3lite/application/handlers/correction.py` (8 шагов `corr_*`).

Состояние персистируется в таблице `pid_state` (integral/derivative/stats
переживают рестарт automation-engine).

Это **не** классический continuous PID: между импульсами идёт transport delay +
observe window; hard cap `dose ≤ gap / process_gain` не даёт одному pulse
перелететь target. При `kp ≥ 1` выход часто упирается в model dose
(`gap/gain`) — коэффициенты в основном задают undershoot и вклад I/D.

### 1.2. Источник конфигурации

Параметры zoned PID tuning (dead/close/far zones, `zone_coeffs`)
читаются из authority-документов
`zone.pid.ph` и `zone.pid.ec`, а в AE3 runtime попадают через compiled
bundle `automation_effective_bundles.config.zone.pid.*`.

Каноническое разделение source of truth — см. §0.

Поля `target`, `max_output`, `min_interval_ms` в `zone.pid.*` (вне актуального контракта) и
`system.pid_defaults.*` удалены и не поддерживаются.

### 1.3. Расчёт дозы (упрощённо)

```
gap = max(0, T_step - current)        # EC: T_step = active cumulative target; всегда ≥ 0 (вверх-only)
integral += gap * dt                  # только active-time dt (не hold/observe); не тикаем при corr_ec_pid_frozen
derivative = (gap - prev_error) / dt  # скорость изменения ошибки
derivative = α * raw + (1-α) * prev   # EMA; α default 0.35 если ключ отсутствует

# process_gain: per-component ec_component_gains.{component}.ec_gain_per_ml если задан,
# иначе phase ec_gain_per_ml; fail-closed если отсутствует
# effective_gain = auth ⊕ learned EMA (clamp 0.25×–4×; tank_recirc EC floor)
# learned EMA — не общий across components (auth per-component only; см. §11)
output_units = kp*gap + ki*integral + kd*derivative
dose_ml = output_units / effective_gain

dose_ml = min(dose_ml, gap / effective_gain)   # hard cap: не перелетать T_step за 1 импульс
dose_ml = clamp(dose_ml, 0, max_dose_ml)
# при saturation (gap/gain | max_dose_ml | max_dose_ms) — conditional integration:
# ΔI тика не персистится (anti-windup via _with_frozen_integral)
duration_ms = dose_ml / ml_per_sec * 1000
# импульс < pump_calibration.min_dose_ms → discard (below_min_dose_ms)
```

`solution_volume_l` обязателен в correction config (fail-closed metadata/UI),
но **не входит** в формулу `dose_ml`.

`expected_effect` для no-effect использует тот же `effective_process_gain`,
что и planner (parity порога с gain, которым считали дозу).

---

## 2. Структура correction bundle

Correction runtime-контракт хранится в authority-документе `zone.correction`
и materialized в `payload.resolved_config`, а PID tuning хранится отдельно
в `zone.pid.ph` и `zone.pid.ec`.

```json
{
  "solution_volume_l": 100.0,

  "controllers": {
    "ec": {
      "kp": 30.0,
      "ki": 0.3,
      "kd": 0.0,
      "deadband": 0.1,
      "min_interval_sec": 120,
      "max_dose_ml": 50.0,
      "max_integral": 100.0,
      "derivative_filter_alpha": 0.35
    },
    "ph": {
      "kp": 5.0,
      "ki": 0.05,
      "kd": 0.0,
      "deadband": 0.05,
      "min_interval_sec": 90,
      "max_dose_ml": 20.0,
      "max_integral": 20.0,
      "derivative_filter_alpha": 0.35
    }
  },

  "max_ec_dose_ml": 50.0,
  "max_ph_dose_ml": 20.0
}
```

Ограничение дозы: `min(controller.max_dose_ml, max_ec/ph_dose_ml)` —
controller-level ограничение имеет приоритет при `> 0`.

---

## 3. Описание параметров контроллера

### 3.1. `kp` — пропорциональный коэффициент

**Тип:** float
**Влияние:** прямая реакция на текущий gap (`kp * gap → output_units`).

| Параметр | pH (рекомендуемый диапазон) | EC (рекомендуемый диапазон) |
|----------|----------------------------|-----------------------------|
| Быстрый отклик | 8–15 | 40–70 |
| Умеренный | 3–8 | 20–40 |
| Осторожный | 1–3 | 5–20 |

### 3.2. `ki` — интегральный коэффициент

**Тип:** float
**Влияние:** устраняет постоянное отклонение, накапливая `gap * dt`.

Рекомендации:
- pH: 0.02–0.1 (осторожно, склонен к перерегулированию)
- EC: 0.05–0.3

> Интегральный term **ограничивается** полем `max_integral` (anti-windup
> через clamp).

### 3.3. `kd` — дифференциальный коэффициент

**Тип:** float, обычно `0.0`

Производная фильтруется через `derivative_filter_alpha` (EMA). Для
большинства гидропонных систем рекомендуется оставить `0.0` — шум датчика
усиливается дифференциатором.

### 3.4. `deadband` — мёртвая зона

**Тип:** float
Если `gap ≤ deadband`, коррекция не выполняется (нет дозы, нет обновления
integral).

| | pH | EC |
|--|----|----|
| Типовое значение | 0.05 | 0.1 |
| Минимальное | 0.02 | 0.05 |

### 3.5. `min_interval_sec` — минимальный интервал между дозами

**Тип:** int (секунды)
**Хранится в:** `pid_state.last_dose_at` (datetime в БД).

Пишется **только после terminal `DONE`** дозирующей команды в correction handler
(не на этапе планирования / не при TIMEOUT/ERROR). Это якорь для `min_interval_sec` cooldown
и observe-window (`last_dose_at + transport_delay_sec`).

Проверяется через `_retry_after()` — если `now - last_dose_at < min_interval_sec`,
planner возвращает `retry_after_sec` и доза не выдаётся.

| | pH | EC |
|--|----|----|
| Рекомендованный дефолт | 90 с | 120 с |
| Безопасный минимум | 60 с | 90 с |

### 3.6. `max_dose_ml` — лимит разовой дозы

**Тип:** float
Итоговое ограничение: `min(controller.max_dose_ml, correction_config.max_ph/ec_dose_ml)`.

| | pH | EC |
|--|----|----|
| Дефолт | 20 мл | 50 мл |
| Максимум рекомендованный | 30 мл | 100 мл |

### 3.7. `max_integral` — ограничение интегратора (anti-windup)

**Тип:** float  
**Source of truth:** `zone.correction.controllers.{ph,ec}.max_integral` (AE3 читает
только отсюда).

Ограничивает накопленный integral через clamp: `integral ∈ [-max_integral, max_integral]`.

> `zone.pid.*.max_integral` — **deprecated / not used by AE3**. Поле может
> сохраняться в authority payload / PidConfigForm для совместимости, но
> runtime clamp его **не** читает. Тюнить anti-windup потолок — через
> correction controllers / LiveEdit `controllers.*.max_integral`.

Дополнительно (AE3, 2026-07-20):
- **Integral freeze / active-time:** за hold+observe `integral` не растёт;
  `_next_pid_state(..., accumulate_integral=False)` или touch
  `last_measurement_at` после observe двигает measurement clock без `gap×dt` (production observe finalize пишет clock без ΔI — эквивалент флага; dual EC+PH: I только для dosing controller).
- **Conditional integration:** если доза на тике упёрлась в `gap/gain`,
  `max_dose_ml` или `clamped_to_max_dose_ms`, ΔI тика откатывается
  (`_with_frozen_integral`) — clamp `max_integral` остаётся запасным потолком.
  Флаг schema `anti_windup.enabled` **ignored-by-runtime** (логика всегда
  условная при saturation).

| | pH | EC |
|--|----|----|
| Дефолт | 20.0 | 100.0 |

Максимальная доза от интегрального терма: `ki * max_integral / gain`.

### 3.8. `derivative_filter_alpha` — фильтр производной

**Тип:** float, диапазон `[0.0, 1.0]`
EMA-фильтр: `derivative = alpha * raw + (1 - alpha) * prev_derivative`.

- ключ **отсутствует** → default **`0.35`** (код: `_DEFAULT_DERIVATIVE_FILTER_ALPHA`);
- `1.0` — без фильтрации (явное значение уважается);
- `0.0` — полностью инерционный (явное значение уважается; обычно не использовать);
- для большинства гидроконтуров рекомендуется `kd = 0.0`.

---

## 4. Калибровка дозирующих насосов

### 4.1. Обязательные поля

```json
{
  "calibration": {
    "ml_per_sec": 1.0,
    "min_effective_ml": 0.05
  }
}
```

**`ml_per_sec`** — скорость насоса в мл/сек. **Обязательное поле.**

- Допустимый диапазон: `[0.01, 100.0]`
- Если значение вне диапазона — `PlannerConfigurationError` (защита от опечаток)
- Пример: насос 1 мл/с, доза 5 мл → `duration_ms = 5000 мс`

> ⚠️ Опечатки типа `100.0` вместо `1.0` критичны: доза в 100× быстрее
> приведёт к передозировке. При `ml_per_sec < 0.01` (0.36 л/ч) нужна ручная
> проверка — скорее всего, ошибка единиц.

**`min_effective_ml`** — минимальная доза для надёжного срабатывания насоса.

- Если `dose_ml < min_effective_ml`, доза принудительно поднимается до `min_effective_ml`
- Значение `0.0` или отсутствие = не применяется

### 4.2. Минимальный порог `pump_calibration.min_dose_ms`

После конвертации `ml → ms` импульсы короче **`pump_calibration.min_dose_ms`**
отбрасываются (reason `below_min_dose_ms`, команда не публикуется).

Hard-coded `_MIN_DOSE_MS = 50` в AE3 runtime **нет** — порог задаётся
калибровкой насоса (вместе с `ml_per_sec` / `max_dose_ms`). Типовые
production-значения часто порядка десятков–сотен мс; согласуйте с
физическим разрешением насоса и firmware `safe_limits`.

Если доза отброшена — в лог/событие попадают:
- `dose_ml`, `ml_per_sec`, `duration_ms`, `min_dose_ms`

Это обычно значит, что `min_effective_ml` слишком мало для данной скорости
насоса, либо `min_dose_ms` завышен. Увеличь `min_effective_ml`, замедли
насос или пересмотри `min_dose_ms`.

**Формула проверки:**
```
min_pulse_ml = ml_per_sec * (min_dose_ms / 1000)

Если min_effective_ml < min_pulse_ml → доза может быть отброшена.
```

---

## 5. Калибровка процесса (`process_calibrations`)

Задаётся в runtime snapshot как маппинг `фаза → параметры`:

```json
{
  "solution_fill": {
    "ec_gain_per_ml": 0.25,
    "ph_up_gain_per_ml": 0.10,
    "ph_down_gain_per_ml": 0.12,
    "transport_delay_sec": 6,
    "settle_sec": 4,
    "meta": {
      "observe": {
        "telemetry_period_sec": 2,
        "window_min_samples": 3,
        "decision_window_sec": 6,
        "observe_poll_sec": 2,
        "min_effect_fraction": 0.25,
        "stability_max_slope": 0.05,
        "no_effect_consecutive_limit": 3
      }
    }
  },
  "irrigation": {
    "ec_gain_per_ml": 0.15,
    "transport_delay_sec": 8,
    "settle_sec": 6
  }
}
```

**`ec_gain_per_ml`** — прирост EC (mS/cm) на 1 мл дозы в текущей фазе
(эмпирическая process gain калибровка). Используется как делитель:
`dose_ml = output_units / effective_gain`. Величина **зависит** от объёма
контура физически, но `solution_volume_l` в runtime-формулу **не подставляется**
автоматически — оператор калибрует gain под реальный бак/контур.

**`ec_component_gains`** (optional, schema v1+): per-component override для
sequential nutrient pipeline:

```json
"ec_component_gains": {
  "calcium":   { "ec_gain_per_ml": 0.22 },
  "magnesium": { "ec_gain_per_ml": 0.18 },
  "npk":       { "ec_gain_per_ml": 0.25 },
  "micro":     { "ec_gain_per_ml": 0.12 }
}
```

При активном компоненте pipeline AE3 берёт
`ec_component_gains.{component}.ec_gain_per_ml`, иначе fallback на phase
`ec_gain_per_ml`. Общий EMA learned gain **не** смешивает компоненты
(см. §11).

Observation-driven runtime требует явные process gain:
`ec_gain_per_ml` (или per-component) / `ph_up_gain_per_ml` / `ph_down_gain_per_ml`.
Если для фазы отсутствует нужный gain или не заданы
`transport_delay_sec` / `settle_sec`, planner/handler работают fail-closed.

**Effective gain** (`effective_process_gain` / `_process_gain`):
`auth ⊕ learned EMA` с весом по числу observations, retention/wave,
clamp `[0.25×, 4×] auth`. Тот же effective gain использует
`ObservationAnalyzer.expected_effect` для порога no-effect.

Для `tank_recirc` runtime дополнительно использует conservative floor:
learned `pid_state.stats.adaptive.gains.ec_gain_per_ml.ema` может
повысить оценку gain, но не может опустить её ниже authoritative
`process_calibrations.tank_recirc.ec_gain_per_ml`. Это защищает рециркуляцию
от раздувания EC-дозы из-за переобучения на слишком “мягких” окнах.

**Adaptive observations (B10):** счётчики
`stats.adaptive.observations` и gain `observations` / effectiveness /
retention / wave EMA инкрементируются только при валидном learning update
(`dose_amount_ml > 0` и `learning_effect > 0`). Timing EMA обновляется
отдельно и не раздувает gain observations.

### Observe-параметры

`meta.observe` у phase calibration задаёт поведение окна наблюдения:

- `telemetry_period_sec` — ожидаемый период telemetry;
- `window_min_samples` — минимальное количество samples в окне;
- `decision_window_sec` — минимальная длина decision-window;
- `observe_poll_sec` — шаг повторной проверки, если окно ещё не готово;
- `min_effect_fraction` — нижняя граница физически значимого отклика;
- `stability_max_slope` — порог стабильности окна;
- `no_effect_consecutive_limit` — сколько подряд no-effect доз допускается до alert/fail-closed.

### Маппинг фаз

| Workflow phase | Canonical key | Источник конфига |
|----------------|--------------|-----------------|
| `solution_fill`, `tank_filling` | `solution_fill` | phases.solution_fill merged with base |
| `tank_recirc`, `prepare_recirculation` | `tank_recirc` | phases.tank_recirc merged with base |
| `irrigating`, `irrigation`, `irrig_recirc` | `irrigation` | phases.irrigation merged with base |
| всё остальное | `generic` | base config |

> Функция `normalize_phase_key` вынесена в
> `ae3lite/domain/services/phase_utils.py` — единственный источник правды
> для маппинга фаз.

---

## 6. PID State (`pid_state`)

### 6.1. Поля таблицы `pid_state`

| Поле | Тип | Назначение |
|------|-----|-----------|
| `zone_id` | int | ID зоны |
| `pid_type` | str (`'ph'`, `'ec'`) | Тип контроллера |
| `integral` | float | Накопленный интеграл (`gap * dt`) |
| `prev_error` | float | Предыдущий gap (для деривативы) |
| `prev_derivative` | float | Сглаженная производная |
| `last_dose_at` | timestamp | Время последней **успешной** дозы (`DONE`; для min_interval_sec и observe anchor) |
| `last_measurement_at` | timestamp | Время последнего измерения (для dt) |
| `last_measured_value` | float | Последнее измеренное значение |
| `feedforward_bias` | float | Смещение pH после EC-дозы |
| `no_effect_count` | int | Счётчик доз без эффекта (equipment anomaly guard) |
| `hold_until` | timestamp | До этого времени pH-плановый bias активен |
| `stats` | jsonb | Persisted runtime-learning: learned gain, timing, wave/retention EMA |
| `current_zone` | str (`dead/close/far`) | Активная PID-зона, выбранная planner-ом |

### 6.2. Сброс состояния при возврате в норму

Когда текущие pH и EC попадают в допустимые границы, `correction_planner`
автоматически сбрасывает PID state в ноль, записывая в `pid_state_updates`:

```python
{
    "integral": 0.0,
    "prev_error": 0.0,
    "prev_derivative": 0.0,
    "last_measurement_at": now,   # ← критично: обновляется до now
}
```

> **Важно:** `last_measurement_at` сбрасывается в `now`, а не остаётся
> старым timestamp'ом. Без этого при следующем выходе за пределы нормы
> `dt = now - stale_ts` мог быть несколько часов → integral мгновенно
> прыгал до `max_integral` уже при первом тике (integral spike).

### 6.3. Сохранение и восстановление

- Состояние сохраняется через `PgPidStateRepository.upsert_states()`
  после каждого `_run_check` в correction handler.
- При перезапуске процесса состояние восстанавливается из БД.
- `NULL` значение `last_measurement_at` при первом вызове → dt не
  вычисляется, integral остаётся 0.
- В `stats.adaptive` сохраняются learned runtime-метрики по отработанным
  окнам коррекции:
  - `gains.{ec_gain_per_ml|ph_up_gain_per_ml|ph_down_gain_per_ml}.ema`
  - `retention_ema`
  - `wave_score_ema`
  - `effectiveness_ema`
  - `timing.transport_delay_sec_ema`
  - `timing.settle_sec_ema`
- Эти данные не являются authority-конфигом и не редактируются из UI,
  но используются runtime после рестарта automation-engine.

---

## 7. Рекомендованные конфигурации

### 7.1. Салат (консервативно, pH 6.0, EC 1.5 mS/cm)

```json
{
  "controllers": {
    "ph": {
      "kp": 4.0, "ki": 0.02, "kd": 0.0,
      "deadband": 0.07, "min_interval_sec": 120,
      "max_dose_ml": 15.0, "max_integral": 20.0
    },
    "ec": {
      "kp": 20.0, "ki": 0.1, "kd": 0.0,
      "deadband": 0.1, "min_interval_sec": 180,
      "max_dose_ml": 30.0, "max_integral": 80.0
    }
  },
  "solution_volume_l": 100.0,
  "max_ph_dose_ml": 15.0,
  "max_ec_dose_ml": 30.0
}
```

### 7.2. Томат/Огурец (агрессивнее, pH 5.8, EC 2.5 mS/cm)

```json
{
  "controllers": {
    "ph": {
      "kp": 6.0, "ki": 0.05, "kd": 0.0,
      "deadband": 0.05, "min_interval_sec": 90,
      "max_dose_ml": 20.0, "max_integral": 20.0
    },
    "ec": {
      "kp": 35.0, "ki": 0.2, "kd": 0.0,
      "deadband": 0.1, "min_interval_sec": 120,
      "max_dose_ml": 50.0, "max_integral": 100.0
    }
  },
  "solution_volume_l": 150.0,
  "max_ph_dose_ml": 20.0,
  "max_ec_dose_ml": 50.0
}
```

---

## 8. Диагностика и мониторинг

### 8.1. Ключевые события в zone_events

| Тип | Условие |
|-----|---------|
| `EC_DOSING` | После отправки команды EC-насосу |
| `PH_CORRECTED` | После отправки команды pH-насосу |
| `CORRECTION_SKIPPED_COOLDOWN` | `retry_after_sec > 0` |
| `CORRECTION_SKIPPED_DOSE_DISCARDED` | discard ≠ deadband success |
| `CORRECTION_SKIPPED_DEAD_ZONE` | true deadband, нет discard reason |

### 8.2. Признаки неправильной настройки

| Симптом | Вероятная причина | Действие |
|---------|-------------------|---------|
| Постоянные дозы малого объёма | `deadband` слишком мал | Увеличить `deadband` |
| Перерегулирование (oscillation) | `kp` или `ki` слишком велики | Снизить на 20% |
| Медленная реакция | `kp` слишком мал | Увеличить `kp` |
| WARNING / discard `below_min_dose_ms` | `duration_ms < pump_calibration.min_dose_ms` | Поднять `min_effective_ml` или снизить `min_dose_ms` / скорость |
| `PlannerConfigurationError: ml_per_sec out of range` | Некорректная калибровка насоса | Проверить значение ml_per_sec |
| Integral spike после нормализации | Устаревшая версия planner | Обновить до фикса `last_measurement_at` + freeze |
| Ложные no-effect после адаптации gain | Порог на auth gain (legacy) | Runtime должен считать `expected_effect` через `effective_process_gain` |

### 8.3. Просмотр PID state через БД

```sql
SELECT zone_id, pid_type, integral, prev_error,
       last_dose_at, last_measurement_at, no_effect_count
FROM pid_state
WHERE zone_id = $1
ORDER BY pid_type;
```

### 8.4. Ручной сброс интегратора

```sql
UPDATE pid_state
SET integral = 0, prev_error = 0, prev_derivative = 0,
    last_measurement_at = NOW(), updated_at = NOW()
WHERE zone_id = $1;
```

---

## 11. Pipeline ↔ PID инварианты (sequential nutrient)

Pipeline **не заменяет** PID — меняет target (`T_step`) и actuator. Канон
(см. `CORRECTION_CYCLE_SPEC.md` §3.7, `EFFECTIVE_TARGETS_SPEC.md` §9):

| # | Инвариант | Поведение |
|---|-----------|-----------|
| 1 | EC gap | `gap = max(0, T_step − current_ec)` |
| 2 | Один насос на шаг | `pump_b` для Ca, `pump_c` Mg, `pump_a` NPK, `pump_d` Micro |
| 3 | Reset I/D на смене компонента | `pid_state.ec.integral/prev_* → 0`; event `PID_EC_RESET` |
| 4 | Reset I + no_effect на dilute | после `RECIRC_DILUTE_*` |
| 5 | Freeze EC на pH-gate | `corr_ec_pid_frozen=true`: EC PID не тикает (нет ΔI, нет EC dose) |
| 6 | Per-component gain | `ec_component_gains.{component}` (auth); не общий EMA across components |
| 7 | no-effect per component | счётчик сбрасывается при switch компонента |
| 8 | fill_ca → recirc_ca | **не** reset I (тот же компонент calcium) |
| 9 | irrigation | только pH PID; EC off |
| 10 | Overshoot | только dilute (`zone.correction.recirc.*`); EC вверх-only |

Нарушение reset/freeze на switch/pH-gate → перелёты и ложный no-effect.

---

## 12. Связанные файлы

| Файл | Назначение |
|------|-----------|
| `ae3lite/domain/services/correction_planner.py` | Расчёт дозы, PID inline, `effective_process_gain` |
| `ae3lite/domain/services/observation_analyzer.py` | Observe window, expected_effect, adaptive EMA |
| `ae3lite/domain/services/phase_utils.py` | `normalize_phase_key` |
| `ae3lite/infrastructure/repositories/pid_state_repository.py` | Персистентность |
| `ae3lite/application/handlers/correction.py` | Orchestration (pipeline + corr_* FSM) |
| `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` | State machine коррекции |
| `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` §9 | Water-baseline + `T_*` |

---

## 13. Удалённый legacy (не восстанавливать)

Удалены из дерева (2026-07-20): `utils/adaptive_pid.py`,
`services/pid_config_service.py`, `correction_cooldown.py` и связанные
legacy unit-тесты. Канон — только AE3-Lite planner + `pid_state` +
`zone.correction` / `zone.pid` / `process_calibration`.

Deprecated семантика prepare (2026-07-22): `npk_ec_share` / `target_ec_prepare`
как owner prepare EC; post-irrigation EC recovery; EC dosing на irrigation.
