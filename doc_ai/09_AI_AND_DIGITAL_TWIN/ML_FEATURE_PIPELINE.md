# ML_FEATURE_PIPELINE.md
# План внедрения ML feature pipeline для hydro2.0
# Прогноз дрейфа pH/EC • Детекция аномалий • Обучение модели дозирования

**Статус:** DRAFT · предложение к внедрению
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md`
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
**Breaking-change:** нет (только additive DDL, новые сервисы)

---

## 0. Назначение документа

Документ определяет, **что и как построить поверх существующего телеметрического
конвейера**, чтобы получить ML-ready данные для:

1. прогноза дрейфа pH/EC на 5–60 минут вперёд,
2. детекции аномалий (закисление, засоление, отказ датчика, забитая форсунка),
3. обучения модели, которая подсказывает объём дозировки корректора.

Документ обязателен к прочтению:
- **человеку** — как дорожная карта с фазами и критериями приёмки;
- **ИИ-агенту** — как спецификация, по которой можно генерировать миграции,
  SQL-запросы, сервисный код и тесты. Все данные должны соответствовать
  инвариантам из раздела 7 и 8.

---

## 1. Итоговые цели ML-слоя

### 1.1. Бизнес-цели

- Снизить ручные корректировки pH/EC в зонах минимум на 50% за 3 месяца после
  релиза ML-дозатора.
- Предупреждать оператора об аномалиях за ≥20 минут до выхода за safety-пороги.
- Давать в UI прогноз pH/EC на 1 час с MAE ≤ 0.1 pH, ≤ 0.15 mS/cm.

### 1.2. Технические цели

- Иметь широкую (wide) ML-ready витрину `zone_features_5m` со всеми фичами
  в одной строке на окно 5 минут × зона.
- Иметь витрину `dose_response_events` «доза → отклик» для supervised-обучения
  модели дозирования.
- Иметь таблицу таргетов `ml_labels` с несколькими горизонтами прогноза.
- Иметь лог предсказаний `ml_predictions` для детекции дрейфа модели.
- Все перечисленные витрины должны строиться инкрементально (continuous
  aggregate / периодический worker) и быть idempotent.

### 1.3. Не-цели (вне скоупа этого документа)

- Обучение конкретных моделей (это отдельные runbook'и в `tools/ml/`).
- Замена `automation-engine` или `digital-twin`.
- Изменение контрактов MQTT (топики и payload не трогаем).

---

## 2. Текущее состояние (ревизия ветки `ae3`)

| Слой | Что есть | Путь |
|---|---|---|
| Raw телеметрия | `telemetry_samples` (id, sensor_id, ts, zone_id, cycle_id, value, quality, metadata) | `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md §4.2` |
| Last values | `telemetry_last` | `§4.3` |
| 1m агрегаты | `telemetry_agg_1m` (avg/min/max/median/count по `(zone, node, channel, metric_type, ts)`) | `backend/services/telemetry-aggregator/main.py` L201–274 |
| 1h / daily | `telemetry_agg_1h`, `telemetry_daily` | same |
| События коррекций | `zone_events` с типами `CORRECTION_COMPLETE`, `CORRECTION_SKIPPED_*`, `CORRECTION_NO_EFFECT` | `§8.1` |
| Команды дозирования | `commands`, `command_tracking`, `command_audit` (последняя содержит `telemetry_snapshot`, `decision_context`, `pid_state`) | `§6.1–6.3` |
| Циклы роста | `grow_cycles` (якорь «эпизода») | `§6.1 Recipes` |
| Симуляция | `digital-twin/main.py` + `models.py` (простые pH/EC-модели с фикс. параметрами) | `backend/services/digital-twin/` |
| Retention | raw 30 дней, 1m 30 дней, 1h 365 дней, daily ∞ | `doc_ai/05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md` |

### Что уже правильно и не трогаем

- Единая точка записи телеметрии — Python Router (никто не пишет в БД мимо него).
- `command_audit` уже пишет `telemetry_snapshot` рядом с командой — **это и есть
  фундамент для обучения dose-response модели.**
- Timescale (есть `time_bucket`), `ON CONFLICT DO UPDATE` логика — сделано.

---

## 3. Пробелы, которые закрываем

| # | Пробел | Почему это блокер для ML |
|---|---|---|
| G1 | Агрегаты «длинные» (row-per-metric), а не «широкие» | На каждый train/inference нужен дорогой pivot |
| G2 | Нет `std` / rolling variance | Заявлено в `AI_ARCH_FULL.md §4.1`, но не реализовано. Без него нет фичи «нестабильность» |
| G3 | Нет `slope` (dp/dt) | Ключевая фича для прогноза и детекции |
| G4 | Нет соединения (dose → telemetry after N min) в одной таблице | Ручной join каждый раз; риск ошибок point-in-time |
| G5 | Нет таблицы таргетов | Leakage при обучении почти гарантирован |
| G6 | Нет лога предсказаний модели | Дрейф не задетектим |
| G7 | Агрегаты считают и по `quality = BAD/UNCERTAIN` | Смещение avg при обрыве датчика |
| G8 | 1m retention 30 дней | Для сезонных паттернов нужно ≥ 6–12 мес |
| G9 | Нет регистра событий калибровки сенсоров | Данные до/после калибровки нельзя мешать без поправки |
| G10 | Нет feature schema versioning | Любая эволюция фичей ломает старые чекпоинты моделей |

---

## 4. Архитектура решения (высокоуровнево)

```
                  telemetry_samples (raw, 30 дней)
                             │
                             ▼
               telemetry-aggregator (расширен)
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
 telemetry_agg_1m     telemetry_agg_1h   telemetry_daily
 (+std, +slope,       (warm, 365 дней)   (cold, ∞)
  +valid_count;
  1m, 365 дней
  с Timescale
  compression)
           │
           ▼
   feature-builder (новый сервис)
           │
           ├─► zone_features_5m          (ML wide view, 5-мин окно)
           ├─► dose_response_events      (доза → отклик, готовый датасет)
           ├─► ml_labels                 (таргеты на +5/+15/+60 мин)
           └─► ml_data_quality_windows   (окна, непригодные для обучения)
                             │
                             ▼
            ┌────────────────┴────────────────┐
            ▼                                 ▼
      training notebooks                inference-server
      (tools/ml/)                       (новый сервис)
            │                                 │
            ▼                                 ▼
       ml_models table                  ml_predictions table
       (registry, versioning)           (лог inference + ground truth)
                                              │
                                              ▼
                                    automation-engine
                                    (использует ML-поправку
                                     как advisory, не как control)
