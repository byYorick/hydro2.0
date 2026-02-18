# AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md
# AE2: мастер-план для ИИ-ассистентов (эволюционное развитие)

**Версия:** v1.5  
**Дата:** 2026-02-18  
**Статус:** REVIEWED_AFTER_DEEP_CODE_CRITIQUE_AND_EXECUTION_GAP_HARDENING  
**Область:** `backend/services/automation-engine*`, `backend/services/scheduler`, `backend/laravel`, `tests/e2e`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.  
Breaking-change: Big Bang rewrite отменен; AE2 внедряется эволюционно поверх текущего automation-engine с feature-flag cutover.

## Что изменено в v1.5

1. Скорректировано описание реальных активов: `WorkflowRouter` зафиксирован как `route_diagnostics`-router, а не универсальный topology-dispatch.
2. В P0 добавлен обязательный аудит двух God Object: `scheduler_task_executor/scheduler_executor_impl` и `api.py` (крупный orchestration surface).
3. Single-writer уточнен до исполняемой механики: `CommandGateway` + `per-zone lock` + `scheduler-gating` + explicit fallback mode.
4. Safety-priority закреплен: bounds/rate-limit enforcement относится к P2 как safety-critical минимум, а не к поздней фазе.
5. Зафиксирован техдолг monkey-patch в `scheduler_task_executor.py` и обязательная миграция на DI wiring в P1.5.
6. Уточнены topology/shadow/replay-state части: strict topology после DB-gate, fan-out/compare для shadow, crash-safe PID checkpointing.
7. Добавлены CI-верифицируемые критерии P0 и стратегия retirement feature flags.

---

## 1. Цель AE2

Развить `automation-engine` до AE2 как расширяемую и отказоустойчивую платформу полного цикла выращивания:

1. Приоритеты бизнеса:
   - стабильность;
   - скорость роста;
   - автономность.
2. Контролируемые параметры:
   - `pH`;
   - `EC`;
   - уровни баков;
   - полив;
   - освещение;
   - температура воздуха.
3. Контроль границ:
   - hard limits задаются на фронте;
   - базовое правило: `±20%` от целевых параметров (процент задается из UI);
   - для `pH`, `EC`, температуры и критичных уровней обязательны также абсолютные границы (`abs_min/abs_max`);
   - изменение уставок ограничивается по скорости (`max_delta_per_min`), чтобы исключать резкие прыжки.
4. Поведение при потере связи:
   - держать последнее безопасное состояние;
   - отправлять alert;
   - запускать автоматическое восстановление связи.
5. Масштаб:
   - сейчас: 2 теплицы, 5 зон, 5 нод в зоне;
   - через месяц: x2.
6. Аудит и логирование:
   - полный трассируемый audit trail;
   - хранение логов `90` дней по умолчанию, параметр настраивается с фронта.

## 1.1. Стратегия реализации (пивот на hybrid)

AE2 реализуется как **формализация и расширение существующего кода**, а не переписывание всего сервиса с нуля:

1. Сначала in-place эволюция в `backend/services/automation-engine/`.
2. Затем опциональное выделение `automation-engine-v2` только после достижения паритета.
3. Переход через `shadow (отдельный деплой) -> canary -> full`, без остановки эксплуатации.

## 1.2. Что это меняет практически

1. Используем существующие рабочие модули как baseline:
   - `WorkflowRouter`, `WorkflowStateStore`, `CommandBus`, `CorrectionController`,
     `zone_correction_gating`, `_zone_states`.
2. Новые контракты/политики добавляем поверх текущих API и тестов.
3. Любая замена модуля допустима только после прохождения parity-проверок.

## 1.3. Gate до начала реализации

Перед любыми изменениями обязателен завершенный P0-аудит.
Если P0 не завершен, реализация фич кроме диагностики/метрик запрещена.

---

## 2. Жесткие ограничения (не нарушать)

1. Ноды остаются только исполнителями, без бизнес-логики.
2. Команды к нодам идут только через защищенный путь:
   - `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.
3. Пайплайн телеметрии не ломать:
   - `ESP32 -> MQTT -> Python -> PostgreSQL -> Laravel -> Vue`.
4. Изменения backend делать минимально, но допустимо расширять контракт вместе с backend.
5. Контракт `scheduler <-> automation-engine` развивается эволюционно, без необязательных breaking changes.
6. Любые изменения БД только через Laravel-миграции.

---

## 3. Целевая архитектура AE2

## 3.1. Принципы

1. **Extensibility-first**: новая топология или похожий workflow добавляются как плагин, без правки ядра.
2. **Deterministic state machine**: каждое решение и переход повторяемы и восстанавливаемы после рестарта.
3. **Fail-safe networking**: при деградации сети система уходит в безопасный режим, а не в silent-failure.
4. **Audit-first**: у каждого действия есть `trace_id/correlation_id`, причина и результат.
5. **Data-driven policies**: границы, таймауты, retry/backoff приходят из конфигурации, а не хардкодом.

## 3.2. Логическая схема

```text
Scheduler
  -> AE2 Ingress API
    -> Task Journal (durable)
      -> Execution Kernel
        -> Topology Dispatch target (evolved routing layer + variant profiles)
          -> Command Delivery (CommandTracker-first, optional outbox)
            -> History-Logger REST
              -> MQTT -> ESP32
                -> status/telemetry
                  -> AE2 Feedback + State Store
```

## 3.3. Компоненты AE2 (эволюция текущего сервиса)

Этап A (основной): in-place изменения в текущем сервисе:

```text
backend/services/automation-engine/
  application/
    workflow_router.py
    workflow_phase_policy.py
    scheduler_executor_impl.py
  domain/
    workflows/
    policies/
  infrastructure/
    command_bus.py
    command_tracker.py
    command_validator.py
    workflow_state_store.py
  services/
    zone_automation_service.py
    zone_correction_gating.py
