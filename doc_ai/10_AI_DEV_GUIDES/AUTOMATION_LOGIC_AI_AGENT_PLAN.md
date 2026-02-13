# AUTOMATION_LOGIC_AI_AGENT_PLAN.md
# План выполнения для ИИ-агента: рефактор логики автоматики (scheduler + automation-engine)

**Дата:** 2026-02-13  
**Статус:** Draft/Active (Refined v1.1)  
**Владелец:** AI Agent (cross-layer)  
**Приоритет:** высокий

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.  
Breaking-change: контракт runtime-логики автоматики обновляется; дублирование recipe-targets в logic-конфиге удаляется.

---

## 1) Цель

Перевести систему на строгую модель:

1. `Recipe` хранит только целевые значения фаз выращивания (targets/limits).
2. `Automation Logic` хранит только операционную логику исполнения:
   - расписания (tick-интервалы, окна);
   - алгоритмы принятия решения `run/skip/retry/fail`;
   - state-machine шагов операций;
   - safety/rate/attempt лимиты;
   - fallback-поведение.

Ключевое правило:
- scheduler только предлагает задачу (`tick`);
- automation-engine принимает решение и исполняет;
- успех только при `DONE` и/или измеряемом подтверждении эффекта.

## 1.1) Границы MVP и вне scope

В scope MVP:
- перенос decision/state-machine логики в `automation-engine`;
- удаление дублей recipe-targets из logic profile;
- унификация outcome-контракта задач;
- добавление недостающих входов (`soil_moisture`, `soil_temp`, `wind_speed`, `outside_temp`).

Вне scope текущего MVP:
- перестройка MQTT namespace;
- изменение ролей/авторизации;
- полный пересмотр UI/UX за пределами конфигуратора логики.

---

## 2) Зафиксированные решения (по итогам обсуждения)

1. Разделение `Recipe` и `Automation Logic` подтверждено.
2. Scheduler отправляет абстрактные задачи, не device-команды.
3. Для drip-полива добавляются ноды/каналы сенсоров почвы:
   - влажность субстрата;
   - температура субстрата.
4. Для климата добавляется наружный датчик скорости ветра.
5. Skip-причины (минимум):
   - уже идёт операция;
   - вне окна;
   - цель достигнута;
   - safety-блок.
6. `low_water` и `nodes_unavailable`:
   - не считаются окончательным skip;
   - создают alerts;
   - запускают retry (до 10 попыток).
7. При online-коррекции порядок дозирования:
   - сначала `EC`, затем `pH`.
8. При недостижении корректного раствора во время полива:
   - остановить полив;
   - переключить контур на коррекцию “бак -> бак”;
   - выполнить отдельную логику коррекции.
9. Смена раствора поддерживает триггеры:
   - по расписанию;
   - по событию;
   - вручную.
10. Для топологий `2 бака` и `3 бака` нужны разные state-machine.
11. Если внешние climate-ноды недоступны:
   - fallback: только логирование (без активного открытия/вентиляции по ним).
12. Итог задачи должен содержать расширенный контроль:
   - `decision`, `reason_code`, `action_required`, `executed_steps`, `safety_flags`, `next_due_at`, и др.
13. Шаги state-machine в event-хранилище сохраняются агрегированным summary.

---

## 3) Канонические типы задач (scheduler -> automation-engine)

1. `irrigation_tick`
   - проверка необходимости полива;
   - решение `run/skip`;
   - при `run`: полив + online EC/pH коррекция + контроль эффекта.
2. `solution_prepare_tick`
   - подготовка рабочего раствора до recipe-targets.
3. `solution_change_tick`
   - смена раствора (включая опциональную промывку по флагу).
4. `climate_tick`
   - управление вентиляцией/форточками с учётом внешних ограничений.
5. `lighting_tick`
   - управление светом по окнам/интервалам.
6. `diagnostics_tick`
   - проверка готовности контуров и узлов.
