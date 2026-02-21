# AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md
# AE2: мастер-план для ИИ-ассистентов (эволюционное развитие)

**Версия:** v1.10
**Дата:** 2026-02-18
**Статус:** LEGACY / SUPERSEDED  
**Область:** `backend/services/automation-engine*`, `backend/services/scheduler`, `backend/laravel`, `tests/e2e`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.  
Breaking-change: Big Bang rewrite отменен; AE2 внедряется эволюционно поверх текущего automation-engine с feature-flag cutover.

> Внимание: документ устарел для текущего runtime.
> Каноничный план исполнения и контракты AE2-Lite:
> `doc_ai/10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md`.
> Упоминания `/scheduler/task` в этом файле являются историческими.

## Что изменено в v1.10

1. **Аудит LOC:** исправлены оценки firmware LOC (24.6k → ~34.8k) и общий масштаб (~280k).
2. **Аудит God Objects:** добавлены `main.py` AE (1233 LOC) и `correction_controller.py` (900 LOC) в раздел 3.7.
3. **Аудит check_phase_transitions:** раздел 6.13 исправлен — функция является активным кодом, не disabled stub.
4. **Аудит нод:** раздел 14.4.4 исправлен (irrig_node → pump_node), добавлен раздел 14.4.6 для relay_node.
5. **Аудит ROLE_ALIASES:** раздел 14.5 дополнен до полных 14 ролей из кода.
6. **Уточнения формулировок:** раздел 3.8 п.5 (owner-файл), раздел 3.9 (to-be пометка), deprecated publish path в main.py.

## Что изменено в v1.9

1. План переведен в `S-only` режим исполнения для ИИ: канонические этапы только `S1..S12`.
2. Раздел 7 переписан в self-contained формат: обязательные stage-task файлы, gate-верификация и роли по этапам.
3. Добавлен обязательный `AE2_CURRENT_STATE.md` как межсессионный источник прогресса.
4. Добавлены machine-checkable guard rails (`AE2_INVARIANTS.py`) для CI.
5. Зафиксированы конкретные call sites миграции на `CommandGateway` и требование отдельного плана миграции тестов.
6. Safety этап разделен на исследование (`S2`) и реализацию (`S3`).
7. Hardened security явно помечен как `DEFERRED` до отдельного запроса/threat-model.
8. Добавлен baseline масштаба системы и целевой профиль «посадил и забыл».
9. Добавлен tiered backlog автономности (Tier 1/2/3) с привязкой к `S9..S12`.
10. Зафиксирован отдельный техдолг `scheduler/main.py` и phased split план.

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
3. Переход выполняется через один из режимов:
   - `shadow -> canary -> full` (если оправдано по риску/ресурсам);
   - `canary-first -> full` для малого масштаба при ограниченной команде.

## 1.2. Что это меняет практически

1. Используем существующие рабочие модули как baseline:
   - `WorkflowRouter`, `WorkflowStateStore`, `CommandBus`, `CorrectionController`,
     `zone_correction_gating`, `_zone_states`.
2. Новые контракты/политики добавляем поверх текущих API и тестов.
3. Любая замена модуля допустима только после прохождения parity-проверок.

## 1.3. Gate до начала реализации

Перед любыми изменениями обязателен Stage-gate:
1. `S1` (минимальный blocking audit) — обязателен до реализации фич.
2. `S5` (baseline/coverage) — обязателен до release-gates.

## 1.4. Rewrite Exit-Criteria (анти-догма)

Эволюционный путь является default, но не безусловным.
После `S2` допускается controlled pivot на selective rewrite, если одновременно выполняются условия:
1. Ownership-map показывает критическую связанность без безопасного декомпозиционного пути.
2. Стоимость эволюции (оценка по этапам) выше стоимости ограниченного rewrite выбранного bounded context.
3. Есть план миграции без нарушения защищенного пайплайна `Scheduler -> AE -> History-Logger -> MQTT -> ESP32`.
4. Pivot утвержден отдельным ADR с rollback-стратегией.

## 1.5. Фактический масштаб и зрелость системы (baseline)

Текущий масштаб (оценка по коду и структуре репозитория, верифицировано 2026-02-18):
1. Firmware (ESP32, C): ~34.8k LOC, 6 типов нод (`ph_node`, `ec_node`, `pump_node`, `climate_node`, `light_node`, `relay_node`) + `common/components`.
2. Python-сервисы: ~54k LOC (production), 11 сервисов (`automation-engine`, `scheduler`, `history-logger`, `mqtt-bridge`, `digital-twin`, `node-sim`, `protocol-check`, `telemetry-aggregator`, `seed-service`, `notification-service`, `test-utils`).
3. Laravel backend (PHP): ~85k LOC.
4. Frontend (Vue/JS/TS): ~92k LOC.
5. Тесты: ~16.5k LOC в automation-engine + Laravel/e2e.
6. Общий порядок масштаба: ~280k LOC (production).

Оценка зрелости автоматизации:
1. Layer 1-2 (базовая эксплуатация): работает стабильно.
2. Частичная автономность: ~60-65% (есть recovery/degraded/tracking, но неполные).
3. Layer 3-5 (предиктивность/полная автономность): в основном отсутствует и требует отдельного roadmap.

## 1.6. Целевой профиль «Посадил и забыл»

Для AE2 целевой профиль определяется поэтапно:
1. Сначала закрываем safety и crash/recovery фундамент (`S1..S6`).
2. Затем добавляем минимальный автономный контур (Tier 1) без отдельной ML-платформы.
3. После стабилизации вводим комфортный уровень автономности (Tier 2).
4. Только затем — расширенная автономность (Tier 3: weather/adaptive/cv).

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

Текущее состояние (верифицировано 2026-02-18):
1. `scheduler_task_executor.py` (59 LOC) — thin wrapper/re-export слой, а не основной носитель доменной сложности.
2. Реальный orchestration debt сосредоточен в `application/scheduler_executor_impl.py` (417 LOC) + 10 `executor_bound_*` модулей (~1531 LOC суммарно) + 6 `executor_*_delegates/init/run` модулей (~864 LOC).
3. Ownership и границы домена в bound-паттерне остаются размытыми (monolith-in-files, 16 файлов ~2657 LOC суммарно).
4. God Object: `backend/services/automation-engine/api.py` (крупный orchestration surface, 860 строк, stage decomposition в прогрессе).
5. God Object: `backend/services/automation-engine/main.py` (1233 LOC, содержит глобальные переменные throttling/circuit-breaker alert state, runtime loop orchestration).
6. God Object: `backend/services/automation-engine/correction_controller.py` (900 LOC, PID-контроль + correction logic + batch building).
7. Реальная сложность выше количества строк: высокая скрытая связанность через bound/delegate назначения и policy-модули.
8. Смежный риск: `zone_automation_service.py` (893 LOC, 70+ импортов) содержит крупный runtime-state surface и должен декомпозироваться синхронно с executor/API.
9. Отдельный блокирующий техдолг: `backend/services/scheduler/main.py` (крупный монолитный orchestration surface, 2824 LOC) ограничивает рост к autonomous orchestration.