```

Ключевой принцип: **feature-builder — единственный owner** таблиц
`zone_features_5m`, `dose_response_events`, `ml_labels`. Никто другой в них не
пишет. Любой пользовательский/модельный код читает эти витрины только на чтение.

---

## 5. Изменения в схеме данных

> Все DDL ниже — **предложение**. Финальная миграция оформляется по конвенциям
> `backend/laravel/database/migrations/` и сопровождается Rollback-скриптом.

### 5.1. Расширение `telemetry_agg_1m` (additive)

```sql
ALTER TABLE telemetry_agg_1m
  ADD COLUMN value_std        double precision,
  ADD COLUMN value_p10        double precision,
  ADD COLUMN value_p90        double precision,
  ADD COLUMN slope_per_min    double precision,  -- линейная регрессия по окну
  ADD COLUMN valid_count      integer DEFAULT 0, -- только quality=GOOD
  ADD COLUMN agg_version      smallint DEFAULT 1;
```

**Зачем каждое поле:**

- `value_std` — «нестабильность» сигнала; фича для аномалий (забитая форсунка,
  шумный кабель).
- `value_p10`/`value_p90` — устойчивые к выбросам границы; дают модели
  сигнал о распределении без веса хвостов.
- `slope_per_min` — скорость изменения; главная фича прогноза.
- `valid_count` — сколько из `sample_count` прошли quality-фильтр. Отношение
  `valid_count / sample_count` = метрика «здоровья» сенсора в окне.
- `agg_version` — позволит перепрожарить агрегаты без удаления старых, если
  когда-то поменяется формула.

Обновление запроса в `telemetry-aggregator/main.py` (L201): добавить
`stddev_samp(ts.value)`, `percentile_cont(0.1)`, `percentile_cont(0.9)`, и
`regr_slope(ts.value, extract(epoch from ts.ts)/60.0)`. Quality-фильтр — не через
`WHERE`, а через `FILTER (WHERE ts.quality = 'GOOD')` на всех агрегатах, чтобы
сохранить `sample_count` и отдельно считать `valid_count`.

### 5.2. `zone_features_5m` (ML-ready wide view)

**Owner:** `feature-builder`. **Назначение:** основная обучающая витрина и
источник признаков для inference.

```sql
CREATE TABLE zone_features_5m (
  ts                    timestamptz NOT NULL,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,

  -- контекст эпизода
  cycle_id              bigint      REFERENCES grow_cycles(id),
  recipe_phase          varchar(32),          -- 'vegetative' | 'flowering' | ...
  hours_since_cycle_start double precision,
  hours_since_water_change double precision,

  -- основные параметры раствора (mean / std / slope за окно 5 мин)
  ph_mean               double precision,
  ph_std                double precision,
  ph_slope              double precision,
  ph_min                double precision,
  ph_max                double precision,

  ec_mean               double precision,
  ec_std                double precision,
  ec_slope              double precision,
  ec_min                double precision,
  ec_max                double precision,

  water_temp_mean       double precision,
  water_level_mean      double precision,

  -- внешние условия
  air_temp_mean         double precision,
  air_hum_mean          double precision,
  light_mean            double precision,
  co2_mean              double precision,

  -- производные инженерные фичи
  ph_buffer_est         double precision, -- Δph / (volume_ph_corrector) за последние 30 мин
  ec_consumption_rate   double precision, -- mS/cm в час, прокси транспирации
  water_evaporation_rate double precision, -- L/ч

  -- актуаторы: объёмы за окно 5 мин
  dose_ph_down_ml       double precision DEFAULT 0,
  dose_ph_up_ml         double precision DEFAULT 0,
  dose_npk_ml           double precision DEFAULT 0,
  dose_ca_ml            double precision DEFAULT 0,
  dose_mg_ml            double precision DEFAULT 0,
  dose_micro_ml         double precision DEFAULT 0,
  water_added_ml        double precision DEFAULT 0,

  -- качество данных
  valid_ratio           double precision,    -- доля GOOD точек
  data_gap_seconds      integer,             -- максимальный разрыв в окне
  feature_schema_version smallint NOT NULL DEFAULT 1,

  PRIMARY KEY (zone_id, ts)
);