7. `safety_tick`
   - контроль safety-ограничений и блокировок.

## 3.1) Переходная совместимость task_type (обязательное правило rollout)

Чтобы избежать скрытого breaking-change в transport-контракте, вводится 2 уровня именования:

1. Канонические доменные имена (в документации логики):
   - `irrigation_tick`, `solution_prepare_tick`, `solution_change_tick`, `climate_tick`, `lighting_tick`, `diagnostics_tick`, `safety_tick`.
2. Транспортные имена (scheduler/automation API v1, текущий runtime):
   - `irrigation`, `solution_change`, `ventilation`, `lighting`, `diagnostics`, `mist`.

Правило на MVP:
- до явного апдейта transport-контракта использовать текущие транспортные имена в runtime;
- в документации/коде рядом указывать доменный alias;
- добавление новых transport task-types (`solution_prepare`, `safety`) делать отдельным этапом с обновлением:
  - `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`;
  - `backend/services/scheduler/main.py` (`SUPPORTED_TASK_TYPES`);
  - `backend/services/automation-engine/*` (executor + tests).

---

## 4) Контракт данных: что хранится где

## 4.1 Recipe (источник целей)
- `ph/ec/temp/humidity/light` targets;
- лимиты и допустимые диапазоны;
- фазовые окна/расписания, относящиеся к агрономической цели.

## 4.2 Automation Logic Profile (источник поведения)
- интервалы и окна tick-задач;
- алгоритмы decision-layer;
- retry/backoff/attempt limits;
- safety thresholds;
- execution-state параметры (таймауты, max_steps, fail-conditions);
- режимы `setup|working`.

Запрет:
- targets из recipe не должны дублироваться в automation logic profile.

## 4.3 Минимальная структура Automation Logic Profile (MVP v1)

```json
{
  "mode": "setup",
  "subsystems": {
    "irrigation": {
      "enabled": true,
      "tick": {"interval_sec": 900, "window": {"start": "06:00", "end": "22:00"}},
      "decision": {"reduced_run_ratio": 0.3, "max_retry": 10, "backoff_sec": 60},
      "safety": {"max_daily_cycles": 24, "low_water_block": true},
      "execution": {"max_steps": 20, "step_timeout_sec": 120}
    },
    "climate": {
      "enabled": true,
      "tick": {"interval_sec": 300},
      "limits": {"strong_wind_mps": 10.0, "low_outside_temp_c": 8.0}
    }
  }
}
```

Ограничение:
- значения `targets.*` (например `ph.target`, `ec.target`) в этом профиле отсутствуют.

---

## 5) Требования к алгоритмам (MVP v1)

## 5.1 Drip irrigation decision
Вход:
- recipe targets (через effective-targets);
- soil moisture/temp;
- ambient temp;
- состояние контуров и safety.

Базовые правила:
1. Норма влажности (временный дефолт): `80% ±10%`.
2. Если влажность `ok` и нет жара -> `skip`.
3. Если влажность `ok`, но высокая температура -> `run_reduced` (30% базовой дозы).
4. Если влажность ниже нормы -> `run_full`.
5. Если `low_water`/`nodes_unavailable` -> alert + retry (до 10 попыток).

## 5.2 Полив и коррекция
1. До старта проверить наличие раствора в баке (уровень).
2. Во время полива:
   - online коррекция по проточному узлу;
   - порядок: EC -> pH;
   - PID-регуляторы обязательны.
3. Если корректировка неуспешна:
   - аварийно остановить полив;
   - запустить баковую коррекцию (контур рециркуляции в бак);
   - зафиксировать outcome как `failed/recovered`.

## 5.3 Solution prepare/change
1. Готовность раствора: соответствие recipe-targets.
2. Смена раствора:
   - триггеры: schedule/event/manual;
   - промывка опциональна (флаг с фронта);
   - завершение этапов по датчикам уровня.
