# AE3-Lite: Minimal Canonical Spec

**Версия:** 3.5-canonical
**Дата:** 2026-04-04
**Статус:** CANONICAL MINIMAL SPEC

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Роль документа

`ae3lite.md` задаёт минимальный исполнимый контракт для `AE3-Lite`.

Это не roadmap, не RFC на всю evolution runtime и не план на множество параллельных агентов.
Цель документа одна: зафиксировать минимальный scope `v1`, который можно безопасно
реализовать и проверить в production на ограниченном числе зон.

Если требование не нужно для `cycle_start` или `irrigation_start` runtime v1, его в этом документе быть не должно.
Этот план рассчитан на выполнение одним ИИ-агентом последовательно, без распараллеливания deliverables.

---

## 1. Scope v1

AE3-Lite v1 это:
1. DB-backed executor для `cycle_start` и `irrigation_start`.
2. Protected command pipeline без изменений:
   `Laravel scheduler-dispatch -> Automation-Engine -> history-logger -> MQTT -> ESP32`.
3. Внешние ingress (scheduler/API compat):
   `POST /zones/{id}/start-cycle`, `POST /zones/{id}/start-irrigation`,
   `POST /zones/{id}/start-lighting-tick` (dispatch света для `zones.automation_runtime='ae3'`, см. C1).
4. Один canonical status endpoint:
   `GET /internal/tasks/{task_id}`.
5. Ручной rollout по зоне через `zones.automation_runtime='ae3'`.
6. Recovery после restart для `claimed|running|waiting_command`.

AE3-Lite v1 не включает:
1. `lighting_tick`
2. `ventilation_tick`
3. `solution_change`
4. `mist`
5. `diagnostics`
6. `recovery` как отдельный business task
7. native `GET /zones/{id}/state`
8. relay-autotune runtime как отдельный business task
9. multi-replica runtime
10. auto-canary router
11. auto-rollback controller
12. outbox/domain-events platform
13. generic workflow framework

---

## 2. Неподвижные инварианты

1. Команды на узлы публикуются только через `history-logger` (`POST /commands`).
2. Прямой MQTT publish из AE и Laravel запрещён.
3. До полного cutover внешние ingress runtime ограничены `POST /zones/{id}/start-cycle`,
   `POST /zones/{id}/start-irrigation` и `POST /zones/{id}/start-lighting-tick` (см. §1 scope).
4. В production v1 допускается только одна активная реплика AE3-Lite.
5. На одну зону допускается не более одной активной execution task.
6. Успешный terminal outcome mutating-команды только `DONE`.
7. `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` считаются fail для v1.
8. Runtime path не зависит от runtime HTTP-вызовов в Laravel.
9. Runtime читает zone state напрямую из PostgreSQL read-model.
10. Изменения БД выполняются только через Laravel migrations.
11. `ae3lite/*` не импортирует пакеты прежнего monolithic runtime вне `ae3lite/`.
12. Переключение зоны на `ae3` запрещено при активной task или активной lease.
13. План выполняется одним ИИ-агентом, строго последовательно, без параллельных веток работ.
14. Любое отклонение от этого документа считается defect, а не “допустимой импровизацией”.

### 2.1 Фаза зоны `ready` и стадия `await_ready` (полив)

Источник истины для «зона готова к поливу» в runtime плана — поле **`zone_workflow_phase`** в snapshot зоны (read-model), которое AE3-Lite кладёт в `plan.runtime` при планировании (`CycleStartPlanner` / аналог). Значение **`ready`** означает: workflow зоны в PostgreSQL (`zone_workflow_state.workflow_phase`) приведён в состояние готовности после завершения подготовительных шагов (например, после успешного `cycle_start` / завершения связанной задачи в `WorkflowRouter`).

Стадия **`await_ready`** в задаче `irrigation_start`:

1. Пока `zone_workflow_phase != ready`, исполнитель возвращает **poll** с интервалом `AE_IRRIGATION_WAIT_READY_POLL_SEC` и при первом заходе фиксирует дедлайн `irrigation_wait_ready_deadline_at` (окно `AE_IRRIGATION_WAIT_READY_SEC`).
2. Когда snapshot даёт **`ready`**, стадия переходит в **`decision_gate`** (дальнейшие решения по поливу).
3. Если дедлайн истёк, задача завершается с ошибкой **`irrigation_wait_ready_timeout`**; при этом пишется structured log, zone event `IRRIGATION_WAIT_READY_TIMEOUT`, опционально business alert `biz_irrigation_wait_ready_timeout` (dedupe по зоне/задаче), инкрементируются метрики `ae3_irrigation_wait_ready_*`.

Связка «цикл → готовность → полив» не должна обходить этот контракт: нельзя полагаться на устаревший snapshot без poll/reconcile.

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
2. добавлять новые task types вне `cycle_start|irrigation_start|lighting_tick`
3. добавлять новые API вне `POST /zones/{id}/start-cycle`,
   `POST /zones/{id}/start-irrigation`, `POST /zones/{id}/start-lighting-tick` и `GET /internal/tasks/{task_id}`
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
10. для `solution_fill_check` attempt caps не закрывают correction window: stage живёт под общим `solution_fill_timeout_sec` и останавливает коррекцию только по `no-effect` fail-closed или по stage timeout.

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

В `v1` разрешены два business task:
1. `cycle_start`
2. `irrigation_start`

Другие task types считаются out of scope и не должны появляться
ни в migration, ни в API, ни в runtime wiring `v1`.

### 4.3 Task statuses

Main path:
`pending -> claimed -> running -> waiting_command -> completed`

Terminal:
`failed | cancelled`

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

`startup` как отдельная `workflow_phase` не существует: возврат в startup кодируется как
`workflow_phase='idle'` + `payload.ae3_cycle_start_stage='startup'`.

---

## 5. Runtime flow

### 4.1 High-level sequence

1. `POST /zones/{id}/start-cycle` или `POST /zones/{id}/start-irrigation`
   валидирует контракт и создаёт canonical `AutomationTask(status=pending)`.
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
13. Если зона была в `ready`, но `solution_min` датчик сработал, runtime обязан
    auto-reset `zone_workflow_state` обратно в `idle/startup`, чтобы зона больше
    не считалась готовой к поливу до следующего `cycle_start`.

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
4. Runtime обязан жёстко ограничивать tracked background tasks; переполнение registry не может игнорироваться и должно отклоняться fail-closed.
5. Полное исполнение `ExecuteTaskUseCase.run()` должно быть ограничено `AE_MAX_TASK_EXECUTION_SEC` (default `900s`); timeout не может оставлять task в подвешенном active state.
6. Timeout whole-task execution обязан идти по fail-closed path: worker отменяет run с внутренней причиной `ae3_task_execution_timeout`, runtime выполняет fail-safe shutdown актуаторов, затем завершает task/intent как `failed`.
7. Обычная отмена процесса/loop shutdown не должна маскироваться под timeout: recovery path после restart остаётся отдельным механизмом.
8. Fail-safe shutdown команды публикуются как publish-only batch: они не должны повторно переводить уже terminal/closing task в `waiting_command` и не должны искажать `ae_commands` ложным `publish_failed`, если устройство реально подтвердило shutdown после terminal failure основной задачи.
9. Перед fail-closed terminal transition runtime обязан синхронизировать `zone_workflow_state` обратно в `workflow_phase='idle'`, чтобы stale phase не переживала terminal failure task.

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
6. `zone.correction.payload.resolved_config` для AE3 correction runtime считается полным обязательным контрактом:
   отсутствие required field в `runtime/timing/dosing/retry/tolerance/controllers/safety`
   должно приводить к fail-closed, без silent fallback на catalog defaults или устаревшие
   `diagnostics.execution.*`.

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
1. `task_type IN ('cycle_start', 'irrigation_start')` для всех записей `v1`
2. уникальность `idempotency_key` в допустимом scope
3. не более одной активной task на `zone_id`
4. terminal task не может вернуться в active status
5. runtime state irrigation decision/replay хранится в explicit typed columns, а не в произвольном JSON `payload`

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

---

## 9. Recovery и failure model

### 9.1 Startup recovery

