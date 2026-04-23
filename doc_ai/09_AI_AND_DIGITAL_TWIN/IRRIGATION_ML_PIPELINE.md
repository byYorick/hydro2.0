# IRRIGATION_ML_PIPELINE.md
# План внедрения умного полива для hydro2.0
# VPD/ET baseline • Learned Kc • Weather-aware forecasting • Closed-loop dryback
# Культура MVP: клубника · Система: substrate drip · Теплица: закрытая с влиянием наружки

**Статус:** DRAFT · предложение к внедрению
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/IRRIGATION_ML_PIPELINE.md`
**Связанные документы:**
- `doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md` — ML по pH/EC/телеметрии
- `doc_ai/09_AI_AND_DIGITAL_TWIN/VISION_PIPELINE.md` — CV по растениям
- `doc_ai/06_DOMAIN_ZONES_RECIPES/WATER_FLOW_ENGINE.md` — существующий контракт
  ирригации (насосы, клапаны, flow, drain) — **остаётся в силе**, ML только
  надстраивается
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
**Breaking-change:** нет. Существующий `irrigation_interval_sec`/`duration_sec`
остаются как fallback и hard-limits. ML — advisory слой поверх

---

## 0. Назначение документа

Документ описывает, как превратить текущий **blind-scheduling полив** (фиксированные
интервал + длительность из рецепта) в **умный полив** — с учётом климата, погоды,
реального потребления воды, фенологической фазы и состояния растения по CV.

Для **человека** — дорожная карта + физическая база (VPD, ET, Kc, dryback).
Для **ИИ-агента** — спецификация контрактов, таблиц, сервисов, safety-инвариантов.

---

## 1. Цели

### 1.1. Бизнес-цели (клубника, substrate drip, закрытая теплица)

- Снизить водопотребление на 20–40% без потерь урожая (стандарт для перехода
  от blind-scheduling к VPD/ET-based полива).
- Стабилизировать WC субстрата в целевом коридоре — снизить частоту
  растрескивания ягод в фазе плодоношения (главная KPI для клубники).
- Предупреждать water stress за ≥ 2 часа до wilting (комбинация VPD-predict
  + CV tip-burn score + WC trend).
- Автоматически поддерживать целевой leaching fraction в коридоре 15–25% —
  защита от солевого накопления без перерасхода.

### 1.2. Технические цели

- ML-advisory, не замена. Существующий `WATER_FLOW_ENGINE` и
  `automation-engine` **всегда** имеют последнее слово и safety-ограничения.
- Планировщик полива работает на трёх уровнях:
  1. Rule-based baseline (VPD-integral trigger, **всегда активен**).
  2. Physics-based ET (Penman-Monteith с greenhouse modification).
  3. ML overlay (learned Kc + learned adjustment по WC response).
- Полный feedback loop: каждый полив записан с входными фичами, выходным
  объёмом и результатом (WC response, EC drain, leaching fraction).
- Интеграция с Open-Meteo forecast для планирования на 24 часа вперёд.

### 1.3. Не-цели

- Замена физической логики `WATER_FLOW_ENGINE` (насосы, клапаны, flow — не трогаем).
- Автоматическая диагностика неисправностей forсунок (отдельно, через CV + flow).
- Поддержка DWC/NFT/aeroponics в этом документе (будет в отдельном приложении
  при необходимости — там задача принципиально проще, только top-up на
  испарение).

---

## 2. Текущее состояние (ревизия `ae3`)

Из `doc_ai/06_DOMAIN_ZONES_RECIPES/WATER_FLOW_ENGINE.md` §4:

```
if now - last_irrigation >= irrigation_interval_sec:
  if water_level_ok:
    запуск насоса на irrigation_duration_sec
```

- Интервал и длительность берутся из snapshot рецепта (`recipe_phase_snapshots.irrigation_interval_sec`).
- Flow подтверждается в первые 3 секунды; нет → `NO_FLOW` alert.
- Объём считается как `sum(flow * dt)`, пишется в `zone_events` типа `IRRIGATION_FINISHED`.
- Drain logic есть, но без закрытой обратной связи по leaching fraction.
- Есть water level sensor, но **нет**: WC substrate sensor, drainage flow sensor,
  отдельного flow-сенсора на drain, weather source, PAR integration в irrigation
  логике.

**Итого:** идеальный стартовый кейс. Вся физика дозирования уже решена,
нужно построить «мозг», который решает **когда** и **сколько**.

---

## 3. Пробелы, которые закрываем

| # | Пробел | Почему блокер |
|---|---|---|
| I1 | Полив по таймеру без учёта климата | В солнечный день 25°C растение пьёт вдвое больше, чем в пасмурный 18°C — таймер не различает |
| I2 | Нет учёта фенологической фазы | Молодая клубника потребляет в 3–4 раза меньше плодоносящей при той же фазе света |
| I3 | Нет прямого измерения dryback | WC sensor запланирован, но не интегрирован в логику принятия решений |
| I4 | Нет leaching fraction control | Без этого либо переполив (→ waste), либо накопление солей в субстрате |
| I5 | Нет weather forecast integration | Нельзя пре-поливать до жары, нельзя отложить до пасмурного дня |
| I6 | Нет feedback loop | Модель не видит, как отреагировала зона на полив |
| I7 | Нет безопасного ML overlay | Любой ML-контроллер без rule-based floor опасен: пропущенный полив = гибель растения |
| I8 | Нет связи с visual-алертами | Tip-burn, wilting на CV должны триггерить corrective irrigation |
| I9 | Нет единой ML-витрины для обучения | Данные размазаны по `zone_events`, `telemetry_samples`, `commands` |

---

## 4. Архитектура решения

### 4.1. Трёхслойная модель принятия решения

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1 — Rule-based baseline (всегда активен, safety floor)    │
│                                                                  │
│  - VPD-integral trigger: полив если Σ(VPD × dt) ≥ threshold      │
│  - WC floor: полив если WC_substrate < WC_min_safety             │
│  - Max interval: полив если прошло > max_interval_sec            │
│  - Visual emergency: полив если wilting_detected                 │
└────────────────────────────┬─────────────────────────────────────┘
                             │ если хоть одно правило сработало
                             ▼ → немедленный полив дефолт-объёма
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2 — Physics ET baseline                                   │
│                                                                  │
│  - Penman-Monteith ET₀ (greenhouse-modified)                     │
│  - ETc = Kc_phenology × ET₀                                      │
│  - Volume_baseline = ETc × canopy_area + leaching_target         │
│  - Next trigger = when accumulated_ETc ≥ trigger_threshold       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼ → advisory predicted_volume / predicted_time
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3 — ML overlay (shadow → canary → active)                 │
│                                                                  │
│  - Learned Kc adjustment по response истории                     │
│  - Volume fine-tune по target_leaching / target_WC_response      │
│  - Pre-emptive scheduling по weather forecast                    │
│  - Post-harvest / stress adjustment                              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
                 Final irrigation advisory:
                 { trigger_at, volume_ml, valve_mask }
                             │
                             ▼
                 automation-engine (unchanged)
                             │
                             ▼
                 history-logger → MQTT → node (unchanged)
```

