# DIGITAL_TWIN_SIMULATOR_CHARTER.md
# Паспорт pipeline: симулятор зоны — what-if engine, RL-среда, recipe optimizer

**Статус:** 🟡 CHARTER
**Целевое размещение:** `doc_ai/09_AI_AND_DIGITAL_TWIN/DIGITAL_TWIN_SIMULATOR_CHARTER.md`
**Связанные:** существующий `backend/services/digital-twin/`, `ML_FEATURE_PIPELINE.md`,
`IRRIGATION_ML_PIPELINE.md`, `CLIMATE_CONTROL_CHARTER.md`, `NUTRIENT_BUDGET_CHARTER.md`

---

## 1. Назначение

В проекте уже есть сервис `digital-twin` с простыми `PHModel`/`ECModel`
и фиксированными параметрами. Этот charter превращает его в полноценный
симулятор всей зоны — what-if engine, способный:
- **обучать опасные модели (RL) безопасно**, без риска для живых растений;
- **предсказывать результат изменения рецепта** на 7–30 дней вперёд;
- **воспроизводить инциденты** для отладки;
- **служить средой для Bayesian optimization** рецептов.

## 2. Цели

- Параметры калибруются по фактическим данным конкретной зоны автоматически
  (не фиксированные defaults).
- Один «шаг» симуляции = 5 минут, ресурс ≤ 10 мс на CPU → 1000 симуляций
  / секунда на worker.
- Валидация: симулятор на `dose_response_events` дает ошибку не выше той,
  что у baseline ML-моделей (иначе смысла в нём нет).
- API для любого pipeline'а: «прогнать сценарий (X, настройка Y, период Z),
  вернуть trajectory».

## 3. Ключевые дизайн-решения

1. **Модульная структура**: каждая подсистема — отдельный solver, связаны
   общим time step:
   - `plant_uptake` (pH, EC, отдельные ионы если включён NUTRIENT_BUDGET)
   - `tank_dynamics` (смешивание, испарение, долив)
   - `climate` (если включён CLIMATE_CONTROL — energy/water balance)
   - `substrate` (WC dynamics, drainage)
   - `plant_growth` (canopy area, GDD, stage transitions из YIELD_FORECASTING)
   - `actuators` (насосы, клапаны, HVAC — задержки, noise, износ)
2. **Hybrid physics + ML**: физика (mass balance, Michaelis-Menten, Penman-
   Monteith) + ML-residuals (корректируют систематическое отклонение).
3. **Stochasticity first-class**: каждый параметр имеет distribution, не
   скаляр. Симуляция возвращает confidence интервалы.
4. **Snapshot & replay**: сохраняем состояние в любой момент, можно
   «перезапустить» с корректировкой параметров.
5. **Deterministic mode** (для тестов и RL) + stochastic mode (для
   uncertainty).

## 4. Структура данных

```sql
CREATE TABLE zone_dt_params (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  param_group varchar(32) NOT NULL,      -- 'ph'|'ec'|'tank'|'climate'|'substrate'|'uptake'
  params jsonb NOT NULL,                 -- {buffer_capacity: 0.11, evaporation_k: 0.023, ...}
  calibrated_at timestamptz NOT NULL,
  calibrated_from_range tstzrange NOT NULL,
  calibration_mae jsonb,                 -- MAE по каждой выходной переменной
  n_samples_used integer,
  version smallint NOT NULL DEFAULT 1,
  superseded_at timestamptz,
  UNIQUE (zone_id, param_group, version)
);

CREATE TABLE simulation_runs (
  id bigserial PRIMARY KEY,
  zone_id bigint NOT NULL REFERENCES zones(id),
  created_at timestamptz NOT NULL,
  created_by bigint REFERENCES users(id),
  purpose varchar(32),                   -- 'what_if'|'rl_training'|'incident_replay'|'optimization'
  initial_state jsonb NOT NULL,
  inputs_schedule jsonb,                 -- план actuations/окружения
  duration_hours double precision NOT NULL,
  time_step_seconds integer NOT NULL,
  n_stochastic_samples integer,          -- 1 = deterministic
  status varchar(16) NOT NULL,           -- 'queued'|'running'|'done'|'failed'
  result_summary jsonb,                  -- {final_ph, final_ec, stress_events, ...}
  result_trajectory_uri text,            -- s3://... большой временной ряд
  cost_cpu_seconds double precision
);

CREATE TABLE simulation_scenarios (
  id bigserial PRIMARY KEY,
  name varchar(128) NOT NULL,
  description text,
  scenario_spec jsonb NOT NULL,          -- шаблон для reuse
  created_by bigint REFERENCES users(id),
  is_public boolean DEFAULT false
);
```

## 5. Сервисы