При старте runtime обязан:
1. проверить `waiting_command` задачи по строкам в `commands`
2. если terminal уже есть, корректно финализировать task
3. `claimed|running` без подтверждённой активной внешней команды перевести в `failed` с контролируемым `error_code`
4. освободить lease с истёкшим `leased_until`
5. не создавать retry storm

### 9.2 Crash windows

Для `v1` обязательно покрыть тестами минимум такие окна:
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

Prometheus runtime минимум для lifecycle intents:
1. `ae3_intent_claimed_total{source_status}`
2. `ae3_intent_terminal_total{status}`
3. `ae3_intent_stale_reclaimed_total`

Дополнительно сохраняются обязательные command/runtime метрики:
1. `ae3_command_dispatched_total`
2. `ae3_command_dispatch_duration_seconds`
3. `ae3_command_terminal_total`
4. `ae3_tick_duration_seconds`

Минимальные event/log точки для irrigation observability:
1. `AE_TASK_STARTED` включает `bundle_revision` и locked irrigation decision strategy при наличии
2. `IRRIGATION_DECISION_SNAPSHOT_LOCKED` фиксирует strategy/config/bundle_revision для текущего irrigation task; на первом run event эмитится даже если snapshot уже был записан в `ae_tasks` на create-path

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

```text
backend/services/automation-engine/ae3lite/
├── api/
│   ├── compat_endpoints.py
│   └── internal_endpoints.py
├── application/
│   ├── adapters/
│   │   └── <intent adapter>.py
│   └── use_cases/
│       ├── create_task_from_intent.py
│       ├── claim_next_task.py
│       ├── execute_task.py
│       ├── reconcile_command.py
│       └── finalize_task.py
├── application/handlers/
│   ├── await_ready.py
│   ├── decision_gate.py
│   ├── irrigation_check.py
│   └── irrigation_recovery.py
├── domain/
│   ├── entities/
│   │   ├── automation_task.py
│   │   ├── planned_command.py
│   │   ├── zone_lease.py
│   │   └── zone_workflow.py
│   ├── services/
│   │   ├── cycle_start_planner.py
│   │   └── irrigation_decision_controller.py
│   ├── value_objects.py
│   └── errors.py
├── infrastructure/
│   ├── repositories/
│   ├── gateways/
│   └── read_models/
├── runtime/
│   ├── worker.py
│   └── recovery.py
└── main.py
```

Правила:
1. один публичный use case или один публичный класс на файл
2. без module-level mutable state
3. DTO и domain objects не смешиваются
4. compatibility code живёт только в adapter/facade слое (`application/adapters/`, фактическое имя модуля см. в репозитории)

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
1. Реализованы только два production task type: `cycle_start` и `irrigation_start`.
2. Вход в runtime идёт только через `POST /zones/{id}/start-cycle` и `POST /zones/{id}/start-irrigation`.
3. Для зоны одновременно невозможны два активных execution task на уровне DB constraints и runtime lease.
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
12. Каждый этап реализации был покрыт и проверен своими stage-level tests до перехода к следующему этапу.
13. После завершения реализации покрыт и пройден полный обязательный `e2e`-набор.
14. На staging выполнен как минимум один воспроизводимый rollout и один rollback.
15. Как минимум одна production зона отработала на `automation_runtime='ae3'` без двойного исполнения и без ручного ремонта БД.
16. В `ae3lite/*` нет импортов из пакетов прежнего monolithic runtime вне `ae3lite/`.
17. Реализация была выполнена одним ИИ-агентом без отклонений от порядка работ из раздела 3.
18. Для каждого зафиксированного отклонения выполнены self-stop, corrective rollback и дополнительный тест.
19. Всё, что не входит в этот список, считается out of scope для `v1`.

---

## 14. Что дальше, но не в этом документе

После успешного `v1` отдельными RFC могут обсуждаться:
1. дополнительные task types
2. runtime API parity с прежней версией automation runtime
3. multi-replica deployment
4. более сложный rollout controller
5. отдельные safety/recovery workflows

Эти пункты не должны возвращаться в canonical spec `v1` задним числом.