**Принцип:** любой из слоёв 2 и 3 может отключиться — полив всё равно пойдёт
по слою 1. Слой 3 (ML) никогда не решает **один**, его предложение проходит
через slope 2 (физика) и гейтится слоем 1 (safety).

### 4.2. Сервисы

| Сервис | Новый | Путь | Обязанности |
|---|---|---|---|
| `weather-fetcher` | ✅ | `backend/services/weather-fetcher/` | Тянет Open-Meteo каждые 15 мин, пишет в `weather_observations` и `weather_forecasts` |
| `irrigation-planner` | ✅ | `backend/services/irrigation-planner/` | Реализует 3 слоя, публикует advisory в `irrigation_advisories`, по триггеру — отправляет команду в `automation-engine` как сейчас |
| `feature-builder` | ⇨ расширение | (из `ML_FEATURE_PIPELINE.md`) | Собирает витрины irrigation-специфичных фичей |
| `automation-engine` | без изменений | — | Принимает команду, запускает PID, отправляет в history-logger |
| `WATER_FLOW_ENGINE` | без изменений | — | Физика насосов/клапанов/flow |

---

## 5. Схема данных

### 5.1. `irrigation_events` (замена `zone_events` IRRIGATION_* для ML)

Существующие события `IRRIGATION_FINISHED` в `zone_events` остаются для UI/аудита.
Отдельная таблица — для ML: богаче, типизирована, с заполненным response окном.

```sql
CREATE TABLE irrigation_events (
  id                      bigserial PRIMARY KEY,
  zone_id                 bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  cycle_id                bigint      REFERENCES grow_cycles(id),
  recipe_phase            varchar(32),
  advisory_id             bigint,                   -- FK на irrigation_advisories

  triggered_at            timestamptz NOT NULL,
  completed_at            timestamptz NOT NULL,
  trigger_source          varchar(16) NOT NULL,     -- 'rule'|'et'|'ml'|'manual'|'emergency'
  trigger_reason          varchar(64) NOT NULL,     -- 'vpd_integral'|'wc_floor'|'max_interval'|
                                                    -- 'et_threshold'|'ml_advisory'|'wilting_cv'|...

  -- предписание
  planned_volume_ml       double precision,
  planned_duration_sec    double precision,
  -- факт
  actual_volume_ml        double precision NOT NULL,
  actual_duration_sec     double precision NOT NULL,
  avg_flow_L_per_min      double precision,

  -- состояние зоны ДО полива (snapshot на triggered_at)
  vpd_kpa_before          double precision,
  vpd_integral_kpa_h      double precision,         -- накопленный с прошлого полива
  par_integral_mol_m2     double precision,         -- накопленный с прошлого полива
  et0_mm_since_last       double precision,         -- Penman-Monteith ET₀
  etc_mm_since_last       double precision,         -- ETc = Kc × ET₀
  air_temp_c_before       double precision,
  air_humidity_pct_before double precision,
  co2_ppm_before          double precision,
  par_umol_m2_s_before    double precision,
  outdoor_temp_c_before   double precision,
  outdoor_solar_w_m2_before double precision,
  wc_substrate_before     double precision,         -- % объёмной влажности
  ec_solution_before      double precision,
  ph_solution_before      double precision,
  water_tank_level_before double precision,

  -- response окно (заполняется feature-builder через 60 мин)
  wc_substrate_peak       double precision,         -- максимум WC после полива (в окне +15 мин)
  wc_substrate_peak_ts    timestamptz,
  wc_substrate_at_plus_60m double precision,
  drain_volume_ml         double precision,
  drain_ec                double precision,
  leaching_fraction       double precision,         -- drain_vol / planned_vol
  ec_rise_after_2h        double precision,         -- EC в субстрате через 2ч (признак концентрации)

  -- флаги качества для обучения
  is_clean                boolean NOT NULL,         -- no other events in response window
  is_stable_climate       boolean NOT NULL,         -- climate did not jump during response
  exclusion_reason        varchar(64),

  feature_schema_version  smallint NOT NULL DEFAULT 1,
  created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX irr_ev_zone_ts_idx ON irrigation_events (zone_id, triggered_at DESC);
CREATE INDEX irr_ev_source_clean_idx ON irrigation_events (trigger_source, is_clean);
CREATE INDEX irr_ev_cycle_idx ON irrigation_events (cycle_id);
```

### 5.2. `irrigation_advisories` (что предлагает планировщик)

Пишется при каждом тике `irrigation-planner`, даже если полив не нужен.

```sql
CREATE TABLE irrigation_advisories (
  id                      bigserial PRIMARY KEY,
  zone_id                 bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  generated_at            timestamptz NOT NULL,

  -- решение
  should_irrigate_now     boolean NOT NULL,
  next_irrigation_at_est  timestamptz,              -- прогноз момента следующего полива
  volume_ml_recommended   double precision,
  confidence              double precision,

  -- разложение по слоям
  layer1_rule_fired       varchar(64),              -- NULL если ни одно правило не сработало
  layer2_et_due_at        timestamptz,              -- когда физика ожидает накопление ETc
  layer2_volume_ml        double precision,
  layer3_ml_correction_ml double precision,         -- поправка от ML (может быть отрицательной)
  layer3_model_id         bigint REFERENCES ml_models(id),

  -- входы, которые привели к решению (для объяснимости)
  inputs_hash             varchar(64),
  inputs_snapshot         jsonb NOT NULL,

  -- safety сработки (даже если advisory)
  safety_override         varchar(64),              -- NULL если нет override

  schema_version          smallint NOT NULL DEFAULT 1
);
CREATE INDEX irr_adv_zone_ts_idx ON irrigation_advisories (zone_id, generated_at DESC);
SELECT create_hypertable('irrigation_advisories', 'generated_at', chunk_time_interval => interval '7 days');
```