```

Этап B (опциональный): выделение `automation-engine-v2/` только после подтвержденного паритета.

## 3.4. Базовые активы, которые переиспользуем

1. Диагностический router (не универсальный topology-dispatch):
   - `backend/services/automation-engine/application/workflow_router.py`
   - текущий публичный фокус: `route_diagnostics(...)` внутри scheduler-driven execution.
2. State machine policy:
   - `backend/services/automation-engine/application/workflow_phase_policy.py`
3. Durable workflow state:
   - `backend/services/automation-engine/infrastructure/workflow_state_store.py`
4. Командный контур:
   - `backend/services/automation-engine/infrastructure/command_bus.py`
   - `backend/services/automation-engine/infrastructure/command_tracker.py`
   - `backend/services/automation-engine/infrastructure/command_validator.py`
5. Continuous loop и backoff/degraded state:
   - `backend/services/automation-engine/services/zone_automation_service.py`
6. Freshness/gating:
   - `backend/services/automation-engine/services/zone_correction_gating.py`
7. PID-контроль:
   - `backend/services/automation-engine/correction_controller.py`

## 3.5. Целевая модель исполнения (single-writer)

Целевая модель AE2:
1. Единственный writer команд в steady-state: scheduler-driven оркестрация (`POST /scheduler/task`).
2. Continuous loop (`ZoneAutomationService.process_zone()`) остается на переходный период:
   - как источник мониторинга/health/gating;
   - без конкурентной оркестрации тех же actuator-команд.

Требование:
1. Исключить race-condition между двумя writer-путями.
2. Зафиксировать режим деградации, при котором fallback в continuous loop включается только по явному флагу.
3. Ввести обязательную механику арбитража:
   - `CommandGateway` как единственная точка решения side-effect publish;
   - `per-zone asyncio.Lock` перед решением о dispatch;
   - scheduler-gating: если в зоне активна scheduler-task orchestration, continuous loop не публикует actuator-команды;
   - fallback публикует команды только в `AE2_FALLBACK_LOOP_WRITER_ENABLED=true`.

## 3.6. Консолидация существующей декомпозиции

Перед любыми архитектурными расширениями:
1. Провести inventory существующих `application/domain/infrastructure` helper-модулей.
2. Убрать дубли и склеить близкие helper-блоки в логические пакеты.
3. Сохранить поведение, покрытое текущими тестами (без потери покрытия).

## 3.7. Явный техдолг: SchedulerTaskExecutor God Object pattern

Текущее состояние:
1. `SchedulerTaskExecutor` остается центром orchestration-логики.
2. Логика разнесена по множеству `executor_bound_*` модулей, но ownership и границы домена остаются размытыми (monolith-in-files).
3. Дополнительно зафиксирован второй God Object: `backend/services/automation-engine/api.py` (крупный orchestration surface, ~2859 строк, stage decomposition в прогрессе).
4. Масштаб декомпозиции выше ожидаемого: большое количество bound/delegate helper-модулей усложняет сопровождение и изменение контракта.

Обязательный deliverable в P0:
1. Инвентаризация `executor_bound_*` с ownership-map (модуль -> ответственность -> owner-слой).
2. Целевая декомпозиция минимум на 6 интерфейсов:
   - `IWorkflowExecutor`
   - `IDiagnosticsExecutor`
   - `IRefillExecutor`
   - `ICommandGateway`
   - `IWorkflowStateCoordinator`
   - `ITaskOutcomeAssembler`
3. Инвентаризация `api.py` по ownership-map и декомпозиционным кандидатам.
4. ADR по реструктуризации coordinator/API и точек миграции с decision-complete выбором:
   - либо доменная декомпозиция с DI boundaries;
   - либо явно утвержденный `monolith-in-files` со строгими ограничениями роста.

Критерий выхода:
1. Coordinator содержит только orchestration-flow.
2. Domain/policy логика удалена из coordinator (остаются только вызовы интерфейсов).
3. Для `api.py` выделены отдельные bounded handlers; orchestration и transport-код не смешиваются.

## 3.8. Полная карта путей публикации команд

В системе зафиксированы следующие пути side-effect публикации команд:

1. Continuous loop:
   - путь: `main.py -> ZoneAutomationService.process_zone() -> controllers -> CommandBus`
   - owner: `automation-engine/runtime loop`
   - steady-state: `monitoring/gating only` (без конкурентного оркестрования scheduler-task).
2. Scheduler task execution:
   - путь: `POST /scheduler/task -> SchedulerTaskExecutor.execute() -> CommandBus`
   - owner: `scheduler-driven orchestration`
   - steady-state: основной writer.
3. Internal enqueue:
   - путь: `scheduler/internal enqueue -> scheduler task lifecycle -> SchedulerTaskExecutor`
   - owner: `automation-engine internal workflows`
   - steady-state: разрешен как продолжение scheduler-driven flow.
4. Correction controller:
   - путь: `CorrectionController.* -> publish_controller_command_* -> CommandBus`
   - owner: `correction subsystem`
   - steady-state: только через policy арбитраж и `CommandGateway`.
5. Controller actions (light/climate/irrigation/recirculation):
   - путь: `zone_controller_processors -> publish_controller_action_with_event_integrity -> CommandBus`
   - owner: `zone controllers`
   - steady-state: только через policy арбитраж и `CommandGateway`.

Целевое правило арбитража:
1. Все side-effect команды проходят через `CommandGateway`.
2. `CommandGateway` применяет single-writer policy, idempotency policy и safety-gates до publish.
3. Любой прямой обход `CommandGateway` считается нарушением архитектурного контракта.
4. Арбитраж выполняется под `per-zone lock` для устранения гонок между concurrent путями.

---

## 4. Модель расширения логики (ключ для похожих “двух баков”)

## 4.1. Что должно расширяться без правки ядра

1. Топология (`two_tank`, `three_tank`, и вариации).
2. Набор workflow-ов (`startup`, `refill_check`, `irrigation_recovery`, новые шаги).
3. Правила коррекции pH/EC и safety-политики.
4. Карта действий по параметрам (`irrigation`, `lighting`, `climate`).

## 4.2. Контракт плагина (lifecycle-aware)

Минимальный обязательный контракт:

1. `initialize(deps: PluginDependencies) -> None`
2. `topology_id() -> str`
3. `supports(task_type, workflow, context) -> bool`
4. `execute(context) -> Result`
5. `fail_forward(context, error) -> RecoveryAction`
6. `checkpoint() -> Dict[str, Any]`
7. `restore(state: Dict[str, Any]) -> None`
8. `health() -> Dict[str, Any]`

`PluginDependencies` (минимум):
1. `CommandGateway`
2. Repository adapters (`Zone/Telemetry/Node/Recipe/...`)
3. Observability adapter (structured log + metrics + alerts)
4. Clock/time provider
5. Feature flag provider

Правила:
1. Плагин не может публиковать команды в MQTT напрямую.
2. Плагин не может публиковать side-effect команды в обход `CommandGateway`.
3. Плагин обязан быть детерминированным при одинаковом входном snapshot.
4. Контракт обязан быть async-safe: без блокирующих операций в event loop.
5. `checkpoint/restore` обязателен для recovery после рестарта.
6. Для физически необратимых действий используется `fail-forward + safety stop`, а не compensating transaction.
7. Расширение контракта выполняется через ADR с backward-compatibility анализом.

## 4.3. Шаблон добавления новой похожей логики

1. Создать новый вариант через `variant profile` от `two_tank_base`, без копипасты ядра.
2. Поменять только декларативные части профиля:
   - карту шагов state machine;
   - preconditions;
   - safety limits;
   - command plan.
3. Зарегистрировать variant в существующем `workflow_router`/routing-слое (без второго параллельного registry-ядра).
4. Добавить:
   - unit-тесты плагина;
   - contract-тесты scheduler payload;
   - минимум 1 e2e сценарий;
   - parity-сравнение с базовым `two_tank_base` на одинаковом входе.

---

## 5. Контракт scheduler <-> AE2 v2 (to-be)

## 5.1. Что меняем

1. Переводим контракт на явный `intent + topology + workflow + bounds + deadlines`.
2. Убираем неявные default workflow и silent fallback в steady-state.
3. Разделяем:
   - `business_status` (owner: AE2),
   - `transport_status` (owner: scheduler).
4. Вводим `topology` как временно optional поле только до завершения topology strict-gate.

## 5.2. Минимальная форма payload (черновой to-be)

```json
{
  "task_id": "uuid",
  "zone_id": 21,
  "topology": "two_tank_drip_substrate_trays",
  "workflow": "startup",
  "task_type": "solution_prepare",
  "targets": {
    "ph": {"target": 6.0},
    "ec": {"target": 1.6}
  },
  "bounds": {
    "ph": {"hard_pct": 20, "abs_min": 5.2, "abs_max": 6.8, "max_delta_per_min": 0.15},
    "ec": {"hard_pct": 20, "abs_min": 0.6, "abs_max": 2.8, "max_delta_per_min": 0.2}
  },
  "timing": {
    "scheduled_for": "2026-02-18T10:00:00Z",
    "due_at": "2026-02-18T10:00:20Z",
    "expires_at": "2026-02-18T10:05:00Z"
  },
  "retry_policy": {
    "max_attempts": 10,
    "backoff_sec": 30
  },
  "delivery": {
    "idempotency_key": "task+step+attempt hash",
    "dedupe_ttl_sec": 3600
  },
  "trace": {
    "correlation_id": "sch:...",
    "initiator": "scheduler",
    "trace_id": "uuid"
  }
}
```

Транспортные security headers (обязательные):

```http
Authorization: Bearer <service-token>
X-Request-Nonce: <uuid>
X-Sent-At: 2026-02-18T10:00:00Z
X-Trace-Id: <trace-id>
```

## 5.3. Что сохраняем для минимальных изменений backend

1. Общая модель REST-взаимодействия scheduler -> AE.
2. Источник целевых параметров через effective-targets/Laravel API.
3. Исторические журналы `zone_events`, `scheduler_logs`, `command_audit`.

## 5.4. Security и anti-replay требования к контракту

1. Все internal вызовы подписываются сервисным токеном через HTTP `Authorization` header.
2. Для каждого запроса обязательны `X-Request-Nonce` + `X-Sent-At`.
3. AE2 обязан отклонять replay-запросы по `nonce/idempotency_key` в окне TTL.
4. Ошибки аутентификации и replay должны идти в audit и infra-alert.
5. Расширяем существующую auth-модель, а не заменяем её:
   - используем текущие `HISTORY_LOGGER_API_TOKEN` / `PY_INGEST_TOKEN`;
   - сохраняем `X-Trace-Id` и текущую trace-связку.
6. Это internal perimeter hardening: без message-level signing в payload и без усложнения бизнес-контракта.
7. Nonce-store должен быть persistent:
   - таблица PostgreSQL `ae_request_nonces` через Laravel migration;
   - cleanup TTL через плановый Laravel scheduled command.
8. Replay-window по умолчанию:
   - `X-Sent-At` допустим в окне `[-60s; +15s]` относительно времени AE2;
   - расширение окна требует ADR и security-review.

Минимальная спецификация nonce-store:

```sql
CREATE TABLE ae_request_nonces (
    nonce VARCHAR(64) PRIMARY KEY,
    scheduler_id VARCHAR(64) NOT NULL,
    trace_id VARCHAR(64) NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_ae_request_nonces_expires_at
    ON ae_request_nonces (expires_at);
```

Правила cleanup:
1. Cleanup запускается по расписанию (не реже 1 раза в минуту в runtime profile).
2. Удаляются записи с `expires_at < NOW()` батчами с ограничением на размер пачки.
3. Cleanup логирует статистику (`deleted_count`, `duration_ms`, `oldest_expired_age_sec`) в `scheduler_logs`/service logs.

Обязательные негативные сценарии:
1. `duplicate nonce` в активном окне TTL -> `409 replay_detected`.
2. `stale X-Sent-At` (вне replay-window) -> `422 sent_at_out_of_window`.
3. `missing/invalid Authorization` -> `401 unauthorized`.
4. `missing X-Request-Nonce` или `missing X-Sent-At` -> `422 invalid_security_headers`.

## 5.5. Семантика поля `topology`

1. `task_type` отвечает на вопрос «что делать», `topology` отвечает на вопрос «как именно выполнять для физической конфигурации».
2. `topology` хранится в zone-конфиге backend (источник истины: Laravel).
3. Scheduler читает `topology` через backend API вместе с effective-targets контекстом.
4. Миграция topology выполняется как 3-компонентный gate (Laravel schema/data -> scheduler read-path -> AE2 strict contract).
5. После завершения DB/data-миграции `topology` становится обязательным полем контракта.
6. Отсутствие `topology` после strict-gate:
   - `422 missing_topology`;
   - audit + infra-alert;
   - без silent fallback.

## 5.6. Owner-модель статусов и single-writer arbitration

1. `business_status` owner: AE2 (`accepted/running/completed/failed/rejected/expired`).
2. `transport_status` owner: scheduler (`timeout/not_found` и иные transport деградации).
3. Арбитраж single-writer:
   - решение о side-effect публикации принимает только `CommandGateway`;
   - scheduler-driven путь имеет приоритет в steady-state;
   - continuous loop публикует команды только в явно разрешенном fallback-режиме;
   - решение принимается под `per-zone lock` и с проверкой active scheduler-task state.
4. Любой concurrent dispatch без решения `CommandGateway` считается нарушением контракта.

---

## 6. Надежность, сбои, деградации

## 6.1. Поведение при потере связи

1. Freeze risky actions, оставить последнее безопасное состояние.
2. Перевести зону в `degraded` с причиной (`link_lost`, `telemetry_stale`, `history_logger_down`).
3. Запустить recovery-loop:
   - экспоненциальный backoff;
   - ограничение max attempts;
   - алерты с троттлингом.
4. После восстановления связи:
   - reconcile состояния;
   - восстановить workflow с checkpoint;
   - зафиксировать событие `ZONE_RECOVERED`.

## 6.2. Надежность команд: CommandTracker-first, outbox-optional

Базовый путь (обязательный):
1. Переиспользовать текущий `CommandBus + CommandTracker + CommandAudit`.
2. Добавить строгую дедупликацию и idempotency на уровне `CommandBus`.
3. Закрыть known-gap по повторной отправке для дозирующих команд.

Расширенный путь (опциональный):
1. PostgreSQL outbox вводится только если gap-analysis показывает окно потери между AE и history-logger.
2. Решение об outbox фиксируется отдельным ADR с оценкой дублирования относительно `commands`/`CommandTracker`.

## 6.3. Command delivery semantics (обязательные)

1. Модель доставки: `at-least-once + строгий dedupe`.
2. Идемпотентность на уровне команды: `idempotency_key = zone + workflow + step + attempt`.
3. Окно дедупликации: `dedupe_ttl_sec` из payload/конфига.
4. `CommandBus` обязан выполнять dedupe-check **до** publish в history-logger.
5. Повторная доставка без нового `attempt` должна завершаться `NO_EFFECT_DUPLICATE`.
6. Для дозирования обязательна защита от double-apply:
   - повтор с тем же ключом не меняет дозу;
   - повтор с новым ключом возможен только после обновленного snapshot.
7. Dedupe-решение должно писать audit-поле:
   - `dedupe_decision`: `new | duplicate_blocked | duplicate_no_effect`
   - `dedupe_reference_key`
   - `dedupe_ttl_sec`.
8. При `duplicate_blocked` side-effect publish не выполняется.

## 6.4. Safe State Matrix (обязательная таблица)

Safe-state матрица задается как config-driven policy, а не hardcoded список.

Примечание:
1. Матрица хранится в конфиге AE2 и версионируется.
2. Любое изменение матрицы требует e2e safety-regression.
3. Safe-state обязательно дублируется на уровне firmware/ESP32 (watchdog/LWT policy), а не только в AE.
4. Матрица должна учитывать тип исполнительного механизма:
   - `fail-closed` (например, нормально-закрытые клапаны);
   - `fail-open` (например, часть гидравлических элементов).

Минимальная форма policy:

```yaml
actuator_types:
  pump:
    default_safe_state: OFF
    conditions:
      link_lost: OFF
      telemetry_stale: OFF
      history_logger_down: OFF
  valve:
    default_safe_state: CLOSED
    conditions:
      link_lost: CLOSED
      telemetry_stale: CLOSED
      history_logger_down: CLOSED
```

## 6.5. Telemetry Freshness Contract

1. Для каждого обязательного сигнала задается `max_age_sec`.
2. При превышении возраста:
   - блокировать risky action;
   - переводить зону в `degraded`;
   - публиковать `CORRECTION_SKIPPED_STALE_FLAGS` или профильный код.
3. Freshness проверяется перед каждым step с side-effect.

Базовое правило миграции:
1. Переиспользовать существующие настройки `AE_CORRECTION_FLAGS_MAX_AGE_SEC` и `AE_CORRECTION_FLAGS_REQUIRE_TS`
   как baseline, затем расширять на остальные сигналы.
2. Переиспользовать текущие `correction_freshness.py`/`check_flags_freshness()` и развивать их, не переписывать с нуля.

## 6.6. SLA/SLO (после baseline-измерений)

1. Сначала фиксируем baseline текущей системы (latency, recovery, errors).
2. Только после baseline утверждаем финальные SLO числа.
3. Стартовые целевые значения (кандидаты):
   - availability `POST /scheduler/task`: `>=99.9%` в месяц;
   - task-start latency (accepted -> running): `p95 <= 3s`, `p99 <= 8s`;
   - command dispatch latency (run decision -> history-logger accepted): `p95 <= 2s`;
   - recovery RTO после рестарта AE2: `<=60s`;
   - alerting на `link_lost`: `<=30s`;
   - duplicate side-effect rate: `0` для дозирующих команд.
4. Error budget и алерт-пороги фиксируются в `AE2_TEST_MATRIX.md`.
5. До завершения P0 baseline и P9 приемки кандидатные числа не используются как release-gate.

## 6.7. Retention guardrails

1. Настройка retention идет с фронта, но в рамках guardrails:
   - `min_days = 30`
   - `default_days = 90`
   - `max_days = 365`
2. Значения вне диапазона отклоняются backend-валидацией.
3. Очистка логов выполняется планово с dry-run отчетом.
4. Для расследований поддерживается `legal_hold` флаг на период инцидента.
5. Ответственный за cleanup:
   - Laravel scheduled command/cron;
   - таблицы минимум: `zone_events`, `scheduler_logs`, `command_audit`, `commands` (по утвержденной retention policy).

## 6.8. Security baseline AE2

1. Internal endpoints защищены service-to-service auth.
2. Все входы в AE2 валидируются по схеме и размеру payload.
3. Включить replay-protection по `nonce/idempotency_key`.
4. Secrets хранятся только в env/secret-store, не в коде.
5. Security-события пишутся в audit и алертятся.

## 6.9. Миграция состояния и паритет данных (обязательный gate)

Перед production cutover обязателен миграционный контур:

1. PID-state migration:
   - экспорт/импорт интегральной и производной составляющей;
   - warm-start интегратора с anti-windup clamp;
   - периодический crash-safe checkpoint PID-state в runtime (не только graceful shutdown);
   - проверка, что после переключения нет скачка управляющего сигнала.
   - при детекте скачка:
     - немедленный safety-stop дозирования;
     - rollback на legacy path для зоны;
     - алерт `PID_TRANSFER_UNSTABLE` + блокировка canary.
2. Backoff/degraded migration:
   - перенос `_zone_states` (error_streak, next_allowed_run_at, degraded_alert_active) в совместимое хранилище.
3. In-flight tasks/commands:
   - freeze окно переключения;
   - дофинализация pending задач;
   - запрет двойного исполнения на границе cutover.
4. Parity validation:
   - dual-run (shadow) с сравнением AE1 vs AE2 решений;
   - отклонения выше порога блокируют canary/full rollout.
5. Runtime-state migration (обязательная):
   - `_zone_states`;
   - `_controller_failures` и cooldown maps;
   - `_correction_sensor_mode_state`;
   - runtime flags, влияющие на decision/retry/degraded.

Минимальный алгоритм transfer-state:
1. Считать последний стабильный PID snapshot зоны.
2. Применить warm-start (I/D) с ограничением `max_delta_per_min`.
3. Выполнить короткий monitoring window без увеличения дозы.
4. Разрешить активное дозирование только после прохождения window.

Обязательные требования к сериализации:
1. Все runtime-state структуры имеют явные методы `serialize()/deserialize()`.
2. Формат serialization фиксируется в версии схемы состояния.
3. Изменение формата serialization требует migration strategy и backward-readability window.

Persistent store policy:
1. PostgreSQL — источник истины для durable workflow/runtime state.
2. Redis (опционально) — только для transient TTL-state и ускоряющих кешей.
3. Отсутствие Redis не должно приводить к потере корректности исполнения.
4. Crash-recovery обязателен для неплановых рестартов (OOM/SIGKILL/container restart), не только для graceful shutdown.

## 6.10. Тестовая зрелость и coverage gate

1. До canary обязателен baseline coverage report по компонентам:
   - scheduler task execution;
   - command publish/dedupe;
   - correction dosing;
   - recovery/state migration.
2. Gate по критическим путям:
   - запрещено снижать baseline coverage критических модулей;
   - новые рисковые ветки требуют unit + integration + e2e.
3. Для canary обязателен replay/chaos пакет:
   - replay-атаки (`nonce`, `idempotency_key`);
   - restart recovery;
   - degraded/fail-safe переходы.

## 6.11. Обязательные тестовые сценарии AE2

1. Replay/security:
   - duplicate nonce;
   - stale `X-Sent-At`;
   - invalid/missing auth headers.
2. Command dedupe:
   - повтор с тем же `idempotency_key` не дает side-effect;
   - повтор с новым ключом без нового snapshot блокируется.
3. Recovery:
   - restart с восстановлением workflow/PID/runtime state.
4. Single-writer:
   - отсутствие конфликтов при активном continuous loop и scheduler task.
5. Safety:
   - config-driven safe-state transitions по причинам деградации.

## 6.12. Управление feature flags и retirement

1. Для каждого флага обязателен владелец, дата введения, целевая дата удаления и критерий retirement.
2. Поддерживается единый реестр флагов AE2 (`flag`, `owner`, `default`, `depends_on`, `remove_by`).
3. Для каждого релиза фиксируется тестируемая матрица поддерживаемых комбинаций.
4. Флаги без owner или с просроченным `remove_by` блокируют релиз до решения.
5. Добавление нового флага без плана удаления запрещено.

## 6.13. Владение phase transitions (stub-policy)

1. `check_phase_transitions` (disabled stub) фиксируется как явный архитектурный выбор, а не «забытый код».
2. P0 обязан принять решение:
   - либо phase transitions полностью owned Laravel (`GrowCyclePhase`) и stub удаляется;
   - либо stub восстанавливается как поддерживаемый runtime path с тестами и owner.
3. Двусмысленный статус (stub есть, но ответственность не определена) не допускается после P0 gate.

---

## 7. План работ для ИИ-ассистентов (пошагово)

Ниже обязательный формат: в каждом этапе указано, **куда смотреть**, **что делать**, **что на выходе**.

## 7.0. Рекомендуемая последовательность (Hybrid Track)

1. P0: baseline + аудит уже существующей декомпозиции.
2. P1: consolidation текущих helper-модулей + minimal contract v2 draft.
3. P1.5: Dependency Injection Container + service boundaries для executor/plugin слоев.
4. P2: safety-critical bounds/rate-limit/freshness/security headers в текущем AE.
5. P4: variant-profile расширяемость для `two_tank` (без heavy SDK).
6. P5: коррекционные policy-улучшения.
7. P3: single-writer orchestration target + migration from dual writers (после P5).
8. P6: resilience hardening (safe-state + dedupe + optional outbox by ADR).
9. P7: observability/SLO после baseline.
10. P8: интеграция и cutover.
11. P9: нагрузочные/chaos и приемка.

### P0. Baseline и заморозка контуров

**Куда смотреть:**
- `doc_ai/SYSTEM_ARCH_FULL.md`
- `doc_ai/ARCHITECTURE_FLOWS.md`
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `backend/services/automation-engine/*`
- `backend/services/scheduler/main.py`

**Что делать:**
1. Зафиксировать as-is карту потоков AE/scheduler/history-logger и всех путей публикации команд.
2. Составить реестр инвариантов, которые нельзя ломать.
3. Подготовить список legacy-поведения, которое в AE2 удаляется.
4. Зафиксировать Mermaid-карту потоков команд с ownership и policy арбитражем.
5. Зафиксировать диаграмму state machine workflow фаз (как контракт восстановления после рестарта).
6. Извлечь Core plugin-контракт из `workflow_router`/`domain.workflows`.
7. Снять baseline-метрики текущей системы (latency, recovery, error-rate, duplicate-rate) и оформить CSV (`p50/p95/p99`).
8. Зафиксировать baseline по тестам и coverage (объем, pass-rate, критические модули).
9. Явно зафиксировать техдолг `SchedulerTaskExecutor + executor_bound_*` как обязательный ADR-документ и декомпозиционную карту.
10. Зафиксировать `api.py` как второй крупный orchestration техдолг и карту разбиения.
11. Зафиксировать monkey-patch wiring в `scheduler_task_executor.py` как обязательный техдолг к устранению через DI.
12. Провести инвентаризацию существующего retry-контура (`correction_command_retry.py`) и исключить планируемое дублирование retry-слоев.
13. Зафиксировать решение по `check_phase_transitions` (Laravel-only или поддерживаемый runtime path).
14. Подготовить CI-артефакты baseline:
   - dashboard snapshot;
   - baseline metrics export file;
   - checksum/hash экспортированного baseline файла.
15. Принять раннее архитектурное решение по shadow fan-out/comparator (источник fan-out, owner diff-comparison, хранилище diff-логов).

**Что на выходе:**
1. `doc_ai/10_AI_DEV_GUIDES/AE2_P0_BASELINE_AUDIT.md`
2. Таблица инвариантов и breaking-points.
3. Mermaid карта путей публикации команд с owner/policy.
4. State machine diagram фаз workflow (as-is/to-be).
5. Чек-лист миграции со старого AE на AE2.
6. Черновик `PLUGIN_CORE_CONTRACT_FROM_EXISTING.md`.
7. `AE1_BASELINE_METRICS.md` + baseline CSV (`p50/p95/p99`).
8. `AE1_TEST_BASELINE_REPORT.md` + coverage baseline report.
9. `SCHEDULER_TASK_EXECUTOR_RESTRUCTURE_ADR.md`.
10. `AE2_API_P0_DECOMPOSITION_AUDIT.md`.
11. `AE2_FLAG_REGISTRY_AND_RETIREMENT_PLAN.md`.
12. `AE2_P0_BASELINE_CHECKSUM.txt`.

Gate P0:
1. P0 считается завершенным только при наличии всех артефактов выше.
2. P1+ реализация блокируется при незакрытом P0 gate.
3. P0 gate CI-верифицируем:
   - baseline test/coverage job `green`;
   - baseline metrics export присутствует и проходит checksum-проверку;
   - dashboard snapshot приложен и валиден по timestamp/traceability.

### P1. Консолидация + минимальный контракт scheduler

**Куда смотреть:**
- `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`
- `backend/services/scheduler/main.py`
- `backend/services/automation-engine/api.py`
- `backend/laravel/app/Http/Controllers/SchedulerTaskController.php`

**Что делать:**
1. Провести consolidation существующих helper-модулей по логическим пакетам.
2. Спроектировать минимальный `contract v2` (request/response/status/outcome/errors) без лишнего payload-overhead.
3. Определить idempotency, дедлайны, retry semantics.
4. Добавить security-контур на headers (`Authorization`, `X-Request-Nonce`, `X-Sent-At`).
5. Спроектировать dedupe-ключи и replay-window для текущего `CommandBus`.
6. Специфицировать persistent nonce-store (`ae_request_nonces`) и TTL cleanup стратегию.
7. Провести gap-analysis: нужен ли отдельный outbox поверх `CommandTracker`.
8. Зафиксировать topology migration plan как cross-service gate без бессрочного fallback-периода.

**Что на выходе:**
1. `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA_V2.md`
2. Расширение существующих contract tests (`backend/services/automation-engine/tests/e2e/test_scheduler_payload_contract.py`)
   + negative/replay сценарии.
3. Consolidation plan (`AE2_CONSOLIDATION_PLAN.md`) с маппингом старых/новых модулей.
4. Migration note для scheduler и backend.
5. ADR `COMMAND_DELIVERY_GAP_ANALYSIS.md` (outbox required / not required).
6. Спека nonce-storage (`AE_REQUEST_NONCES_SPEC.md`) + migration/cleanup plan.
7. SQL schema draft для `ae_request_nonces` (PK + TTL index + replay semantics).

### P1.5. Dependency Injection Container

**Куда смотреть:**
- `backend/services/automation-engine/application/scheduler_executor_impl.py`
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/application/workflow_router.py`
- `backend/services/automation-engine/domain/workflows/*`

**Что делать:**
1. Ввести DI-контейнер для wiring executor/policies/plugins без ручного monkey-patching.
2. Зафиксировать lifecycle для зависимостей (`init`, `health`, `shutdown`).
3. Разделить runtime wiring и business policies.
4. Подготовить plugin-ready dependency graph через `PluginDependencies`.

**Что на выходе:**
1. `AE2_DI_CONTAINER_SPEC.md`.
2. Dependency map executor/plugin слоев.
3. План миграции ручного wiring на container-based wiring.
4. Unit тесты на корректность dependency resolution и lifecycle hooks.
5. План удаления monkey-patch wiring (`_impl.* = *_proxy`) из runtime пути.

### P2. Каркас AE2-режима (in-place)

**Куда смотреть:**
- `backend/services/automation-engine/` (для reuse только идей, не копипасты)
- `backend/services/scheduler/README.md`
- `backend/docker-compose.dev.yml`

**Что делать:**
1. Добавить AE2-mode в текущий `backend/services/automation-engine/` через feature flags.
2. Внедрить bounds (`hard_pct`, `abs_min`, `abs_max`) в коррекционный контур как safety-critical enforcement.
3. Внедрить `max_delta_per_min`.
4. Перевести freshness на per-signal config поверх существующей реализации.
5. Добавить middleware для header-based security и replay window.
6. Переиспользовать существующий `application/executor_constants.py` для feature-flag wiring, без параллельной системы флагов.
7. Зафиксировать и запустить flag retirement schedule для существующих AE-флагов.

**Что на выходе:**
1. AE2-mode в текущем сервисе с переключателем (`AE2_ENABLED`) и compare-режимом для shadow-deployment.
2. Реальные улучшения safety/коррекции без смены архитектурного ядра.
3. Unit + integration тесты на bounds/freshness/security.
4. Flag registry с owner/remove_by и матрицей поддерживаемых комбинаций.

### P4. Variant profiles для `two_tank` и похожих сценариев

**Куда смотреть:**
- `backend/services/automation-engine/domain/workflows/*`
- `tests/e2e/scenarios/automation_engine/E75_two_tank_fill_contract.yaml`
- `tests/e2e/scenarios/automation_engine/E66_fail_closed_corrections.yaml`

**Что делать:**
1. Рефакторинг текущего `two_tank` workflow в минимальный plugin-контракт без потери поведения.
2. Добавить variant-profile шаблон для следующей похожей `two_tank` логики.
3. Избежать создания параллельного framework-ядра, использовать текущий routing слой.

**Что на выходе:**
1. `domain/workflows/*` + variant profiles.
2. Минимальный routing update в текущем workflow-router.
3. Набор unit-тестов на plugin API.
4. Спека `VARIANT_PROFILE_SPEC.md`.

### P5. Контроль параметров и коррекция к целям

**Куда смотреть:**
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_correction_*`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`

**Что делать:**
1. Вынести pH/EC control в отдельные policy-модули AE2 из текущего `CorrectionController`.
2. Уточнить policy-интерпретацию bounds/rate-limit, уже внедренных в P2.
3. Сделать fail-safe логику при stale telemetry/flags.
4. Добавить policy-тесты на anti-windup и дозирование в стресс-сценариях.

**Что на выходе:**
1. `domain/policies/ph_policy.py`, `ec_policy.py`, `bounds_policy.py`.
2. Contract тесты на границы и решение `run/skip/retry/fail`.
3. e2e сценарии на коррекцию и safety stop.
4. Матрица тестов `pct vs absolute bounds`.

### P3. Single-writer orchestration migration (после P5)

**Куда смотреть:**
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`
- `tests/e2e/scenarios/automation_engine/E75_two_tank_fill_contract.yaml`
- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/application/scheduler_executor_impl.py`

**Что делать:**
1. Формализовать существующие workflow phases/stages как canonical state machine.
2. Ввести `CommandGateway` как единую точку арбитража side-effect dispatch.
3. Перевести steady-state на single writer (scheduler-driven).
4. Ограничить continuous loop до monitoring/gating роли.
5. Добавить deterministic recovery после рестарта.
6. Реализовать per-zone lock и scheduler-gating для устранения dual-writer гонок.

**Что на выходе:**
1. `domain/state_machine/*` в AE2.
2. Расширение `workflow_state_store` под режим single-writer.
3. Спека `SINGLE_WRITER_ORCHESTRATION_RULES.md`.
4. Integration тесты: restart + continue from checkpoint + отсутствие dual-writer конфликтов.
5. Negative tests: concurrent loop/task dispatch не приводит к двойной публикации.

### P6. Сетевой resilience (и optional outbox)

**Куда смотреть:**
- `backend/services/automation-engine/infrastructure/command_bus.py`
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`
- `tests/e2e/scenarios/chaos/E70_mqtt_down_recovery.yaml`

**Что делать:**
1. Реализовать dedupe-слой команд поверх текущего `CommandBus`.
2. Уточнить и унифицировать retry/backoff/circuit-breaker политику с учетом уже существующего `correction_command_retry.py`.
3. Добавить режим `hold_last_safe_state` при link-loss.
4. Реализовать и подключить `Safe State Matrix`.
5. Если ADR из P1 требует outbox — внедрить PostgreSQL outbox.

**Что на выходе:**
1. `CommandBus` dedupe/idempotency patch + тесты.
2. Chaos-тесты: history-logger down, mqtt down, ae2 restart.
3. Метрики по очереди и recovery.
4. Инвариант-тесты на отсутствие повторного side-effect.
5. Опционально: outbox implementation + migration (если outbox утвержден ADR).
6. ADR/документ по retry layering (кто отвечает за retry: CorrectionController vs CommandBus) без двойного retry-контура.

### P7. Observability, audit, alerting

**Куда смотреть:**
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `backend/services/automation-engine/infrastructure/observability.py`
- `backend/laravel` API для zone events/scheduler logs

**Что делать:**
1. Стандартизовать события AE2 (event_id, seq, trace_id, correlation_id).
2. Обеспечить полный audit trail решений и команд.
3. Реализовать retention policy (90 дней, настройка через frontend).
4. Внедрить guardrails retention и `legal_hold`.
5. Реализовать cleanup как Laravel scheduled command:
   - батч-удаление/архивирование;
   - dry-run режим;
   - отчет по очистке.

**Что на выходе:**
1. Спека `AE2_EVENT_TAXONOMY.md`.
2. Миграции/индексы для хранения и очистки.
3. E2E проверка отображения timeline в UI.
4. Документ `RETENTION_AND_LEGAL_HOLD_POLICY.md`.
5. Runbook для cleanup (`scope`, `batch size`, `rollback strategy`, `legal_hold exclusions`).

### P8. Интеграция scheduler/backend/frontend с минимальными правками

**Куда смотреть:**
- `backend/services/scheduler/main.py`
- `backend/laravel/routes/api.php`
- `backend/laravel/app/Http/Controllers/*`
- `doc_ai/07_FRONTEND/*`

**Что делать:**
1. Переключить scheduler на contract v2.
2. Добавить/минимально расширить backend DTO для новых полей outcome/bounds.
3. Протащить настройки hard-limits и retention из frontend.
4. Реализовать cutover режимы: `shadow (separate deployment) -> canary -> full`.
5. Зафиксировать rollback и обработку in-flight задач при переключении.
6. Специфицировать shadow fan-out/comparison pipeline:
   - источник fan-out (scheduler или proxy);
   - read-only DB доступ shadow;
   - место хранения diff-логов и owner сравнения.

**Что на выходе:**
1. Рабочий сквозной контракт `frontend -> backend -> scheduler -> AE2`.
2. Feature flag для cutover (`AE2_ENABLED`).
3. E2E сценарии для новых полей в API/UI.
4. Документ `AE2_CUTOVER_AND_ROLLBACK_RUNBOOK.md`.
5. Формальное определение shadow-mode:
   - отдельный `ae2-shadow` deployment;
   - без записи в `commands/zone_events/zone_workflow_state`;
   - только diff-лог решений AE1 vs AE2;
   - обязательный comparator с KPI parity.

### P9. Нагрузочные, chaos, приемка

**Куда смотреть:**
- `tests/e2e/scheduler/*.sh`
- `tests/e2e/scenarios/automation_engine/*.yaml`
- `tests/e2e/scenarios/chaos/*.yaml`

**Что делать:**
1. Добавить матрицу тестов под текущий и x2 масштаб.
2. Прогнать restart/failover/packet-loss сценарии.
3. Подготовить release checklist и rollback plan.
4. Проверить достижение SLO (p95/p99 latency, RTO, alerting SLA).
5. Выполнить parity-анализ AE1 vs AE2 на одинаковом наборе задач/телеметрии.
6. Подтвердить KPI `duplicate side-effect rate = 0` для дозирующих команд.

**Что на выходе:**
1. `doc_ai/10_AI_DEV_GUIDES/AE2_TEST_MATRIX.md`
2. Протокол приемки с метриками стабильности.
3. Go-live чеклист.
4. Отчет по SLO/error-budget.
5. Отчет `AE1_AE2_PARITY_REPORT.md` + diff-лог отклонений.
6. Release gate sheet:
   - parity within threshold;
   - duplicate side-effect KPI passed;
   - canary rollback drill passed;
   - SLO gate использует только baseline-утвержденные значения (не кандидатные).

---

## 8. Роли ИИ-ассистентов и зоны ответственности

1. `AI-ARCH`  
   - проектирует контракт и архитектуру модулей;  
   - выход: спеки + ADR.
2. `AI-CORE`  
   - ядро исполнения, state machine, recovery;  
   - выход: production код + unit/integration тесты.
3. `AI-PLUGIN`  
   - variant profiles и routing-расширение для `two_tank`/`three_tank`;  
   - выход: минимальные plugin-адаптеры + e2e.
4. `AI-RELIABILITY`  
   - dedupe, retry/backoff, circuit breaker, optional outbox (ADR-gated), chaos;  
   - выход: resilience-контур + chaos regression.
5. `AI-INTEGRATION`  
   - scheduler/backend/frontend минимальные контрактные изменения;  
   - выход: сквозной контракт и feature-flag cutover.
6. `AI-SEC`  
   - service auth, anti-replay, security-аудит;  
   - выход: security baseline tests + hardening checklist.
7. `AI-QA`  
   - тест-матрица, CI gates, релизная приемка;  
   - выход: green pipeline + acceptance report.

---

## 9. Критерии готовности AE2 (Definition of Done)

1. Новая похожая логика “два бака” добавляется как новый плагин без правки ядра.
2. При потере связи система уходит в безопасный режим, алертит и восстанавливается автоматически.
3. Нет потери задач/команд при рестартах `AE2/scheduler/history-logger`.
4. В steady-state отсутствует dual-writer конфликт (single writer enforcement).
5. Полная трассировка решения:
   - входной intent;
   - decision;
   - команда;
   - подтверждение эффекта.
6. Проходят unit + integration + e2e + chaos тесты.
7. Regression покрытие не хуже baseline `AE1_TEST_BASELINE_REPORT.md`.
8. UI получает и показывает:
   - hard limits;
   - decision/outcome;
   - timeline;
   - alerts.
9. Ретеншн логов 90 дней (настраиваемо с фронта) работает автоматически.
10. Для дозирующих команд подтверждено отсутствие duplicate side-effect.
11. Cutover `shadow (separate deployment) -> canary -> full` и rollback проверены на стенде.

---

## 10. Шаблон задачи для любого ИИ-ассистента (обязательный)

```markdown
# Задача: <P0..P9 + короткое название>

## Роль
Ты <AI-ARCH|AI-CORE|AI-PLUGIN|AI-RELIABILITY|AI-INTEGRATION|AI-SEC|AI-QA>.

## Куда смотреть
- <список .md>
- <список файлов кода>

## Что делать
1. ...
2. ...
3. ...

## Ограничения
- Не ломать pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32`.
- Ноды только исполнители.
- Изменения БД только через Laravel migrations.

## На выходе
1. Измененные/новые файлы: ...
2. Тесты: ...
3. Обновленная документация: ...
4. Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
```

---

## 11. Реалистичный старт (первые 2 недели)

Первые 2 недели — только обязательный минимум с низким миграционным риском:

1. P0 полностью:
   - baseline-аудит;
   - инварианты;
   - Mermaid карта потоков команд;
   - state machine diagram;
   - baseline CSV (`p50/p95/p99`);
   - baseline test/coverage report.
2. P1 + P1.5:
   - contract v2 draft;
   - security headers (`Authorization`, `X-Request-Nonce`, `X-Sent-At`);
   - dedupe/replay policy;
   - DI container spec + dependency map.
3. Sprint-1 implementation (ограниченный объем P2):
   - bounds (`hard_pct`, `abs_min`, `abs_max`) в коррекционном контуре как safety-critical;
   - `max_delta_per_min`;
   - telemetry freshness из конфигурации per-signal;
   - без single-writer enforcement в этом спринте.

Фазы P3+ запускаются только после подтверждения P0 gate, baseline-отчетов и согласования ADR по outbox.

---

## 12. Пересмотренный приоритет фаз

| Фаза | Приоритет | Обоснование |
|------|-----------|-------------|
| P0 | Критический | Без формального baseline/gate реализация AE2 небезопасна и нерепродуцируема. |
| P1 | Критический | Contract v2 + security/replay — фундамент межсервисной корректности. |
| P1.5 | Высокий | DI-container нужен для управляемой декомпозиции и plugin lifecycle. |
| P2 | Высокий | Bounds/freshness напрямую влияют на safety корректировок. |
| P5 | Высокий | Политики коррекции влияют на здоровье растений и риск передозировки. |
| P3 | Средний | Single-writer выполняется после консолидации/политик, иначе высокий риск регрессий. |
| P4 | Средний | Plugin/variant расширяемость зависит от стабилизированных интерфейсов. |
| P6 | Средний | Resilience наращивается после базовой корректности контрактов и policy слоев. |
| P7 | Низкий | Observability/retention усиливаются после стабилизации ядра исполнения. |
| P8 | Низкий | Cutover выполняется только после прохождения parity и reliability gates. |
| P9 | Низкий | Нагрузочная и chaos приемка завершают цикл перед full rollout. |

---

## 13. Допущения и defaults для текущей ревизии

1. Правки текущей итерации ограничены одним документом:
   - `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`.
2. Новые артефакты/ADR в этом шаге фиксируются как обязательные deliverables, без создания файлов.
3. Пайплайн и инварианты совместимости не меняются.
4. Формат документа остается в стиле `doc_ai` (русский язык, структурные секции, Compatible-With).