3. Для `2 баков` и `3 баков` использовать разные state-machine.

## 5.4 Climate
1. Решение только в automation-engine по `climate_tick`.
2. Ограничения:
   - сильный ветер -> форточки не открывать;
   - низкая наружная температура -> форточки не открывать и вентиляцию не включать.
3. Пороги ветра/температуры настраиваются в automation profile.

## 5.5 Канонический decision/outcome словарь (MVP минимум)

`decision`:
- `run`
- `skip`
- `retry`
- `fail`

`reason_code` (минимум для валидации и UI):
- `already_running`
- `outside_window`
- `target_already_met`
- `safety_blocked`
- `nodes_unavailable`
- `low_water`
- `online_correction_failed`
- `tank_to_tank_correction_started`
- `wind_blocked`
- `outside_temp_blocked`

Правило:
- любые новые `reason_code` добавлять одновременно в backend словарь, frontend labels и тесты API/UI.

## 5.6 Подсистема Startup/Prepare/Irrigation для топологии `2 бака` (зафиксировано)

Целевой тип системы выращивания:
- `капельная`;
- `субстрат в лотках`;
- runtime-идентификатор топологии: `two_tank_drip_substrate_trays`.

Состав оборудования (одна нода управления контуром):
- датчики уровня: `clean_min`, `clean_max`, `solution_min`, `solution_max`;
- клапаны: набор чистой воды, забор чистой воды, набор раствора, забор раствора, полив;
- исполнитель: главный насос;
- узел коррекции EC/pH в линии потока.

Обязательное правило:
- одна нода обслуживает полный цикл `startup -> prepare -> irrigation -> recovery`.

### 5.6.1 State-machine (канонический порядок)

1. `STARTUP_CHECK_CLEAN_TANK`
   - проверка `clean_max`;
   - если `clean_max=1` -> `PREPARE_FILL_SOLUTION`;
   - если `clean_max=0` -> `CLEAN_FILL_START`.
2. `CLEAN_FILL_START`
   - automation-engine отправляет команду на наполнение чистого бака;
   - нода открывает клапан набора чистой воды;
   - при `clean_max=1` нода обязана сама остановить наполнение и отправить подтверждение в backend.
3. `CLEAN_FILL_WAIT`
   - параллельно:
     - ожидание события от ноды "чистый бак наполнен";
     - периодический poll состояния через scheduler self-task.
   - интервал poll по умолчанию: `60 сек` (настраивается во frontend).
   - таймаут цикла: `20 мин` (настраивается во frontend).
   - допускается ещё 1 цикл retry; далее `fail + alert + stop`.
4. `PREPARE_FILL_SOLUTION`
   - открыть клапан забора чистой воды + клапан набора раствора;
   - включить главный насос;
   - поток проходит через узел коррекции.
5. `PREPARE_CORRECTION_ONLINE`
   - пока заполняется бак раствора, выполнять только `EC(NPK)` и `pH`;
   - целевой `EC_prepare_npk = EC_target_recipe * nutrient_npk_ratio_pct / 100`.
6. `PREPARE_WAIT_SOLUTION_MAX`
   - ожидать `solution_max=1` по схеме poll + событие от ноды;
   - интервал poll: `60 сек`;
   - таймаут цикла: `30 мин` (настраивается во frontend).
7. `PREPARE_RECIRC_NPK_PH_FALLBACK`
   - если бак раствора уже полный, но цель не достигнута:
     - остановить наполнение из чистого бака;
     - открыть клапан забора раствора + клапан набора раствора;
     - включить насос и рециркулировать через узел коррекции;
     - корректировать только `NPK + pH` до достижения цели или таймаута (`20 мин`).
8. `IRRIGATION_RUN`
   - открыть клапан забора раствора + клапан полива;
   - включить насос;
   - параллельно online-коррекция:
     - `EC`: только `calcium + magnesium + micro` (без `NPK`);
     - затем финальная коррекция `pH`.
