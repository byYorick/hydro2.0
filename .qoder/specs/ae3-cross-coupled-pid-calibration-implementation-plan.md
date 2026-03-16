# AE3 Cross-Coupled PID And Calibration Delta Plan

**Дата:** 2026-03-07  
**Статус:** Audit-Driven Rewrite  
**Область:** AE3 runtime core, Laravel/data contracts, post-core autotune/HIL

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Переписать план внедрения phase-aware cross-coupled коррекции не как greenfield redesign, а как
расширение уже существующего AE3 runtime.

Документ фиксирует:

- что в AE3 уже существует и считается входным контрактом;
- какие именно изменения допустимы в runtime core;
- какие schema/API изменения нужны для production enablement;
- какие deliverables относятся только к post-core roadmap и не блокируют initial merge.

## Неподвижные архитектурные инварианты

1. Protected command pipeline не меняется:
   `Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`.
2. Прямой MQTT publish из Laravel и AE3 запрещён.
3. Новый control layer встраивается в существующий AE3 correction sub-machine, а не создаёт второй runtime path.
4. Любые изменения БД выполняются только через Laravel migrations.
5. Runtime path остаётся на direct SQL read-model; новые runtime HTTP-зависимости не добавляются.
6. Новых внешних ingress/API для запуска correction runtime не вводится.
7. Phase-aware policy для EC хранится в одном месте:
   `diagnostics.execution.correction.ec_component_policy`.
8. Новые MQTT/history-logger контракты этим планом не вводятся.

## 1. Роль документа

Это не full rewrite AE3 и не параллельная архитектура PID-контроллеров.

Это roadmap расширения существующей correction architecture AE3 до:

- in-flow correction с transport delay и settle window;
- cross-coupled decision model `EC <-> pH`;
- phase-aware allocator для EC компонентов;
- persistent runtime state для hold/feedforward/no-effect;
- fail-closed safety guards;
- production-готовых Laravel/data contracts.

## 2. Baseline As-Is

Ниже перечислено то, что уже есть в репозитории и считается входным контрактом, а не deliverable.

### 2.1 AE3 runtime foundation

- `WorkflowRouter` уже исполняет correction как sub-machine внутри основного workflow.
- `CorrectionState` уже является persisted runtime state для шага коррекции.
- `CorrectionHandler` уже реализует correction lifecycle:
  `corr_activate -> corr_wait_stable -> corr_check -> corr_dose_* -> corr_wait_* -> corr_deactivate`.
- `CorrectionPlanner` уже строит rule-based dose plan поверх resolved actuators и pump calibration.
- `ZoneSnapshot` и `PgZoneSnapshotReadModel` уже загружают `pid_state`, `zone_pid_configs`,
  `pump_calibrations`, `targets`, `diagnostics_execution` и actuator bindings.

### 2.2 Существующие data contracts

- `pump_calibrations` уже существует и содержит базовую калибровку насоса, validity window,
  quality metadata и backfill из legacy `node_channels.config`.
- `zone_pid_configs` уже существует и используется Laravel/API и runtime read-model.
- `pid_state` уже существует и хранит per-controller runtime state:
  `integral`, `prev_error`, `prev_derivative`, `last_output_ms`, `last_dose_at`, `stats`.

### 2.3 Существующие Laravel/API contracts

- Уже есть API для PID config:
  `GET /api/zones/{zone}/pid-configs`,
  `GET /api/zones/{zone}/pid-configs/{type}`,
  `PUT /api/zones/{zone}/pid-configs/{type}`.
- Уже есть API для pump calibrations:
  `GET /api/zones/{zone}/pump-calibrations`,
  `PUT /api/zones/{zone}/pump-calibrations/{channelId}`.
- Уже есть relay-autotune proxy path в Laravel.

### 2.4 Следствие для нового плана

Новый PID/cross-coupling слой обязан расширять следующие canonical integration points:

- `backend/services/automation-engine/ae3lite/application/handlers/correction.py`
- `backend/services/automation-engine/ae3lite/domain/services/correction_planner.py`
- `backend/services/automation-engine/ae3lite/infrastructure/read_models/zone_snapshot_read_model.py`

Greenfield формулировки вида `создать correction runtime`, `создать pump calibration API`,
`создать pid state` считаются ошибочными и в этом документе не используются.

