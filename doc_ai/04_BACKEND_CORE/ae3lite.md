# AE3-Lite: Minimal Canonical Spec

**Версия:** 3.9-canonical
**Дата:** 2026-07-08
**Статус:** CANONICAL MINIMAL SPEC (sync с runtime кодом 2026-05-28: file tree, task types, FSM `update_stage`, error codes, lighting_tick/greenhouse_climate_tick добавлены в canonical scope; lighting day/night ON/OFF — этап A doc-first 2026-07-08; **solution_change semi-auto v1 — этап D.1 doc-first 2026-07-08**)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Роль документа

`ae3lite.md` задаёт минимальный исполнимый контракт для `AE3-Lite`.

Это не roadmap, не RFC на всю evolution runtime и не план на множество параллельных агентов.
Цель документа одна: зафиксировать минимальный scope `v1`, который можно безопасно
реализовать и проверить в production на ограниченном числе зон.

Если требование не нужно для `cycle_start`, `irrigation_start`, `lighting_tick`, `greenhouse_climate_tick` или **doc-first** `solution_change` semi-auto v1, его в этом документе быть не должно.
Этот план рассчитан на выполнение одним ИИ-агентом последовательно, без распараллеливания deliverables.

---

## 1. Scope v1

AE3-Lite v1 это:
1. DB-backed executor для `cycle_start`, `irrigation_start`, `lighting_tick`, `greenhouse_climate_tick` и **`solution_change` (semi-auto v1, этап D.1)**.
2. Protected command pipeline без изменений:
   `Laravel scheduler-dispatch -> Automation-Engine -> history-logger -> MQTT -> ESP32`.