9. `IRRIGATION_RECOVERY_RECIRC`
   - если online-коррекция в поливе неуспешна:
     - остановить полив;
     - запустить рециркуляцию раствора в баке;
     - коррекция только `calcium + magnesium + micro + pH`;
     - максимум `5` попыток продолжить полив, затем `fail + alert + stop`.
10. `DEGRADED_TOLERANCE_MODE`
    - допускается завершение с отклонением, если цели недостижимы в лимитах времени:
      - `EC`: `+-20%` от целевого;
      - `pH`: `+-10%` от целевого.

### 5.6.2 Поведение ноды и automation-engine

1. Нода:
   - обязана локально остановить наполнение по датчику `*_max`;
   - обязана отправить событие о завершении наполнения;
   - обязана публиковать текущий snapshot состояний датчиков уровня и клапанов.
2. Automation-engine:
   - запускает workflow startup;
   - отправляет команду старта наполнения;
   - периодически проверяет состояние через scheduler self-task (`+1 мин`);
   - одновременно обрабатывает асинхронные сообщения ноды о завершении.

### 5.6.3 Минимальные reason/error коды для `2 бака`

`reason_code`:
- `clean_fill_started`
- `clean_fill_completed`
- `clean_fill_timeout`
- `clean_fill_retry_started`
- `solution_fill_started`
- `solution_fill_completed`
- `solution_fill_timeout`
- `prepare_recirculation_started`
- `prepare_targets_reached`
- `prepare_targets_not_reached`
- `irrigation_started`
- `online_correction_failed`
- `tank_to_tank_correction_started`
- `irrigation_recovery_started`
- `irrigation_recovery_recovered`
- `irrigation_recovery_failed`
- `sensor_stuck_detected`
- `sensor_failure_detected`

`error_code`:
- `clean_tank_not_filled_timeout`
- `solution_tank_not_filled_timeout`
- `level_sensor_stuck`
- `level_sensor_fault`
- `prepare_npk_ph_target_not_reached`
- `irrigation_online_correction_failed`
- `irrigation_recovery_attempts_exceeded`

### 5.6.4 Ручной override (обязательная поддержка)

Операторские действия:
- `fill_clean_tank`
- `prepare_solution`
- `recirculate_solution`
- `resume_irrigation`

Правила:
1. Каждое действие пишет `zone_event` с `manual_action`.
2. Каждое действие создаёт lifecycle snapshot в scheduler/automation task-логах.
3. Ручной override не отключает safety-проверки датчиков уровня и блокировок.

---

## 6) Новые ноды/каналы (обязательный минимум)

1. `soil_sensor` (или канонический type + metric map)
   - `soil_moisture`
   - `soil_temp`
2. `weather_sensor`
   - `wind_speed`
   - `outside_temp` (если отсутствует в текущем внешнем канале)

Требование:
- добавить канонические node/channel описания в спецификации и обработчики ingestion.

---

## 7) Frontend: конфигуратор логики

Цель:
- единый конфигуратор в `Zone Automation` и в `Setup Wizard`.

Настраиваемые блоки:
1. Tick-интервалы и окна задач.
2. Алгоритмы decision-layer:
   - skip/run rules;
   - reduced-run policy (30%);
   - retry/backoff policy (10 attempts).
3. Safety thresholds.
4. Параметры solution prepare/change, включая флаг промывки.
5. Внешние climate-ограничения (ветер/температура).
6. PID-настройки (или профиль PID).

Запрет:
- target-поля recipe не редактируются в логике автоматики.

---

## 8) API/Contracts (целевое состояние)

1. `POST /api/zones/{zone}/automation-logic-profile`
   - сохраняет только behavior config;
   - `mode=setup|working`.
2. `POST /api/zones/{zone}/commands type=GROWTH_CYCLE_CONFIG`
   - содержит `profile_mode`;
   - не содержит recipe-target дубликатов.
