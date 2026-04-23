# YIELD_FORECASTING_CHARTER.md
# Паспорт pipeline: прогноз урожая + экономический слой

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/YIELD_FORECASTING_CHARTER.md`
**Связанные:** `VISION_PIPELINE.md` (fruit counts — основа), `ML_FEATURE_PIPELINE.md`,
`IRRIGATION_ML_PIPELINE.md`, `CLIMATE_CONTROL_CHARTER.md`

---

## 1. Назначение

Без yield-прогноза вся оптимизация ML — это оптимизация прокси-метрик (EC
в коридоре, WC стабилен, дефициты не растут), но не финального результата.
Этот pipeline:
- прогнозирует кг спелой клубники в разбивке по дням на 14–30 дней вперёд;
- переводит все технологические KPI (расход воды, энергии, удобрений) в
  валюту через per-unit costs;
- даёт per-zone / per-cultivar / per-recipe P&L, который возможно улучшать.

## 2. Цели

- **Yield forecast MAE ≤ 15%** на горизонте 7 дней, ≤ 25% на 21 день.
- **Cash-flow prognosis** — отгрузка по неделям, включая сезонные цены.
- **Recipe ROI ranking** — какой рецепт → лучше всего по «€/м²/месяц».
- **Break-even per zone** — сколько дней до выхода на окупаемость для зоны,
  с учётом CAPEX амортизации + OPEX.

## 3. Ключевые дизайн-решения

1. **Двухступенчатый прогноз:**
   - Stage A — count forecast: сколько ягод по стадиям (flower → green →
     white → turning → ripe) на горизонте N дней. Dynamics: transition rates
     между стадиями зависят от температуры (GDD — growing degree days).
   - Stage B — weight/quality conversion: ripe_count × mean_berry_weight ×
     quality_grade_distribution → кг по сортам (Extra/I/II/Отход).
2. **Survival analysis** для цветов и плодов: не всякий цветок станет плодом
   (abortion rate), не всякий плод — спелый (shrivelling, cracking). Cox PH
   модель или Weibull.
3. **GDD-based timing** — переходы между стадиями клубники:
   flower→ripe ≈ 200–250 GDD (base 5°C).
4. **Economic layer — строго read-only от технических**. Yield модель не
   знает про деньги; экономический слой их только умножает на цены.

## 4. Структура данных

```sql
CREATE TABLE plant_fruit_stage_transitions (
  id bigserial PRIMARY KEY,
  plant_id bigint NOT NULL REFERENCES plants(id),
  fruit_track_id varchar(64) NOT NULL,   -- трекинг одной ягоды через стадии
  from_stage varchar(16) NOT NULL,
  to_stage varchar(16) NOT NULL,
  transitioned_at timestamptz NOT NULL,
  days_in_from_stage double precision,
  gdd_accumulated double precision,
  UNIQUE (fruit_track_id, to_stage)
);

CREATE TABLE yield_forecasts (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  generated_at timestamptz NOT NULL,
  forecast_for_date date NOT NULL,
  horizon_days smallint NOT NULL,
  predicted_count_ripe integer,
  predicted_weight_g double precision,
  predicted_grade_distribution jsonb,    -- {extra: 0.6, one: 0.3, two: 0.08, waste: 0.02}
  confidence double precision,
  lower_p10 double precision,
  upper_p90 double precision,
  model_id bigint REFERENCES ml_models(id),
  UNIQUE (zone_id, generated_at, forecast_for_date)
);
SELECT create_hypertable('yield_forecasts','generated_at',
                         chunk_time_interval=>interval '30 days');

CREATE TABLE harvests (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  cycle_id bigint REFERENCES grow_cycles(id),
  harvested_at timestamptz NOT NULL,
  harvested_by bigint REFERENCES users(id),
  weight_g double precision NOT NULL,
  grade_counts jsonb NOT NULL,           -- {extra: 142, one: 88, ...}
  notes text
);

-- Экономический слой
CREATE TABLE cost_rates (
  id bigserial PRIMARY KEY,
  resource varchar(32) NOT NULL,         -- 'water'|'electricity_kwh'|'heat_kwh'|'co2_kg'|
                                         -- 'nutrient_npk'|'nutrient_ph'|'labor_hour'|'seedling'
  unit varchar(16) NOT NULL,
  cost_per_unit double precision NOT NULL,
  currency varchar(8) NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_to timestamptz,
  source varchar(32)                     -- 'contract'|'tariff_import'
);