### 5.3. `weather_observations` — факт погоды

```sql
CREATE TABLE weather_observations (
  id                      bigserial PRIMARY KEY,
  greenhouse_id           bigint REFERENCES greenhouses(id),
  ts                      timestamptz NOT NULL,
  source                  varchar(32) NOT NULL,     -- 'open_meteo'|'local_station'|'manual'
  temp_c                  double precision,
  humidity_pct            double precision,
  pressure_hpa            double precision,
  wind_speed_m_s          double precision,
  wind_direction_deg      double precision,
  solar_radiation_w_m2    double precision,         -- GHI
  cloud_cover_pct         double precision,
  precipitation_mm_h      double precision,
  raw_payload             jsonb                     -- сырой ответ API
);
CREATE INDEX wobs_gh_ts_idx ON weather_observations (greenhouse_id, ts DESC);
SELECT create_hypertable('weather_observations', 'ts', chunk_time_interval => interval '30 days');
```

### 5.4. `weather_forecasts` — прогноз на будущее

```sql
CREATE TABLE weather_forecasts (
  id                      bigserial PRIMARY KEY,
  greenhouse_id           bigint REFERENCES greenhouses(id),
  fetched_at              timestamptz NOT NULL,    -- когда получили прогноз
  forecast_for_ts         timestamptz NOT NULL,    -- на какое время прогноз
  horizon_hours           smallint NOT NULL,       -- forecast_for_ts - fetched_at, часы
  source                  varchar(32) NOT NULL,

  temp_c                  double precision,
  humidity_pct            double precision,
  solar_radiation_w_m2    double precision,
  cloud_cover_pct         double precision,
  wind_speed_m_s          double precision,
  precipitation_prob_pct  double precision,

  PRIMARY KEY (id)
);
CREATE INDEX wfc_gh_for_ts_idx ON weather_forecasts (greenhouse_id, forecast_for_ts);
CREATE INDEX wfc_gh_fetched_idx ON weather_forecasts (greenhouse_id, fetched_at DESC);
```

Каждый fetch пишет **все** горизонты (1h, 3h, 6h, 12h, 24h) — это позволит
потом измерить качество прогноза ретроспективно (actual vs forecasted).

### 5.5. `irrigation_features_5m` — ML-ready витрина

Аналогично `zone_features_5m` из `ML_FEATURE_PIPELINE.md`, но фокус — на воду.

```sql
CREATE TABLE irrigation_features_5m (
  ts                      timestamptz NOT NULL,
  zone_id                 bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  cycle_id                bigint      REFERENCES grow_cycles(id),
  recipe_phase            varchar(32),
  phenology_stage         varchar(32),              -- 'transplant'|'veg'|'flower'|'fruit'|'harvest'|'senescence'

  -- климат внутри (агрегаты окна 5 мин)
  air_temp_mean           double precision,
  air_humidity_mean       double precision,
  vpd_kpa_mean            double precision,         -- вычислен внутри feature-builder
  par_umol_m2_s_mean      double precision,
  co2_ppm_mean            double precision,
  canopy_temp_mean        double precision,         -- если есть IR, иначе NULL

  -- накопители с последнего полива (reset при IRRIGATION_FINISHED)
  minutes_since_last_irrigation integer,
  vpd_integral_since_last_kpa_h double precision,
  par_integral_since_last_mol_m2 double precision,
  et0_mm_since_last       double precision,
  etc_mm_since_last       double precision,

  -- субстрат
  wc_substrate            double precision,         -- последнее измерение в окне
  wc_dryback_since_peak_pct double precision,       -- (WC_peak - WC_now)/WC_peak × 100
  ec_substrate            double precision,         -- если есть sub-sensor, иначе NULL

  -- растение (prevailing, NULL если нет данных)
  canopy_area_mm2         double precision,         -- из VISION_PIPELINE
  canopy_growth_rate_7d   double precision,
  vision_tip_burn_score   double precision,
  vision_wilting_score    double precision,

  -- внешняя погода (факт)
  outdoor_temp_c          double precision,
  outdoor_humidity_pct    double precision,
  outdoor_solar_w_m2      double precision,
  outdoor_wind_m_s        double precision,

  -- прогноз на ближайшие 6 часов (среднее)
  forecast_temp_next_6h   double precision,
  forecast_solar_next_6h  double precision,
  forecast_vpd_next_6h    double precision,

  -- время
  hour_of_day_frac        double precision,         -- 0..24 (учитывая минуты)
  minutes_since_lights_on integer,
  minutes_until_lights_off integer,
  days_since_planted      double precision,
  days_since_phase_start  double precision,

  -- качество
  valid_ratio             double precision,
  feature_schema_version  smallint NOT NULL DEFAULT 1,
  PRIMARY KEY (zone_id, ts)
);
CREATE INDEX irr_feat_ts_idx ON irrigation_features_5m (ts);
SELECT create_hypertable('irrigation_features_5m', 'ts', chunk_time_interval => interval '7 days');
ALTER TABLE irrigation_features_5m SET (timescaledb.compress, timescaledb.compress_segmentby = 'zone_id');
SELECT add_compression_policy('irrigation_features_5m', interval '14 days');
```

### 5.6. `irrigation_strategy_profiles` — настройки на зону/фазу

Таблица пользовательских настроек: WC-границы, leaching target, VPD thresholds.
Owner: Laravel (UI).