Обязательный deliverable-пакет до завершения `S7`:
1. В `S1`:
   - инвентаризация `executor_bound_*` с ownership-map (модуль -> ответственность -> owner-слой);
   - инвентаризация `api.py` по ownership-map и декомпозиционным кандидатам.
   - инвентаризация `scheduler/main.py` с картой extraction-кандидатов (`ingress`, `planning`, `dispatch`, `polling/reconciliation`).
2. В `S4/S7`:
   - целевая декомпозиция минимум на 6 интерфейсов:
   - `IWorkflowExecutor`
   - `IDiagnosticsExecutor`
   - `IRefillExecutor`
   - `ICommandGateway`
   - `IWorkflowStateCoordinator`
   - `ITaskOutcomeAssembler`
3. В `S7`:
   - ADR по реструктуризации coordinator/API и точек миграции с decision-complete выбором:
   - либо доменная декомпозиция с DI boundaries;
   - либо явно утвержденный `monolith-in-files` со строгими ограничениями роста.
   - ADR по декомпозиции `scheduler/main.py` с фазовым планом без остановки текущего расписания.

Критерий выхода:
1. Coordinator содержит только orchestration-flow.
2. Domain/policy логика удалена из coordinator (остаются только вызовы интерфейсов).
3. Для `api.py` выделены отдельные bounded handlers; orchestration и transport-код не смешиваются.
4. Для `scheduler/main.py` утвержден и запущен phased split-план, достаточный для подключения autonomous orchestrator без роста монолита.

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
   - путь: `zone_controller_processors -> zone_controller_execution.publish_controller_action_with_event_integrity -> CommandBus`
   - owner: `zone controllers`
   - steady-state: только через policy арбитраж и `CommandGateway`.
6. Deprecated correction path (legacy, подлежит удалению в S8):
   - путь: `main.py:publish_correction_command() -> CommandBus`
   - owner: `automation-engine runtime loop`
   - steady-state: deprecated, не должен использоваться в новом коде.

Целевое правило арбитража:
1. Все side-effect команды проходят через `CommandGateway`.
2. `CommandGateway` применяет single-writer policy, idempotency policy и safety-gates до publish.
3. Любой прямой обход `CommandGateway` считается нарушением архитектурного контракта.
4. Арбитраж выполняется под `per-zone lock` для устранения гонок между concurrent путями.

## 3.9. Дизайн `CommandGateway` (implementation baseline)

Расположение и роль:
1. Файл (to-be, создаётся в S8): `backend/services/automation-engine/infrastructure/command_gateway.py`.
2. Роль: единственная точка pre-dispatch решения перед `CommandBus`.

Минимальный интерфейс:
1. `acquire_zone_slot(zone_id, correlation_id) -> ZoneDispatchLease`.
2. `evaluate_dispatch(intent, zone_runtime_state, orchestration_state) -> DispatchDecision`.
3. `publish_via_bus(decision, command_payload) -> DispatchResult`.
4. `release_zone_slot(lease) -> None`.

Интеграция:
1. `CommandGateway` вызывает существующий `CommandBus` как transport-adapter, не дублируя transport-логику.
2. `SchedulerTaskExecutor` и continuous loop публикуют side-effect только через gateway API.
3. Решение «активна scheduler-task orchestration или нет» берется из явного orchestration state provider (не из скрытых module-level переменных).

Lock registry:
1. Single-instance baseline: in-process `dict[int, asyncio.Lock]` + lease timeout.
2. Multi-worker/scale-out: distributed lock (PostgreSQL advisory lock или Redis lock по ADR).
3. При падении воркера lease освобождается по timeout/heartbeat, чтобы избежать вечной блокировки зоны.

---

## 4. Модель расширения логики (ключ для похожих “двух баков”)

## 4.1. Что должно расширяться без правки ядра

1. Топология (`two_tank`, `three_tank`, и вариации).
2. Набор workflow-ов (`startup`, `refill_check`, `irrigation_recovery`, новые шаги).
3. Правила коррекции pH/EC и safety-политики.
4. Карта действий по параметрам (`irrigation`, `lighting`, `climate`).

## 4.2. Контракт плагина (lifecycle-aware)

MVP (для ИИ-исполнения) — strategy-first контракт:

1. `supports(task_type, workflow, context) -> bool`
2. `execute(context) -> Result`
3. `health() -> Dict[str, Any]`

Full lifecycle plugin framework (`initialize/checkpoint/restore/fail_forward`) — `DEFERRED` до подтвержденной потребности.

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
5. `checkpoint/restore` обязателен для recovery после рестарта (реализуется в `S6`, не в MVP strategy-first контракте).
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

## 4.4. Регистрация и discovery плагинов

1. Для MVP используется простой strategy registry (без тяжелого plugin framework).
2. Источники discovery:
   - встроенные плагины (кодовая регистрация);
   - конфигурационные entries (feature-flag gated).
3. DI-container в MVP управляет только `health()` и wiring зависимостей.
4. Для каждого plugin-entry фиксируются:
   - `plugin_id`;
   - `topology_id`;
   - версия контракта;
   - флаг включения;
   - owner.
5. Ошибка регистрации или несовместимость версии контракта блокирует запуск strategy-path и создает infra-alert.

---

## 5. Контракт scheduler <-> AE2 v2 (to-be)

## 5.1. Что меняем

1. Переводим контракт на явный `intent + topology + workflow + bounds + deadlines`.
2. Убираем неявные default workflow и silent fallback в steady-state.
3. Разделяем:
   - `business_status` (owner: AE2),
   - `transport_status` (owner: scheduler).
4. `topology` трактуется как greenfield cross-service feature (Laravel schema + scheduler read-path + AE dispatch), а не как локальное расширение одного сервиса.
5. Временная optional-фаза допускается только как короткое migration-window с явной датой завершения.

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