## 3. Delta Scope v1.1 Runtime Core

Этот трек описывает только runtime-логику, без Laravel admin UI и без autotune/HIL.

### 3.1 Что входит в runtime core

1. Cross-coupled decision model поверх существующего `CorrectionHandler`.
2. Process calibration model для in-flow response:
   primary gain, cross-coupling gain, transport delay, settle window.
3. Phase-aware EC allocator:
   `solution_fill` и `tank_recirc` используют только `npk`;
   `irrigating` и `irrig_recirc` используют shares из `ec_component_policy`.
4. Hold/settle semantics:
   после каждой дозы controller выставляет `hold_until` и не принимает новую correction decision до завершения окна.
5. Persistent runtime state:
   hold/feedforward/no-effect bookkeeping переживает следующий tick и restart runtime.
6. Safety layer:
   anti-windup, stale telemetry guard, no-effect detection, overshoot/hard-bounds fail-closed.

### 3.2 Что не входит в runtime core merge

- новый ingress для запуска runtime;
- новые MQTT contracts;
- relay-autotune как обязательная часть control-core;
- test node physics model;
- deterministic HIL/e2e infrastructure;
- staged real-hardware rollout automation.

### 3.3 Runtime implementation policy

1. Existing `CorrectionState` остаётся canonical foundation.
2. Existing `CorrectionHandler` остаётся точкой orchestration correction cycle.
3. Existing `CorrectionPlanner` не удаляется, а преобразуется в decision/allocator layer:
   сначала `cross-coupled decision`, затем `dose allocation`, затем `command emission`.
4. Второй параллельный controller runtime, независимый от correction sub-machine, запрещён.
5. Existing stage-managed sensor mode semantics должны сохраниться без регрессии.

## 4. Data And Interface Contracts

В этом разделе фиксируются только допустимые и выбранные контракты. Формулировки
`при необходимости` и `или` запрещены.

### 4.1 `pump_calibrations`

Таблица не создаётся заново, а расширяется аддитивно.

Новые поля:

- `mode` `varchar(32)` — calibration profile mode (`solution_fill`, `tank_recirc`, `irrigating`, `irrig_recirc`, `generic`)
- `min_effective_ml` `numeric(12,3)` — минимальная доза с гарантированным физическим эффектом
- `transport_delay_sec` `integer` — ожидаемая задержка от дозы до наблюдаемого отклика
- `deadtime_sec` `integer` — технологическая deadtime для коротких импульсов
- `curve_points` `jsonb` — нелинейная dose curve для short-pulse/nonlinear поведения

Уже существующие поля сохраняют canonical смысл:

- `valid_from` / `valid_to` — единственное validity window; новый `expires_at` не вводится
- `quality_score`
- `sample_count`

Резолв профиля в runtime:

1. exact `mode`
2. fallback `generic`
3. fail-closed, если calibration обязательна, но profile не найден

### 4.2 `zone_process_calibrations`

Вводится новая таблица для process-level calibration, не заменяющая `pump_calibrations`.

Минимальный контракт:

- `id`
- `zone_id`
- `mode`
- `ec_gain_per_ml`
- `ph_up_gain_per_ml`
- `ph_down_gain_per_ml`
- `ph_per_ec_ml`
- `ec_per_ph_ml`
- `transport_delay_sec`
- `settle_sec`
- `confidence`
- `source`
- `valid_from`
- `valid_to`
- `is_active`
- `meta`
- `created_at`
- `updated_at`

Резолв в runtime:

1. active calibration by `zone_id + mode`
2. fallback `zone_id + generic`
3. иначе fail-closed для нового cross-coupled controller path

### 4.3 `pid_state`

Таблица расширяется аддитивно; existing rows и existing semantics сохраняются.

Новые поля:

- `hold_until` `timestampTz nullable`
- `last_measurement_at` `timestampTz nullable`
- `last_measured_value` `float nullable`
- `feedforward_bias` `float default 0.0`
- `no_effect_count` `unsignedInteger default 0`
- `last_correction_kind` `varchar(32) nullable`

Назначение:

- `hold_until` блокирует раннюю коррекцию;
- `last_measurement_at` и `last_measured_value` дают wall-clock state для restart recovery;
- `feedforward_bias` хранит cross-coupling feedforward;
- `no_effect_count` используется safety layer;
- `last_correction_kind` хранит тип последнего воздействия (`ec`, `ph_up`, `ph_down`).

Поле `stats` остаётся для non-critical diagnostic counters и не используется как единственный runtime contract
для safety-critical логики.

### 4.4 `zone_pid_configs.config`

JSON contract расширяется, а не создаётся заново.

Для `ph` обязательна поддержка разделов:

- `controller.mode = "cross_coupled_pi_d"`
- `controller.kp`
- `controller.ki`
- `controller.kd`
- `controller.deadband`
- `controller.max_dose_ml`
- `controller.min_interval_sec`
- `controller.max_integral`
- `controller.anti_windup`
- `controller.overshoot_guard`
- `controller.no_effect`

Для `ec` обязательна поддержка разделов:

- `controller.mode = "supervisory_allocator"`
- `controller.kp`
- `controller.ki`
- `controller.deadband`
- `controller.max_dose_ml`
- `controller.min_interval_sec`
- `controller.max_integral`
- `controller.anti_windup`
- `controller.overshoot_guard`
- `controller.no_effect`

Controller config хранит только controller tuning и guards.
Физические gains и transport behavior хранятся только в `zone_process_calibrations`.

### 4.5 `ec_component_policy`

Единственный допустимый источник policy:

`diagnostics.execution.correction.ec_component_policy`

Политика приходит в runtime через существующую цепочку:

`EffectiveTargetsService -> diagnostics.execution -> SQL read-model parity -> ZoneSnapshot`

Формат policy:

```json
{
  "ec_component_policy": {
    "solution_fill": { "npk": 1.0, "calcium": 0.0, "magnesium": 0.0, "micro": 0.0 },
    "tank_recirc":   { "npk": 1.0, "calcium": 0.0, "magnesium": 0.0, "micro": 0.0 },
    "irrigating":    { "npk": 0.0, "calcium": 0.45, "magnesium": 0.25, "micro": 0.30 },
    "irrig_recirc":  { "npk": 0.0, "calcium": 0.45, "magnesium": 0.25, "micro": 0.30 }
  }
}
```

Правила валидации:

1. Для каждой фазы все доли неотрицательны.
2. Сумма долей по фазе равна `1.0`.
3. Для `solution_fill` и `tank_recirc` разрешён только `npk`.
4. Если доля компонента больше нуля, должны существовать:
   active binding, actuator channel, compatible pump calibration.
5. SQL overrides, если нужны, используют тот же dotted path:
   `diagnostics.execution.correction.ec_component_policy.*`.

## 5. Runtime Core Deliverables

### 5.1 Process response model

Добавляется process calibration/domain layer поверх existing correction runtime:

- prediction after EC dose;
- prediction after pH dose;
- cross-coupling estimate `ec -> ph`;
- cross-coupling estimate `ph -> ec`;
- runtime computation of `hold_until = now + transport_delay + settle_window`.

### 5.2 Cross-coupled decision engine

`CorrectionPlanner` расширяется до следующей последовательности:

1. загрузить актуальные telemetry, controller config, process calibration, pump calibration, policy;
2. проверить stale/fail-closed guards;
3. вычислить primary error;
4. учесть cross-coupling feedforward от последнего воздействия;
5. принять одно решение на текущий tick:
   `none | dose_ec_component | dose_ph_up | dose_ph_down`;
6. передать решение в allocator;
7. получить конкретный `PlannedCommand` и persistent state update.

Одновременная выдача двух независимых correction actions в одном tick запрещена.

### 5.3 Phase-aware EC allocator

Allocator обязан:

1. принимать только одну requested EC correction amount;
2. разворачивать её в один component-specific command по active phase policy;
3. использовать только `npk` в `solution_fill` и `tank_recirc`;
4. использовать configured phase shares в `irrigating` и `irrig_recirc`;
5. fail-closed, если policy требует компонент без active binding/calibration.

### 5.4 Hold and persistence

После каждой дозы runtime обязан:

1. сохранить `hold_until` в `pid_state`;
2. сохранить `last_correction_kind`, `feedforward_bias`, `last_dose_at`;
3. не выполнять повторное correction decision до завершения hold window;
4. после restart восстановить состояние из persisted `pid_state`, а не из in-memory fallback.