```sql
CREATE TABLE irrigation_strategy_profiles (
  id                      bigserial PRIMARY KEY,
  zone_id                 bigint REFERENCES zones(id) ON DELETE CASCADE,
  recipe_phase            varchar(32),              -- NULL = default для всех фаз

  -- rule-based floor (слой 1)
  vpd_integral_trigger_kpa_h double precision NOT NULL,
  max_interval_sec        integer NOT NULL,
  wc_floor_pct            double precision NOT NULL,
  wc_target_pct           double precision NOT NULL,
  wc_ceiling_pct          double precision NOT NULL,

  -- ET-based (слой 2)
  kc_base                 double precision,         -- из FAO-56 для фазы
  canopy_area_override_mm2 double precision,
  et_trigger_mm           double precision NOT NULL,

  -- leaching
  leaching_target_pct     double precision NOT NULL,
  leaching_min_pct        double precision NOT NULL,
  leaching_max_pct        double precision NOT NULL,

  -- pre-dawn dryback
  predawn_dryback_target_pct double precision,      -- целевой dryback за ночь

  -- ML gating
  ml_advisory_enabled     boolean NOT NULL DEFAULT false,
  ml_max_correction_pct   double precision NOT NULL DEFAULT 20,  -- ML не меняет объём более чем на ±20%

  created_by              bigint REFERENCES users(id),
  valid_from              timestamptz NOT NULL DEFAULT now(),
  valid_to                timestamptz,
  UNIQUE (zone_id, recipe_phase, valid_from)
);
CREATE INDEX irr_profile_zone_idx ON irrigation_strategy_profiles (zone_id, valid_to);
```

### 5.7. `irrigation_labels` — таргеты для обучения

Отдельно от фичей, как принято в `ML_FEATURE_PIPELINE.md §5.4`.

```sql
CREATE TABLE irrigation_labels (
  ts                      timestamptz NOT NULL,
  zone_id                 bigint      NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  horizon                 varchar(8)  NOT NULL,    -- 'next_1h'|'next_6h'|'next_24h'

  -- предикт
  next_irrigation_needed_within boolean,           -- true если полив в горизонте
  actual_next_irrigation_ts    timestamptz,
  actual_next_volume_ml        double precision,

  -- успех (ретроспективно)
  achieved_leaching_pct   double precision,
  had_wilting_event       boolean,                 -- CV заметил wilting в горизонте
  had_wc_floor_breach     boolean,
  had_wc_ceiling_breach   boolean,

  is_valid                boolean NOT NULL,
  invalid_reason          varchar(64),
  label_schema_version    smallint NOT NULL DEFAULT 1,
  PRIMARY KEY (zone_id, ts, horizon)
);
CREATE INDEX irr_lbl_ts_idx ON irrigation_labels (ts);
```

---

## 6. Сервис `weather-fetcher`

**Путь:** `backend/services/weather-fetcher/`
**Стек:** Python, httpx, asyncpg, prometheus_client.

### 6.1. Источник