Транспортные security headers:

Baseline profile (default):

```http
Authorization: Bearer <service-token>
X-Trace-Id: <trace-id>
```

Hardened profile (по threat-model):

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

Профили безопасности:
1. `Baseline (default для internal Docker perimeter)`:
   - обязательны `Authorization` + `X-Trace-Id`;
   - `X-Sent-At` рекомендуется, но не блокирует запрос при отсутствии;
   - фокус на service-to-service auth, audit и rate-limit.
2. `Hardened (включается по threat-model или внешнему периметру)`:
   - обязательны `X-Request-Nonce` + `X-Sent-At`;
   - активируется replay-window и persistent nonce-store;
   - отказ по replay/auth является blocking.
   - статус: `DEFERRED` (не реализовывать без явного запроса).

Базовые требования (всегда):
1. Все internal вызовы подписываются сервисным токеном через HTTP `Authorization` header.
2. Ошибки аутентификации всегда пишутся в audit и infra-alert.
3. Расширяем существующую auth-модель, а не заменяем её:
   - используем текущие `HISTORY_LOGGER_API_TOKEN` / `PY_INGEST_TOKEN`;
   - сохраняем `X-Trace-Id` и текущую trace-связку.

Hardened replay требования (условно-обязательные):
1. AE2 отклоняет replay-запросы по `nonce/idempotency_key` в окне TTL.
2. Replay-window по умолчанию:
   - `X-Sent-At` допустим в окне `[-60s; +15s]` относительно времени AE2;
   - расширение окна требует ADR и security-review.
3. Nonce-store хранится в PostgreSQL с TTL-cleanup через Laravel scheduled command.

Минимальная спецификация nonce-store (для Hardened profile):

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

CREATE INDEX idx_ae_request_nonces_scheduler_created
    ON ae_request_nonces (scheduler_id, created_at DESC);