3. Internal `effective-targets`:
   - recipe targets + runtime behavior extensions;
   - явное разделение `targets` и `execution/logic`.
4. Scheduler task result:
   - обязательные поля контроля:
     - `decision`
     - `reason_code`
     - `action_required`
     - `executed_steps`
     - `safety_flags`
     - `next_due_at`
     - `measurements_before_after`
     - `commands_effect_confirmed`
     - `error_code` (если есть)

## 8.1 Минимальный transport-контракт scheduler-task (MVP v1)

Request (`POST /scheduler/task`, transport v1):

```json
{
  "zone_id": 28,
  "task_type": "irrigation",
  "scheduled_for": "2026-02-13T10:00:00Z",
  "due_at": "2026-02-13T10:00:15Z",
  "expires_at": "2026-02-13T10:02:00Z",
  "correlation_id": "sch:z28:irrigation:2026-02-13T10:00:00Z",
  "payload": {
    "logic_alias": "irrigation_tick",
    "trigger_time": "2026-02-13T10:00:00Z",
    "targets": {},
    "config": {}
  }
}
```

Terminal result (`GET /scheduler/task/{task_id}`):

```json
{
  "status": "ok",
  "data": {
    "task_id": "st-001",
    "zone_id": 28,
    "task_type": "irrigation",
    "status": "completed",
    "result": {
      "decision": "skip",
      "reason_code": "target_already_met",
      "action_required": false,
      "executed_steps": [],
      "safety_flags": [],
      "next_due_at": "2026-02-13T10:15:00Z",
      "measurements_before_after": {},
      "commands_effect_confirmed": 0
    },
    "error_code": null
  }
}
```

Инварианты:
- `correlation_id`, `due_at`, `expires_at` обязательны;
- `completed` допускается при `action_required=false` (осознанный `skip`);
- `timeout|not_found` — transport деградация scheduler, не decision automation-layer.

---

## 9) План работ по этапам (для ИИ-агента)

### Этап A0: Спецификация и freeze контрактов
- Scope:
  - `doc_ai/04_BACKEND_CORE`, `doc_ai/05_DATA_AND_STORAGE`, `doc_ai/06_DOMAIN_ZONES_RECIPES`.
- Changes:
  - зафиксировать новые task types, state-machine, payload/response схемы.
- Checks:
  - consistency review между doc-и кодом.
- Gate:
  - согласованные спецификации без противоречий.
- Deliverables:
  - обновлённые разделы контрактов в `doc_ai/04_BACKEND_CORE/*`;
  - таблица маппинга `*_tick -> transport task_type` в документации.
- Checks (минимум):
  - документированный diff без конфликтов терминов `tick`/transport.

### Этап A1: Модель данных и миграции
- Scope:
  - Laravel migrations/models + data reference.
- Changes:
  - структуры для behavior-конфига, retry/safety/pid параметров.
- Checks:
  - миграции up/down, feature tests.
- Gate:
  - схема применима и обратима.
