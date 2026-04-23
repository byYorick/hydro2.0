# SENSOR_HEALTH_CHARTER.md
# Паспорт pipeline: здоровье датчиков, cross-check, drift detection

**Статус:** 🟡 CHARTER (внедрять РАНО, до любого ML)
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/SENSOR_HEALTH_CHARTER.md`
**Связанные:** `ML_FEATURE_PIPELINE.md§5.5 ml_calibration_events`,
все остальные — все используют датчики

---

## 1. Назначение

Ошибка датчика ≠ сломанный датчик. Датчик может:
- дрейфовать медленно и незаметно;
- конфликтовать с соседними (T внутри зоны выше наружной при выключенном
  отоплении — что-то не так);
- давать шум выше нормы (стареет ADC / EMI);
- читать stale value (firmware bug, висит последнее значение).

Без этого слоя вся ML-башня тренируется на мусоре.

## 2. Цели

- Определять «плохой датчик» до того, как его значения попадут в обучение.
- Автоматически помечать окна в `ml_data_quality_windows` как excludable.
- Напоминать о калибровке по расписанию / по дрейфу.
- Гарантировать ≥ 2 независимых источника для критичных метрик (pH, EC,
  T) где возможно.

## 3. Ключевые дизайн-решения

1. **Cross-check правила**: set of invariants, которые должны быть истинны
   (например: T_inside > T_outside - 5°C при работающем отоплении). Нарушение
   → flag.
2. **Drift detection**: для каждого sensor_id fit линейный тренд на
   `telemetry_samples` за 30 дней. Если `|slope| > threshold` — flag.
3. **Noise scoring**: rolling std за 1 час сравнивается с ожидаемым по типу
   датчика. Выше — flag.
4. **Stale detection**: `telemetry_last` не обновился > `expected_interval ×
   2` → flag.
5. **Redundancy voting**: где есть 2+ датчика одной метрики, median-voting +
   flag на отклоняющегося.

## 4. Структура данных

```sql
CREATE TABLE sensor_health_checks (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL,
  sensor_id bigint NOT NULL REFERENCES sensors(id),
  zone_id bigint REFERENCES zones(id),
  check_type varchar(32) NOT NULL,       -- 'cross_check'|'drift'|'noise'|'stale'|'voting'
  status varchar(16) NOT NULL,           -- 'ok'|'warn'|'fail'
  value_observed double precision,
  threshold_used double precision,
  details jsonb
);
SELECT create_hypertable('sensor_health_checks','ts',chunk_time_interval=>interval '7 days');
CREATE INDEX shc_sensor_ts ON sensor_health_checks (sensor_id, ts DESC);

CREATE TABLE sensor_invariants (
  id bigserial PRIMARY KEY,
  name varchar(64) NOT NULL,
  description text,
  invariant_expr text NOT NULL,          -- SQL или DSL
  severity varchar(16) NOT NULL,
  enabled boolean DEFAULT true,
  source varchar(32)                     -- 'best_practice'|'domain_expert'|'ml_learned'
);

CREATE TABLE calibration_reminders (
  id bigserial PRIMARY KEY,
  sensor_id bigint NOT NULL REFERENCES sensors(id),
  due_at timestamptz NOT NULL,
  reason varchar(64) NOT NULL,           -- 'schedule'|'drift_detected'|'after_replacement'
  created_at timestamptz NOT NULL DEFAULT now(),
  acknowledged_by bigint REFERENCES users(id),
  acknowledged_at timestamptz
);
```

Расширение `sensors.specs` (JSONB) полями `expected_noise_std`,
`max_drift_per_day`, `calibration_interval_days`.

## 5. Сервис `sensor-health-monitor`

- Раз в 5 минут: проверяет все invariants из `sensor_invariants`.
- Раз в час: drift detection по 30-дневной истории.
- На каждый новый `telemetry_samples`: noise checking в скользящем окне.
- Пишет flags в `sensor_health_checks` и `ml_data_quality_windows`
  (с `severity='exclude'`).

## 6. Invariants (примеры)

| Invariant | Условие | Severity |
|---|---|---|
| T_inside ≥ T_outside - 5 при heater ON | physical | warn |
| |pH_sensor1 - pH_sensor2| ≤ 0.3 | redundancy | fail |
| EC ≥ 0.2 при любых условиях | minimum | fail |
| RH ∈ [10, 100] | range | fail |
| VPD = es(T)·(1-RH/100) совместим | derived | warn |
| last_read_at не старше 60 сек для active sensor | stale | fail |

## 7. Фазы

| Phase | Задача | DoD |
|---|---|---|
| S0 | Скрипт-разовик: анализ существующих данных, какие sensors уже мусор | Отчёт по зонам |
| S1 | `sensor-health-monitor` skeleton + базовые checks | Пишет `sensor_health_checks` |
| S2 | Invariants DSL + seed 20 базовых | 20 правил активны |
| S3 | Drift detection + reminders UI | Оператор видит «калибровать через N дней» |
| S4 | Integration с `ml_data_quality_windows` | Bad windows реально исключаются из обучения |
| S5 | Redundancy voting (где доступно) | Outlier среди дублёров flag'ируется |

## 8. Интеграция

- **Все ML pipeline'ы** читают `ml_data_quality_windows` при тренировке —
  sensor-health-monitor главный писатель туда.
- **UNIFIED_ALERTING** — critical sensor fails туда.
- **ML_FEATURE_PIPELINE** — уже имеет `ml_calibration_events`, расширяется
  автоматическими notifications.

## 9. Правила для ИИ-агентов

### Можно:
- Добавлять новые invariants в `sensor_invariants` (с цитатой источника).
- Учить ML-based drift detection поверх правил.

### Нельзя:
- Автоматически отключать датчик по flag'у (только ops-UI).
- Менять invariants с severity='fail' без ревью (safety-impact).

## 10. Открытые вопросы

1. Где хранить DSL invariant'ов: inline SQL / CEL / собственный? SQL проще.
2. Как bootstrap'ить `expected_noise_std` для новых датчиков — из
   вендорских specs или из первой недели работы?

---

# Конец SENSOR_HEALTH_CHARTER.md