**Open-Meteo** (https://open-meteo.com) — бесплатно, без ключа, лимит
~10k запросов/день. Alternative: OpenWeatherMap (API key, бесплатный tier
лимитированный).

Для каждой `greenhouses.coordinates` (JSONB с lat/lng) каждые **15 минут**:
- fetch current → `weather_observations`
- fetch forecast на 48 часов (hourly) → `weather_forecasts`, все горизонты

### 6.2. Endpoints

- `GET /healthz`
- `GET /metrics`
- `POST /admin/refresh/{greenhouse_id}` — форс-апдейт
- `GET /v1/current/{greenhouse_id}` — последние observation
- `GET /v1/forecast/{greenhouse_id}?horizon_hours=6` — прогноз

### 6.3. Конфигурация

```
WEATHER_PROVIDER=open_meteo
WEATHER_POLL_INTERVAL_SEC=900        # 15 min
WEATHER_FORECAST_HORIZON_HOURS=48
WEATHER_RETENTION_DAYS=365           # observations; forecasts=180
WEATHER_RATE_LIMIT_RPM=10            # на провайдер
```

### 6.4. Метрики

```
weather_fetches_total{provider,type="obs|forecast"}
weather_fetch_errors_total{provider,reason}
weather_fetch_latency_seconds
weather_forecast_rows_written_total
weather_forecast_rmse{greenhouse_id,variable,horizon_hours}  # заполняется отдельно
```

---

## 7. Сервис `irrigation-planner`

**Путь:** `backend/services/irrigation-planner/`
**Стек:** Python, asyncpg, paho-mqtt, torch (CPU).

### 7.1. Основной цикл

Для каждой `zones.automation_runtime='ae3'` с `settings.irrigation_ml_enabled=true`:

```
every 60 seconds:
  inputs = collect_inputs(zone)         # текущая строка из irrigation_features_5m
  profile = load_active_profile(zone, phase)

  # Layer 1: safety rules
  layer1 = evaluate_rules(inputs, profile)
  if layer1.must_fire:
    advisory = {trigger_now=true, volume=layer1.volume, reason=layer1.rule, source='rule'}
    save_advisory(advisory)
    send_to_automation_engine(advisory)
    continue

  # Layer 2: Physics ET
  etc = compute_etc(inputs, profile.kc_base, phase)
  layer2 = et_decide(etc, accumulated_etc, profile, forecast)

  # Layer 3: ML overlay (if enabled)
  if profile.ml_advisory_enabled and active_model_available:
    correction = ml_model.predict(inputs, forecast, layer2.volume)
    correction_capped = clip(correction, -profile.ml_max_correction_pct/100 * layer2.volume,
                                          +profile.ml_max_correction_pct/100 * layer2.volume)
  else:
    correction_capped = 0.0

  final_volume = layer2.volume + correction_capped
  trigger_now = (accumulated_etc >= profile.et_trigger_mm) or forecast_pre_emptive_due

  advisory = {..., source='ml' if correction_capped != 0 else 'et'}
  save_advisory(advisory)
  if trigger_now:
    send_to_automation_engine(advisory)
```

### 7.2. Интерфейсы с `automation-engine`

Новая связь: `irrigation-planner` публикует advisory и делает
`POST http://automation-engine:9405/v1/irrigation/trigger` с payload:

```json
{
  "zone_id": 12,
  "advisory_id": 44871,
  "volume_ml": 320.0,
  "duration_hint_sec": 12.0,
  "source": "ml",
  "safety_floor_applied": false,
  "trace_id": "irr-adv-44871"
}
```

AE принимает, создаёт intent в БД (по паттерну `AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`),
дальше работает существующий pipeline. **AE3 имеет право отклонить** (например,
если water_state != NORMAL_RECIRC) — в этом случае в `irrigation_advisories`
пишется `safety_override`.

### 7.3. Конфигурация

```
IRR_PLANNER_TICK_INTERVAL_SEC=60
IRR_PLANNER_LOOKBACK_MINUTES=15
IRR_PLANNER_ETC_TRIGGER_DEFAULT_MM=2.5
IRR_PLANNER_DEFAULT_KC_MAP_JSON={"veg":0.7,"flower":0.85,"fruit":1.0,"senescence":0.75}
IRR_PLANNER_PREFETCH_FORECAST_HOURS=6
```

### 7.4. Метрики

```
irrigation_advisories_total{zone_id,source}
irrigation_triggers_total{zone_id,source,safety_override}
irrigation_volume_ml_planned_total{zone_id}
irrigation_volume_ml_actual_total{zone_id}
irrigation_volume_error_ratio{zone_id}      # (actual - planned) / planned
irrigation_leaching_fraction{zone_id}
irrigation_wc_drift_breach_total{zone_id,bound="floor|ceiling"}
irrigation_planner_tick_seconds{stage}
```

---

## 8. Модели

### 8.1. Layer 1 (Rule-based) — формулы

**VPD** (Tetens + насыщенное давление):
```
es(T_c)  = 0.6108 × exp(17.27 × T_c / (T_c + 237.3))   # кПа
ea       = es(T_c) × RH_pct / 100
VPD_kPa  = es - ea
```

**VPD-integral trigger:**
```
accumulate VPD × Δt (часы)
if VPD_integral ≥ vpd_integral_trigger_kpa_h → fire
```

Типичные значения для клубники в плодоношении:
- Дневной VPD target: 0.8–1.2 kPa
- Integral trigger между поливами: 2–4 kPa·h

**WC-floor:**
```
if wc_substrate < wc_floor_pct → fire (safety)
```

**Max interval:**
```
if minutes_since_last_irrigation > max_interval_sec / 60 → fire
```

**Visual emergency:**
```
if vision_wilting_score > 0.7 → fire
```

### 8.2. Layer 2 (Physics ET) — Penman-Monteith для закрытой теплицы

FAO-56 PM в оригинале предполагает outdoor wind. Для теплицы берём
**Stanghellini** или упрощённую форму:

```
Δ  = 4098 × es(T) / (T + 237.3)²                    # наклон давления пара
γ  = 0.665e-3 × P                                   # психрометрический коэф.
Rn = 0.77 × solar_radiation_w_m2 × 0.0864            # чистая радиация, МДж/м²/день
     (коэф. 0.77 — для теплицы, часть солнца срезает кровля и затенение)
G  = 0   # soil heat flux ≈ 0 в substrate drip
aerodynamic term =  γ × (37 / (T + 273)) × u × VPD / (Δ + γ × (1 + 0.34 × u))
     (для закрытой теплицы u ≈ 0.3-0.5 m/s — внутренняя вентиляция)
radiation term  =  Δ × (Rn - G) / (Δ + γ × (1 + 0.34 × u))

ET₀ = radiation_term + aerodynamic_term   # mm/day
```

Пересчёт на 5-мин окно: `ET₀_5m = ET₀_day × (solar_5m / solar_day_total)`.

**Kc для клубники** (FAO-56 + практика hydroponic greenhouse, индикативно):
| Фаза | Kc | Длительность (дней) |
|---|---|---|
| После пересадки | 0.40 | 7–14 |
| Вегетативный рост | 0.70 | 20–30 |
| Начало цветения | 0.80 | 10–14 |
| Полное цветение | 0.90 | 14–21 |
| Плодоношение (peak) | 1.00–1.05 | 30–60 |
| Senescence / пост-уборка | 0.75 → 0.50 | 14–21 |

**Объём полива:**
```
volume_ml = ETc_mm × canopy_area_mm2 / 1000 × (1 + leaching_target_pct / 100)
```

Где `canopy_area_mm2` — из `plant_visual_features_1h.canopy_area_mm2_mean`,
суммированный по растениям зоны. Если CV ещё не запущен — из профиля
`canopy_area_override_mm2` или рассчитанный по плотности посадки
× средней площади листа фазы.

### 8.3. Layer 3 (ML overlay)

**Задача 1 — learned Kc_correction (regression):**

Вход (фичи):
- `irrigation_features_5m` за момент триггера
- Исторические `irrigation_events.is_clean=true` за последние 90 дней по этой зоне
  → dataset для supervised

Таргет: `Kc_effective = actual_volume_ml / (ET0 × canopy_area × (1 + leaching_target))`

Модель: XGBoost / LightGBM с квантильной регрессией (predict median + P10/P90
для доверительных интервалов).

Использование: `Kc_ml = Kc_base × Kc_correction_factor`.

**Задача 2 — next irrigation time forecaster:**

Вход: те же фичи + прогноз погоды на 6 часов.
Таргет: `minutes_until_next_irrigation` (regression).
Модель: GBM или TFT (если много данных).

Использование: UI «ожидаемый следующий полив через N минут»; pre-emptive
подготовка системы.

**Задача 3 — leaching quality classifier (позже):**

Вход: volume_planned + климат.
Таргет: achieved_leaching в коридоре [leaching_min, leaching_max]?
Модель: binary classifier; advisory сообщает, если вероятность промаха > 30%.

### 8.4. Ограничения ML

- `IRR_PLANNER_ML_MAX_CORRECTION_PCT=20` — не меняем объём более чем на ±20%
  от Layer 2.
- Если модель predicts `volume < 0.5 × layer2` или `> 2 × layer2`
  → сработка `safety_override='ml_out_of_bounds'`, используется Layer 2.
- Модель отключается автоматически при `feature_freshness > 10 min` или
  `valid_ratio < 0.7`.

---

## 9. Safety-слой (жёстче, чем у дозирования)

Пропущенный полив в жару = гибель растения за 4–8 часов. Перелив = корневая
гниль за 2–3 дня. Поэтому **каждый** сценарий имеет дублирующую защиту.

### 9.1. Глобальные хард-лимиты (нельзя отключить через UI)

| Параметр | Значение | Причина |
|---|---|---|
| `MIN_IRRIGATION_INTERVAL_SEC` | 180 | Защита от залива при ошибке сенсора |
| `MAX_IRRIGATION_DURATION_SEC` | 120 | Если насос не остановится — не затопит |
| `MAX_DAILY_VOLUME_L_PER_PLANT` | 3.0 | Гидропонная клубника расходует ≤ 1 л/растение/день |
| `WC_EMERGENCY_FLOOR_PCT` | 20 | Ниже — forced irrigation независимо от логики |
| `WC_EMERGENCY_CEILING_PCT` | 80 | Выше — блокировка полива |
| `MAX_CONSECUTIVE_SKIPS` | 3 | Если advisory 3 раза подряд сказал «не лить», а WC упал — форс |

Хранятся в `automation_config_documents(namespace='system.irrigation_safety')`
(по паттерну pump calibration из `DATA_MODEL_REFERENCE §3`).

### 9.2. Emergency-инициаторы полива

- `wc_substrate < wc_emergency_floor` — немедленно
- `vision_wilting_score > 0.7` (тройное подтверждение в 3-х кадрах подряд) — немедленно
- `minutes_since_last > max_interval × 1.5` — fallback ручной режим

Пишется `zone_events.type='IRRIGATION_EMERGENCY_FIRED'` с причиной.

### 9.3. Emergency-блокировки

- `drainage_not_detected` в первые 30 сек после полива в DtW режиме →
  блокировка следующего полива + alert (вероятная засорка слива).
- `flow_too_low` → блокировка + alert (forсунка / насос).
- `wc_substrate > wc_emergency_ceiling` → блокировка полива.
- `ec_drain > 3 × ec_solution` → блокировка + alert «возможно пересоление
  корневой зоны».

### 9.4. Rollback Layer 3 → Layer 2

Автоматический откат ML-слоя, если за последние 24 часа:
- `rate(irrigation_wc_drift_breach_total) > 1.5 × baseline`
- или хоть один `IRRIGATION_EMERGENCY_FIRED` с `source='ml'`

---

## 10. Интеграция с соседними pipeline'ами

### 10.1. Что читаем из `ML_FEATURE_PIPELINE.md`

- `zone_features_5m.ec_mean`, `ec_slope` — для fallback «прокси транспирации»
  (EC растёт → воды убыло → пить хочет), когда WC-сенсор недоступен.
- `zone_features_5m.ph_mean`, `ph_slope` — для safety-проверки «pH не должен
  улететь после полива».

### 10.2. Что читаем из `VISION_PIPELINE.md`

- `plant_visual_features_1h.canopy_area_mm2_mean` — обновлённая площадь
  листового покрова (каждый час).
- `plant_visual_features_1h.tip_burn_score_max` — сигнал Ca-дефицита /
  избыточного EC → триггер для пересмотра leaching target в сторону увеличения.
- **Новая фича в VISION_PIPELINE:** `vision_wilting_score` — детектор увядания.
  Это **отдельная модель** (не в этом документе) с классом `mild_wilting` /
  `severe_wilting`. Должна быть добавлена в Приложение B VISION_PIPELINE
  одновременно с Phase I2 этого плана.

### 10.3. Что пишем в `ML_FEATURE_PIPELINE.md`

В `zone_features_5m` добавляются колонки (additive):
```sql
ALTER TABLE zone_features_5m
  ADD COLUMN vpd_kpa_mean              double precision,
  ADD COLUMN vpd_integral_since_last_kpa_h double precision,
  ADD COLUMN par_umol_m2_s_mean        double precision,
  ADD COLUMN co2_ppm_mean              double precision,
  ADD COLUMN wc_substrate              double precision,
  ADD COLUMN minutes_since_last_irrigation integer,
  ADD COLUMN outdoor_temp_c            double precision,
  ADD COLUMN outdoor_solar_w_m2        double precision;
```

Инкремент `feature_schema_version` → 2. Backfill по правилам §9
`ML_FEATURE_PIPELINE.md`.

### 10.4. Как feature-builder расширяется

Новые задачи в `feature-builder` (по аналогии с §6.1 `ML_FEATURE_PIPELINE.md`):

1. Тик раз в минуту → достраивать `irrigation_features_5m` (JOIN телеметрии,
   погодных данных, CV-фичей).
2. На каждый `IRRIGATION_FINISHED` → запланировать заполнение
   `irrigation_events` (через 60 минут — чтобы набрать response окно).
3. Раз в 5 минут → пересчитать `irrigation_labels` для тех `ts`, где
   прошло `horizon + 5 мин`.

---

## 11. Retention

| Таблица | Hot | Warm/Compressed | Cold/Drop |
|---|---|---|---|
| `irrigation_events` | 365 дней | 365 дней – ∞ | — (маленькая, ценная) |
| `irrigation_advisories` | 90 дней | 90 дней – 12 мес | drop после 12 мес |
| `weather_observations` | 365 дней | 30–365 дней compressed | — |
| `weather_forecasts` | 180 дней | — | drop |
| `irrigation_features_5m` | 14 дней | 14 дней – 24 мес | — |
| `irrigation_labels` | 12 мес | 12–24 мес compressed | пересчёт по запросу |
| `irrigation_strategy_profiles` | ∞ | — | — |

Env переменные добавляются в `weather-fetcher` и `irrigation-planner`
(по паттерну §10 `DATA_RETENTION_POLICY.md`), обновить сам документ.

---

## 12. Inference / real-time контур

Частоты и SLO:

| Компонент | Частота | p95 latency |
|---|---|---|
| `weather-fetcher` | 1 / 15 мин / теплица | < 2 сек на fetch |
| `irrigation-planner` tick | 1 / мин / зона | < 500 мс на зону |
| ML inference (Layer 3) | на тике, если требуется | < 100 мс |
| Запись advisory | 1 / мин / зона | < 50 мс |
| Feature freshness требование для ML | ≤ 10 мин | — |

Всё в пределах существующих ресурсов, GPU не требуется.

---

## 13. Model lifecycle

Модели живут в `ml_models` (из `ML_FEATURE_PIPELINE.md §5.6`) с `name`:
- `irrigation_kc_correction`
- `irrigation_next_trigger`
- `irrigation_leaching_classifier`

Переходы статусов **jестче** чем для дозирования:
- `shadow → canary`: ≥ 45 дней shadow + снижение
  `irrigation_wc_drift_breach_total` на 25% vs baseline + MAE на test ≤ 15%.
- `canary → active`: ≥ 30 дней canary + ни одного `IRRIGATION_EMERGENCY_FIRED`
  с `source='ml'`.
- Автоматический rollback → `retired`: 1 emergency event с ML-источником.

---

## 14. План внедрения по фазам

### Phase I0 · Подготовка (1 неделя)

| Задача | DoD |
|---|---|
| Ревью/утверждение документа | merge в `doc_ai/` |
| Регистрация `greenhouses.coordinates` для пилотных теплиц | UI позволяет задать lat/lng |
| Настройка `automation_config_documents(namespace='system.irrigation_safety')` | Значения из §9.1 залиты |
| Добавление WC-сенсора в hardware_profile пилотной зоны | Реально подключено, `sensors` содержит `type='SOIL_MOISTURE'` (scope substrate) |

### Phase I1 · Weather fetcher (1 неделя)

| Задача | DoD |
|---|---|
| Миграции §5.3, §5.4 | Up/down |
| `backend/services/weather-fetcher/` + Open-Meteo интеграция | E2E: запись в obs+forecast каждые 15 мин |
| Grafana dashboard «Weather» | График T/RH/solar для каждой теплицы |
| Обратный тест качества forecast (actual vs forecasted через 24ч) | RMSE solar ≤ 150 W/m² на 24h |

### Phase I2 · Rule-based Layer 1 + события (2 недели)

| Задача | DoD |
|---|---|
| Миграции §5.1, §5.2, §5.6, §5.7 | Up/down |
| `backend/services/irrigation-planner/` skeleton (FastAPI, metrics, tick) | `/healthz` 200, pod работает |
| VPD-integral и WC-floor правила | Unit-тесты покрывают 8 сценариев; E2E: при VPD-integral ≥ threshold — advisory со `source='rule'` |
| Запись `irrigation_events` при каждом IRRIGATION_FINISHED | Строка появляется с pre-values |
| Отложенное заполнение response (+60 мин) | Через 70 мин после полива `wc_substrate_peak` и `leaching_fraction` заполнены |
| UI «Стратегия полива» в Laravel (редактирование `irrigation_strategy_profiles`) | Можно задать WC-границы, VPD-trigger, etc |

### Phase I3 · Physics ET Layer 2 (2 недели)

| Задача | DoD |
|---|---|
| Имплементация Penman-Monteith с greenhouse-modification | Unit-тесты сверяют с reference-значениями (±5%) |
| Kc-таблица для клубники в `irrigation_strategy_profiles.kc_base` + phase override | Заполнено |
| Logic: ETc accumulation → trigger | E2E: за солнечный день число поливов > чем за пасмурный |
| Включён Layer 2 на 1 пилотной зоне в shadow (рекомендации пишутся, но не исполняются) | 14 дней чистого shadow-run без расхождения с текущей логикой > 30% |
| Grafana: ET₀, ETc, VPD, накопители | Работает |

### Phase I4 · Переключение пилота на Layer 1+2 active (2 недели)

| Задача | DoD |
|---|---|
| `zones.settings.irrigation_planner_enabled=true` на 1 зоне | Полив идёт по advisory от планировщика |
| Сравнение с соседней зоной на blind-scheduling | A/B: расход воды, WC-стабильность, число breach'ей |
| Критерий успеха для продвижения | Снижение расхода ≥ 15% при отсутствии emergency events |

### Phase I5 · Feature-builder расширение + витрина (1 неделя)

| Задача | DoD |
|---|---|
| Миграция §5.5 (`irrigation_features_5m`) | Up/down, hypertable |
| Feature-builder тик раз в минуту собирает витрину | Лаг ≤ 5 мин на пилотной зоне |
| ALTER `zone_features_5m` (§10.3) с инкрементом schema version | Backfill 30 дней данных пройден |

### Phase I6 · ML Layer 3 shadow (3 недели)

| Задача | DoD |
|---|---|
| Training notebook `tools/ml/irrigation/kc_correction.ipynb` | Модель на XGBoost, MAE по Kc_effective лучше baseline на 15% |
| Регистрация модели `irrigation_kc_correction` в `ml_models` со статусом shadow | Записи идут в `ml_predictions` |
| `irrigation-planner` читает predictions в advisory (но `layer3_ml_correction_ml=0` в prod) | Shadow-режим |
| 45 дней run + дашборд качества | Grafana `ML / Irrigation Quality` |

### Phase I7 · Canary → Active (TBD, отдельный runbook)

Только при соблюдении критериев §13.

### Phase I8 · Vision-integration (1 неделя; зависит от Phase V5 из VISION)

| Задача | DoD |
|---|---|
| Фича `vision_wilting_score` добавлена в `plant_visual_features_1h` | Приложение B VISION_PIPELINE обновлён |
| `irrigation-planner` читает wilting + canopy_area из CV | Emergency-триггер работает E2E |

---

## 15. Чек-лист перед мержем фичи в Irrigation-слой

- [ ] Новые таблицы/колонки задокументированы в `DATA_MODEL_REFERENCE.md`
- [ ] `feature_schema_version` / `schema_version` инкрементирован
- [ ] Up/down миграции пройдены на dev
- [ ] Unit-тесты покрывают все правила Layer 1
- [ ] Unit-тесты покрывают P-M формулу (сверка с reference ±5%)
- [ ] E2E: изменение T/RH → изменение advisory
- [ ] Point-in-time: фичи на `ts` используют только `telemetry < ts` и
      `forecasts.fetched_at < ts`
- [ ] Safety-лимиты из §9.1 нельзя обойти через ML
- [ ] Rollback Layer 3 → 2 проверен (чёрный тест: сломанная модель → Layer 2)
- [ ] `weather-fetcher` rate-limit соблюдён
- [ ] Prometheus метрики + Grafana dashboard обновлены
- [ ] Retention policy обновлена в `DATA_RETENTION_POLICY.md`
- [ ] `WATER_FLOW_ENGINE.md` — добавлена ссылка «когда ML включён, см. IRRIGATION_ML_PIPELINE.md»

---

## 16. Правила для ИИ-агентов

### Можно:

- Генерировать DDL/миграции по §5 (up+down обязательны).
- Писать код `weather-fetcher`, `irrigation-planner`, их тесты, метрики.
- Расширять `feature-builder` irrigation-специфичными агрегатами.
- Писать training notebooks в `tools/ml/irrigation/`.
- Добавлять новые правила в Layer 1 (с обязательным тестом и описанием в §8.1).
- Добавлять новые Kc-значения и фазы в `irrigation_strategy_profiles` defaults.

### Нельзя:

- **Менять hardcoded safety-лимиты** из §9.1 без явного подтверждения человека
  через PR, обновляющий `automation_config_documents(namespace='system.irrigation_safety')`.
- Использовать ML Layer 3 в обход Layer 1+2.
- Запускать полив из сервисов кроме `automation-engine` (как и сейчас).
- Писать в `weather_observations` что-либо кроме данных от `weather-fetcher`.
- Модифицировать физику в `WATER_FLOW_ENGINE` в рамках этого документа
  (только добавлять advisory-интеграцию).
- Игнорировать `safety_override` в `irrigation_advisories` — если он сработал,
  причина должна быть расследована.
- Тренировать ML на `irrigation_events` с `is_clean=false`.

### Обязательно:

- Каждый PR с irrigation — обновление этого документа.
- Любое изменение формулы ET / Kc — обновление §8.2 + backfill-стратегия.
- Любая новая модель → запись в `ml_models` с `trained_on_range`, `metrics_json`,
  `feature_schema_version`.
- При активации ML на новой зоне → явное подтверждение оператора + запись в
  `zone_events.type='IRRIGATION_ML_ENABLED'`.

---

## 17. Открытые вопросы

1. **Источник погоды:** Open-Meteo (бесплатно, надёжно) vs OpenWeatherMap vs
   physical weather station на крыше. Рекомендую Open-Meteo на старте +
   локальную станцию как override если есть.
2. **Leaching strategy:** drain-to-waste (DtW) vs recirculating substrate.
   Этот документ писан под DtW. Для recirc — отдельная логика: там leaching
   fraction не самоцель, а баланс солей в бак возврата.
3. **WC-сенсоры:** какие именно используем (TEROS 12, SMT100, capacitive
   cheap)? От этого зависит калибровочная кривая WC↔sensor_value. Добавить
   в `sensors.specs`.
4. **CO2 эффект на транспирацию:** включать ли stomatal-resistance модель
   с учётом CO2? В простом P-M — нет. Для high-CO2 теплиц (1000+ ppm)
   транспирация ниже на 15–20% при той же VPD → стоит заложить поправку.
5. **Единая модель для всех зон** или per-zone? Для MVP — глобальная с
   `zone_id` как фичей; per-zone при накоплении ≥ 90 дней на зону.
6. **Night-time irrigation:** допускать или полностью запрещать? Клубнике
   обычно противопоказан поздний вечерний полив (риск Botrytis). Надо
   отразить в Layer 1 через `night_irrigation_allowed=false`.
7. **Фото drainage tank:** стоит ли поставить камеру на бак слива и оценивать
   объём drain visually, если нет flow-sensor'a на дрен? Это backup-канал.

---

## Приложение A. VPD nomogram для клубники

| T°C | RH 40% | RH 50% | RH 60% | RH 70% | RH 80% | RH 90% |
|---|---|---|---|---|---|---|
| 18 | 1.24 | 1.03 | 0.83 | 0.62 | 0.41 | 0.21 |
| 20 | 1.40 | 1.17 | 0.94 | 0.70 | 0.47 | 0.23 |
| 22 | 1.59 | 1.32 | 1.06 | 0.79 | 0.53 | 0.26 |
| 24 | 1.79 | 1.49 | 1.19 | 0.89 | 0.60 | 0.30 |
| 26 | 2.02 | 1.68 | 1.34 | 1.01 | 0.67 | 0.34 |
| 28 | 2.26 | 1.89 | 1.51 | 1.13 | 0.75 | 0.38 |

(кПа; клубника комфортна при 0.6–1.0; тревожно > 1.3)

## Приложение B. Пример строки `irrigation_features_5m`

```json
{
  "ts": "2026-04-22T14:30:00Z",
  "zone_id": 12,
  "cycle_id": 47,
  "recipe_phase": "fruiting",
  "phenology_stage": "fruit",
  "air_temp_mean": 24.3,
  "air_humidity_mean": 58.0,
  "vpd_kpa_mean": 1.27,
  "par_umol_m2_s_mean": 412.0,
  "co2_ppm_mean": 950.0,
  "minutes_since_last_irrigation": 142,
  "vpd_integral_since_last_kpa_h": 2.91,
  "par_integral_since_last_mol_m2": 3.52,
  "et0_mm_since_last": 1.84,
  "etc_mm_since_last": 1.84 * 1.0,
  "wc_substrate": 54.2,
  "wc_dryback_since_peak_pct": 8.1,
  "canopy_area_mm2": 68200.0,
  "vision_tip_burn_score": 0.08,
  "vision_wilting_score": 0.02,
  "outdoor_temp_c": 21.0,
  "outdoor_solar_w_m2": 612.0,
  "forecast_temp_next_6h": 23.5,
  "forecast_solar_next_6h": 580.0,
  "forecast_vpd_next_6h": 1.35,
  "hour_of_day_frac": 14.5,
  "minutes_since_lights_on": 420,
  "days_since_planted": 52.0,
  "valid_ratio": 1.0,
  "feature_schema_version": 1
}
```

## Приложение C. Kc-таблица для клубники (FAO-56 adapted)

Уже в §8.2. Дублируется здесь для быстрой справки + добавлены
температурные поправки:

```python
def kc_strawberry(phenology, days_in_phase, mean_temp_c):
    base = {
        "transplant": 0.40,
        "veg_early":  0.55,
        "veg_late":   0.75,
        "flower_early": 0.80,
        "flower_full":  0.90,
        "fruit_peak":   1.00,
        "post_harvest": 0.75,
        "senescence":   0.50,
    }[phenology]
    # температурная поправка (при cool climates Kc чуть ниже)
    if mean_temp_c < 18:
        base *= 0.92
    elif mean_temp_c > 28:
        base *= 1.05
    return base
```

Использовать как initial. `irrigation_kc_correction` ML-модель выучит поправки
поверх этого.

---

# Конец файла IRRIGATION_ML_PIPELINE.md