```

Laravel migration contract (для Hardened profile):
1. Имя миграции по шаблону: `*_create_ae_request_nonces_table.php`.
2. Миграция должна включать оба индекса (`expires_at`, `scheduler_id+created_at`).
3. Down-миграция обязана удалять индексы и таблицу в обратном порядке.

Правила cleanup:
1. Cleanup запускается по расписанию (не реже 1 раза в минуту в runtime profile).
2. Удаляются записи с `expires_at < NOW()` батчами с ограничением на размер пачки.
3. Cleanup логирует статистику (`deleted_count`, `duration_ms`, `oldest_expired_age_sec`) в `scheduler_logs`/service logs.

Обязательные негативные сценарии:
1. `duplicate nonce` в активном окне TTL -> `409 replay_detected`.
2. `stale X-Sent-At` (вне replay-window) -> `422 sent_at_out_of_window`.
3. `missing/invalid Authorization` -> `401 unauthorized`.
4. В Hardened profile: `missing X-Request-Nonce` или `missing X-Sent-At` -> `422 invalid_security_headers`.

## 5.5. Семантика поля `topology`

1. As-is: в текущем runtime поле `topology` отсутствует, поэтому внедрение считается новой cross-service capability.
2. `task_type` отвечает на вопрос «что делать», `topology` отвечает на вопрос «как именно выполнять для физической конфигурации».
3. `topology` хранится в zone-конфиге backend (источник истины: Laravel).
4. Scheduler читает `topology` через backend API вместе с effective-targets контекстом.
5. Миграция topology выполняется как 3-компонентный gate:
   - Laravel schema/data;
   - scheduler read-path;
   - AE2 strict dispatch.
6. Optional-режим ограничен migration-window и не считается steady-state режимом.
7. После завершения DB/data-миграции `topology` становится обязательным полем контракта.
8. Отсутствие `topology` после strict-gate:
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

Обязательные требования к dedupe-реализации:
1. Dedupe-store должен поддерживать pre-publish reserve/check (PostgreSQL или Redis с durable fallback).
2. Операция `check + reserve + publish decision` должна быть атомарной на уровне зоны/ключа (без race между конкурентными воркерами).
3. Cleanup dedupe-key выполняется TTL-политикой с метриками эффективности (`dedupe_hits`, `dedupe_false_miss`, `dedupe_reserve_conflicts`).

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
5. До завершения `S5` baseline и `S12` приемки кандидатные числа не используются как release-gate.

## 6.7. Retention guardrails

1. Настройка retention идет с фронта, но в рамках guardrails:
   - `min_days = 30`
   - `default_days = 90`
   - `max_days = 365`
2. Значения вне диапазона отклоняются backend-валидацией.
3. Очистка логов выполняется планово с dry-run отчетом.
4. `legal_hold` не входит в MVP и рассматривается как post-MVP/enterprise extension.
5. Ответственный за cleanup:
   - Laravel scheduled command/cron;
   - таблицы минимум: `zone_events`, `scheduler_logs`, `command_audit`, `commands` (по утвержденной retention policy).

## 6.8. Security baseline AE2

1. Internal endpoints защищены service-to-service auth.
2. Все входы в AE2 валидируются по схеме и размеру payload.
3. Replay-protection по `nonce` включается в Hardened profile; для baseline обязателен `idempotency` и audit.
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
4. Parity validation (по выбранному cutover-профилю):
   - `shadow profile`: dual-run с сравнением AE1 vs AE2 решений;
   - `canary-first profile`: parity через canary KPI/decision drift thresholds;
   - отклонения выше порога блокируют full rollout.
5. Runtime-state migration (обязательная):
   - `_zone_states`;
   - `_controller_failures` и cooldown maps;
   - `_correction_sensor_mode_state`;
   - `_pid_by_zone`;
   - `_last_pid_tick`;
   - `_freshness_check_failure_count`;
   - runtime flags, влияющие на decision/retry/degraded;
   - глобальные throttle/circuit-breaker alert state из `main.py`.

Минимальный инвентарь распределенного in-memory state:
1. `zone_automation_service.py`:
   - `_zone_states`, `_controller_failures`, `_correction_sensor_mode_state`.
2. `correction_controller.py`:
   - `_pid_by_zone`, `_last_pid_tick`, `_freshness_check_failure_count`.
3. `main.py`:
   - глобальные переменные троттлинга/circuit-breaker alert.

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
5. Recovery тестируется отдельно для сценариев:
   - crash в середине PID-дозирования;
   - crash во время transition workflow phase;
   - crash в период cooldown/block window.

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
   - duplicate nonce (для Hardened profile);
   - stale `X-Sent-At` (для Hardened profile);
   - invalid/missing auth headers.
2. Command dedupe:
   - повтор с тем же `idempotency_key` не дает side-effect;
   - повтор с новым ключом без нового snapshot блокируется.
3. Recovery:
   - restart с восстановлением workflow/PID/runtime state;
   - crash во время PID-дозирования;
   - crash во время transition workflow phase.
4. Single-writer:
   - отсутствие конфликтов при активном continuous loop и scheduler task;
   - конкурентные loop + scheduler task для одной зоны под нагрузкой.
5. Safety:
   - config-driven safe-state transitions по причинам деградации.
6. Network partition:
   - деградация канала AE -> history-logger с проверкой hold-last-safe-state и корректного recovery.

## 6.12. Управление feature flags и retirement

1. Для каждого флага обязателен владелец, дата введения, целевая дата удаления и критерий retirement.
2. Поддерживается единый реестр флагов AE2 (`flag`, `owner`, `default`, `depends_on`, `remove_by`).
3. Для каждого релиза фиксируется тестируемая матрица поддерживаемых комбинаций.
4. Флаги без owner или с просроченным `remove_by` блокируют релиз до решения.
5. Добавление нового флага без плана удаления запрещено.

## 6.13. Владение phase transitions (active code, требуется ownership decision)

1. `check_phase_transitions` (`services/zone_controller_execution.py:15-100`) — **активная функция** (~85 LOC), реализующая:
   - переход фазы grow cycle (`advance_phase()`) по sim_clock таймингу;
   - завершение цикла (`harvest_cycle()`) при достижении последней фазы;
   - обработку circuit-breaker ошибок при переходе.
2. Функция активна только в simulation mode (`sim_clock.mode != "live"`), в live-режиме — no-op.
3. `S1` обязан принять решение:
   - либо phase transitions полностью owned Laravel (`GrowCyclePhase`) и AE-path удаляется;
   - либо AE-path фиксируется как поддерживаемый runtime path с тестами и owner;
   - либо AE-path ограничивается simulation-only с явным scope guard.
4. Двусмысленный статус (активный код без формального owner) не допускается после `S1` gate.
5. `S8` не может быть начат до фиксации этого решения, так как оно определяет объем runtime state machine в AE2.

## 6.14. Redis-vs-PostgreSQL стратегия состояния

1. PostgreSQL обязателен для durable state:
   - workflow phase/state;
   - PID snapshots;
   - dedupe decisions, требующие auditability.
2. Redis допускается только для transient TTL-state:
   - lock tokens;
   - short-lived dedupe reservations;
   - fast cooldown/freshness caches.
3. Недоступность Redis не должна ломать correctness:
   - fallback на PostgreSQL path;
   - деградация только по latency, не по safety.
4. Решение по Redis фиксируется отдельным ADR в `S4`:
   - какие ключи/TTL;
   - policy fallback;
   - требования к локальной разработке без Redis.

## 6.15. Observability и shadow-correlation

1. Метрики AE2 интегрируются в текущие Grafana dashboards без потери AE1 графиков.
2. Для shadow режима обязателен trace correlation AE1 vs AE2:
   - единый `trace_id/correlation_id`;
   - diff-код причины расхождения;
   - owner сравнения и SLA обработки divergence.
3. Пороги alerting мигрируются поэтапно:
   - baseline AE1;
   - canary thresholds для AE2;
   - финальные пороги после parity-gate.

## 6.16. Rollback playbook (обязательный минимум)

1. Триггеры отката:
   - breach по duplicate side-effect;
   - breach по safety bounds;
   - parity divergence выше порога;
   - критические replay/auth ошибки.
2. Последовательность отката:
   - freeze новых task ingress;
   - переключение feature flags (`AE2_ENABLED` и связанный набор) на legacy-safe;
   - завершение/маркировка in-flight задач;
   - возврат traffic на AE1 path.
3. Состояние и данные при откате:
   - PID/workflow state rollback strategy;
   - правила работы с миграциями БД (forward-only или controlled rollback);
   - обязательный post-rollback consistency check.

## 6.17. Фичи автономности для «посадил и забыл» (tiered backlog)

Tier 1 (минимум для режима «без ночных ручных дежурств», 4-6 недель после `S6`):
1. Trend-based proactive correction:
   - EWMA/slope-анализ по последним измерениям `pH/EC` (окно по умолчанию: 20 точек);
   - ранняя коррекция при `slope > threshold`, до выхода за target.
2. Equipment anomaly detection:
   - правило `dose sent -> no expected metric movement` в 3 последовательных окнах;
   - действие: `alarm + block dosing + zone degrade`.
3. Auto-recovery loop:
   - при offline ноде: 3 retry с backoff;
   - если восстановление не произошло за 30 минут: freeze зоны + alert.
4. Safety bounds enforcement (обязательный foundation):
   - `hard_pct`, `abs_min/abs_max`, `max_delta_per_min` (реализация в `S3`).

Tier 2 (комфортная автономность, 4-6 недель после Tier 1):
1. GDD-based phase transitions:
   - гибридное правило перехода фазы: по времени и/или по накопленному GDD (настраиваемо в рецепте).
2. Mobile approvals/notifications:
   - Telegram/push уведомления для критичных событий и resume-approve сценариев.
3. Daily health digest:
   - суточный summary по зонам (uptime, время в target, drift, equipment status).

Tier 3 (расширенная автономность, 8-12 недель, опционально):
1. Weather integration (pre-cool/pre-heat и корректировка climate policy).
2. Adaptive recipe optimization на основе истории коррекций и стабильности контуров.
3. Computer vision (вне ядра AE2, отдельный трек с камерным/ML pipeline).

Технические границы внедрения:
1. Tier 1 делается преимущественно in-place в текущих модулях (`correction_controller.py`, `zone_automation_service.py`, `zone_runtime_backoff.py`) без обязательного выделения нового сервиса.
2. Tier 2/3 не блокируют go-live AE2 core и выполняются feature-flag gated.
3. Все tier-фичи обязаны сохранять совместимость с существующим pipeline и owner-моделью статусов.

---

## 7. План работ для ИИ-ассистентов (S-only)

`P*` нумерация больше не используется в задачах исполнения.
Канонический формат — только `S1..S12`.

### 7.1. Последовательность Stage

1. `S1` Baseline Audit (минимальный blocking).
2. `S2` Safety Research (исследование, без production-кода).
3. `S3` Safety Implementation.
4. `S4` Contract + Security Baseline.
5. `S5` Baseline Metrics/Coverage.
6. `S6` State Serialization Audit.
7. `S7` DI/Wiring.
8. `S8` CommandGateway Migration.
9. `S9` Correction/Policy Hardening.
10. `S10` Resilience Consolidation.
11. `S11` Observability + Integration + Cutover.
12. `S12` Load/Chaos/Acceptance.

### 7.2. Роли по Stage

| Stage | Роль | Режим |
|------|------|-------|
| S1 | AI-ARCH | read-only audit |
| S2 | AI-ARCH | read-only research |
| S3 | AI-CORE | implementation |
| S4 | AI-ARCH + AI-SEC | contract/spec + limited code |
| S5 | AI-QA + AI-ARCH | metrics/coverage baseline |
| S6 | AI-ARCH | read-only audit |
| S7 | AI-CORE | implementation |
| S8 | AI-CORE + AI-RELIABILITY | migration implementation |
| S9 | AI-CORE | implementation |
| S10 | AI-RELIABILITY | implementation |
| S11 | AI-INTEGRATION + AI-QA | integration/cutover |
| S12 | AI-QA | validation/release |

### 7.3. Формат self-contained задачи (обязательный для каждого Stage)

Для каждого stage создается отдельный файл:
`doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S<NN>_TASK.md`

Минимальная структура:
1. `Входной контекст (что прочитать)`.
2. `Конкретные файлы для изменения`.
3. `Файлы, которые запрещено менять`.
4. `Тесты для проверки`.
5. `Критерий завершения`.
6. `Роль и режим (read-only / implementation)`.

### 7.4. Верификация gate предыдущего Stage (обязательная)

Перед стартом любого `S(n)` исполнитель обязан:
1. Проверить наличие артефактов `S(n-1)` в `doc_ai/10_AI_DEV_GUIDES/`.
2. Проверить checklist gate предыдущего Stage.
3. Зафиксировать результат в `AE2_CURRENT_STATE.md`.

Пример gate `S1 -> S2`:
1. `[ ]` существует `AE2_STAGE_S01_TASK.md`.
2. `[ ]` существует `AE2_P0A_MIN_BLOCKING_AUDIT.md`.
3. `[ ]` в аудите есть `Invariants`, `Command Flow Map`, `Ownership Map`.
4. `[ ]` базовые тесты automation-engine проходят.

### 7.5. CURRENT_STATE (обязательный артефакт между сессиями)

Поддерживать файл:
`doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`

Минимум:
1. `Текущий Stage`.
2. `Завершенные Stage`.
3. `Открытые решения/ADR`.
4. `Известные проблемы/flaky tests`.
5. `Кумулятивный список измененных файлов`.

### 7.6. Machine Guard Rails (обязательные CI-инварианты)

В CI добавить проверку `AE2_INVARIANTS.py` (или эквивалент shell-check), минимум:
1. Команды к history-logger отправляются только из `infrastructure/command_bus.py`.
2. Нет прямой MQTT-публикации из automation-engine runtime-кода.
3. Все feature flags зарегистрированы в `application/executor_constants.py`.
4. В Python-сервисах нет ручного SQL DDL (`CREATE/ALTER/DROP TABLE`).

### 7.7. Конкретные call sites для миграции на CommandGateway (S8)

Обязательные точки миграции:
1. `services/zone_controller_processors.py`:
   - `process_climate_controller()`
   - `process_irrigation_controller()`
   - `process_light_controller()`
   - `process_recirculation_controller()`
2. `correction_controller.py`:
   - `check_and_correct()` и связанные publish-path.
3. `correction_command_retry.py`:
   - `publish_controller_command_with_retry()`
   - `trigger_ec_partial_batch_compensation()`
4. `application/command_publish_batch.py`:
   - `publish_batch()`.
5. `application/command_dispatch.py`:
   - все прямые вызовы `CommandBus`.
6. `main.py:publish_correction_command()` (deprecated):
   - legacy path, подлежит удалению после миграции.

Для `S8` обязателен отдельный план миграции тестов:
1. список тестов, которые должны быть адаптированы;
2. стратегия совместимости (`adapter shim` или полный cutover);
3. подтверждение, что regression suite не деградировал.

### 7.8. Stage Cards (кратко)

`S1` Baseline Audit:
1. Выход: `AE2_P0A_MIN_BLOCKING_AUDIT.md`, `AE2_SAFETY_HOTFIX_BACKLOG.md`.
2. Режим: read-only.

`S2` Safety Research:
1. Выход: `AE2_SAFETY_RESEARCH_S2.md` (где именно внедрять bounds/freshness/rate-limit).
2. Режим: read-only.

`S3` Safety Implementation:
1. Изменять: `correction_controller.py`, `zone_automation_service.py`, `config/settings`.
2. Не менять: `command_bus.py`, `main.py` (кроме согласованного crash-mitigation).
3. Выход: зелёные тесты + новые tests на `hard_pct/abs_min/abs_max/max_delta_per_min`.

`S4` Contract + Security Baseline:
1. Baseline security: `Authorization` + `X-Trace-Id`.
2. Hardened security: `DEFERRED`, не реализовывать без явного запроса.

`S5` Baseline Metrics/Coverage:
1. Baseline CSV (`p50/p95/p99`) + coverage report + фиксация gate-метрик.

`S6` State Serialization Audit:
1. Инвентарь runtime-state + `serialize()/deserialize()` contracts.

`S7` DI/Wiring:
1. Manual composition root baseline + удаление monkey-patch пути.

`S8` CommandGateway Migration:
1. Спецификация миграции call sites + phased split для `scheduler/main.py`.
2. Cutover обязательных publish-path через `CommandGateway`.
3. Regression suite обязателен без снижения pass-rate.

`S9` Correction/Policy Hardening:
1. Extraction policy/state machine без регрессий дозирования.
2. Реализовать Trend-based proactive correction (EWMA/slope) для `pH/EC`.
3. Реализовать Equipment anomaly detection (`dose -> no_effect x3`) с авто-блокировкой дозирования и деградацией зоны.

`S10` Resilience Consolidation:
1. dedupe/retry/backoff/circuit-breaker слой в согласованной архитектуре.
2. Реализовать auto-recovery loop для offline нод с retry/backoff/freeze и state reconcile.
3. Довести crash-recovery для runtime-state (`_zone_states`, PID, cooldown maps) до проверяемого состояния.

`S11` Observability + Integration + Cutover:
1. default: `canary-first -> full`;
2. optional: `shadow -> canary -> full` по ADR/risk-review.
3. Tier 2 integrations:
   - GDD-based phase transitions (в связке с recipe/backend контрактом);
   - mobile push/telegram approvals;
   - daily health digest.

`S12` Acceptance:
1. load/chaos/parity/SLO gates;
2. go-live только после полного release checklist.
3. Tier 3 planning gate:
   - weather integration;
   - adaptive recipe optimization;
   - computer vision трек (отдельный ADR и scope).

### 7.9. Tier roadmap для «посадил и забыл»

1. Tier 1 (4-6 недель после `S6`): `S9 + S10`
   - proactive correction, anomaly detection, auto-recovery;
   - mandatory safety bounds уже должны быть закрыты в `S3`.
2. Tier 2 (4-6 недель после Tier 1): `S11`
   - GDD transitions, mobile approvals, daily digest.
3. Tier 3 (8-12 недель, отдельный budget): post-`S12`
   - weather, adaptive optimization, computer vision.
4. Rule:
   - Tier 2/3 не стартуют, пока Tier 1 не прошел acceptance на реальных зонах.

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
11. Выбранный cutover-профиль (`canary-first` или `shadow -> canary -> full`) и rollback проверены на стенде.
12. Для Tier 1 подтверждено:
   - proactive correction снижает поздние коррекции по выходу за target;
   - anomaly detection корректно блокирует неэффективное дозирование;
   - auto-recovery восстанавливает/замораживает зону по регламенту без silent-failure.
13. Для Tier 2 (если включен в релиз) подтверждено:
   - GDD/time phase transitions работают по настройке рецепта;
   - critical alerts доступны в mobile channel;
   - daily health digest формируется автоматически.

---

## 10. Шаблон задачи для любого ИИ-ассистента (обязательный)

```markdown
# Задача: <S1..S12 + короткое название>