| Сервис | Роль |
|---|---|
| `digital-twin` | Существующий, расширяется: модульный solver, callable API |
| `dt-calibrator` | Новый. Периодически переобучает `zone_dt_params` по новым данным |
| `dt-runner` | Новый worker. Queue `simulation_runs`, исполнение на CPU-пуле |

## 6. API (примерно)

```python
POST /v1/simulate
{
  "zone_id": 12,
  "initial_state": {"ph": 5.9, "ec": 1.8, "wc": 65, "canopy_mm2": 68000, ...},
  "inputs_schedule": [
    {"t_min": 0,   "action": "set_ec_target", "value": 2.0},
    {"t_min": 30,  "action": "dose", "reagent": "npk", "ml": 5.0},
    {"t_min": 120, "action": "irrigation", "volume_ml": 300},
    {"t_min": 0,   "action": "env_series", "series_uri": "s3://forecasts/..."}
  ],
  "duration_hours": 72,
  "n_stochastic_samples": 50
}

→ 201, returns simulation_run_id + websocket URL для progress
```

## 7. Модели

- **Parameter estimation**: scipy.optimize / Bayesian optimization
  (`botorch`) для калибровки по истории. Цель — минимизировать MAE на
  held-out `dose_response_events`.
- **ML residual**: XGBoost учит разницу между симулятором и реальностью,
  добавляется как correction. Когда ML residual маленький — физика работает.
- **Scenario generator**: позже — LLM + prompt для human-friendly
  «симулируй жаркую неделю с перебоями отопления».

## 8. Use cases

1. **RL-training** (самая важная мотивация): обучать агента дозирования или
   полива на симуляторе, переносить в shadow-режим после достижения ревардов
   выше baseline. Без симулятора RL запрещён §12 ML_FEATURE_PIPELINE.
2. **Recipe optimization**: Bayesian optimization над рецептом (EC per phase,
   irrigation targets) → симулятор оценивает 72-часовую траекторию → метрика
   «stress events + overrun» → next sample.
3. **Incident replay**: «в понедельник в зоне 12 произошёл скачок pH; что
   было бы, если бы не дозировали кислоту?» — воспроизвести из
   `telemetry_samples` initial state + убрать команду → сравнить.
4. **Operator training**: оператор видит в UI «если ты сейчас сделаешь X,
   через 24 часа будет Y» — важный explainer для trust.

## 9. Safety

- Симулятор **никогда не отправляет команды в прод-систему**. Это read-only
  сервис.
- Результаты симуляции помечаются `is_simulation=true` в любой таблице,
  куда могут попасть (UI, логи).
- Параметры (`zone_dt_params`) обновляются только автоматически по
  retrospective данным, оператор не должен править вручную (используется
  физ-модель как prior + данные).

## 10. Фазы

| Phase | Задача | DoD |
|---|---|---|
| D0 | Рефакторинг текущего `digital-twin/models.py`: модульные solvers | Unit-тесты на каждый модуль |
| D1 | `zone_dt_params` + calibrator | Параметры заполняются автоматически |
| D2 | `simulation_runs` + runner + API | Можно запустить симуляцию через REST |
| D3 | Валидация: симулятор vs реальность на `dose_response_events` | MAE ≤ baseline ML |
| D4 | ML residual layer | Улучшение MAE на 20% |
| D5 | Scenario library + UI | Оператор запускает what-if |
| D6 | RL-среда + пример обучения | baseline RL-агент выше PID-baseline на симуляторе |

## 11. Интеграция

- Основа для **всех** ML-моделей: хорошая прокся для shadow-режимов.
- Читает параметры/историю из всего `ML_FEATURE_PIPELINE` + `IRRIGATION` +
  `CLIMATE`.
- Возвращает trajectory, которая может подпитывать `EXPLAINABILITY_UX`
  (what-if панель в UI).

## 12. Правила для ИИ-агентов

### Можно:
- Добавлять новые модули (new plant model, new substrate model) с
  unit-тестами.
- Расширять `simulation_scenarios` с сценариями.

### Нельзя:
- Подменять данные в `zone_dt_params` вручную — только через calibrator.
- Использовать симулятор как «альтернативу измерениям» (результат ≠ факт).
- Обучать production ML-модели только на симулированных данных без real
  valication (sim2real gap).

## 13. Открытые вопросы

1. RL-фреймворк: Stable-Baselines3 / CleanRL / RLlib? (влияет на integration
   с симулятором).
2. Какая валюта «реалистичности»: MAE на pH/EC, или задачно-специфичная
   (например yield drift)?
3. Параллельные симуляции — CPU pool на одном узле vs dask cluster?
4. Как отслеживать sim2real drift: периодический replay последних 7 дней
   с метрикой «совпадение» → автотрриггер рекалибровки.

---

# Конец DIGITAL_TWIN_SIMULATOR_CHARTER.md