- Deliverables:
  - миграции Laravel для runtime-полей logic profile (без recipe-target дублей);
  - обновлённый `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.
- Checks (минимум):
  - `php artisan migrate --pretend`;
  - feature-тесты профиля логики.

### Этап A2: Backend API и effective-targets merge
- Scope:
  - Laravel services/controllers/requests.
- Changes:
  - удалить дубли recipe-targets из logic-профиля;
  - merge behavior в execution-ветки.
- Checks:
  - unit/feature tests.
- Gate:
  - контракт API стабилен.
- Deliverables:
  - request/response валидация для `automation-logic-profile`;
  - merge runtime behavior в `effective-targets` без target-дублей.
- Checks (минимум):
  - feature-тесты `ZoneAutomationLogicProfileController`;
  - feature-тесты `/api/internal/effective-targets/batch`.

### Этап A3: Scheduler planner-only update
- Scope:
  - `backend/services/scheduler/*`.
- Changes:
  - dispatch только абстрактных scheduler-task intent (без device-level команд).
- Checks:
  - pytest scheduler.
- Gate:
  - нет device-level dispatch из scheduler.
- Deliverables:
  - scheduler dispatch только abstract task intent;
  - фиксированная owner-модель статусов (`business` vs `transport`).
- Checks (минимум):
  - `pytest -q backend/services/scheduler/test_main.py`.

### Этап A4: Automation-engine decision/state-machine
- Scope:
  - `backend/services/automation-engine/*`.
- Changes:
  - decision-layer, state-machine 2/3 tanks, retry policy, PID integration.
- Checks:
  - unit/integration pytest + summary outcomes.
- Gate:
  - DONE/measure-based success semantics соблюдены.
- Deliverables:
  - decision-layer `run/skip/retry/fail`;
  - state-machine для `2 бака` и `3 бака`;
  - workflow `startup/prepare/irrigation/recovery` для одной ноды в `2 бака`;
  - summary outcome с обязательными полями.
- Checks (минимум):
  - `pytest -q backend/services/automation-engine/test_scheduler_task_executor.py`;
  - `pytest -q backend/services/automation-engine/test_api.py`.

### Этап A5: Frontend configurator unification
- Scope:
  - Zone tab + Setup wizard.
- Changes:
  - единый конфигуратор;
  - убрать редактирование recipe-targets в logic UI.
- Checks:
  - typecheck + vitest.
- Gate:
  - идентичный behavior-config UI в двух местах.
- Deliverables:
  - единая форма/типизация профиля логики для Zone tab и Setup wizard;
  - запрет редактирования recipe-targets в logic UI.
- Checks (минимум):
  - `npm run typecheck`;
  - `npm run test -- setup wizard zone automation`.

### Этап A6: Ноды/каналы и ingestion
- Scope:
  - node registry, history-logger ingestion, docs.
- Changes:
  - новые node/channel типы и обработчики.
- Checks:
  - ingestion tests + smoke telemetry.
- Gate:
  - automation-engine получает валидные входы от новых датчиков.
- Deliverables:
  - канонические описания node/channel для `soil_sensor` и `weather_sensor`;
  - ingestion mapping и запись в telemetry-таблицы.
- Checks (минимум):
  - pytest history-logger ingestion;
  - smoke проверка наличия данных в `telemetry_samples` и `telemetry_last`.

### Этап A7: E2E и наблюдаемость
- Scope:
  - e2e scenarios + alerts + dashboards.
- Changes:
  - сценарии полива/коррекции/смены/климата;
  - алерты и summary логирование.
- Checks:
  - e2e pass.
- Gate:
  - воспроизводимость в dev/staging.
- Deliverables:
  - e2e сценарии `run/skip/retry/fail`;
  - dashboard/alerts для ключевых reason/error кодов.
- Checks (минимум):
  - e2e pass для сценариев полива, коррекции, климата, смены раствора;
  - проверка timeline/outcome полей в API зоны.

---

## 10) Критерии приёмки

1. В logic profile нет дублей recipe-targets.
2. Scheduler dispatch-ит только абстрактные scheduler-task intent (без device-level команд).
3. Automation-engine принимает decision `run/skip/retry/fail` на основе правил.
4. Для drip учитываются `soil_moisture + soil_temp + ambient_temp`.
5. `low_water`/`nodes_unavailable` -> alerts + retry<=10.
6. Online коррекция в поливе: EC->pH.
7. При неуспехе online коррекции полив останавливается и запускается баковая коррекция.
8. Отдельные state-machine для `2 баков` и `3 баков`.
9. Climate учитывает `wind_speed` и `outside_temp` ограничения.
10. Task outcome содержит расширенный summary-контракт.
11. Для `2 баков`: startup использует `clean_max` с локальным auto-stop наполнения на ноде.
12. Для `2 баков`: проверка наполнения идёт и по событию от ноды, и по poll self-task каждые `60 сек`.
13. Для `2 баков`: таймауты настраиваются с фронта (`20 мин` чистый бак, `30 мин` бак раствора).
14. Для `2 баков`: prepare-коррекция только `NPK + pH`, а при поливе `calcium + magnesium + micro + pH`.
15. При недостижении целей допускается degraded mode в рамках `EC +-20%`, `pH +-10%`.

---

## 11) Открытые вопросы (актуальный остаток до production)

1. PID-коэффициенты по умолчанию для каждого подрежима:
   - `prepare(NPK+pH)`,
   - `irrigation(Ca/Mg/Micro+pH)`,
   - `recovery recirculation`.
2. Формальная детекция "залипания" датчика уровня:
   - порог по времени,
   - порог по числу одинаковых измерений,
   - реакция на флаппинг.
3. Финальная формула расчёта целевого EC по долям компонента:
   - подтверждение коэффициентов пересчёта для NPK/Ca/Mg/Micro.

Примечание:
- до закрытия пунктов использовать временные дефолты и обязательный feature-flag rollout.

## 11.1 Временные дефолты до решения открытых вопросов

1. `high_temperature_c`: `30.0`.
2. `strong_wind_mps`: `10.0`.
3. `low_outside_temperature_c`: `8.0`.
4. `reduced_irrigation_ratio`: `0.30`.
5. `retry_max_attempts`: `10`, `retry_backoff_sec`: `60`.
6. PID defaults (временные):
   - online: `kp=0.40`, `ki=0.05`, `kd=0.02`;
   - tank-to-tank: `kp=0.55`, `ki=0.08`, `kd=0.03`.
7. `clean_fill_timeout_sec`: `1200` (`20 мин`).
8. `solution_fill_timeout_sec`: `1800` (`30 мин`).
9. `level_poll_interval_sec`: `60`.
10. `irrigation_recovery_max_attempts`: `5`.
11. `prepare_recirculation_timeout_sec`: `1200` (`20 мин`).
12. `degraded_tolerance`:
    - `ec_pct`: `20`,
    - `ph_pct`: `10`.

Ограничение:
- эти значения разрешены только под feature-flag и должны быть вынесены в профиль логики.

## 11.2 Feature-flag matrix (обязателен для безопасного rollout)

1. `AUTO_LOGIC_DECISION_V1`
   - включает decision-layer `run/skip/retry/fail`.
2. `AUTO_LOGIC_TANK_STATE_MACHINE_V1`
   - включает state-machine `2 бака/3 бака`.
3. `AUTO_LOGIC_CLIMATE_GUARDS_V1`
   - включает ветровые/температурные climate-блоки.
4. `AUTO_LOGIC_NEW_SENSORS_V1`
   - включает использование `soil_*` и `weather_*` входов.
5. `AUTO_LOGIC_EXTENDED_OUTCOME_V1`
   - включает обязательный расширенный summary в task result.

---

## 12) Формат отчёта ИИ-агента по каждому этапу

1. `Scope`
2. `Changes`
3. `Checks`
4. `Gate`
5. `Risks/Assumptions`
6. `Rollback`

---

## 13) Порядок rollout по средам

1. Dev:
   - включить все `AUTO_LOGIC_*_V1`;
   - стабилизировать unit/integration/e2e;
   - зафиксировать baseline метрик skip/retry/fail.
2. Staging:
   - включать флаги по одному (decision -> outcome -> sensors -> climate -> state-machine);
   - держать откат через выключение последнего включенного флага.
3. Production:
   - включение по зонам (canary);
   - мониторить алерты `low_water`, `nodes_unavailable`, `command_effect_not_confirmed`;
   - при деградации: откат флагов в обратном порядке без rollback схемы БД.