3. Внешние ingress (scheduler/API compat):
   `POST /zones/{id}/start-cycle`, `POST /zones/{id}/start-irrigation`,
   `POST /zones/{id}/start-lighting-tick` (dispatch света для `zones.automation_runtime='ae3'`, см. C1),
   `POST /zones/{id}/start-solution-change` (полуавтоматическая подмена раствора, см. D.1 / `CORRECTION_CYCLE_SPEC.md` §10),
   `POST /greenhouses/{id}/start-climate-tick` (климат крыши на уровне теплицы; single-writer lease на `greenhouse_id`; см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`).
4. Один canonical status endpoint:
   `GET /internal/tasks/{task_id}`.
5. Ручной rollout по зоне через `zones.automation_runtime='ae3'`.
6. Recovery после restart для `claimed|running|waiting_command`.

AE3-Lite v1 не включает:
1. `ventilation_tick` на уровне зоны вне контура greenhouse climate (см. roadmap / `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`)
2. **полностью автоматический** `solution_change` без operator gates и CIP (этап D.2; semi-auto v1 **в scope**, см. §1 и §7.2.3)
3. `mist`
4. `diagnostics` как отдельный productized runtime (compat через `start-cycle` допускается см. `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md`)
5. `recovery` как отдельный business task
6. relay-autotune runtime как отдельный business task (endpoint `POST /zones/{id}/start-relay-autotune` не реализован)
7. multi-replica runtime
8. auto-canary router
9. auto-rollback controller
10. outbox/domain-events platform
11. generic workflow framework

`GET /zones/{id}/state` доступен как internal operator endpoint (см. §7.4 и `runtime/app.py`), но не считается canonical ingress runtime path и не используется как single source of truth — UI обязан читать состояние из Laravel/SQL read-model.

---

## 2. Неподвижные инварианты

1. Команды на узлы публикуются только через `history-logger` (`POST /commands`).
2. Прямой MQTT publish из AE и Laravel запрещён.
3. До полного cutover внешние ingress runtime ограничены `POST /zones/{id}/start-cycle`,
   `POST /zones/{id}/start-irrigation`, `POST /zones/{id}/start-lighting-tick`,
   `POST /zones/{id}/start-solution-change` и
   `POST /greenhouses/{id}/start-climate-tick` (см. §1 scope).
4. В production v1 допускается только одна активная реплика AE3-Lite.
5. На одну зону допускается не более одной активной execution task (`ae_tasks` / `ae_zone_leases`).
6. На одну теплицу допускается не более одного конкурирующего writer для greenhouse climate tick (`greenhouse_automation_leases` + lifecycle `greenhouse_automation_intents`).
7. Успешный terminal outcome mutating-команды только `DONE`.
8. `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` считаются fail для v1.
9. Runtime path не зависит от runtime HTTP-вызовов в Laravel.
10. Runtime читает zone state напрямую из PostgreSQL read-model.
11. Изменения БД выполняются только через Laravel migrations.
12. `ae3lite/*` не импортирует пакеты прежнего monolithic runtime вне `ae3lite/`.
13. Переключение зоны на `ae3` запрещено при активной task или активной lease.
14. План выполняется одним ИИ-агентом, строго последовательно, без параллельных веток работ.
15. Любое отклонение от этого документа считается defect, а не “допустимой импровизацией”.

### 2.1 Фаза зоны `ready` и стадия `await_ready` (полив)

Источник истины для «зона готова к поливу» в runtime плана — поле **`zone_workflow_phase`** в snapshot зоны (read-model), которое AE3-Lite кладёт в `plan.runtime` при планировании (`CycleStartPlanner` / аналог). Значение **`ready`** означает: workflow зоны в PostgreSQL (`zone_workflow_state.workflow_phase`) приведён в состояние готовности после завершения подготовительных шагов (например, после успешного `cycle_start` / завершения связанной задачи в `WorkflowRouter`).

Ingress-guard `POST /zones/{id}/start-irrigation`:

1. До создания canonical task runtime проверяет текущее значение `zone_workflow_state.workflow_phase` в read-model.
2. Если фаза не `ready` (или row отсутствует), запрос отклоняется fail-closed с `409 start_irrigation_setup_pending`; `irrigation_start` task не создаётся, lease зоны не захватывается.
3. Для observability пишется zone event `IRRIGATION_BLOCKED_SETUP_PENDING` и инкрементируется `ae3_start_irrigation_blocked_total{reason="setup_pending"}`.
4. Этот guard не заменяет `await_ready`: стадия остаётся safety-net для уже созданных задач (recovery/старые intents), где runtime обязан подтвердить `ready` по poll/reconcile.

Стадия **`await_ready`** в задаче `irrigation_start`:

1. Пока `zone_workflow_phase != ready`, исполнитель возвращает **poll** с интервалом `AE_IRRIGATION_WAIT_READY_POLL_SEC` и при первом заходе фиксирует дедлайн `irrigation_wait_ready_deadline_at` (окно `AE_IRRIGATION_WAIT_READY_SEC`).
2. Когда snapshot даёт **`ready`**, стадия переходит в **`decision_gate`** (дальнейшие решения по поливу).
3. Если дедлайн истёк, задача завершается с ошибкой **`irrigation_wait_ready_timeout`**; при этом пишется structured log, zone event `IRRIGATION_WAIT_READY_TIMEOUT`, опционально business alert `biz_irrigation_wait_ready_timeout` (dedupe по зоне/задаче), инкрементируются метрики `ae3_irrigation_wait_ready_*`.

Связка «цикл → готовность → полив» не должна обходить этот контракт: нельзя полагаться на устаревший snapshot без poll/reconcile.

Детализация integration-contract для channel-level событий `level_* /event` от
`storage_irrigation_node` вынесена в `AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`.
Детализация fail-safe/e-stop mirror-contract для IRR-ноды вынесена в
`AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`.

---

## 3. Контракт одного ИИ-агента

### 3.1 Режим исполнения

AE3-Lite `v1` реализует один ИИ-агент.

Агент обязан:
1. выполнять работу строго последовательно
2. держать активным только один deliverable за раз
3. сначала доводить schema/invariants, потом runtime, потом rollout/status path
4. не начинать следующий шаг, пока предыдущий не закрыт тестом или явным documented blocker
5. не расширять scope без прямого изменения этого документа человеком
6. тестировать каждый этап сразу после реализации, не откладывая тесты на финал

Агенту запрещено:
1. вести параллельные реализации нескольких подсистем
2. добавлять новые task types вне `cycle_start|irrigation_start|lighting_tick|greenhouse_climate_tick`
3. добавлять новые API вне `POST /zones/{id}/start-cycle`,
   `POST /zones/{id}/start-irrigation`, `POST /zones/{id}/start-lighting-tick`,
   `POST /greenhouses/{id}/start-climate-tick` и `GET /internal/tasks/{task_id}`
4. вносить “временные” обходные решения вне spec
5. оправдывать отклонение словами `temporary`, `later`, `for now`, `quick fix`, если это нарушает инвариант

### 3.2 Жёсткий порядок работ

Разрешён только такой порядок:
1. schema и DB constraints
2. lease/claim invariants
3. `CycleStartPlanner`
4. command publish gateway
5. command reconcile
6. startup recovery
7. `GET /internal/tasks/{task_id}`
8. rollout/rollback runbook

Переход к следующему пункту запрещён, если предыдущий:
1. не реализован полностью
2. не покрыт обязательными тестами своего уровня
3. оставляет известный дефект в инвариантах
4. не прошёл фактический запуск stage-level tests

### 3.3 Протокол отклонения и самонаказание

Если агент отклоняется от плана, он обязан считать это нарушением spec.

Наказание за отклонение:
1. немедленный self-stop: агент прекращает дальнейшую реализацию в текущем направлении
2. deliverable автоматически считается проваленным до исправления отклонения
3. агент обязан явно зафиксировать `DEVIATION:` с описанием нарушенного пункта spec
4. агент обязан удалить или откатить собственные незамерженные изменения, которые ввели отклонение
5. агент обязан вернуться к ближайшему последнему состоянию, совместимому с этим документом
6. после отклонения агент обязан добавить минимум один тест, который не позволит повторить это нарушение
7. повторное отклонение того же типа считается грубым нарушением и требует остановки работы до явного решения человека

Под отклонением понимается:
1. расширение scope сверх `cycle_start|irrigation_start`
2. ослабление DB/runtime инварианта
3. обход protected command pipeline
4. добавление runtime path без теста
5. переход к следующему шагу при незакрытом предыдущем
6. смешение rollout/API parity с core runtime до закрытия core

### 3.4 Fail-closed правило для самого агента

Если агент не может доказать, что изменение совместимо с этим документом, он обязан:
1. считать изменение запрещённым
2. не писать код “на предположении”
3. зафиксировать blocker, а не додумывать архитектуру
4. предпочесть сокращение scope, а не расширение абстракций
5. считать непроверенный этап незавершённым

---

## 4. Минимальная модель исполнения

### 4.1 Runtime entities

#### `AutomationTask`

Единственный root aggregate исполнения.

Поля уровня модели:
1. `id`
2. `zone_id`
3. `task_type`
4. `status`
5. `idempotency_key`
6. `topology`
7. `intent_source`
8. `intent_trigger`
9. `intent_id`
10. `intent_meta`
11. `workflow.current_stage`
12. `workflow.workflow_phase`
13. `claimed_by`
14. `claimed_at`
15. `error_code`
16. `error_message`
17. `completed_at`

Correction state для `cycle_start` хранится в explicit columns `ae_tasks`, а не в JSON payload.
Канонический retry-contract:
1. `corr_ec_attempt` / `corr_ec_max_attempts`
2. `corr_ph_attempt` / `corr_ph_max_attempts`
3. `workflow.stage_retry_count` для recirculation timeout windows
4. terminal error `prepare_recirculation_attempt_limit_reached` после исчерпания `prepare_recirculation_max_attempts`
5. stage timeout (`solution_fill_timeout_sec` / `prepare_recirculation_timeout_sec`) ограничивает весь stage целиком, включая активный correction sub-machine; при истечении deadline correction обязан быть прерван fail-closed переходом stage
6. возврат correction из `solution_fill_check` обратно в `solution_fill_check` не переоткрывает `solution_fill_timeout_sec`; stage deadline сохраняется до terminal transition из stage
7. runtime обязан передавать stage timeout в `pump_main/set_relay` start-команде как `params.timeout_ms` + `params.stage`; timed-start исполняется по `ACK -> DONE/ERROR`, при этом gateway резюмирует batch уже на `ACK`

Correction runtime invariants:
1. для `EC` и `pH` используется только observation-driven модель `dose -> hold -> observe -> decide`;
2. device-level команда для correction pumps публикуется как `cmd="dose"` с `params.ml`; `duration_ms` остаётся внутренней вычисляемой величиной planner/runtime и не является каноническим дозовым входом для node-effect;
3. correction decision не опирается на один `telemetry_last` sample;
4. observation window читается из `telemetry_samples`;
5. planner может одновременно держать в одном correction window потребность и в `EC`, и в `pH`;
6. исполнение химических шагов остаётся последовательным: между `EC` и `pH` обязателен повторный `observe-step`, но повторный вход parent-stage не требуется;
7. `3` consecutive `no-effect` для одного `pid_type` дают alert и fail-closed ветку текущего correction window;
8. ordinary correction attempts и `no-effect` attempts считаются раздельно.
9. устаревшие timing wait-поля и секция adaptive timing отсутствуют в authority/runtime contract; базовое окно наблюдения определяется через `zone_process_calibrations.transport_delay_sec + settle_sec` и controller observe config, но AE3 может только удлинять его на основе persisted runtime-learning в `pid_state.stats.adaptive.timing`.
9. correction retry caps принимают только явные конечные значения внутри контрактных верхних границ; magic sentinel values не поддерживаются ни runtime, ни API.
10. для `solution_fill_check` attempt caps не закрывают correction window: stage живёт под общим `solution_fill_timeout_sec` и останавливает коррекцию только по `no-effect` fail-closed или по stage timeout;
    текущая canonical fail-closed реализация для `no-effect` — переход в `solution_fill_timeout_stop` без повторного входа в correction.
11. `workflow_ready` строже correction-success: если runtime уже содержит явные `target_ph_min/max` и `target_ec_min/max`, переходы в `*_stop_to_ready` обязаны подтверждать именно этот explicit ready band; fallback на `prepare_tolerance` допустим только при отсутствии explicit band.

#### `PlannedCommand`

Execution record внутри task:
1. `step_no`
2. `node_uid`
3. `channel`
4. `payload`
5. `external_id`
6. `terminal_status`

#### `ZoneLease`

Модель single-writer на уровне зоны:
1. `zone_id`
2. `owner`
3. `leased_until`

#### `ZoneWorkflow`

Минимальный workflow state зоны:
1. `workflow_phase`
2. `version`
3. `scheduler_task_id`
4. `started_at`
5. `updated_at`

### 4.2 Canonical task types

В `v1` разрешены business task'и (записи в `ae_tasks`):
1. `cycle_start`
2. `irrigation_start`
3. `lighting_tick`
4. `solution_change` — полуавтоматическая подмена раствора (drain → clean_fill → solution_fill → prepare_recirc → `ready` с operator gates; см. `CORRECTION_CYCLE_SPEC.md` §10)

Greenhouse climate runtime (`greenhouse_climate_tick`) исполняется отдельной таблицей `greenhouse_automation_tasks` (и lease в `greenhouse_automation_leases`), не в `ae_tasks` — см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`. Поэтому в DB CHECK constraint на `ae_tasks.task_type` лежат четыре значения выше (после миграции D.1; до реализации — doc-first only).

Другие task types считаются out of scope и не должны появляться ни в migration, ни в API, ни в runtime wiring `v1`.

### 4.3 Task statuses

Main path:
`pending -> claimed -> running -> waiting_command -> completed`

Two-tank stage requeue (`running|claimed|waiting_command -> pending`) реализован атомарно методом `PgAutomationTaskRepository.update_stage(...)`: одна транзакция сбрасывает claim, обновляет `current_stage` и correction-поля (`corr_*`), переводит task в `pending`. Прежний метод `requeue_pending` снят. Любое `StageOutcome.transition/poll/enter_correction` от handler'а транслируется `WorkflowRouter` в `update_stage`.

Terminal:
`failed | cancelled`

`cancelled` используется только для controlled abort:
1. `control_mode_switched_to_manual` — переключение зоны в manual прерывает active task (см. `application/use_cases/set_control_mode.py`);
2. явная отмена через operator API (`POST /zones/{id}/manual-step` с cancel-семантикой);
3. экспирация lease на restart, если recovery определяет task как невосстановимую.

Дополнительные статусы в `v1` не вводятся.

### 4.4 Workflow phases

Допустимые фазы:
1. `idle`
2. `tank_filling`
3. `tank_recirc`
4. `irrigating`
5. `irrig_recirc`
6. `ready`

`zone_workflow_state` мутируется только каноническими AE3 task-ами:
1. `cycle_start` управляет переходами `idle -> tank_filling -> tank_recirc -> ready`
2. `irrigation_start` управляет переходами `ready -> irrigating -> irrig_recirc -> ready`
3. `solution_change` управляет переходами `ready -> (drain + refill substages) -> tank_recirc -> ready`; не переводит зону в `irrigating`

`startup` как отдельная `workflow_phase` не существует: возврат в startup кодируется как
`workflow_phase='idle'` + `payload.ae3_cycle_start_stage='startup'`.

---

## 5. Runtime flow

### 4.1 High-level sequence

1. `POST /zones/{id}/start-cycle`, `POST /zones/{id}/start-irrigation`, `POST /zones/{id}/start-lighting-tick` или `POST /greenhouses/{id}/start-climate-tick`
   валидирует контракт и создаёт canonical execution context (зона: `AutomationTask` в `ae_tasks`; теплица: intent/lease/state в `greenhouse_automation_*` — см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`).
2. Worker выбирает следующую `pending` task.
3. Worker пытается получить `ZoneLease`.
4. Если lease не получена, task не исполняется.
5. Загружается `ZoneSnapshot` через direct SQL read-model.
6. `CycleStartPlanner` строит последовательный `CommandPlan`.
7. Шаг команды записывается в `ae_commands`.
8. Команда публикуется через `history-logger`.
9. Runtime ждёт terminal status в таблице `commands` (источник ведёт history-logger).
10. Только `DONE` переводит execution к следующему step.
11. Любой другой terminal завершает task как `failed`.
12. После terminal task lease освобождается.
13. Если зона была в `ready`, но канонический monitor уровней больше не подтверждает
    наличие раствора по `solution_min` (датчик не активен / `is_triggered=false`),
    runtime обязан auto-reset `zone_workflow_state` обратно в `idle/startup`, чтобы
    зона больше не считалась готовой к поливу до следующего `cycle_start`.
14. Для IRR-ноды runtime принимает fast-path node events только через
    `history-logger -> zone_events -> PostgreSQL NOTIFY ae_zone_event -> worker.kick()`;
    после wake-up решение всё равно принимается только по DB read-model
    (`telemetry_last`, `zone_events`, `zone_workflow_state`, при необходимости `commands`).

### 4.2 Execution policy

1. Все steps исполняются строго последовательно.
2. Параллельные command-steps в `v1` запрещены.
3. Следующий step разрешён только после terminal предыдущего.
4. `v1` не использует отдельные compensation tasks.
5. Если нужен safety-stop, он выполняется inline и не создаёт новую business task.

### 4.3 DONE-only contract

Для всех mutating-команд:
1. success = только `DONE`
2. `NO_EFFECT` не считается success в `v1`
3. dedupe не заменяет реальный terminal status
4. publish failure не трактуется как implicit ACK

### 4.4 Runtime hardening

1. `HistoryLoggerClient` в `v1` может сделать ровно один дополнительный HTTP retry только для transient transport error или `HTTP 5xx`, затем runtime обязан fail-closed.
2. Polling ожидания terminal статуса команды должен быть bounded: старт от `AE_RECONCILE_POLL_INTERVAL_SEC`, backoff `x1.5`, верхняя граница `5s`.
3. `scheduler_intent_terminal` `LISTEN/NOTIFY` используется как fast-path для `worker.kick()`, но не заменяет canonical DB state и обязательный polling fallback.
4. `ae_zone_event` `LISTEN/NOTIFY` используется как fast-path только для node runtime events (`LEVEL_SWITCH_CHANGED`, `storage_state/event` и связанных aggregate событий).
5. `initial=true` от level-switch runtime event не считается самостоятельным основанием для stage-complete; он используется для wake-up/observability и допускается для `ready/startup guard`, если depletion подтверждён DB read-model.
6. `storage_state/event` от IRR-ноды используется как shortcut для reconcile только через `zone_events` read-model:
   `clean_fill_source_empty` -> `clean_fill_retry_stop` два раза, затем `clean_fill_source_empty_stop`;
   `solution_fill_source_empty` -> `solution_fill_source_empty_stop`;
   `solution_fill_leak_detected` -> `solution_fill_leak_stop`;
   `recirculation_solution_low` -> `prepare_recirculation_solution_low_stop`;
   `irrigation_solution_low` -> тот же replay/setup path, что и `solution_min=false` в `irrigation_check`.
7. `emergency_stop_activated` не завершает stage автоматически: AE3 обязан сначала попытаться перепроверить ожидаемый hardware snapshot через reconcile; continuation допустим только если актуаторы вернулись в ожидаемое состояние.
8. Runtime обязан жёстко ограничивать tracked background tasks; переполнение registry не может игнорироваться и должно отклоняться fail-closed.
9. Полное исполнение `ExecuteTaskUseCase.run()` должно быть ограничено `AE_MAX_TASK_EXECUTION_SEC` (default `900s`); timeout не может оставлять task в подвешенном active state.
10. Timeout whole-task execution обязан идти по fail-closed path: worker отменяет run с внутренней причиной `ae3_task_execution_timeout`, runtime выполняет fail-safe shutdown актуаторов, затем завершает task/intent как `failed`.
11. Обычная отмена процесса/loop shutdown не должна маскироваться под timeout: recovery path после restart остаётся отдельным механизмом.
12. Fail-safe shutdown команды публикуются как publish-only batch: они не должны повторно переводить уже terminal/closing task в `waiting_command` и не должны искажать `ae_commands` ложным `publish_failed`, если устройство реально подтвердило shutdown после terminal failure основной задачи.
13. Перед fail-closed terminal transition runtime обязан синхронизировать `zone_workflow_state` обратно в `workflow_phase='idle'`, чтобы stale phase не переживала terminal failure task.

---

## 6. Read-model и planner

### 5.1 Единственный planner v1

В `v1` допускаются:
1. `CycleStartPlanner`
2. decision-controller registry для `irrigation_start`

Planner:
1. принимает `AutomationTask` и `ZoneSnapshot`
2. возвращает `CommandPlan`
3. не содержит SQL и HTTP

### 5.2 `ZoneSnapshot`

`ZoneSnapshot` это immutable DTO application layer.

Минимальные источники данных:
1. `zones`
2. `grow_cycles`
3. `grow_cycle_phases`
4. `automation_effective_bundles`
5. `zone_workflow_state`
6. `telemetry_last`
7. `nodes`
8. `node_channels`
9. `channel_bindings`
10. `pump_calibrations`
11. `pid_state`
12. `automation_config_documents`

### 5.3 Требования к read consistency

1. `ZoneSnapshot` должен читаться в одной DB transaction.
2. Runtime обязан использовать фиксированный порядок резолва runtime config:
   `phase snapshot -> cycle.phase_overrides -> cycle.manual_overrides -> zone.logic_profile(active mode)`.
3. Если snapshot не может быть собран консистентно, task завершается fail-closed.
4. Hardcoded default targets запрещены.
5. Stale critical telemetry должна приводить к fail-closed.

### 5.4 Определение online actuator channels

Поле `nodes.status` обновляется фоновой задачей `monitor_offline_nodes` (history-logger) с интервалом `NODE_OFFLINE_CHECK_INTERVAL_SEC=60s` и порогом `NODE_OFFLINE_TIMEOUT_SEC=120s`. Чтобы устранить ложно-отрицательные срабатывания при кратковременных drift-ах, фильтр `actuator_rows` в `PgZoneSnapshotReadModel` использует комбинацию:

```sql
LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
OR COALESCE(n.last_seen_at, n.last_heartbeat_at, n.updated_at)
       >= NOW() - (AE3_NODE_FRESHNESS_FALLBACK_SEC * INTERVAL '1 second')
```

`AE3_NODE_FRESHNESS_FALLBACK_SEC` (default `180`) обязан быть ≥ `NODE_OFFLINE_TIMEOUT_SEC + NODE_OFFLINE_CHECK_INTERVAL_SEC`.

Если выборка пуста, выполняется отдельный диагностический запрос по всем нодам зоны (`status`, `last_seen_age_sec`, `active_actuator_count`) и результат прокидывается в `SnapshotBuildError.details`:

```json
{
  "zone_id": 1,
  "zone_nodes": [
    {"uid": "nd-irrig-1", "type": "irrig", "status": "offline", "last_seen_age_sec": 145, "active_actuator_count": 6}
  ],
  "persistently_offline_uids": [],
  "transiently_offline_uids": ["nd-irrig-1"],
  "persistent_dead_threshold_sec": 600
}
```

`ExecuteTaskUseCase` использует этот breakdown:

1. Если `persistently_offline_uids` непуст (узел давно мёртв, `last_seen_age_sec ≥ AE3_NODE_PERSISTENT_DEAD_SEC`) — задача fail-closed с кодом `ae3_snapshot_required_node_persistently_offline` без retry.
2. Иначе срабатывает transient retry (`SNAPSHOT_TRANSIENT_RETRY_SEC=10s`, бюджет `AE3_SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC=600s`); breakdown пробрасывается в `AE_SNAPSHOT_RETRY_SCHEDULED` / `AE_SNAPSHOT_RETRY_EXHAUSTED` events и в `infra_ae3_snapshot_retry_*` алерты.

Дополнительно для two-tank-топологий (`two_tank`, `two_tank_drip_substrate_trays`) `ExecuteTaskUseCase._verify_topology_required_node_types` после загрузки snapshot проверяет, что среди actuator'ов представлены все требуемые `node_type` ∈ `{irrig, ph, ec}`. При отсутствии — fail-closed с конкретным кодом `ae3_snapshot_required_node_type_missing` и `details.missing_node_types`, без retry.

Канонические env-переменные:

| ENV | Default | Семантика |
|-----|---------|-----------|
| `AE3_NODE_FRESHNESS_FALLBACK_SEC` | `180` | Окно «нода ещё считается живой по `last_seen_at`», если `nodes.status` ещё не успел обновиться |
| `AE3_NODE_PERSISTENT_DEAD_SEC` | `600` | Возраст `last_seen_at`, после которого нода persistently dead → fail-closed без retry |
| `AE3_SNAPSHOT_TRANSIENT_RETRY_SEC` | `10` | Интервал retry'а после transient snapshot gap |
| `AE3_SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC` | `600` | Бюджет (wall-clock) retry'а transient snapshot gap |
6. `zone.correction.payload.resolved_config` для AE3 correction runtime считается полным обязательным контрактом:
   отсутствие required field в `runtime/timing/dosing/retry/tolerance/controllers/safety`
   должно приводить к fail-closed, без silent fallback на catalog defaults или устаревшие
   `diagnostics.execution.*`.

### 5.4 Per-phase EC и day/night в runtime spec (2026-04-13)

Two-tank `cycle_start` runtime spec (`backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py`) расширен полями, которые AE3 handlers обязан использовать вместо сырых `target_ec`:

| Поле runtime spec | Источник | Назначение |
|-------------------|----------|------------|
| `target_ec_prepare` | `target_ec * npk_ec_share` | EC target для prepare-фаз (`solution_fill`, `tank_recirc`) — только NPK-доля. |
| `target_ec_prepare_min` / `target_ec_prepare_max` | `phase.ec_min/ec_max * npk_ec_share` | Диапазон prepare-target. |
| `npk_ec_share` | `nutrient_npk_ratio_pct / Σratios` | Коэффициент NPK от полного EC; `1.0` если ratios отсутствуют (legacy phase). |
| `day_night_enabled` | `phase.day_night_enabled` | Включает late-binding override pH/EC по локальному времени. |
| `day_night_config` | `phase.extensions.day_night` (нормализованный) | `{enabled, lighting, ph, ec}` — готовый для handler. |

Handler-уровневые accessors (`backend/services/automation-engine/ae3lite/application/handlers/base.py:1107..1245`):
- `_effective_ec_target/min/max(task, runtime)` — выбирает prepare vs full target по `task.workflow_phase`;
- `_effective_ph_target/min/max(task, runtime)` — применяет day/night override;
- `_is_day_now(day_night_config)` — late-binding, использует `datetime.now()` локального процесса AE3;
- `_day_night_override_scaled` сохраняет NPK-долю при night-override для prepare-фаз.

Полная семантика — `../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` §9 (per-phase EC) и §10 (day/night).

---

## 7. Минимальная схема данных

### 6.1 `ae_tasks`

Обязательные поля:
1. `id`
2. `zone_id`
3. `task_type`
4. `status`
5. `idempotency_key`
6. `topology`
7. `intent_source`
8. `intent_trigger`
9. `intent_id`
10. `intent_meta`
11. `scheduled_for`
12. `due_at`
13. `current_stage`
14. `workflow_phase`
15. `claimed_by`
16. `claimed_at`
17. `error_code`
18. `error_message`
19. `created_at`
20. `updated_at`
21. `completed_at`

Примечание:
`ae_tasks` в canonical runtime `v1` использует явные typed columns для topology,
intent metadata и workflow state. Произвольный JSON в `payload` не является источником истины
для stage progression.

Обязательные ограничения:
1. `task_type IN ('cycle_start', 'irrigation_start', 'lighting_tick')` для всех записей `v1` (DB CHECK constraint, см. миграцию `2026_04_04_*`)
2. уникальность `idempotency_key` в допустимом scope — scoped по `(zone_id, idempotency_key)` начиная с миграции `2026_03_17_131000_scope_idempotency_keys_by_zone.php`
3. не более одной активной task на `zone_id` — partial unique index `ae_tasks_active_zone_unique` по `WHERE status IN ('pending','claimed','running','waiting_command')`
4. terminal task не может вернуться в active status
5. runtime state irrigation decision/replay хранится в explicit typed columns, а не в произвольном JSON `payload`
6. correction runtime сохраняет causal snapshot context в explicit columns `corr_snapshot_*`, чтобы `EC_DOSING` / `PH_CORRECTED` могли ссылаться на конкретный `IRR_STATE_SNAPSHOT` после requeue/restart

### 6.2 `ae_commands`

Обязательные поля:
1. `id`
2. `task_id`
3. `step_no`
4. `node_uid`
5. `channel`
6. `payload`
7. `external_id`
8. `publish_status`
9. `terminal_status`
10. `ack_received_at`
11. `terminal_at`
12. `last_error`
13. `created_at`
14. `updated_at`

Обязательные ограничения:
1. уникальность `(task_id, step_no)`
2. `step_no` монотонно возрастает внутри task
3. один execution step соответствует не более одной внешней команде

`ae_commands` хранит локальный execution log AE3-Lite.
Terminal source of truth для publish/reconcile в `v1` остаётся таблица `commands` (ведётся history-logger),
связанная через `ae_commands.external_id -> commands.id`.

### 6.3 `ae_zone_leases`

Обязательные поля:
1. `zone_id`
2. `owner`
3. `leased_until`
4. `updated_at`

Обязательные ограничения:
1. одна активная lease на `zone_id`
2. reclaim допускается только после истечения lease или явного release

### 6.4 `zone_workflow_state`

Обязательное расширение:
1. `version BIGINT NOT NULL DEFAULT 0`

В таблице храним только:
1. `workflow_phase`
2. `version`
3. `scheduler_task_id`
4. `started_at`
5. `updated_at`

CAS update по `version` обязателен для workflow mutation.

### 6.5 `zones`

Для rollout достаточно одного поля:
1. `automation_runtime TEXT NOT NULL DEFAULT 'ae3' CHECK (automation_runtime IN ('ae3'))`

Правило:
1. switch на `ae3` запрещён, если у зоны есть active task или active lease

### 6.6 Config modes (Phase 5, 2026-04-15)

Миграция `2026_04_15_142400_add_config_mode_to_zones.php` добавляет поля в `zones`:
- `config_mode TEXT NOT NULL DEFAULT 'locked' CHECK (config_mode IN ('locked','live'))` — `locked` фиксирует cycle snapshot, `live` включает hot-reload на AE3 checkpoint
- `live_until TIMESTAMP NULL` — TTL, auto-revert cron flip'ает в locked при истечении
- `live_started_at TIMESTAMP NULL` — первое включение live (для 7-day cap)
- `config_revision BIGINT NOT NULL DEFAULT 1` — монотонный integer counter, bump'ается через `ZoneConfigRevisionService::bumpAndAudit` при каждом PUT zone-scoped config
- `config_mode_changed_at`, `config_mode_changed_by` — audit metadata
- CHECK constraint: `config_mode = 'locked' OR live_until IS NOT NULL`

Дополнительная таблица `zone_config_changes`:
- PK `id`, FK `zone_id`, `revision` (unique per zone), `namespace` (`zone.config_mode` | `zone.correction` | `zone.correction.live` | `recipe.phase`), `diff_json`, `user_id`, `reason`, `created_at`
- Unique constraint `(zone_id, revision)` — correctness net против race conditions

**Hot-reload контракт AE3 runtime (Phase 5.5+):**

`BaseStageHandler._checkpoint(task, plan, now) -> RuntimePlan` вызывается в начале каждого handler `run()`:

```python
new_runtime = await self._checkpoint(task=task, plan=plan, now=now)
if new_runtime is not plan.runtime:
    plan = replace(plan, runtime=new_runtime)
runtime = plan.runtime
```

Семантика:
1. Если `live_reload_enabled=False` (unit tests) — возвращает `plan.runtime` без изменений
2. Читает `zones.config_mode`, `zones.config_revision`, `zones.live_until`
3. Если не live / TTL истёк / revision не advanced → возвращает `plan.runtime`
4. Иначе: `PgZoneSnapshotReadModel().load(zone_id=...)` + `resolve_two_tank_runtime_plan(snapshot)` → fresh RuntimePlan, stamps `config_revision=new_revision` через `model_copy(update=...)`, эмитит `CONFIG_HOT_RELOADED` zone_event + metric `ae3_config_hot_reload_total{result=applied}`

`dataclasses.replace(plan, runtime=fresh)` создаёт новый immutable CommandPlan — все downstream helpers (в correction.py 9 step methods, в base.py `_workflow_ready_reached`/`_targets_reached`, и т.д.) автоматически видят refresh через `plan.runtime` без изменения сигнатур.

**Cron auto-revert:** `automation:revert-expired-live-modes` (Laravel scheduler `everyMinute`) — select candidates without lock, per-zone `Zone::lockForUpdate()` + double-check `config_mode='live' AND live_until < NOW()` внутри транзакции, flip в locked, write audit + `CONFIG_MODE_AUTO_REVERTED` event.

---

## 8. API-контракты

### 7.1 `POST /zones/{id}/start-cycle`

Обязательный внешний ingress setup/runtime path.

Требования:
1. сохраняет текущий внешний контракт
2. принимает `source`, `idempotency_key`
3. валидирует security baseline
4. создаёт canonical `AutomationTask`
5. при active task или active lease возвращает controlled error

### 7.2 `POST /zones/{id}/start-irrigation`

Обязательный внешний ingress irrigation/runtime path.

Требования:
1. принимает `source`, `idempotency_key`
2. принимает `mode: normal|force`
3. принимает `requested_duration_sec`
4. создаёт canonical task `task_type='irrigation_start'`
5. при `mode=normal` проходит через decision-controller strategy registry
6. неизвестная irrigation strategy считается ошибкой конфигурации, завершает task fail-closed с `irrigation_decision_strategy_unknown` и поднимает business alert через `decision_gate`
7. active irrigation task фиксирует decision snapshot (`strategy/config/bundle_revision`) при создании canonical task под zone advisory lock; первый runtime pass только эмитит observability event, а последующие изменения `zone.logic_profile` применяются только к следующему irrigation task
8. при `mode=force` bypass-ит decision-controller, но не bypass-ит canonical task/runtime path
9. при active task или active lease возвращает controlled error

### 7.2.1 `POST /zones/{id}/start-lighting-tick`

Обязательный внешний ingress для scheduler-driven освещения (`task_type='lighting_tick'`, C1 + этап A day/night).

Требования:
1. принимает `source`, `idempotency_key` (как у `start-irrigation`)
2. принимает опционально `desired_state: on|off` (default `on`) — целевое состояние для одного tick; `"off"` обязателен на границе выхода из фотопериода (см. `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` §7)
3. принимает опционально `brightness_pct: 0..100` — явная яркость для ON-tick; при OFF игнорируется
4. создаёт canonical task `task_type='lighting_tick'` с одношаговым workflow
5. `CycleStartPlanner._build_lighting_tick_plan` строит команду по типу actuator-канала:
   - `desired_state=on` → `set_pwm {duty}` или `set_relay {state:true}`; duty из `brightness_pct`, затем `targets.lighting.brightness`, fallback `100`
   - `desired_state=off` → `set_pwm {duty:0}` или `set_relay {state:false}`
6. при active task или active lease возвращает controlled error (`409 start_lighting_tick_zone_busy`)

Контракт Pydantic: `ae3lite/api/contracts.py` → `StartLightingTickRequest`.

**Baseline до этапа A (текущий код):** request содержит только `source` + `idempotency_key`; planner всегда ON с duty из `targets.lighting.brightness`/`pwm_duty` (fallback `100`). Поля `desired_state` / `brightness_pct` — целевое расширение §A.3 `AGRO_AUTONOMY_MASTER_PLAN.md`.

### 7.2.3 `POST /zones/{id}/start-solution-change` (semi-auto v1, этап D.1)

Ingress для **полуавтоматической подмены раствора** (`task_type='solution_change'`). Полная семантика workflow, operator gates и UI — `CORRECTION_CYCLE_SPEC.md` §10.

**Статус реализации:** semi-auto v1 (этап D.1) — endpoint, planner, handlers и operator gates в canonical scope AE3.

Требования (целевой контракт):

1. принимает `source`, `idempotency_key` (как у `start-irrigation`);
2. опционально `trigger: operator|scheduler` (audit);
3. ingress только при `workflow_phase='ready'` и отсутствии active irrigation;
4. создаёт canonical task `task_type='solution_change'`;
5. первый runtime stage — `await_operator_drain_confirm` (G1); **drain не начинается** до manual step `solution_drain_confirm`;
6. после успешного refill (`solution_fill_check`) — `await_operator_refill_confirm` (G2) до manual step `solution_refill_confirm`;
7. reuse handlers: `solution_drain_*` (новые), `clean_fill_*`, `solution_fill_*`, `prepare_recirculation_*` (существующие);
8. при active task или active lease — `409 start_solution_change_zone_busy`;
9. scheduler intent `SOLUTION_CHANGE_TICK` (Laravel `ScheduleDispatcher`) маршрутизируется в этот endpoint, но v1 **не bypass** operator gates.

Новые manual steps (дополнение к `manual_control_contract.py` / Vue `AutomationManualStep`):

| Step | Stage |
|------|-------|
| `solution_drain_confirm` | `await_operator_drain_confirm` |
| `solution_refill_confirm` | `await_operator_refill_confirm` |
| `solution_change_abort` | любой pre-terminal stage |

Fail-safe: terminal failure синхронизирует `workflow_phase='idle'`, batch OFF актуаторов (инвариант §5.4).

### 7.2.2 `POST /greenhouses/{id}/start-climate-tick`

Ingress для **greenhouse-level** rule-based климата крыши (две roof-форточки, `set_position`), не смешивается с `ae_tasks` зоны.

Требования:
1. принимает `source`, `idempotency_key` (идемпотентность в рамках `greenhouse_id` через `greenhouse_automation_intents`)
2. захватывает/продлевает single-writer lease в `greenhouse_automation_leases` (отдельно от `ae_zone_leases`)
3. читает конфиг из `greenhouses.logic_profile` (compiled bundle namespace `greenhouse.logic_profile`) и телеметрию из read-model
4. публикует команды только через `history-logger` `POST /commands` с `cmd='set_position'`
5. обновляет строку `greenhouse_automation_state` (в т.ч. snapshot полей для UI)
6. полная семантика, метрики и DD — в `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`

### 7.3 `GET /internal/tasks/{task_id}`

Canonical status endpoint для зон на `ae3`.

Минимальный ответ:
1. `task_id`
2. `zone_id`
3. `task_type`
4. `status`
5. `error_code`
6. `error_message`
7. `created_at`
8. `updated_at`
9. `completed_at`

### 7.4 Internal operator/runtime API

В `v1` разрешены internal endpoints:
1. `/zones/{id}/state`
2. `/zones/{id}/control-mode`
3. `/zones/{id}/manual-step`

Ограничения:
1. они не публикуют команды напрямую и работают только поверх canonical AE3 task path;
2. public backward-compatible `FORCE_IRRIGATION` в Laravel обязан маршрутизироваться в
   `POST /zones/{id}/start-irrigation`, а не в direct device command.
3. `control_mode='manual'` запрещает только автоматические `start/stop` переходы, инициируемые самим AE3 по обычному poll-loop; hardware-originated safe/runtime events (`*_completed`, `*_source_empty`, `*_solution_low`, `emergency_stop_activated`) обязаны продолжать проходить через reconcile.

### 7.5 Config mode API (Phase 5, 2026-04-15)

Управление `config_mode` (locked/live), live-edit активной recipe phase и fine-tuning correction runtime:

- `GET  /api/zones/{zone}/config-mode` — возвращает текущий state: `{config_mode, config_revision, live_until, live_started_at, config_mode_changed_at, config_mode_changed_by}`. Доступ: any authenticated user с policy `view`.
- `PATCH /api/zones/{zone}/config-mode` — переключение locked↔live. Body: `{mode, reason, live_until?}`.
  - Role middleware: `role:operator,admin,agronomist,engineer`
  - Policy `setLive` (agronomist/engineer/admin) дополнительно проверяется при переходе в live
  - 409 `CONFIG_MODE_CONFLICT_WITH_AUTO` если zone в `control_mode='auto'` при переходе в live
  - 422 `TTL_OUT_OF_RANGE` если TTL < 5 min или > 7 days
  - На success: atomic update + audit row `zone_config_changes{namespace='zone.config_mode'}`
- `PATCH /api/zones/{zone}/config-mode/extend` — продление live TTL. Body: `{live_until}`.
  - Role: `role:admin,agronomist,engineer`
  - Внутри `DB::transaction` + `Zone::lockForUpdate()` — защита от race с TTL cron
  - 409 `NOT_IN_LIVE_MODE` если zone в locked
  - 422 `TTL_TOTAL_EXCEEDED` если суммарное время от `live_started_at` > 7 days
- `GET  /api/zones/{zone}/config-changes?namespace=...&limit=50` — history timeline из `zone_config_changes`.
- `PUT  /api/grow-cycles/{growCycle}/phase-config` — live edit setpoint'ов активной recipe phase. Body: `{reason, ph_target?, ph_min?, ph_max?, ec_target?, ec_min?, ec_max?, temp_air_target?, humidity_target?, co2_target?, irrigation_{interval,duration}_sec?, lighting_photoperiod_hours?, lighting_start_time?, mist_{interval,duration}_sec?}`.
  - Role middleware: `role:admin,agronomist,engineer` + policy `setLive`
  - 409 `ZONE_NOT_IN_LIVE_MODE` если zone в locked — invariant: recipe.phase mutation only in live
  - 409 `NO_ACTIVE_PHASE` если у цикла нет `current_phase_id`
  - 422 `NO_FIELDS_PROVIDED` если payload не содержит whitelisted полей
  - Flow: `GrowCyclePhase::lockForUpdate()` → `forceFill(whitelisted)` → `compileGrowCycleBundle(cycle.id)` → `ZoneConfigRevisionService::bumpAndAudit(namespace='recipe.phase')`
- `PUT /api/zones/{zone}/correction/live-edit` — live edit correction/PID/observe/process calibration. Body: `{reason, phase?, correction_patch?, calibration_patch?}`.
  - Role middleware: `role:admin,agronomist,engineer` + policy `setLive`
  - `phase` общий для обоих patch'ей: без `phase` correction patch идёт в `base_config.*`; с `phase` — в `phase_overrides.{phase}.*`; `calibration_patch` пишет в `zone.process_calibration.{phase}`
  - 409 `ZONE_NOT_IN_LIVE_MODE` если zone в locked
  - 422 `NO_FIELDS_PROVIDED` если оба patch'а пусты
  - 422 `PATH_NOT_WHITELISTED` если в payload есть path вне live-edit whitelist
  - 422 `CALIBRATION_PHASE_REQUIRED` если передан `calibration_patch` без `phase`
  - 422 `CALIBRATION_PHASE_UNKNOWN` если `phase` не входит в `generic|solution_fill|tank_recirc|irrigation` для calibration patch
  - Success: один `bumpAndAudit(namespace='zone.correction.live')` на весь request, даже если одновременно меняются `zone.correction` и `zone.process_calibration.*`
- **Background cron**: `automation:revert-expired-live-modes` (Laravel scheduler `everyMinute`) — flip истёкших live в locked + `CONFIG_MODE_AUTO_REVERTED` event.

**Authorization invariants:**
- operator может переключать только в locked (через `update` policy), live — нельзя
- viewer не может редактировать config
- admin / agronomist / engineer — любые операции

**Revision bump invariant:**
- Любой PUT zone-scoped namespace (`zone.correction`, `zone.logic_profile`, ...) или `recipe.phase` через live-edit endpoint автоматически вызывает `ZoneConfigRevisionService::bumpAndAudit` через атомарный SQL `UPDATE zones SET config_revision = COALESCE(config_revision, 0) + 1 WHERE id = ? RETURNING`
- AE3 `_checkpoint` сравнивает `zones.config_revision` с `plan.runtime.config_revision` → hot-swap при advance

**Cascade bundle recompile (критично для live-mode понимания):**

`AutomationConfigDocumentService::upsertDocument(...)` после сохранения document'а вызывает `AutomationConfigCompiler::compileAffectedScopes($scopeType, $scopeId)`, который для `scopeType='zone'` делегирует `compileZoneCascade(zoneId)`:

1. `compileZoneBundle(zoneId)` — пересобирает `automation_effective_bundles` scope='zone' для этой zone
2. Для всех `GrowCycle::active()` с `zone_id = $zoneId` — `compileGrowCycleBundle(cycleId)` пересобирает snapshot bundle scope='grow_cycle'

Аналогично, `GrowCyclePhaseConfigController::update` после `forceFill` на `grow_cycle_phases` явно вызывает `compileGrowCycleBundle(growCycle->id)` (без zone cascade — phase принадлежит только одному cycle).

Это означает: к моменту когда AE3 `_checkpoint()` делает `PgZoneSnapshotReadModel().load(zone_id)` и читает `automation_effective_bundles WHERE scope_type='grow_cycle'`, bundle уже отражает свежую config. Нет race window между PUT commit и AE3 read — recompile происходит синхронно в том же request'е, под той же `DB::transaction` (внутри `ZoneConfigRevisionService::bumpAndAudit` или controller-level). Hot-swap всегда читает committed state.

**Idempotent PUT semantics:** любой PUT с тем же payload всё равно bump'ает revision → `CONFIG_HOT_RELOADED` event эмитится → metric `applied` инкрементится. Это accepted trade-off: идемпотентность на уровне содержимого не реализована ради простоты. Handler rebuild при том же payload — no-op для observable behaviour (fresh RuntimePlan структурно идентичен previous), но revision counter продвигается.

---

---

## 9. Recovery и failure model

### 9.1 Startup recovery

> **Roadmap:** детальный план улучшений (фазы 1–6, матрица состояний, критерии приёмки) —  
> `doc_ai/04_BACKEND_CORE/AE3_STARTUP_RECOVERY_IMPROVEMENT_PLAN.md`.

При старте runtime обязан:
1. проверить `waiting_command` задачи по строкам в `commands`
2. если terminal уже есть, корректно финализировать task
3. `claimed|running` без подтверждённой активной внешней команды перевести в `failed` с контролируемым `error_code`
4. **исключение (фаза 2):** если у `claimed|running` последняя `ae_commands` + legacy `commands` уже terminal `DONE`, recovery выполняет тот же topology transition, что и для `waiting_command` + DONE (без republish в MQTT)
5. если у `claimed|running` команда ещё не terminal — перевести задачу в `waiting_command` и оставить на reconcile (без fail)
6. освободить lease с истёкшим `leased_until` и при recovery-fail владельца задачи
7. фоновый reconcile `waiting_command` задач (`WaitingCommandReconcileUseCase` в worker loop) без republish
8. не создавать retry storm
9. **graceful shutdown (фаза 4):** при `SIGTERM`/остановке lifespan worker перестаёт claim'ить новые задачи, ждёт in-flight до `AE_SHUTDOWN_GRACE_SEC` (default 30 с); `claimed|running` без `ae_commands` откатывается в `pending` с release zone lease
10. **multi-instance (фаза 6):** `StartupRecoveryUseCase.run()` берёт PostgreSQL session advisory lock (`ae3_startup_recovery`); второй экземпляр AE пропускает проход recovery без сканирования задач. Алерты recovery-fail дедуплицируются ключом `biz_ae3_task_failed:{zone_id}:{task_id}:{recovery_source}`. В production рекомендуется **один активный writer** на зону (lease + partial unique index); при нескольких репликах AE координированный recovery обязателен.

### 9.2 Crash windows

Для `v1` обязательно покрыть тестами минимум такие окна (контрактный suite: `test_ae3lite_startup_recovery_crash_windows.py`, `make test-ae-crash-windows`):

1. crash до записи `ae_commands`
2. crash после записи `ae_commands`, но до publish
3. crash после publish, но до локального обновления статуса
4. crash в `waiting_command`
5. delayed terminal status после restart

### 9.3 Failure policy

1. Runtime работает fail-closed.
2. Stale critical telemetry приводит к fail.
3. Неопределённое состояние команды трактуется как incident, а не как success.
4. Recovery не должен повторно публиковать команду без явного безопасного основания.
5. Whole-task execution timeout трактуется как terminal runtime failure, а не как мягкий retry сигнал.

### 9.4 Минимальная observability

#### 9.4.1 UI state payload (`observability`)

**Эндпоинты:** `GET /zones/{zone_id}/state` (AE3) → proxy `GET /api/zones/{id}/state` (Laravel).

**Реализация AE3:**
- модуль `ae3lite/application/services/automation_observability.py` (`build_automation_observability`);
- интеграция в `GetZoneAutomationStateUseCase` (`_attach_observability`) для active/idle/failed path;
- входы: active `ae_task`, `zone_workflow_state`, telemetry read-model, `ZONE_NODES_DIAG_SQL`.

**Реализация Laravel:**
- `ZoneAutomationObservabilityService::enrichPayload($zoneId, $payload, $isStale)`;
- вызывается из `ZoneAutomationStateController::decorateStatePayload`;
- кэш AE payload: TTL 300 с; при `is_stale` runtime/nodes/hints пересобираются из PostgreSQL.

**Ключевые инварианты:**
1. AE — source of truth для runtime-hints на **live** path; Laravel не дублирует `stage_elapsed_long` поверх AE.
2. На **stale cache** Laravel заменяет `observability.runtime` данными из `ae_tasks` + `zone_workflow_state`.
3. Scheduler-hints (`scheduler_intent_*`) генерируются только Laravel из `zone_automation_intents`.
4. `waiting_elapsed_sec` для `waiting_command` считается от `task.updated_at`, не только от `stage_entered_at`.
5. Level-hints (`level_*_unlatched`) эмитятся только на релевантных check-стадиях при доступной telemetry.

Полная схема полей, таблица hint-кодов и пороги — `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md` §3.5.7.

#### 9.4.2 Prometheus / events

Prometheus runtime минимум для lifecycle intents:
1. `ae3_intent_claimed_total{source_status}`
2. `ae3_intent_terminal_total{status}`
3. `ae3_intent_stale_reclaimed_total`

Дополнительно сохраняются обязательные command/runtime метрики:
1. `ae3_command_dispatched_total`
2. `ae3_command_dispatch_duration_seconds`
3. `ae3_command_terminal_total`
4. `ae3_tick_duration_seconds`
5. `ae3_fail_safe_transition_total{topology,stage,reason,source}`
6. `ae3_emergency_stop_reconcile_total{topology,stage,outcome}`
7. `ae3_node_runtime_event_kick_total{event_type,channel}`

Минимальные event/log точки для irrigation observability:
1. `AE_TASK_STARTED` включает `bundle_revision` и locked irrigation decision strategy при наличии
2. `IRRIGATION_DECISION_SNAPSHOT_LOCKED` фиксирует strategy/config/bundle_revision для текущего irrigation task; на первом run event эмитится даже если snapshot уже был записан в `ae_tasks` на create-path
3. fail-safe stop path обязан писать service-log `AE3 fail-safe transition selected` с `zone_id/task_id/topology/stage/reason/source/next_stage`
4. reconcile после `EMERGENCY_STOP_ACTIVATED` обязан писать service-log с outcome `restored` или `failed`
5. wake-up по node runtime event обязан инкрементировать `ae3_node_runtime_event_kick_total` и писать service-log `AE3 worker.kick by node runtime event`
6. `IRRIGATION_CORRECTION_STARTED`, `CORRECTION_DECISION_MADE`, `EC_DOSING`, `PH_CORRECTED` обязаны нести `current_stage`; при наличии probe-context обязаны также нести `snapshot_event_id` и `caused_by_event_id`
7. Для irrigation inline correction `snapshot_event_id` обязан ссылаться на `zone_events.id` события `IRR_STATE_SNAPSHOT`, по которому подтверждён активный flow path (`pump_main=true`)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

---

## 10. Rollout и rollback

### 10.1 Rollout

Rollout выполняется только вручную:
1. выбрать pilot zone
2. убедиться, что active task и active lease отсутствуют
3. установить `zones.automation_runtime='ae3'`
4. перезапустить `automation-engine`
5. выполнить smoke:
   - `start-cycle`
   - task status poll
   - command publish
   - terminal reconcile

### 10.2 Rollback

Controlled stop выполняется вручную:
1. убедиться, что для зоны нет активной AE3 task или выполнить controlled stop по runbook
2. не возвращать прежний режим runtime в БД
3. перезапустить `automation-engine`
4. незавершённые AE3 tasks оставить в БД для расследования
5. ручной destructive cleanup запрещён

### 10.3 Handoff rule

Переключение runtime на зоне запрещено:
1. при active task
2. при active lease
3. при `waiting_command`
4. при неопределённом command terminal state

---

## 11. Минимальная кодовая структура

Дерево актуально на 2026-05-28; точные имена файлов — в `backend/services/automation-engine/ae3lite/`.

```text
backend/services/automation-engine/ae3lite/
├── api/
│   ├── compat_endpoints.py            # start-cycle / start-irrigation / start-lighting-tick
│   ├── internal_endpoints.py          # GET /internal/tasks/{task_id}
│   ├── greenhouse_climate_compat.py   # POST /greenhouses/{id}/start-climate-tick
│   ├── security.py
│   └── rate_limit.py
├── application/
│   ├── use_cases/
│   │   ├── create_task_from_intent.py
│   │   ├── claim_next_task.py
│   │   ├── execute_task.py
│   │   ├── finalize_task.py
│   │   ├── startup_recovery.py        # recovery после restart (включая waiting_command)
│   │   ├── set_control_mode.py
│   │   └── request_manual_step.py
│   ├── handlers/                      # stage handlers: startup, *_fill_*, prepare_recirc_*,
│   │                                  # await_ready, decision_gate, irrigation_*, correction,
│   │                                  # base.py с _checkpoint hot-reload
│   ├── services/
│   │   ├── workflow_topology.py       # TWO_TANK graph (StageDef + transitions)
│   │   ├── workflow_router.py         # запуск handler, перевод StageOutcome в update_stage
│   │   ├── topology_registry.py
│   │   └── correction_transition_policy.py
│   └── adapters/                      # intent mapping
├── config/
│   ├── runtime_plan_builder.py        # resolve_two_tank_runtime_plan
│   └── ...                            # Pydantic schemas, loaders
├── domain/
│   ├── entities/
│   │   ├── automation_task.py         # AutomationTask + ACTIVE_TASK_STATUSES
│   │   ├── planned_command.py
│   │   ├── zone_lease.py
│   │   └── zone_workflow.py
│   ├── services/
│   │   ├── cycle_start_planner.py
│   │   ├── correction_planner.py
│   │   └── irrigation_decision_controller.py
│   ├── value_objects.py
│   └── errors.py                      # ErrorCodes + domain exceptions
├── infrastructure/
│   ├── repositories/
│   │   ├── automation_task_repository.py    # claim/update_stage/mark_*/release_claim
│   │   ├── zone_workflow_repository.py
│   │   ├── zone_lease_repository.py
│   │   ├── ae_command_repository.py
│   │   └── pid_state_repository.py
│   ├── gateways/
│   │   └── sequential_command_gateway.py    # publish + recover_waiting_command polling
│   ├── clients/
│   │   └── history_logger_client.py
│   ├── read_models/
│   │   ├── zone_snapshot_read_model.py
│   │   ├── task_status_read_model.py
│   │   ├── zone_runtime_monitor.py
│   │   └── laravel_schema_contract.py       # contract + NOTIFY_CHANNELS
│   ├── intent_status_listener.py            # LISTEN scheduler_intent_terminal
│   ├── zone_event_listener.py               # LISTEN ae_zone_event
│   └── metrics.py
├── runtime/
│   ├── worker.py                      # Ae3RuntimeWorker (drain loop, lease heartbeat)
│   ├── bootstrap.py                   # build_ae3_runtime_bundle()
│   ├── env.py                         # Ae3RuntimeConfig.from_env()
│   └── app.py                         # create_app() / serve()
├── greenhouse_climate/                # rule-based roof vent tick
└── main.py
```

Правила:
1. один публичный use case или один публичный класс на файл
2. без module-level mutable state
3. DTO и domain objects не смешиваются
4. compatibility code живёт только в adapter/facade слое (`application/adapters/`)
5. модулей `reconcile_command.py` и `runtime/recovery.py` в актуальном дереве **нет**: command reconcile реализован в `gateways/sequential_command_gateway.py::recover_waiting_command`, startup-recovery — в `use_cases/startup_recovery.py`.

---

## 12. Обязательные тесты v1

### 12.1 Unit

1. task status transitions
2. lease rules
3. workflow CAS update
4. `CycleStartPlanner` decisions
5. DONE-only policy

### 12.2 Integration

1. active task uniqueness
2. lease claim/reclaim
3. `history-logger` publish contract
4. `commands` reconcile
5. startup recovery
6. runtime switch denied while zone busy

### 12.3 E2E

1. `start-cycle -> DONE -> completed`
2. `start-cycle -> TIMEOUT -> failed`
3. `start-irrigation(normal) -> decision=skip -> completed`
4. `start-irrigation(force) -> DONE -> completed`
5. `restart during waiting_command -> recovered`
6. `runtime switch denied while zone busy`

### 12.4 Правило тестирования по этапам

1. Каждый этап реализации обязан завершаться запуском своих unit/integration тестов.
2. Переход к следующему этапу запрещён без зелёного результата stage-level tests.
3. Отсутствие тестов для этапа означает, что этап не завершён.
4. Тесты в конце всей работы не заменяют тесты по этапам.
5. После завершения всей реализации агент обязан покрыть недостающие критические сценарии.
6. После этого агент обязан прогнать весь обязательный `e2e`-набор и получить зелёный результат.
7. Если полный `e2e`-набор не пройден, `v1` считается неготовым независимо от статуса unit/integration тестов.

---

## 13. Definition of Done

AE3-Lite `v1` считается готовым, когда выполнены все условия:
1. Реализованы production paths: `cycle_start`, `irrigation_start`, `lighting_tick`, `greenhouse_climate_tick` (последний — только через `POST /greenhouses/{id}/start-climate-tick`).
2. Вход в zone runtime — через `POST /zones/{id}/start-cycle`, `POST /zones/{id}/start-irrigation`, `POST /zones/{id}/start-lighting-tick`; вход в greenhouse climate — через `POST /greenhouses/{id}/start-climate-tick`.
3. Для зоны одновременно невозможны два активных execution task на уровне DB constraints и runtime lease; для теплицы — два конкурирующих climate-writer (см. `greenhouse_automation_leases`).
4. Все команды публикуются только через `history-logger`, без прямого MQTT publish из AE/Laravel.
5. Terminal source of truth для command outcome в `v1` явно определён как таблица `commands`.
6. Успех mutating step подтверждается только terminal `DONE`.
7. После restart runtime корректно восстанавливает `waiting_command` и не создаёт повторный publish без явного безопасного основания.
8. Переключение `zones.automation_runtime` на `ae3` запрещено при активной задаче или активной lease.
9. Реализован canonical status endpoint `GET /internal/tasks/{task_id}`.
10. Laravel poller читает status только из canonical task API для зон на `ae3`.
11. Пройдены обязательные integration/e2e сценарии:
    - `start-cycle -> DONE -> completed`
    - `start-cycle -> TIMEOUT -> failed`
    - `start-irrigation(normal) -> decision=skip -> completed`
    - `start-irrigation(force) -> DONE -> completed`
    - `restart during waiting_command -> recovered`
    - `runtime switch denied while zone busy`
    - `start-climate-tick -> HL set_position -> snapshot в greenhouse_automation_state` (см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`)