CREATE TABLE revenue_rates (
  id bigserial PRIMARY KEY,
  crop varchar(32) NOT NULL,
  grade varchar(16) NOT NULL,            -- 'extra'|'one'|'two'|'waste'
  revenue_per_kg double precision NOT NULL,
  currency varchar(8) NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_to timestamptz,
  season_week smallint                   -- опц.: цена зависит от недели сезона
);

CREATE TABLE zone_economics_daily (
  zone_id bigint NOT NULL REFERENCES zones(id),
  date date NOT NULL,
  water_cost double precision,
  electricity_cost double precision,
  heat_cost double precision,
  co2_cost double precision,
  nutrient_cost double precision,
  labor_cost double precision,
  revenue_actual double precision,
  revenue_forecast_14d double precision,
  roi_daily double precision,
  PRIMARY KEY (zone_id, date)
);
```

## 5. Сервисы

| Сервис | Роль |
|---|---|
| `yield-forecaster` | Новый. На основе `plant_fruit_counts` + climate history + forecast — прогноз на 30 дней, раз в сутки |
| `economic-aggregator` | Новый. Считает `zone_economics_daily` на основе consumption + cost_rates |
| `harvest-logger` | Расширение Laravel: UI для ввода фактических сборов + связка с forecast для retrain |

## 6. Модели

- **Transition rate estimator** — для каждой пары (from_stage, to_stage) GDD
  + влияние стресса (VPD peak, tip_burn_score) на скорость. Модель:
  Accelerated Failure Time (AFT) или quantile regression.
- **Count forecaster** — Kalman filter или State Space model на переходах
  между compartment'ами (flower → green → white → turning → ripe).
- **Grade distribution classifier** — multinomial logit per-berry на основе
  roundness/uniformity/color (фичи из CV).
- **Market price model** (позже) — сезонная ARIMA на исторических ценах.

## 7. Фазы

| Phase | Задача | DoD |
|---|---|---|
| Y0 | Инвентарь: формат регистрации фактических сборов | UI для `harvests` |
| Y1 | Фенологический трекинг per-berry в VISION | `plant_fruit_stage_transitions` пишется |
| Y2 | GDD calculator + baseline transition rates | Жизненный цикл ягоды трекается |
| Y3 | Yield forecaster shadow | 30 дней, MAE на 7d ≤ 25% |
| Y4 | Grade classifier на CV | >80% accuracy vs оператор |
| Y5 | Economic aggregator | `zone_economics_daily` считается |
| Y6 | ROI dashboard + рекомендации по рецептам | UI готов, видны различия между рецептами |

## 8. Интеграция

- **Главный потребитель VISION_PIPELINE** — fruit_counts +
  fruit_stage_transitions — основа всего.
- **Использует** climate_features + irrigation_features для понимания, как
  стресс влиял на переходы.
- **Питает** `EXPLAINABILITY_UX_CHARTER` метрикой yield-impact для каждой
  ML-рекомендации: «если бы вчера поливок шёл иначе, yield через 21 день
  был бы на X кг больше».
- **Связь с AB_TESTING**: рецепты сравниваются именно по yield P&L, а не
  прокси.

## 9. Правила для ИИ-агентов

### Можно:
- Расширять список ресурсов в `cost_rates` с указанием источника тарифа.
- Добавлять grade-специфичные классификаторы.

### Нельзя:
- Смешивать в yield модели технические фичи с экономическими (это антипаттерн,
  экономика должна быть чистой post-processing).
- Публиковать forecast без confidence intervals P10/P90 (принятие решений
  без них опасно).
- Использовать неопубликованные (draft) цены в `zone_economics_daily` —
  только `valid_from ≤ now()`.

## 10. Открытые вопросы

1. Per-zone или глобальная модель переходов? Для клубники разные сорта дают
   разные GDD-пороги.
2. Как обрабатывать berry-level трекинг с top-down (плоды часто закрыты
   листьями)? Использовать Bayesian occupancy model для оценки «невидимых».
3. Цены привязаны к чему: недельный базар (СНГ/EU) или фиксированный
   контракт с сетью?
4. Labor costs — per-hour или per-kg-harvested? Влияет на структуру
   `cost_rates`.

---

# Конец YIELD_FORECASTING_CHARTER.md