## Роль
Ты <AI-ARCH|AI-CORE|AI-PLUGIN|AI-RELIABILITY|AI-INTEGRATION|AI-SEC|AI-QA>.

## Куда смотреть
- <список .md>
- <список файлов кода>

## Конкретные файлы для изменения
- <список файлов>

## Файлы, которые ЗАПРЕЩЕНО менять
- <список файлов>

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
4. Обновление `AE2_CURRENT_STATE.md`.
5. Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
```

---

## 11. Реалистичный старт (первые 2 недели)

Реалистичный 2-недельный план для малой команды:

1. Неделя 1 (обязательный минимум):
   - закрыть `S1` в минимальном объеме (invariants + command map + ownership map);
   - выполнить `S2` для dedupe/state/shadow unknowns;
   - запустить `S3 safety-hotfix track`:
     - bounds (`hard_pct`, `abs_min`, `abs_max`);
     - `max_delta_per_min`;
     - per-signal freshness;
     - быстрый crash-mitigation для `_zone_states`.
2. Неделя 2:
   - `S4` (contract/security baseline: `Authorization` + `X-Trace-Id`, hardened headers только по threat-model);
   - старт `S5` метрик/coverage в параллель;
   - старт `S6` state serialization inventory.
3. За пределами 2 недель:
   - `S7` DI container implementation;
   - `S8/S10/S11+` после закрытия gate по baseline и spike-результатам.
4. Ближайший практический горизонт после core-hardening (следующие 4-6 недель):
   - Tier 1 автономности через `S9 + S10`:
     - proactive correction;
     - anomaly detection;
     - auto-recovery loop.

Условие перехода к `S8+`:
1. `S1` закрыт.
2. Safety-hotfix из `S3` внедрены и протестированы.
3. Решения `S2` и baseline `S5` готовы для release-gate.

---

## 12. Пересмотренный приоритет фаз (через Stage-порядок)

| Stage | Приоритет | Обоснование |
|------|-----------|-------------|
| S1 | Критический | Минимальный blocking аудит нужен для безопасного старта изменений. |
| S2 | Критический | Spike и rewrite-exit проверка нужны до существенных инвестиций в реализацию. |
| S3 | Критический | Safety-hotfix (bounds/freshness/state mitigation) нельзя откладывать. |
| S4 | Высокий | Contract/security baseline нужен для стабильного межсервисного поведения. |
| S5 | Высокий | Baseline метрики/coverage обязательны до release-gate. |
| S6 | Высокий | Без serialization contracts crash-recovery неполный. |
| S7 | Средний | DI нужен для системной декомпозиции, но не должен блокировать safety минимум. |
| S8 | Средний | Миграция single-writer через CommandGateway и закрытие dual-writer рисков. |
| S9 | Высокий | Включает Tier 1 proactive correction и anomaly detection для режима «посадил и забыл». |
| S10 | Высокий | Включает Tier 1 auto-recovery; критично для ночной/безоператорной эксплуатации. |
| S11 | Средний | Tier 2 integrations (GDD/mobile/digest) после стабилизации ядра и Tier 1. |
| S12 | Низкий | Финальная нагрузочная/chaos приемка перед full rollout. |

---

## 13. Матрица ключевых рисков исполнения

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| S1/S5 задерживают проект | Высокая | Критическое | Минимизация S1 + parallel S5 + неблокируемый S3 safety-hotfix track |
| Tier 1 автономности откладывается из-за refactor-only фокуса | Средняя | Высокое | Зафиксировать обязательный delivery `S9+S10` с отдельными acceptance KPI |
| Скрытая связанность bound/delegate методов | Высокая | Высокое | Расширенный inventory + decision-complete ADR |
| Неполное crash-recovery состояния | Средняя | Критическое | S6 serialization contracts + recovery tests |
| Race condition в dedupe reserve/check | Средняя | Высокое | S2 spike + атомарный pre-publish arbitration |
| Сложность shadow deployment/comparator | Средняя | Среднее | Ранний архитектурный выбор в S1/S2 |
| Ошибка миграции PID-state | Низкая | Критическое | warm-start window + safety stop + rollback trigger |

---

## 14. Единая схема команд и каналов AE и нод

### 14.1. Архитектура публикации команд

```
┌─────────────┐    ┌────────────────────┐    ┌────────────────┐    ┌───────┐    ┌─────────┐
│  Scheduler  │───▶│  Automation-Engine │───▶│ History-Logger │───▶│ MQTT  │───▶│ ESP32   │
│   (tasks)   │    │   (decisions)      │    │  (single-writer)│    │broker │    │  Node   │
└─────────────┘    └────────────────────┘    └────────────────┘    └───────┘    └─────────┘
       │                    │                        │
       │                    │                        │
       ▼                    ▼                        ▼
   task_commands      controller_commands      MQTT publish
   (schedule)          (corrections)           (QoS=1)