### 5.5 Safety behavior

Обязательные guards:

1. `stale telemetry guard`
2. `anti-windup`
3. `no-effect detector`
4. `overshoot / hard-bounds guard`
5. `missing calibration/policy/binding fail-closed`

Поведение:

- stale telemetry не участвует в control decision;
- repeated no-effect increments `no_effect_count`;
- превышение порога no-effect переводит correction path в fail-closed error;
- выход за hard bounds завершает correction с ошибкой и zone event;
- low-confidence или missing calibration блокирует новый controller path.

## 6. Laravel/Admin Track

Этот трек обязателен до production enablement, но не определяет структуру runtime core.

### 6.1 PID config API

Расширяется existing API:

- `GET /api/zones/{zone}/pid-configs`
- `GET /api/zones/{zone}/pid-configs/{type}`
- `PUT /api/zones/{zone}/pid-configs/{type}`

Новые обязанности backend:

- validation для `cross_coupled_pi_d` и `supervisory_allocator`;
- validation controller guard blocks;
- backward-compatible read для existing simple configs до миграции данных.

### 6.2 Pump calibration API

Расширяется existing API:

- `GET /api/zones/{zone}/pump-calibrations`
- `PUT /api/zones/{zone}/pump-calibrations/{channelId}`

Новые обязанности backend:

- support `mode`
- support `min_effective_ml`
- support `transport_delay_sec`
- support `deadtime_sec`
- support `curve_points`

### 6.3 Process calibration API

Вводится новый Laravel contract:

- `GET /api/zones/{zone}/process-calibrations`
- `GET /api/zones/{zone}/process-calibrations/{mode}`
- `PUT /api/zones/{zone}/process-calibrations/{mode}`

Payload contract:

- gains
- cross-coupling coefficients
- transport delay
- settle window
- confidence
- source

### 6.4 Effective targets / validation path

Backend обязан:

1. принимать `ec_component_policy` только в `diagnostics.execution.correction`;
2. валидировать policy на этапе сохранения рецепта/effective targets;
3. не создавать вторую параллельную схему хранения policy вне этого path.

## 7. Post-Core Track

Этот трек выполняется только после стабилизации control core.

### 7.1 Relay-autotune

Relay-autotune не входит в initial runtime contract.

Статус:

- existing Laravel proxy path сохраняется;
- autotune runtime считается follow-up deliverable;
- initial merge не зависит от готовности autotune.

### 7.2 Test node physics model

`firmware/test_node` расширяется только после стабилизации core:

- transport delay
- settle delay
- deterministic in-flow response
- controlled `EC -> pH` and `pH -> EC` side effects

### 7.3 Deterministic e2e / HIL

После core merge добавляются:

- deterministic e2e scenarios;
- HIL scenarios on controlled process model;
- real-hardware staged rollout.

## 8. Validation And Test Plan

### 8.1 Unit

- dose allocation by phase policy
- process response prediction
- cross-coupling feedforward
- anti-windup behavior
- hold/settle computation
- no-effect detection

### 8.2 Integration

- snapshot resolution with new contracts
- mode-aware pump calibration resolution
- process calibration resolution
- correction state persistence across ticks
- fail-closed on missing calibration/policy/binding
- regression on existing stage-managed sensor mode flow

### 8.3 E2E

- live telemetry convergence without target backfill
- `solution_fill` and `tank_recirc` use only `npk`
- `irrigating` and `irrig_recirc` use configured phase shares
- command pipeline still goes through `history-logger`
- restart recovery restores hold/PID state

### 8.4 HIL / Post-Core

- deterministic transport delay
- deterministic settle behavior
- controlled `EC <-> pH` coupling
- no ping-pong between controllers

## 9. Definition Of Done

### 9.1 DoD: Runtime Core

1. Existing AE3 correction sub-machine расширен, а не обойдён вторым runtime path.
2. Реализованы process calibration model, cross-coupled decision engine и phase-aware allocator.
3. После дозы реально применяется persisted `hold_until`.
4. `pid_state` переживает restart и достаточен для recovery нового controller path.
5. Все safety guards работают в fail-closed режиме.
6. Existing stage-managed sensor mode semantics и start-cycle invariants не сломаны.