12. Каждый этап реализации был покрыт и проверен своими stage-level tests до перехода к следующему этапу.
13. После завершения реализации покрыт и пройден полный обязательный `e2e`-набор.
14. На staging выполнен как минимум один воспроизводимый rollout и один rollback.
15. Как минимум одна production зона отработала на `automation_runtime='ae3'` без двойного исполнения и без ручного ремонта БД.
16. В `ae3lite/*` нет импортов из пакетов прежнего monolithic runtime вне `ae3lite/`.
17. Реализация была выполнена одним ИИ-агентом без отклонений от порядка работ из раздела 3.
18. Для каждого зафиксированного отклонения выполнены self-stop, corrective rollback и дополнительный тест.
19. Всё, что не входит в этот список, считается out of scope для `v1`.

---

## 13bis. ExecutionChainAssembler (Scheduler Cockpit, Phase 2 UI redesign)

Сервис `App\Services\Scheduler\ExecutionChainAssembler` — собирает
read-model «причинно-следственной цепочки» для отображения в Cockpit-UI
планировщика. **Не меняет поведение AE3 runtime** — только агрегирует
существующие данные из `ae_tasks`, `zone_events`, `commands`.

Возвращает array шагов в порядке: `SNAPSHOT → DECISION → TASK → DISPATCH →
RUNNING → COMPLETE | FAIL | SKIP`. Каждый шаг:

```
{ step, at, ref, detail, status: 'ok'|'err'|'skip'|'run'|'warn', live? }
```

Источники данных:

| Шаг | Поля из БД |
|-----|------------|
| SNAPSHOT | `ae_tasks.corr_snapshot_event_id` → `zone_events.payload_json` |
| DECISION | `ae_tasks.irrigation_decision_*` / `corr_step` / `irrigation_bundle_revision` |
| TASK     | `ae_tasks.id` + `ae_tasks.intent_id` → `zone_automation_intents.idempotency_key` |
| DISPATCH | `commands` по `cmd_id = ae_tasks.corr_snapshot_cmd_id` (fallback: `request_id = intent.idempotency_key`) |
| RUNNING  | `commands.ack_at` или `ae_tasks.claimed_at`. Не добавляется для SKIP-решений и pending-задач. |
| COMPLETE/FAIL/SKIP | `ae_tasks.status` + `error_code` + `irrigation_decision_outcome=='skip'` |

Live-обновления идут через webhook от history-logger-а (см.
[REST_API_REFERENCE.md §16.1](REST_API_REFERENCE.md#161-webhook-history-logger--laravel-scheduler-cockpit-causal-chain))
и broadcast `ExecutionChainUpdated` на канал `hydro.zone.executions.{zoneId}`.

## 14. Что дальше, но не в этом документе

После успешного `v1` отдельными RFC могут обсуждаться:
1. дополнительные task types
2. runtime API parity с прежней версией automation runtime
3. multi-replica deployment
4. более сложный rollout controller
5. отдельные safety/recovery workflows

Эти пункты не должны возвращаться в canonical spec `v1` задним числом.
