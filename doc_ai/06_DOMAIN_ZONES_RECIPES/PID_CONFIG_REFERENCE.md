# PID_CONFIG_REFERENCE.md
# Справочник по настройке PID контроллеров pH/EC

Документ описывает фактическую архитектуру PID-коррекции pH и EC в AE3-Lite,
структуру `correction_config` в БД, параметры насосов и калибровку.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

**Обновлено:** 2026-03-12 — приведено в соответствие с реализацией AE3-Lite
(фикс integral spike, удаление dead-code параметров, валидация ml_per_sec).

---

## 1. Архитектура PID в AE3-Lite

### 1.1. Где живёт PID

**Активный PID** реализован **inline** в
`ae3lite/domain/services/correction_planner.py` (`_next_pid_state`,
`_compute_amount_ml`). Он использует состояние, персистируемое в таблице
`pid_state` в PostgreSQL — это обеспечивает сохранность integral/derivative
при перезапуске процесса.

> **Примечание:** файл `utils/adaptive_pid.py` содержит класс `AdaptivePid` и
> `RelayAutotuner`, которые **не используются в production-потоке коррекции**.
> Они являются standalone-утилитами для relay autotune и офлайн-симуляций.
> Не подключай `AdaptivePid.compute()` к handler'у без решения проблемы
> персистентности состояния.

### 1.2. Источник конфигурации

Параметры zoned PID tuning (dead/close/far zones, `zone_coeffs`, `max_integral`)
читаются из authority-документов
`zone.pid.ph` и `zone.pid.ec`, а в AE3 runtime попадают через compiled
bundle `automation_effective_bundles.config.zone.pid.*`. Класс
`AutomationSettings` в `config/settings.py` **не является** источником
PID-параметров — те поля были удалены как dead code.

Каноническое разделение source of truth:
- `zone.pid.*` хранит только tuning PID-контура;
- target берётся только из текущей recipe phase;
- лимиты доз и интервалы между дозами живут только в `zone.correction.resolved_config.controllers.*`.

Legacy-поля `target`, `max_output`, `min_interval_ms` в `zone.pid.*` и
`system.pid_defaults.*` удалены и не поддерживаются.

### 1.3. Расчёт дозы (упрощённо)

```
gap = max(0, target - current)       # всегда ≥ 0
integral += gap * dt                  # накопление ошибки × время
derivative = (gap - prev_error) / dt  # скорость изменения ошибки

if process_gain настроен:
    output_units = kp*gap + ki*integral + kd*derivative
    dose_ml = output_units / process_gain

else:
    dose_ml = gap * solution_volume_l * sensitivity

dose_ml = clamp(dose_ml, 0, max_dose_ml)
duration_ms = dose_ml / ml_per_sec * 1000
```

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
Ограничивает накопленный integral через clamp: `integral ∈ [-max_integral, max_integral]`.

| | pH | EC |
|--|----|----|
| Дефолт | 20.0 | 100.0 |

Максимальная доза от интегрального терма: `ki * max_integral / gain`.

### 3.8. `derivative_filter_alpha` — фильтр производной

**Тип:** float, диапазон `[0.0, 1.0]`
EMA-фильтр: `derivative = alpha * raw + (1 - alpha) * prev_derivative`.

- `1.0` — без фильтрации
- `0.35` — рекомендовано (умеренное сглаживание)
- `0.0` — полностью инерционный (не использовать)

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

### 4.2. Минимальный порог `_MIN_DOSE_MS = 50 мс`

После конвертации `ml → ms` применяется ещё один фильтр: импульсы короче
50 мс отбрасываются (ниже надёжного времени активации насоса).

Если доза отброшена — в лог пишется **WARNING** с полями:
- `dose_ml`, `ml_per_sec`, `duration_ms`

Это означает, что `min_effective_ml` слишком мало для данной скорости насоса.
Увеличь `min_effective_ml` или замедли насос.

**Формула проверки:**
```
min_pulse_ml = ml_per_sec * (MIN_DOSE_MS / 1000)
             = ml_per_sec * 0.05

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

**`ec_gain_per_ml`** — прирост EC (mS/cm) на 1 мл питательного раствора
в баке `solution_volume_l` литров. Используется как делитель:
`dose_ml = output_units / ec_gain_per_ml`.

Observation-driven runtime требует явные process gain:
`ec_gain_per_ml`, `ph_up_gain_per_ml`, `ph_down_gain_per_ml`.
Если для фазы отсутствует нужный gain или не заданы
`transport_delay_sec` / `settle_sec`, planner/handler работают fail-closed.

Для `tank_recirc` runtime дополнительно использует conservative floor:
learned `pid_state.stats.adaptive.gains.ec_gain_per_ml.ema` может
повысить оценку gain, но не может опустить её ниже authoritative
`process_calibrations.tank_recirc.ec_gain_per_ml`. Это защищает рециркуляцию
от раздувания EC-дозы из-за переобучения на слишком “мягких” окнах.

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
| `last_dose_at` | timestamp | Время последней дозы (для min_interval_sec) |
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

### 8.2. Признаки неправильной настройки

| Симптом | Вероятная причина | Действие |
|---------|-------------------|---------|
| Постоянные дозы малого объёма | `deadband` слишком мал | Увеличить `deadband` |
| Перерегулирование (oscillation) | `kp` или `ki` слишком велики | Снизить на 20% |
| Медленная реакция | `kp` слишком мал | Увеличить `kp` |
| WARNING "Dose discarded" в логах | `min_effective_ml` < `ml_per_sec * 0.05` | Увеличить `min_effective_ml` |
| `PlannerConfigurationError: ml_per_sec out of range` | Некорректная калибровка насоса | Проверить значение ml_per_sec |
| Integral spike после нормализации | Устаревшая версия planner | Обновить до фикса `last_measurement_at` |

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

## 9. Relay Autotune (экспериментально)

`utils/adaptive_pid.py` содержит `RelayAutotuner` (Astrom-Hagglund, 1984):
- Подаёт relay output ±`relay_amplitude_ml`
- Фиксирует extrema при пересечении нуля ошибки
- После `min_cycles` колебаний вычисляет Ku, Tu
- Применяет SIMC: `Kp = 0.45 * Ku`, `Ki = Kp / (0.83 * Tu)`

**Статус:** Не интегрировано в correction handler. Требует разработки
endpoint'а запуска и механизма записи результатов в `correction_config`.

---

## 10. Связанные файлы

| Файл | Назначение |
|------|-----------|
| `ae3lite/domain/services/correction_planner.py` | Расчёт дозы, PID inline |
| `ae3lite/domain/services/phase_utils.py` | `normalize_phase_key` |
| `ae3lite/infrastructure/repositories/pid_state_repository.py` | Персистентность |
| `ae3lite/application/handlers/correction.py` | Orchestration (8-шаговая FSM) |
| `utils/adaptive_pid.py` | Standalone PID (не production) |
| `config/settings.py` | Системные параметры (НЕ PID-коэффициенты) |
| `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` | State machine коррекции |