```

**Правило**: Единственная точка публикации команд в MQTT — `history-logger`. Прямая публикация из Laravel/Scheduler/Automation-Engine запрещена.

### 14.2. Типы каналов

| Тип | Назначение | `message_type` | Примеры каналов |
|-----|------------|----------------|-----------------|
| **SENSOR** | Телеметрия с датчиков | `telemetry` | `ph_main`, `ec_main`, `temp_air`, `humidity`, `water_level` |
| **ACTUATOR** | Управление исполнительными устройствами | `command` / `command_response` | `pump_acid`, `pump_base`, `pump_irrigation`, `fan_air`, `heater_air`, `white_light` |
| **SYSTEM** | Системные команды ноде | `command` (channel=`system`) | `system` (для `activate_sensor_mode`, `deactivate_sensor_mode`) |
| **VIRTUAL** | Вычисляемые метрики (без прямой публикации) | — | internal state, derived metrics |

### 14.3. Реестр команд

#### 14.3.1. Актуаторные команды (`_ACTUATOR_COMMANDS`)

| Команда | Параметры | Совместимые каналы | Описание |
|---------|-----------|-------------------|----------|
| `set_relay` | `state: bool` | ACTUATOR | Вкл/выкл реле |
| `set_pwm` | `value: int (0-255)` | ACTUATOR | PWM-управление (вентиляторы) |
| `run_pump` | `duration_ms: int`, `ml: float` (opt) | ACTUATOR (pump_*) | Запуск насоса на время/объём |
| `dose` | `ml: float`, `ttl_ms: int` | ACTUATOR (pump_acid, pump_base, pump_a/b/c/d) | Точное дозирование |
| `light_on` | `channel: str` | ACTUATOR (white_light, uv_light) | Включить свет |
| `light_off` | `channel: str` | ACTUATOR (white_light, uv_light) | Выключить свет |

#### 14.3.2. Системные команды (`_SYSTEM_MODE_COMMANDS`)

| Команда | Параметры | Канал | Ноды | Описание |
|---------|-----------|-------|------|----------|
| `activate_sensor_mode` | — | `system` | pH/EC nodes | Активировать режим калибровки датчика |
| `deactivate_sensor_mode` | — | `system` | pH/EC nodes | Деактивировать режим калибровки |

**Правило совместимости**: Команды `activate_sensor_mode`/`deactivate_sensor_mode` работают **только** на канале `system` для pH/EC нод. Актуаторные команды **запрещены** на канале `system`.

### 14.3.3. Команды ответа (`command_response`)

**Терминальные статусы** (`_TERMINAL_COMMAND_STATUSES`):

| Статус | Семантика | Источник |
|--------|-----------|----------|
| `DONE` | Успешное выполнение | Node |
| `ERROR` | Ошибка выполнения | Node |
| `INVALID` | Невалидные параметры/несовместимость | Node |
| `BUSY` | Устройство занято | Node |
| `NO_EFFECT` | Команда не изменила состояние | Node |
| `TIMEOUT` | Истёк срок выполнения | Node |
| `SEND_FAILED` | Ошибка публикации (backend) | AE / History-Logger |

**Legacy-статусы `ACCEPTED` и `FAILED` запрещены.**

### 14.4. Реестр каналов по типам нод

#### 14.4.1. pH-нода (ph_node)

| Канал | Тип | `metric_type` | Единицы | Команды |
|-------|-----|---------------|---------|----------|
| `ph_main` | SENSOR | `PH` | pH | — |
| `temp_ph` | SENSOR | `TEMPERATURE` | °C | — |
| `pump_acid` | ACTUATOR | — | ml | `dose`, `run_pump`, `set_relay` |
| `pump_base` | ACTUATOR | — | ml | `dose`, `run_pump`, `set_relay` |
| `system` | SYSTEM | — | — | `activate_sensor_mode`, `deactivate_sensor_mode` |

#### 14.4.2. EC-нода (ec_node)

| Канал | Тип | `metric_type` | Единицы | Команды |
|-------|-----|---------------|---------|----------|
| `ec_main` | SENSOR | `EC` | µS/cm | — |
| `temp_ec` | SENSOR | `TEMPERATURE` | °C | — |
| `pump_a` | ACTUATOR | — | ml | `dose`, `run_pump`, `set_relay` |
| `pump_b` | ACTUATOR | — | ml | `dose`, `run_pump`, `set_relay` |
| `pump_c` | ACTUATOR | — | ml | `dose`, `run_pump`, `set_relay` |
| `pump_d` | ACTUATOR | — | ml | `dose`, `run_pump`, `set_relay` |
| `system` | SYSTEM | — | — | `activate_sensor_mode`, `deactivate_sensor_mode` |

#### 14.4.3. Climate-нода (climate_node)

| Канал | Тип | `metric_type` | Единицы | Команды |
|-------|-----|---------------|---------|----------|
| `temp_air` | SENSOR | `TEMPERATURE` | °C | — |
| `humidity` | SENSOR | `HUMIDITY` | % | — |
| `co2` | SENSOR | `CO2` | ppm | — |
| `fan_air` | ACTUATOR | — | — | `set_pwm`, `set_relay` |
| `heater_air` | ACTUATOR | — | — | `set_relay` |

#### 14.4.4. Pump-нода / Irrigation (pump_node)

**Примечание:** Отдельной `irrig_node` в firmware не существует. Функции полива и управления уровнем воды реализуются через `pump_node` с соответствующей конфигурацией каналов.

| Канал | Тип | `metric_type` | Единицы | Команды |
|-------|-----|---------------|---------|----------|
| `water_level` | SENSOR | `WATER_LEVEL` | cm | — |
| `pump_irrigation` | ACTUATOR | — | ml/L | `run_pump`, `set_relay` |
| `valve_irrigation` | ACTUATOR | — | — | `set_relay` |

#### 14.4.5. Lighting-нода (light_node)

| Канал | Тип | `metric_type` | Единицы | Команды |
|-------|-----|---------------|---------|----------|
| `white_light` | ACTUATOR | — | — | `light_on`, `light_off`, `set_pwm` |
| `uv_light` | ACTUATOR | — | — | `light_on`, `light_off` |

#### 14.4.6. Relay-нода (relay_node)

| Канал | Тип | `metric_type` | Единицы | Команды |
|-------|-----|---------------|---------|----------|
| `relay_1` | ACTUATOR | — | — | `set_relay` |
| `relay_2` | ACTUATOR | — | — | `set_relay` |
| `relay_3` | ACTUATOR | — | — | `set_relay` |
| `relay_4` | ACTUATOR | — | — | `set_relay` |

**Примечание:** Количество каналов зависит от конфигурации конкретной ноды. Relay-нода — универсальный тип для управления нагрузками через реле.

### 14.5. Роли актуаторов (ActuatorRegistry.ROLE_ALIASES)

Система маппинга ролей на конкретные каналы для абстракции доменной логики (верифицировано по `actuator_registry.py`, 14 ролей):

| Роль | Алиасы | Разрешение → канал |
|------|--------|-------------------|
| `irrigation_pump` | `main_pump`, `pump_irrigation`, `pump`, `irrig` | `pump_irrigation` |
| `recirculation_pump` | `recirculation`, `recirc` | `pump_recirculation` |
| `ph_acid_pump` | — | `pump_acid` |
| `ph_base_pump` | — | `pump_base` |
| `ec_npk_pump` | — | `pump_a` (или b/c/d по конфигу) |
| `ec_calcium_pump` | — | `pump_b` (по конфигу) |
| `ec_magnesium_pump` | — | `pump_c` (по конфигу) |
| `ec_micro_pump` | — | `pump_d` (по конфигу) |
| `fan` | `vent`, `ventilation` | `fan_air` |
| `heater` | `heating` | `heater_air` |
| `white_light` | `light_white` | `white_light` |
| `uv_light` | `light_uv` | `uv_light` |
| `flow_sensor` | `flow` | `flow_sensor` |
| `soil_moisture_sensor` | `soil_moisture` | `soil_moisture_sensor` |

### 14.6. MQTT-топики

#### 14.6.1. Формат топиков

```
hydro/{gh}/{zone}/{node}/{channel}/{message_type}
```

| Сегмент | Пример | Описание |
|---------|--------|----------|
| `{gh}` | `gh-1` | Greenhouse UID |
| `{zone}` | `zn-1` | Zone UID или `zn-temp` для PRECONFIG |
| `{node}` | `nd-ph-1` | Node UID |
| `{channel}` | `pump_acid`, `system` | Канал связи |
| `{message_type}` | `telemetry`, `command`, `command_response`, `status` | Тип сообщения |

#### 14.6.2. Примеры топиков

| Направление | Топик |
|-------------|-------|
| Телеметрия pH | `hydro/gh-1/zn-1/nd-ph-1/ph_main/telemetry` |
| Команда дозирования | `hydro/gh-1/zn-1/nd-ph-1/pump_acid/command` |
| Ответ на команду | `hydro/gh-1/zn-1/nd-ph-1/pump_acid/command_response` |
| Системная команда | `hydro/gh-1/zn-1/nd-ph-1/system/command` |
| Статус ноды | `hydro/gh-1/zn-1/nd-ph-1/status` |

### 14.7. Валидация совместимости команд и каналов

```python
# В command_bus.py
_ACTUATOR_COMMANDS = {"set_relay", "set_pwm", "run_pump", "dose", "light_on", "light_off"}
_SYSTEM_MODE_COMMANDS = {"activate_sensor_mode", "deactivate_sensor_mode"}

