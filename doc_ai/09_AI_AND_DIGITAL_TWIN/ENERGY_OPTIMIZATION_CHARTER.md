# ENERGY_OPTIMIZATION_CHARTER.md
# Паспорт pipeline: оптимизация энергопотребления

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/ENERGY_OPTIMIZATION_CHARTER.md`
**Связанные:** `CLIMATE_CONTROL_CHARTER.md`, `MULTI_ZONE_COORDINATION_CHARTER.md`,
`YIELD_FORECASTING_CHARTER.md` (экономический слой)

---

## 1. Назначение

Электричество (LED, HVAC, насосы) — обычно 30–50% OPEX тепличной клубники.
В регионах с dynamic-pricing (ночной тариф, hourly exchange) можно экономить
15–30% просто сдвигая энергоёмкие действия во времени без изменения
агрономии. Этот pipeline:
- получает тариф / forecast цен электричества;
- оптимизирует расписание подсветки, подогрева, CO2-компрессора;
- использует тепловую массу теплицы как аккумулятор.

## 2. Цели

- Сдвинуть ≥30% LED-часов на low-tariff зоны, не ухудшая DLI (Daily Light
  Integral).
- Pre-heat / pre-cool теплицу в экономичные часы.
- Batch-плановать CO2-инжекцию в часы с высоким PAR (тогда CO2 реально
  работает).
- Визуализировать: «сегодня за сутки сэкономлено X руб / X% / X кВт·ч».

## 3. Ключевые дизайн-решения

1. **DLI как инвариант** (для LED). Сколько μmol/m²/день нужно на фазу —
   фиксировано. Распределение по часам — свободный параметр.
2. **Thermal mass model** — теплица имеет инерцию. Знание её (через
   `DIGITAL_TWIN_SIMULATOR`) позволяет pre-heat за часы до потребности.
3. **Cost-aware MPC** — расширение `climate-planner`: в cost function
   добавляется weighted electricity price.
4. **Static vs dynamic pricing**: два режима. Static (ночной/дневной) —
   простой lookup. Dynamic (hourly exchange) — нужен forecast.

## 4. Структура данных

```sql
CREATE TABLE electricity_tariffs (
  id bigserial PRIMARY KEY,
  greenhouse_id bigint REFERENCES greenhouses(id),
  tariff_type varchar(16) NOT NULL,      -- 'flat'|'two_tier'|'hourly_dynamic'
  tariff_json jsonb NOT NULL,            -- {rules для static, API для dynamic}
  valid_from timestamptz NOT NULL,
  valid_to timestamptz
);

CREATE TABLE electricity_prices_forecast (
  id bigserial PRIMARY KEY,
  greenhouse_id bigint REFERENCES greenhouses(id),
  fetched_at timestamptz NOT NULL,
  for_ts timestamptz NOT NULL,
  price_per_kwh double precision NOT NULL,
  currency varchar(8) NOT NULL,
  source varchar(32)                     -- 'nordpool'|'atc'|'manual'
);
SELECT create_hypertable('electricity_prices_forecast','fetched_at',
                         chunk_time_interval=>interval '30 days');

CREATE TABLE energy_consumption_5m (
  ts timestamptz NOT NULL,
  zone_id bigint REFERENCES zones(id),
  resource_code varchar(64) NOT NULL,    -- 'LED-01'|'HVAC-MAIN'|'PUMP-STATION'
  power_kw double precision,
  energy_kwh double precision,           -- за 5 мин
  cost double precision,
  PRIMARY KEY (ts, zone_id, resource_code)
);
SELECT create_hypertable('energy_consumption_5m','ts',chunk_time_interval=>interval '7 days');

CREATE TABLE lighting_plans (
  id bigserial PRIMARY KEY,
  zone_id bigint REFERENCES zones(id),
  date date NOT NULL,
  target_dli double precision NOT NULL,
  schedule jsonb NOT NULL,               -- [{start_ts, end_ts, intensity_pct, reason}]
  optimization_method varchar(32),       -- 'static'|'dynamic_pricing'|'solar_gain'
  expected_cost double precision,
  baseline_cost double precision,
  savings_expected double precision
);
```

## 5. Сервисы

| Сервис | Роль |
|---|---|
| `electricity-fetcher` | Новый. Подтягивает цены (биржа) или static tariff |
| `energy-planner` | Новый. Раз в сутки строит `lighting_plans`; tick каждые 15 мин — актуализирует HVAC MPC |
| `energy-metering` | Новый. Собирает power/energy из сенсоров → `energy_consumption_5m` |

## 6. Фазы

| Phase | Задача | DoD |
|---|---|---|
| En0 | Power sensing на major actuators (LED, HVAC, pumps) | `energy_consumption_5m` пишется |
| En1 | Tariff ingestion + UI ввода | `electricity_tariffs` заполнены |
| En2 | Lighting optimizer (с DLI constraint) | A/B: static vs optimized |
| En3 | HVAC pre-heat/pre-cool в MPC | Совместно с CLIMATE_CONTROL |
| En4 | Dashboard «Энергосбережение» | Виден фактический и потенциальный economy |
| En5 | Dynamic pricing integration | Работает на dynamic-тарифе |

## 7. Safety

- Нельзя откладывать полив ради экономии (water-before-money).
- DLI — **hard constraint**: план должен быть реализуем; если цены плохие
  всю ночь, значит терпим высокую цену, но DLI даём.
- MAX_POWER_PEAK — не превысить contracted load (иначе штраф).

## 8. Интеграция

- **CLIMATE_CONTROL** — читает forecast цен, меняет cost weights.
- **MULTI_ZONE_COORDINATION** — арбитраж: координатор может отложить
  не-критичные actuations в peak-pricing часы.
- **YIELD_FORECASTING.cost_rates** — `electricity_kwh` cost задан там.

## 9. Правила для ИИ-агентов

### Можно:
- Добавлять новые тарифные схемы / провайдеров.
- Улучшать DLI-distribution алгоритм.

### Нельзя:
- Нарушать DLI target ради экономии.
- Превышать contracted peak load.
- Отключать heating ниже safe minimum даже при дорогой энергии.

## 10. Открытые вопросы

1. Источник биржевых цен — NordPool / ATC / локальный brokler?
2. Как считать savings — vs hypothetical baseline «без оптимизации» (нужна
   модель) или vs исторический baseline (сравнение разных сезонов,
   confounding)?
3. Стоит ли интегрировать с solar панелями на крыше?

---

# Конец ENERGY_OPTIMIZATION_CHARTER.md