### 9.2 DoD: Laravel/Data Contracts

1. Все schema changes выполнены через Laravel migrations.
2. `pump_calibrations` расширён аддитивно без дублирования validity semantics.
3. Добавлена `zone_process_calibrations`.
4. `pid_state` расширён выбранным fixed contract.
5. Existing PID/pump calibration APIs расширены.
6. Добавлен process calibration API.
7. `ec_component_policy` валидируется только по path
   `diagnostics.execution.correction.ec_component_policy`.

### 9.3 DoD: Post-Core

1. Relay-autotune интегрирован поверх стабилизированного core.
2. Test node моделирует in-flow correction, а не ideal tank.
3. Deterministic e2e/HIL scenarios покрывают transport delay и cross-coupling.
4. Real-hardware staged rollout проходит без SQL cheats и без обхода protected pipeline.

## 10. Assumptions And Defaults

1. Широкий roadmap сохраняется, но не как один линейный implementation stream.
2. Existing AE3 correction state machine остаётся canonical foundation.
3. Новых внешних ingress/API для запуска runtime не добавляется.
4. Новых MQTT contracts и direct publish path не появляется.
5. `ec_component_policy` выбирается единственным источником из `diagnostics.execution.correction`.
6. Relay-autotune, test node, HIL и staged rollout считаются post-core deliverables.

## 11. Аудит Runtime (2026-03-10) — Зафиксированные Баги И Фиксы

Результаты аудита БД e2e и кода AE3. Все фиксы применены в ветке `ae3`.

### 11.1 BUG-1: `last_applied_at` никогда не проставлялся [FIXED]

**Причина:**

- `ZoneSnapshot` не имел поля `correction_config` → `getattr(snapshot, "correction_config", None)` всегда возвращал `None`.
- `zone_snapshot_read_model.py` не загружал таблицу `zone_correction_configs`.
- Метод `_mark_correction_config_applied_if_needed` завершался сразу на проверке `isinstance(correction_config, dict)`.
- Дополнительно: условие `status == "completed"` исключало failed-таски, хотя конфиг использовался и при них.
- Дополнительно: `meta.get("version")` не находил ключ, т.к. `resolved_config.meta` содержит только `preset_id/name/slug`.

**Фикс:**

1. `zone_snapshot.py`: добавлено поле `correction_config: Optional[Mapping[str, Any]] = None`.
2. `zone_snapshot_read_model.py`: добавлен SQL-запрос `zone_correction_configs`, метод `_build_correction_config` инжектирует `meta.version` из колонки `version`.
3. `execute_task.py`: условие изменено с `!= "completed"` на `not in {"completed", "failed"}`.
4. `test_ae3lite_execute_task.py`: добавлен тест `test_execute_task_marks_correction_config_applied_for_failed_two_tank_task`.

### 11.2 BUG-2: Нет валидации `prepare_recirculation_timeout_sec >= observe_window + stabilization` [FIXED]

**Причина:**

`resolve_two_tank_runtime` не проверял что окно рециркуляции физически позволяет хотя бы один цикл коррекции. Конфиг с `timeout < observe_window + stabilization` принимался молча.

**Фикс:**

1. `two_tank_runtime_spec.py`: добавлена функция `_validate_prepare_recirculation_timing`, вызываемая после резолва runtime-конфига. Бросает `PlannerConfigurationError` если `timeout_sec < observe_window_sec + stabilization_sec`.
2. `test_ae3lite_two_tank_runtime_spec.py`: добавлены два теста — happy path (timeout == minimum) и error case (timeout < minimum).

### 11.3 BUG-4: history-logger `refresh_caches` затирал кеш нулевым результатом [FIXED]

**Причина:**

Race condition при старте e2e: history-logger запускается раньше, чем БД засеяна. `refresh_caches()` в 15:06:18 вернул 0 нод (seeder ещё не завершился), вызвал `_node_cache.clear()` и опустошил кеш. Следующий refresh — через 60 секунд. В этом окне все ноды (включая `nd-test-light-1`) считались "not found", 70+ сэмплов потеряны.

**Фикс:**

`telemetry_processing.py`: `refresh_caches()` теперь не очищает кеш зон/нод если DB вернула 0 записей — логирует warning и сохраняет текущий кеш до следующего успешного refresh.
