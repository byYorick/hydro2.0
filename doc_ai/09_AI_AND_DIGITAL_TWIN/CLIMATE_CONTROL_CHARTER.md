# CLIMATE_CONTROL_CHARTER.md
# Паспорт pipeline: управление климатом теплицы (HVAC, вентиляция, CO2, шторы)

**Статус:** 🟡 CHARTER · разворачивается в FULL перед началом реализации
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/CLIMATE_CONTROL_CHARTER.md`
**Связанные документы:** `AI_ROADMAP.md`, `ML_FEATURE_PIPELINE.md`,
`IRRIGATION_ML_PIPELINE.md` (жёсткая co-optimization), `WATER_FLOW_ENGINE.md`
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0

---

## 1. Назначение

Три существующих pipeline'а **читают** климат (T, RH, CO2, PAR), но **не
управляют** им. Этот pipeline добавляет управляющий контур: setpoints для
HVAC (отопление, охлаждение), осушителя, вентиляторов, CO2-генератора, шторок
теплицы. Цель — совместная оптимизация «проветрить и поднять VPD → растение
пьёт → нужен полив» vs «закрыть и удержать CO2 → рост, но риск болезней».

## 2. Ключевые цели

- Поддерживать целевой VPD и T/RH коридор каждой фазы рецепта.
- Экономить энергию: использовать тепловую массу теплицы, ночное охлаждение,
  солнечный gain.
- Снижать риск ботритиса (клубника!) через контроль влажности: никогда не
  допускать dew point на листьях (leaf_temp < dew_point → roса).
- Co-optimization с поливом: не поливать в пик транспирации, а сначала
  поднять RH и снизить VPD.

## 3. Ключевые дизайн-решения

1. **MPC-контроллер (Model Predictive Control)**, не PID. MPC «смотрит» на
   forecast (погода + свет) на 6–24 часа и выбирает последовательность
   setpoints, минимизируя стоимость (энергия + стресс растения + вода).
2. **Двухконтурная схема:**
   - Быстрый контур — PID на каждое оборудование (как сейчас).
   - Медленный контур (MPC) — каждые 10 минут переопределяет setpoints PID'ов.
3. **Dew point как hard constraint** — никогда не допускаем condensation на
   листья/плоды клубники. Это защита от ботритиса.
4. **Совместность с IRRIGATION:** `irrigation-planner` и `climate-planner`
   работают с общими `zone_features_5m`. При конфликте решений (например,
   MPC хочет закрыть шторы, но forecast solar rising → irrigation-planner
   хочет pre-emptive полив) — единый coordinator арбитрирует.

## 4. Структура данных (summary)

Новые таблицы:
- `climate_setpoints` — цели по фазам рецепта: target_temp_day/night,
  target_rh, target_co2, target_vpd, dew_margin_c
- `climate_actuators` — типы оборудования: heater, chiller, dehumidifier,
  vent_fan, curtain_motor, co2_injector, mist_nozzle
- `climate_commands` — команды к актуаторам (power_pct, angle, duty)
- `climate_advisories` — решения MPC (аналог `irrigation_advisories`)
- `climate_features_5m` — витрина: actual vs target, deviations, actuator_states,
  energy_consumed_kwh, dew_margin_c
- `climate_safety_overrides` — все случаи, когда hard constraint сработал

Ключевая DDL:

```sql
CREATE TABLE climate_advisories (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
  generated_at timestamptz NOT NULL,
  horizon_minutes smallint NOT NULL,
  setpoints jsonb NOT NULL,           -- {temp_c: 22, rh_pct: 65, co2_ppm: 900, ...}
  actuator_plan jsonb NOT NULL,       -- [{actuator_id, action, duty_cycle, duration_min}]
  predicted_energy_kwh double precision,
  predicted_stress_index double precision,
  hard_constraints jsonb,             -- которые учтены
  model_id bigint REFERENCES ml_models(id),
  accepted_by_coordinator boolean,    -- true = coordinator одобрил
  conflict_resolved_with varchar(32), -- 'irrigation'|'energy'|null
  schema_version smallint NOT NULL DEFAULT 1
);
```

## 5. Сервисы

| Сервис | Роль |
|---|---|
| `climate-planner` | Новый. MPC каждые 10 мин, публикует `climate_advisories` |
| `climate-controller` | Новый. Принимает advisory + текущие датчики, генерирует `climate_commands` с rate limiting |
| `zone-coordinator` | Новый (важен!). Арбитр между irrigation+climate+energy. Single source of truth «что делает зона в ближайший час» |
| `automation-engine` | Без изменений — принимает команды по существующему контракту |

## 6. Модели

- **Greenhouse thermal model** — физика: energy balance (solar_in, heat_loss,
  heater_power, ventilation), water balance (transpiration, condensation).
  Параметры калибруются по истории зоны (`scipy.optimize`).
- **MPC solver** — `do-mpc` или `cvxpy` на quadratic cost:
  `min Σ (w1·(T-T_target)² + w2·(RH-RH_target)² + w3·energy + w4·stress)`
- **Predictive VPD** — LightGBM, предсказывает VPD на 2 часа при разных
  управляющих воздействиях.

## 7. Safety-лимиты (non-negotiable)

| Параметр | Хард |
|---|---|
| `leaf_temp - dew_point` | ≥ 2°C всегда (anti-ботритис) |
| `air_temp` | 10 ≤ T ≤ 35 °C (растения выживут) |
| `RH` | 30 ≤ RH ≤ 95% |
| `CO2` | ≤ 1500 ppm (safety для операторов при входе) |
| `setpoint_change_rate` | Δtemp ≤ 2°C/час (thermal shock) |

Хранятся в `automation_config_documents(namespace='system.climate_safety')`.

## 8. Фазы внедрения

| Phase | Задача | DoD |
|---|---|---|
| C0 | Инвентаризация актуаторов в проде (что есть HVAC-wise) | Зона имеет заполненный `hardware_profile.climate` |
| C1 | `climate_setpoints` по фазам рецепта (ручной ввод через UI) | Оператор видит и редактирует целевые значения |
| C2 | `climate-controller` с простыми hysteresis rules | Замена текущей логики без потери функций |
| C3 | `climate-planner` MPC в shadow-режиме | Advisory пишутся, но не исполняются |
| C4 | Калибровка thermal model по истории | RMSE прогноза T через 1ч ≤ 0.5°C |
| C5 | `zone-coordinator` + co-optimization с irrigation | E2E тест: конфликт разрешён корректно |
| C6 | MPC в active на пилотной зоне | 30 дней без hard-constraint violations |

## 9. Интеграция с существующими pipeline'ами

- **Читает** из `ML_FEATURE_PIPELINE.zone_features_5m`: все климат-фичи, VPD,
  CO2, наружка.
- **Пишет** в `ML_FEATURE_PIPELINE.zone_features_5m` (расширение схемой v3):
  `setpoint_temp`, `setpoint_rh`, `climate_stress_index`.
- **Coordinate** с `IRRIGATION_ML_PIPELINE` через `zone-coordinator`:
  - если MPC хочет проветривать → irrigation откладывает на +20 мин
  - если irrigation готовит pre-emptive полив под жару → MPC не закрывает шторы
- **Читает** из `VISION_PIPELINE.plant_visual_features_1h`: если
  `prob_botrytis_max > 0.3` → уменьшить target_rh на 5% авто.

## 10. Правила для ИИ-агентов

### Можно:
- Расширять `climate_setpoints` под новые культуры/фазы.
- Добавлять актуаторы в `climate_actuators` (с проверкой supported в
  `WATER_FLOW_ENGINE.md` для валидаторов).
- Улучшать MPC cost function (с unit-тестами на конвергенцию).

### Нельзя:
- Обходить safety-лимиты §7 через параметры MPC.
- Публиковать `climate_commands` без прохода через `zone-coordinator`.
- Включать CO2-инжекцию без `ppm`-ограничения safety.

## 11. Открытые вопросы

1. Какой MPC-фреймворк: `do-mpc` (академический, медленный) vs `cvxpy`
   (быстрый, quadratic) vs собственный на torch?
2. Horizon MPC: 6 / 12 / 24 часа? Trade-off точность vs compute.
3. Стоит ли иметь IR-камеру на canopy для прямого измерения `leaf_temp`
   (важно для dew_point constraint)? Или считать по wet-bulb approximation?
4. Частота MPC-тиков: 5 / 10 / 15 минут? Медленнее = стабильнее, быстрее =
   реактивнее.

---

# Конец CLIMATE_CONTROL_CHARTER.md