CREATE INDEX zone_features_5m_ts_idx ON zone_features_5m (ts);
CREATE INDEX zone_features_5m_cycle_idx ON zone_features_5m (cycle_id, ts);

-- Timescale hypertable
SELECT create_hypertable('zone_features_5m', 'ts', chunk_time_interval => interval '7 days');
ALTER TABLE zone_features_5m SET (timescaledb.compress, timescaledb.compress_segmentby = 'zone_id');
SELECT add_compression_policy('zone_features_5m', interval '14 days');
```

**Почему ровно 5 минут:**
- pH/EC в DWC/NFT имеют постоянные времени порядка минут — окно 1 мин шумное,
  15 мин уже «размывает» ранние признаки аномалии.
- 5 минут = 288 строк/сутки/зона — за год ~105k строк/зона. Дёшево в Timescale.
- Горизонты прогноза +5/+15/+60 мин ровно ложатся на сетку.

### 5.3. `dose_response_events`

**Owner:** `feature-builder`. **Назначение:** supervised-датасет «доза → отклик»
для обучения модели дозирования.

```sql
CREATE TABLE dose_response_events (
  id                    bigserial PRIMARY KEY,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  cycle_id              bigint      REFERENCES grow_cycles(id),
  recipe_phase          varchar(32),

  dose_ts               timestamptz NOT NULL,   -- момент начала дозирования
  dose_end_ts           timestamptz NOT NULL,
  reagent               varchar(32) NOT NULL,   -- 'ph_down'|'ph_up'|'npk'|'ca'|'mg'|'micro'
  volume_ml             double precision NOT NULL,
  pump_id               bigint,
  command_id            bigint,                 -- FK на commands.id
  source                varchar(16) NOT NULL,   -- 'pid'|'ml_advisory'|'manual'

  -- состояние до (snapshot в момент dose_ts)
  ph_before             double precision,
  ec_before             double precision,
  water_temp_before     double precision,
  water_volume_l_before double precision,
  ph_slope_before       double precision,       -- за 15 мин до
  ec_slope_before       double precision,

  -- отклик через N минут (ph/ec усреднённые за ±30 сек вокруг метки)
  ph_at_plus_5m         double precision,
  ec_at_plus_5m         double precision,
  ph_at_plus_15m        double precision,
  ec_at_plus_15m        double precision,
  ph_at_plus_60m        double precision,
  ec_at_plus_60m        double precision,

  -- нормированный отклик
  d_ph_per_ml_15m       double precision,       -- (ph@15 - ph_before) / volume_ml
  d_ec_per_ml_15m       double precision,

  -- чистота эксперимента
  is_clean              boolean NOT NULL,       -- true, если в окне ±60 мин не было других доз
  is_settled            boolean NOT NULL,       -- true, если |slope_before| < threshold
  exclusion_reason      varchar(64),            -- заполнено, если is_clean=false

  feature_schema_version smallint NOT NULL DEFAULT 1,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX dose_response_zone_ts_idx ON dose_response_events (zone_id, dose_ts);
CREATE INDEX dose_response_reagent_idx ON dose_response_events (reagent, is_clean);
CREATE INDEX dose_response_cycle_idx ON dose_response_events (cycle_id);
```

**Ключевая тонкость:** флаг `is_clean`. Для обучения модели дозирования надо
отфильтровать только те дозы, в окне отклика которых **не было других
возмущений** (другой дозы, долива, смены раствора). Без этого флага модель
выучит шум.

### 5.4. `ml_labels` (таргеты прогноза)

**Owner:** `feature-builder`. Хранится **отдельно** от фичей, чтобы исключить
случайное использование таргета как фичи.

```sql
CREATE TABLE ml_labels (
  ts                    timestamptz NOT NULL,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  horizon_minutes       smallint    NOT NULL,   -- 5, 15, 60

  ph_target             double precision,       -- ph_mean в (ts + horizon, ts + horizon + 5m]
  ec_target             double precision,
  ph_delta              double precision,       -- ph_target - ph_mean(ts)
  ec_delta              double precision,

  is_valid              boolean NOT NULL,       -- false если в окне таргета были возмущения/гэпы
  invalid_reason        varchar(64),

  label_schema_version  smallint NOT NULL DEFAULT 1,
  PRIMARY KEY (zone_id, ts, horizon_minutes)
);

CREATE INDEX ml_labels_ts_idx ON ml_labels (ts);
```

**Важно:** таргет считается **только когда прошло горизонт + 5 мин времени**,
т.е. таргет на `ts=10:00, horizon=60m` становится известен в `11:05`. Это
имитирует реальную задержку inference и защищает от утечек.

### 5.5. `ml_calibration_events`

**Owner:** Laravel (calibration flow). **Назначение:** регистрировать все
события, после которых данные датчика меняют масштаб/смещение, чтобы
feature-builder и training notebook могли корректно разбить историю.

```sql
CREATE TABLE ml_calibration_events (
  id                    bigserial PRIMARY KEY,
  sensor_id             bigint      NOT NULL REFERENCES sensors(id),
  zone_id               bigint      REFERENCES zones(id),
  event_type            varchar(32) NOT NULL,   -- 'calibrated'|'replaced'|'cleaned'|'firmware_update'
  ts                    timestamptz NOT NULL DEFAULT now(),
  before_params         jsonb,                  -- коэффициенты до
  after_params          jsonb,                  -- коэффициенты после
  operator_id           bigint REFERENCES users(id),
  notes                 text
);

CREATE INDEX ml_calibration_sensor_ts_idx ON ml_calibration_events (sensor_id, ts);
```

Training notebook **обязан** исключать окна, пересекающие событие калибровки,
или применять поправку при retrospective-обучении.

### 5.6. `ml_models` (registry)

**Owner:** inference-server / training pipeline.

```sql
CREATE TABLE ml_models (
  id                    bigserial PRIMARY KEY,
  name                  varchar(64) NOT NULL,   -- 'ph_forecaster'|'ec_forecaster'|'dose_advisor'
  version               varchar(32) NOT NULL,   -- semver: '0.1.0'
  algorithm             varchar(64),            -- 'nbeats'|'tft'|'xgboost'
  feature_schema_version smallint NOT NULL,     -- должен совпадать с используемой витриной
  artifact_uri          text        NOT NULL,   -- s3://... или /models/...
  metrics_json          jsonb       NOT NULL,   -- {mae, rmse, coverage, train_window}
  trained_on_range      tstzrange   NOT NULL,
  status                varchar(16) NOT NULL,   -- 'shadow'|'canary'|'active'|'retired'
  created_at            timestamptz NOT NULL DEFAULT now(),
  activated_at          timestamptz,
  retired_at            timestamptz,
  notes                 text,
  UNIQUE (name, version)
);

CREATE INDEX ml_models_name_status_idx ON ml_models (name, status);
```

### 5.7. `ml_predictions` (inference log)

```sql
CREATE TABLE ml_predictions (
  id                    bigserial PRIMARY KEY,
  ts                    timestamptz NOT NULL,  -- момент inference
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  model_id              bigint      NOT NULL REFERENCES ml_models(id),
  horizon_minutes       smallint,              -- NULL для dose_advisor

  input_features_hash   varchar(64),           -- sha1 от input row, для воспроизводимости
  prediction            jsonb       NOT NULL,  -- {ph_target, ec_target, confidence, ...}
  confidence            double precision,
  latency_ms            integer,

  -- ground truth, заполняется feature-builder'ом после того, как время пройдёт
  ground_truth          jsonb,
  error                 jsonb,                 -- {ph_mae, ec_mae}
  ground_truth_filled_at timestamptz
);

CREATE INDEX ml_predictions_zone_ts_idx ON ml_predictions (zone_id, ts);
CREATE INDEX ml_predictions_model_idx ON ml_predictions (model_id, ts);
SELECT create_hypertable('ml_predictions', 'ts', chunk_time_interval => interval '30 days');
```

### 5.8. `ml_data_quality_windows`

Окна, непригодные для обучения (долгий offline, калибровка, известный сбой).
Пишется автоматикой + можно вручную отмечать из UI.

```sql
CREATE TABLE ml_data_quality_windows (
  id                    bigserial PRIMARY KEY,
  zone_id               bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  start_ts              timestamptz NOT NULL,
  end_ts                timestamptz NOT NULL,
  reason                varchar(64) NOT NULL,  -- 'sensor_offline'|'calibration'|'manual_exclude'|...
  severity              varchar(16) NOT NULL,  -- 'exclude'|'warn'
  details               jsonb,
  created_by            bigint REFERENCES users(id),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ml_dq_zone_range_idx ON ml_data_quality_windows (zone_id, start_ts, end_ts);
```

---

## 6. Новый сервис `feature-builder`

**Путь:** `backend/services/feature-builder/`
**Стек:** Python 3.12 + asyncpg (как у других сервисов), FastAPI для health/admin,
prometheus_client.

### 6.1. Обязанности

1. Каждые 60 секунд догонять `zone_features_5m` за последние N часов
   (incremental processing по `last_ts` из `aggregator_state`, по аналогии с
   существующим `telemetry-aggregator`).
2. Каждые 60 секунд догонять `ml_labels` (только для окон, где наступило
   `ts + horizon + 5m`).
3. На каждое `CORRECTION_COMPLETE` из `zone_events` и каждый `command.status='DONE'`
   для `cmd IN ('DOSE_*', 'PUMP_*')` собирать строку в `dose_response_events`.
   Отклик заполняется отложенно, когда пройдёт 60 минут после дозы.
4. Обновлять `ml_data_quality_windows` по правилам:
   - `data_gap_seconds > 300` в окне → `sensor_offline`,
   - пересечение с `ml_calibration_events` ± 10 минут → `calibration`,
   - `valid_ratio < 0.7` подряд > 3 окон → `low_quality`.
5. Отложенное заполнение `ml_predictions.ground_truth` для уже существующих
   предсказаний, у которых `ts + horizon + 5m` уже прошло.

### 6.2. Конфигурация (env)

```
FEATURE_BUILDER_POLL_INTERVAL_SEC=60
FEATURE_BUILDER_LOOKBACK_HOURS=24          # сколько часов тянуть при каждом цикле (safety)
FEATURE_BUILDER_HORIZONS=5,15,60
FEATURE_BUILDER_MIN_VALID_RATIO=0.7
FEATURE_BUILDER_CLEAN_WINDOW_MIN=60        # для is_clean в dose_response_events
FEATURE_BUILDER_SCHEMA_VERSION=1
FEATURE_BUILDER_BACKFILL_BATCH_SIZE=1000
```

### 6.3. API

- `GET /healthz` — alive/ready.
- `GET /metrics` — Prometheus.
- `POST /admin/backfill` — `{"from": "...", "to": "...", "zone_ids": [...]}`.
  Ставит задачу на пересчёт исторических данных.
- `POST /admin/invalidate` — инвалидировать окно (пометить в
  `ml_data_quality_windows`).

### 6.4. Метрики (Prometheus)

```
feature_builder_rows_written_total{table=...}
feature_builder_lag_seconds{pipeline="features_5m|labels|dose_response"}
feature_builder_errors_total{stage=...}
feature_builder_quality_exclusions_total{reason=...}
feature_builder_ground_truth_backfill_lag_seconds
```

### 6.5. Алерты

- `feature_builder_lag_seconds > 300` на 5 минут → WARN
- `feature_builder_lag_seconds > 900` на 5 минут → CRIT
- `rate(feature_builder_errors_total[5m]) > 0.1` → WARN

---

## 7. Контракты данных

### 7.1. Инварианты (ДОЛЖНЫ соблюдаться всегда)

1. **Один owner на таблицу.** Никто, кроме `feature-builder`, не пишет в
   `zone_features_5m`, `dose_response_events`, `ml_labels`.
2. **Идемпотентность.** Повторный запуск feature-builder за то же окно даёт
   тот же результат (UPSERT с детерминированными ключами).
3. **Монотонность ts.** В `zone_features_5m` `ts` всегда кратен 5 минутам
   (00:00, 00:05, ..., 23:55 UTC).
4. **Версионирование.** Любое изменение формулы фичи = инкремент
   `feature_schema_version` + миграция (backfill или сохранение обеих версий).
5. **Качество.** Если `valid_ratio < MIN_VALID_RATIO`, фича всё равно пишется,
   но окно помечается в `ml_data_quality_windows`.

### 7.2. Политика качества

| Условие | Действие |
|---|---|
| `data_gap_seconds > 300` в окне 5m | Окно пишется, помечается `sensor_offline` |
| `valid_ratio < 0.7` | Окно помечается `low_quality` |
| Пересечение с `ml_calibration_events` ± 10 мин | `calibration` |
| Пересечение с active `ml_data_quality_windows(severity=exclude)` | Окно пишется, но не должно попадать в train |
| `WATER_CHANGE_*` во время окна | Окно помечается `water_change`, dose_response с этим окном отбрасывается |

---

## 8. Point-in-time correctness (КРИТИЧНО)

Правила **обязательны** для training notebook и inference:

1. **Фичи окна `[t-5m, t)` используются для предсказания на момент `t` и позже.**
   Никогда — для предсказания на `t-1m`.
2. **Таргеты окна `(t, t+h]` никогда не входят в фичи.** Поэтому `ml_labels`
   лежит в отдельной таблице — чтобы join был явным и осознанным.
3. **При обучении используется temporal split, не random.** Train — прошлое,
   val — средний период, test — самое свежее. Между сплитами — gap ≥ 1 час,
   чтобы не было утечки через скользящие окна.
4. **Inference читает только фичи с `ts <= now() - INFERENCE_DELAY_SEC`**
   (рекомендация: 60 сек), чтобы гарантированно иметь закрытое окно.
5. **При backfill исторических предсказаний** (для валидации модели)
   использовать только те фичи и состояния, что были бы доступны на момент
   `ts`. Никаких «поглядеть, что было дальше».

Каждый training notebook в `tools/ml/` **обязан начинаться с чек-листа
point-in-time** (см. §16).

---

## 9. Стратегия backfill

После появления первых реальных данных:

1. **Прод-агрегаты** (`telemetry_agg_1m` с новыми колонками) — перепрожарить
   через `backend/services/telemetry-aggregator` с `agg_version=2`,
   блок-размер: 1 сутки.
2. **`zone_features_5m`** — собрать из `telemetry_agg_1m` одним запросом с
   `generate_series` по 5-минутной сетке и `LEFT JOIN LATERAL`. Ограничение:
   не более 30 дней за один батч (чтобы не подвесить БД).
3. **`dose_response_events`** — собрать из `command_audit` (есть
   `telemetry_snapshot`) + доскан `telemetry_samples` в окно отклика.
4. **`ml_labels`** — собрать последним, после того как готовы `zone_features_5m`
   (чтобы не было строк без соответствующих фичей).

Управление — через `POST /admin/backfill` feature-builder'а. Прогресс читается
из `feature_builder_lag_seconds`.

---

## 10. Retention и сжатие

| Таблица | Hot | Compressed | Archive | Обоснование |
|---|---|---|---|---|
| `telemetry_samples` | 30 дней | — | S3 Parquet, 5 лет | Как сейчас. ML не тренируется на raw, только на 1m |
| `telemetry_agg_1m` | 14 дней | 14 дней – 12 мес | → 1h | **Изменение:** было 30 дней, становится 365 |
| `telemetry_agg_1h` | 365 дней | 30–365 дней | ∞ как daily | Как сейчас |
| `telemetry_daily` | ∞ | — | — | Как сейчас |
| `zone_features_5m` | 14 дней | 14 дней – 24 мес | ∞ | Дёшево, нужно для ML |
| `dose_response_events` | ∞ | — | — | Маленькая таблица, критичный датасет |
| `ml_labels` | 12 мес | 12–24 мес | — | Пересобирается из features/samples при необходимости |
| `ml_predictions` | 90 дней | 90 дней – 24 мес | → агрегат | Для мониторинга дрейфа нужна история |

Миграция retention — правка `.env` `RETENTION_*` для `telemetry-aggregator` +
Laravel команд + Timescale compression policies (см. §5.2).

---

## 11. Интеграция с `digital-twin`

Задача: заменить фиксированные параметры в
`backend/services/digital-twin/models.py` (`buffer_capacity=0.1`,
`natural_drift=0.01` и т.д.) на параметры, подобранные по реальным данным.

**Процесс:**

1. Training notebook `tools/ml/digital_twin_calibration.ipynb`:
   - читает `dose_response_events` (`is_clean=true`, `is_settled=true`)
   - минимизирует MSE между симуляцией `PHModel.step` и фактическим
     `ph_at_plus_15m` (scipy.optimize.minimize)
   - записывает параметры в `zone_dt_params` (новая таблица зонно-специфичных
     параметров симулятора) с `valid_from`.
2. `digital-twin` при запуске симуляции читает свежие параметры из
   `zone_dt_params` для нужной зоны и фазы рецепта.
3. Если параметров нет (новая зона, мало данных) — fallback на текущие defaults.

Это даёт цифровой двойник, который реально соответствует поведению конкретной
зоны, а не «средний DWC».

---

## 12. Model lifecycle

### 12.1. Статусы модели

```
shadow   → модель делает предсказания, но они не видны юзеру, только пишутся в ml_predictions
canary   → предсказания видны оператору в UI, но не используются automation-engine
active   → используются automation-engine как advisory (не заменяют PID)
retired  → история остаётся, новые inference не делаются
```

Переход `shadow → canary → active` — только вручную через Laravel admin UI,
с явным подтверждением и запись в `zone_events` (`AI_MODEL_PROMOTED`).

### 12.2. Safety ограничения

Никакая ML-модель **никогда** не заменяет safety-слой. Контроллер дозирования
работает так:

```
dose_ml_final = clip(
    dose_ml_pid + ml_advisory_correction_ml,
    min=MIN_DOSE_ML,
    max=MAX_DOSE_ML_PER_HOUR - dosed_last_hour_ml
)
```

Жёсткие ограничения из `automation_config_documents` **всегда** имеют приоритет
над моделью. Выход за safety-пороги → `EMERGENCY_STOP_ACTIVATED`.

### 12.3. Rollout правила

- Переход `shadow → canary`: ≥ 30 дней в shadow + MAE на test-сете лучше
  baseline (persistence/PID) минимум на 10%.
- Переход `canary → active`: ≥ 14 дней в canary + нет жалоб оператора +
  `rate(EMERGENCY_STOP)` не растёт.
- Автоматический rollback на `retired`, если за 24 часа:
  - `rate(ml_predictions.error) > 2×` baseline, или
  - случился хоть один `EMERGENCY_STOP_ACTIVATED` с `source=ml_advisory`.

---

## 13. Inference pipeline

**Путь:** `backend/services/ml-inference/` (новый сервис, Phase 3).

### 13.1. Интерфейсы

- `POST /v1/forecast/{zone_id}` → `{ph_at_plus_5m, ec_at_plus_5m, ..., model_version}`
- `POST /v1/dose_advice/{zone_id}` → `{reagent, volume_ml_suggested, confidence, rationale}`
- `GET /v1/models` — список активных моделей

### 13.2. Нагрузка и latency

- Предполагаемый RPS: 1 req/минуту/зона → даже на 100 зон это <2 RPS.
- p95 latency: < 200 мс (иначе не влезаем в automation-engine loop).
- Модели загружаются в память при старте; hot-swap через `ml_models.status`.

### 13.3. Вызов из automation-engine

automation-engine обращается к ml-inference **только** для зон в
`control_mode = 'auto'` и с `ml_advisory_enabled=true` (новый флаг в
`zones.settings`). При сбое inference → graceful degrade (работает чистый PID).

---

## 14. Feedback loop и мониторинг дрейфа

`feature-builder` после того, как пройдёт `horizon + 5m`, заполняет
`ml_predictions.ground_truth` и считает `error`.

**Dashboards в Grafana** (новые):
- `ML / Model Quality` — MAE/RMSE по моделям, по зонам, скользящее 24h/7d/30d.
- `ML / Data Quality` — % окон с `valid_ratio < 0.7`, gaps.
- `ML / Feature Freshness` — lag feature-builder'а.
- `ML / Dose Response Coverage` — сколько `is_clean` дозоотклик-событий
  набирается в сутки (для переобучения).

**Автоматический retrain trigger** (cron, еженедельно):
- Если MAE на последних 7 днях > 1.5× training-MAE → сгенерировать alert
  `MODEL_DRIFT_DETECTED` в `zone_events`, оператор решает про retrain.

---

## 15. План внедрения по фазам

### Phase 0 · Подготовка (1 неделя)

Задача | Владелец | DoD
---|---|---
Ревью и утверждение документа | человек | Комментарии закрыты, merge в `doc_ai/`
Создать ветку `feature/ml-feature-pipeline` | dev | Ветка + пустые директории `backend/services/feature-builder/`
Синхронизировать retention `.env` | dev | Поднят `RETENTION_SAMPLES_DAYS=30`, `RETENTION_AGG_1M_DAYS=365` (согласовано с Laravel)

### Phase 1 · Расширение агрегатов (1 неделя)

Задача | DoD
---|---
Миграция §5.1 (колонки `value_std`, `slope_per_min` и др. в `telemetry_agg_1m`) | Миграция проходит up/down на dev
Обновить SQL в `telemetry-aggregator/main.py` (`stddev_samp`, `regr_slope`, `FILTER quality='GOOD'`) | Тест `test_main.py` покрывает новые поля
Backfill агрегатов с `agg_version=2` на dev данных (синтетика) | Все строки с `agg_version=2`, `value_std IS NOT NULL` на окнах с >1 точкой
Сompression policy на `telemetry_agg_1m` | `hypertable_compression_stats` показывает компрессию
Метрики агрегатора расширены полями по новым колонкам | Grafana дешборд обновлён

### Phase 2 · feature-builder MVP (2 недели)

Задача | DoD
---|---
Миграции §5.2, §5.4, §5.8 (`zone_features_5m`, `ml_labels`, `ml_data_quality_windows`) | Up/down проходят, hypertable создан
Сервис `backend/services/feature-builder/` (skeleton: FastAPI, metrics, poll loop, conftest) | `make up` поднимает сервис, `/healthz` 200
Основная логика сборки `zone_features_5m` по 5-мин сетке | Синтетический E2E тест: инжект telemetry → через 90 сек строка в `zone_features_5m`
Сборка `ml_labels` для horizons 5/15/60 | Таргеты появляются с лагом `horizon + 5 мин`
`ml_data_quality_windows` пишутся по правилам §7.2 | Unit тесты покрывают все 5 правил
Админ-эндпоинт `POST /admin/backfill` | E2E: backfill 7 дней синтетики за <5 мин
Grafana дешборд `Feature Builder` | Доступен + алерты настроены

### Phase 3 · dose_response_events + ml_calibration_events (1 неделя)

Задача | DoD
---|---
Миграции §5.3, §5.5 | Up/down проходят
Logic в feature-builder: на `CORRECTION_COMPLETE` / `commands DONE DOSE_*` — собрать строку | Тест: доза → через 70 мин есть строка с заполненными `ph_at_plus_60m`
`is_clean` логика (нет других доз/доливов в окне ±60 мин) | Unit тесты на 5 сценариев (чистая доза, перекрывающиеся, долив в окне и т.д.)
Laravel регистрирует события в `ml_calibration_events` при calibration flow | Интеграционный тест

### Phase 4 · Training notebooks (1 неделя)

Задача | DoD
---|---
`tools/ml/README.md` — как запускать notebooks | Reviewed
`tools/ml/baseline_forecast.ipynb` — Prophet + persistence baseline | MAE посчитан на test set, figure с pH/EC прогнозом
`tools/ml/digital_twin_calibration.ipynb` — подбор параметров `PHModel`/`ECModel` | Параметры лежат в новой `zone_dt_params`, `digital-twin` их читает
`tools/ml/data_quality_audit.ipynb` — отчёт по качеству витрин | Отчёт: % валидных окон, coverage dose_response по зонам

### Phase 5 · Model registry + inference (2 недели)

Задача | DoD
---|---
Миграции §5.6, §5.7 | Up/down проходят
Сервис `backend/services/ml-inference/` | `/v1/forecast` отвечает <200мс на mock-модели
Первая реальная модель `ph_forecaster v0.1.0` (N-BEATS/TFT через `darts`) в статусе `shadow` | Запись в `ml_models`, предсказания льются в `ml_predictions`
Grafana `ML / Model Quality` dashboard | Работает на реальных данных
Ground truth backfill + error метрики | `ml_predictions.error` заполняется автоматически

### Phase 6 · Canary / Active rollout (TBD)

Только после 30+ дней shadow и утверждения оператором. Отдельный runbook.

---

## 16. Чек-лист перед мержем фичи в ML-слой

Для человека и ИИ-агента.

- [ ] Новые колонки/таблицы задокументированы в `DATA_MODEL_REFERENCE.md`
- [ ] `feature_schema_version` или `agg_version` инкрементирован, если формулы изменились
- [ ] Up и Down миграции тестированы на dev
- [ ] Unit-тесты покрывают новые правила `ml_data_quality_windows`
- [ ] E2E тест: инжект → feature-builder → ожидаемая строка
- [ ] Point-in-time проверка: фича на `ts` использует только данные `< ts`
- [ ] Prometheus-метрики добавлены и видны в Grafana
- [ ] Retention policy обновлена в `DATA_RETENTION_POLICY.md`
- [ ] Ownership таблицы задокументирован (кто единственный writer)
- [ ] Если задето `digital-twin` — обновлён `DIGITAL_TWIN_ENGINE.md`

---

## 17. Правила для ИИ-агентов

ИИ-агент (Claude Code, Cursor agent и т.д.) работает по этому документу
**с соблюдением следующих правил:**

### Можно:

- Генерировать SQL-миграции по DDL из §5 (с обязательной парой up/down).
- Писать код feature-builder'а, тесты, metrics.
- Добавлять новые фичи в `zone_features_5m`, **инкрементируя
  `feature_schema_version`**.
- Писать training notebooks в `tools/ml/`.
- Расширять правила качества в §7.2, добавляя новые reasons в
  `ml_data_quality_windows.reason`.

### Нельзя:

- **Писать в `zone_features_5m`, `dose_response_events`, `ml_labels` из любого
  сервиса, кроме `feature-builder`.** Одно исключение = ломается контракт.
- Изменять структуру `telemetry_samples` или MQTT-контракт ради удобства ML.
- Уменьшать retention ниже значений §10 без согласования.
- Включать модель в `active`-статус без явного подтверждения человека.
- Использовать ML-модель для замены safety-слоя. Она только advisory (§12.2).
- Тренировать на данных, пересекающих `ml_data_quality_windows` с
  `severity='exclude'`.
- Миксовать фичи и таргеты в одной таблице.
- Добавлять колонки в `ml_predictions` — вместо этого расширять JSONB-поля
  `prediction` / `error`.

### Обязательно:

- Любой PR, затрагивающий ML-слой, включает обновление этого документа
  (`ML_FEATURE_PIPELINE.md`).
- Любая новая фича в `zone_features_5m` сопровождается:
  (а) описанием в §5.2, (б) инкрементом версии, (в) back­fill-стратегией.
- Любая новая модель (`ml_models` INSERT) сопровождается записью
  `trained_on_range` и заполнением `metrics_json`.

---

## 18. Открытые вопросы (ждём решения владельца)

1. **Timescale vs plain PG:** подтвердить, что в проде действительно Timescale
   (в коде есть fallback на `date_trunc` — значит, где-то может не быть).
   Compression и continuous aggregates требуют Timescale.
2. **Scope моделей:** одна глобальная модель для всех зон, или per-zone? Для
   MVP предлагаю глобальную + zone_id как фичу; per-zone когда данных хватит.
3. **Storage для артефактов моделей:** S3-совместимое (как в
   `DATA_RETENTION_POLICY §3.3`) или локальный volume? Влияет на
   `ml_models.artifact_uri`.
4. **ML-inference как отдельный сервис** или расширение `digital-twin`?
   Предлагаю отдельный — разные SLO и deploy cadence.
5. **Тренировочная инфраструктура:** обучение в notebooks на dev-машине, или
   отдельный job runner (типа Metaflow/Prefect)? Для MVP хватит notebooks.
6. **Единицы измерения в `dose_*_ml`:** только мл, или нормировать на объём
   ванны? Предлагаю хранить мл + отдельно держать `water_volume_l_before` в
   той же строке — модель сама выучит соотношение.

---

## Приложение A. Пример строки `zone_features_5m`

```json
{
  "ts": "2026-04-22T14:30:00Z",
  "zone_id": 12,
  "cycle_id": 47,
  "recipe_phase": "vegetative",
  "hours_since_cycle_start": 312.5,
  "hours_since_water_change": 48.2,
  "ph_mean": 5.87, "ph_std": 0.04, "ph_slope": -0.008,
  "ph_min": 5.81, "ph_max": 5.93,
  "ec_mean": 1.92, "ec_std": 0.03, "ec_slope": -0.012,
  "ec_min": 1.88, "ec_max": 1.95,
  "water_temp_mean": 21.4, "water_level_mean": 87.2,
  "air_temp_mean": 23.1, "air_hum_mean": 62.0, "light_mean": 412.0,
  "ph_buffer_est": 0.31, "ec_consumption_rate": 0.18,
  "water_evaporation_rate": 0.45,
  "dose_ph_down_ml": 0, "dose_ph_up_ml": 0,
  "dose_npk_ml": 0, "dose_ca_ml": 0, "dose_mg_ml": 0, "dose_micro_ml": 0,
  "water_added_ml": 0,
  "valid_ratio": 1.0, "data_gap_seconds": 0,
  "feature_schema_version": 1
}
```

## Приложение B. Пример строки `dose_response_events`

```json
{
  "id": 8821,
  "zone_id": 12, "cycle_id": 47, "recipe_phase": "vegetative",
  "dose_ts": "2026-04-22T14:32:10Z", "dose_end_ts": "2026-04-22T14:32:14Z",
  "reagent": "ph_down", "volume_ml": 3.5,
  "pump_id": 4, "command_id": 913224, "source": "pid",
  "ph_before": 6.42, "ec_before": 1.88,
  "water_temp_before": 21.4, "water_volume_l_before": 120.0,
  "ph_slope_before": 0.02, "ec_slope_before": -0.01,
  "ph_at_plus_5m": 6.28, "ec_at_plus_5m": 1.88,
  "ph_at_plus_15m": 6.10, "ec_at_plus_15m": 1.89,
  "ph_at_plus_60m": 5.95, "ec_at_plus_60m": 1.87,
  "d_ph_per_ml_15m": -0.091, "d_ec_per_ml_15m": 0.003,
  "is_clean": true, "is_settled": true, "exclusion_reason": null,
  "feature_schema_version": 1
}
```

---

# Конец файла ML_FEATURE_PIPELINE.md