def verify_command_channel_compatibility(channel: str, cmd: str) -> Tuple[bool, Optional[str]]:
    # Системные команды — только на канале 'system'
    if cmd in _SYSTEM_MODE_COMMANDS:
        if channel != "system":
            return False, "sensor_mode_requires_system_channel"
        return True, None
    
    # Актуаторные команды запрещены на 'system'
    if cmd in _ACTUATOR_COMMANDS:
        if channel == "system":
            return False, "actuator_command_on_system_channel"
    
    return True, None
```

### 14.8. Правила расширения для AE2

1. **Новые команды**: Добавлять только через обновление `_ACTUATOR_COMMANDS` / `_SYSTEM_MODE_COMMANDS` в `command_bus.py` и документирование в данном разделе.

2. **Новые каналы**: Регистрировать в `NODE_CHANNELS_REFERENCE.md` с указанием `metric_type` и единиц измерения.

3. **Новые типы нод**: Создавать полный реестр каналов по аналогии с разделом 14.4.

4. **Новые роли актуаторов**: Добавлять в `ActuatorRegistry.ROLE_ALIASES` с правилами разрешения.

5. **Обратная совместимость**: Любые изменения требуют строки `Compatible-With` в PR/коммите.

### 14.9. Gap-анализ для AE2

| Текущее состояние | Требование AE2 | Действие |
|-------------------|----------------|----------|
| Команды в `_ACTUATOR_COMMANDS` (hardcoded) | Динамический реестр команд | S11: Schema registry |
| Каналы в `NODE_CHANNELS_REFERENCE.md` | Автоматический парсинг | S11: Schema generation |
| Валидация в `command_bus.py` | Централизованный validator | S2: pre-publish dedupe spike + S8 rollout |
| Роли в `ActuatorRegistry` | Zone-specific resolution | S8: Zone controller arbitration |

---

## 15. Appendix: Legacy P->S Mapping (read-only)

Эта таблица нужна только для обратной совместимости со старыми обсуждениями.
В новых задачах использовать только `S1..S12`.

| Legacy | S-Stage |
|--------|---------|
| P0a | S1 |
| P0.5 | S2 |
| P2 | S3 |
| P1 | S4 |
| P0b | S5 |
| P1.3 | S6 |
| P1.5 | S7 |
| P3 | S8 |
| P5 | S9 |
| P6 | S10 |
| P4/P7/P8 | S11 |
| P9 | S12 |

---

## 16. Допущения и defaults для текущей ревизии

1. Правки текущей итерации ограничены одним документом:
   - `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`.
2. Новые артефакты/ADR в этом шаге фиксируются как обязательные deliverables, без создания файлов.
3. Пайплайн и инварианты совместимости не меняются.
4. Формат документа остается в стиле `doc_ai` (русский язык, структурные секции, Compatible-With).
