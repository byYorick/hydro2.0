# SCHEDULER_WORKSPACE_ZERO_LEGACY_ROLLOUT.md
# Реалистичный zero-legacy rollout вкладки Scheduler Workspace

**Версия:** 1.0  
**Дата:** 2026-03-27  
**Статус:** План внедрения

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Зафиксировать реалистичный план перевода вкладки зоны `Scheduler` на каноническую модель
без дальнейшего размножения legacy-контрактов, legacy-терминологии и зависимостей от
`scheduler_logs` в operator UI.

Итоговое состояние:

- operator UI читает только канонический workspace-контракт;
- план (`plan`) и исполнение (`execution`) разделены как разные сущности;
- публичные endpoints `scheduler-tasks` удалены;
- runtime и Laravel scheduler не используют `scheduler_logs` как operational source of truth;
- diagnostics живут в отдельном инженерном контракте и не смешаны с operator UX;
- контракт изначально проектируется расширяемым для новых scheduler-lane:
  `irrigation`, `climate`, `lighting`.

---

## 2. Контекст и исходные проблемы

На момент составления плана система содержит несколько архитектурных противоречий:

1. Frontend-спеки считают `GET /api/zones/{id}/scheduler-tasks` canonical operator-contract.
2. Backend-спеки уже помечают `scheduler-tasks` как `LEGACY / TO BE REMOVED`.
3. Текущая вкладка `ZoneSchedulerTab.vue` по смыслу является экраном исполнения задач,
   а не полноценным экраном планирования.
4. `scheduler_logs` используются не только для исторической диагностики, но и внутри
   Laravel scheduler для вычисления `last_run` interval-задач.
5. В `ae3` на текущем этапе реально поддержан только `irrigation` как исполняемый
   start-cycle task type; значит UI не должен обещать полноценное исполнение всех
   scheduler-lane до выравнивания runtime-capability.

При этом roadmap системы уже предполагает расширение scheduler workspace как минимум на:

- `climate`
- `lighting`

Следствие:

- нельзя просто “перерисовать UI”;
- нельзя просто удалить legacy endpoint;
- нельзя строить новый `plan` на модели, которая отличается от реального dispatcher-а;
- нельзя объявлять unified schedule workspace для task types, которые текущий runtime
  ещё не исполняет канонически.

---

## 3. Жёсткие инварианты rollout

Во всех этапах обязательно сохраняются следующие правила:

- защищённый command pipeline не меняется:
  `Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`;
- Laravel не публикует MQTT напрямую;
- `POST /zones/{id}/start-cycle` остаётся единственной внешней wake-up точкой зоны;
- operator UI не читает `scheduler_logs`;
- runtime read-path для automation config остаётся:
  `automation_config_documents -> automation_effective_bundles`;
- не вводятся временные legacy alias routes, legacy payload fields или dual-contract как
  постоянное состояние;
- все schema changes делаются только через Laravel migrations;
- все breaking changes явно отражаются в `doc_ai`.

---

## 4. Целевая модель

### 4.1. Доменные сущности

Вместо исторического `scheduler-task` используются три отдельные сущности:

1. `PlanWindow`
- ожидаемое окно запуска планировщика;
- строится из того же scheduler/planner кода, который реально используется в dispatch-cycle;
- идентичность:
  `plan_window_id = {zone_id}:{schedule_key}:{trigger_at_iso}`;
- не является командой и не является execution.

2. `ExecutionRun`
- фактическое выполнение одного wake-up / одного канонического runtime run;
- идентичность:
  `execution_id = ae_tasks.id`;
- lifecycle и детализация строятся из `ae_tasks`, `zone_automation_intents`, `zone_events`.

3. `SchedulerDiagnostics`
- инженерный operational/debug слой;
- может опираться на `scheduler_logs`, `laravel_scheduler_active_tasks`, dispatcher metrics;
- не является source of truth для operator UI.

### 4.1.1. Расширяемость lane-model

Контракт workspace должен быть расширяемым без нового redesign API.

Базовые правила:

- каждый lane описывается через `task_type`;
- lane имеет собственный `mode`, `capabilities`, `windows`, `summary`;
- UI не должен хардкодить только `irrigation`;
- новые lane добавляются data-driven через `capabilities` и `plan.lanes[]`;
- `climate` и `lighting` должны включаться в тот же workspace-контракт, а не отдельными
  параллельными scheduler APIs.

Минимально резервируемые `task_type`:

- `irrigation`
- `climate`
- `lighting`

Допускаемые будущие:

- `solution_change`
- `diagnostics`
- `ventilation`
- `mist`

### 4.2. Канонический operator-contract

Новый публичный contract для вкладки зоны:

`GET /api/zones/{id}/schedule-workspace?horizon=24h|7d`

Response envelope:

```json
{
  "status": "ok",
  "data": {
    "control": {
      "automation_runtime": "ae3",
      "control_mode": "auto",
      "allowed_manual_steps": [],
      "bundle_revision": "rev-2026-03-27-01",
      "generated_at": "2026-03-27T10:00:00Z",
      "timezone": "Europe/Simferopol"
    },
    "capabilities": {
      "executable_task_types": ["irrigation"],
      "planned_task_types": ["irrigation", "climate", "lighting"],
      "diagnostics_available": true
    },
    "plan": {
      "horizon": "24h",
      "lanes": [
        {
          "task_type": "irrigation",
          "label": "Полив",
          "mode": "interval"
        },
        {
          "task_type": "climate",
          "label": "Климат",
          "mode": "schedule",
          "enabled": false,
          "available": false
        },
        {
          "task_type": "lighting",
          "label": "Свет",
          "mode": "schedule",
          "enabled": false,
          "available": false
        }
      ],
      "windows": [
        {
          "plan_window_id": "3:zone:3|type:irrigation|time=None|start=None|end=None|interval=1800:2026-03-27T12:00:00Z",
          "zone_id": 3,
          "task_type": "irrigation",
          "schedule_key": "zone:3|type:irrigation|time=None|start=None|end=None|interval=1800",
          "trigger_at": "2026-03-27T12:00:00Z",
          "origin": "effective_targets",
          "state": "planned"
        }
      ],
      "summary": {
        "planned_total": 12,
        "suppressed_total": 0,
        "missed_total": 0
      }
    },
    "execution": {
      "active_run": null,
      "recent_runs": [],
      "counters": {
        "active": 0,
        "completed_24h": 0,
        "failed_24h": 0
      }
    }
  }
}
```

Detail-contract:

`GET /api/zones/{id}/executions/{executionId}`

Источник:

- `ae_tasks`
- `zone_automation_intents`
- `zone_events`
- при необходимости `ae_commands`

Отдельный инженерный contract:

`GET /api/zones/{id}/scheduler-diagnostics`

Доступ:

- только `engineer|admin`

---

## 5. Не-цели первого rollout

В рамках данного rollout не делаем:

- unified executable scheduler для `lighting`, `ventilation`, `solution_change`, `mist`, `diagnostics`,
  пока `ae3` их не поддерживает канонически;
- каноническое исполнение `climate` и `lighting` в v1, если runtime ещё не доведён
  до того же качества инвариантов, что и `irrigation`;
- перенос device-level scheduling в Laravel;
- новый MQTT / command transport;
- сохранение старого operator-contract параллельно новому на долгий срок;
- rebranding всех внутренних scheduler-терминов за одну итерацию.

---

## 6. Принципиальные архитектурные решения

### 6.1. Plan строится только из реального planner path

`plan.windows` не вычисляются отдельной “UI-логикой”.

Обязательное правило:

- Workspace reuse должен использовать тот же scheduler domain path, что и Laravel dispatcher:
  те же `ScheduleItem`, те же parser-ы, те же effective targets, те же правила времени.

Следствие:

- если dispatcher способен породить `ScheduleItem`, workspace обязан показать
  соответствующее `PlanWindow`;
- если dispatcher не может породить executable run для task type в текущем runtime,
  workspace не показывает этот lane как executable.

Требование расширяемости:

- planner path для `climate` и `lighting` должен подключаться в тот же builder `PlanWindow`,
  а не в отдельные ad-hoc endpoints;
- добавление нового task type не должно требовать изменения public response shape.

### 6.2. Execution строится только из canonical runtime state

`execution.active_run` и `recent_runs[]` не читаются из `scheduler_logs`.

Источник истины:

- `zone_automation_intents` для durable lifecycle намерения;
- `ae_tasks` для канонического runtime run;
- `zone_events` для timeline;
- `ae_commands` для command-step details при необходимости.

### 6.3. Diagnostics отделяются физически и семантически

Никаких dev-block внутри основного operator UI.

Diagnostics:

- отдельный endpoint;
- отдельный Vue-block или отдельная вкладка/секция только для инженерных ролей;
- допускает временную опору на `scheduler_logs`, но не протекает в public operator contract.

---

## 7. Реалистичный zero-legacy rollout на 3 этапа

## Этап 1. Canonical foundations

### Цель

Убрать архитектурную двусмысленность и подготовить канонический backend read-model,
не ломая текущий operator UI до момента cutover.

### Что делаем

1. Переписываем документацию:
- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- `doc_ai/07_FRONTEND/FRONTEND_UI_UX_SPEC.md`
- `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

2. Фиксируем новый vocabulary:
- `scheduler-task` больше не используется как operator-domain term;
- operator domain terms: `plan window`, `execution run`, `scheduler diagnostics`.

3. Вводим backend read-model services:
- `ScheduleWorkspaceBuilder`
- `PlanWindowBuilder`
- `ExecutionRunReadModel`

4. Вводим новый API без переключения UI:
- `GET /api/zones/{id}/schedule-workspace`
- `GET /api/zones/{id}/executions/{executionId}`
- `GET /api/zones/{id}/scheduler-diagnostics`

5. Внутри scheduler/runtime убираем operational зависимость от `scheduler_logs`
   для interval `last_run`:
- новый canonical источник `last_completed_at` должен читаться из terminal `ae_tasks`
  для task types, поддержанных текущим runtime;
- если для task type canonical execution отсутствует, task type временно исключается
  из executable workspace.

6. В capability-model явно фиксируем текущее ограничение:
- `ae3` executable v1: только `irrigation`.

7. Одновременно закладываем contract hooks для будущих lane:
- `plan.lanes[]` и `capabilities.*task_types` уже допускают `climate` и `lighting`;
- frontend types и UI layout проектируются как multi-lane, а не как irrigation-only page;
- backend builder умеет возвращать lane без executable windows, если subsystem ещё не поддержан.

### Что не делаем на этапе 1

- не меняем ещё текущую вкладку `ZoneSchedulerTab.vue` как основной operator UI;
- не удаляем legacy routes;
- не скрываем diagnostics для инженерных сценариев, пока новая замена не готова.

### Критерии приёмки

- новый workspace endpoint отдает корректный `plan` и `execution` для `irrigation`;
- контракт workspace уже принимает multi-lane shape и не требует breaking changes для
  последующего включения `climate`/`lighting`;
- `plan` строится из тех же scheduler primitives, что и реальный dispatcher;
- scheduler больше не использует `scheduler_logs` для вычисления `last_run` там,
  где execution уже канонический;
- документация больше не содержит противоречия “frontend считает canonical, backend считает legacy”.

### Stop criteria

Этап не считается завершённым, если хотя бы одно из условий не выполнено:

- `plan windows` считаются отдельной UI-логикой, а не reuse реального scheduler domain path;
- operator-contract всё ещё описывает `scheduler-tasks` как canonical;
- `schedule-workspace` обещает executable lanes, которых runtime реально не поддерживает.

---

## Этап 2. Operator cutover

### Цель

Переключить operator UI на новый workspace-контракт и убрать legacy `scheduler-tasks`
из основного пользовательского сценария.

### Что делаем

1. Полностью переписываем `ZoneSchedulerTab.vue` под модель:
- верхний блок `control + summary`;
- слева `plan timeline` по горизонту `24h/7d`;
- справа `active execution + recent runs`;
- detail panel по `executionId`.

2. Удаляем из operator UI:
- чтение `/api/zones/{id}/scheduler-tasks`;
- чтение `/api/zones/{id}/scheduler-tasks/{taskId}`;
- все `SchedulerTask*` types/formatters/composables как public operator model.

3. Вводим explicit capability UX:
- если task type не executable в текущем runtime, lane либо не показывается,
  либо маркируется как `config-only`, но не как реальный исполняемый план.

4. Верстаем layout сразу как масштабируемый multi-lane workspace:
- lane tabs / filters / timeline rows не завязаны только на `irrigation`;
- карточки и легенда поддерживают `climate` и `lighting` без нового redesign;
- пустой lane допускает состояние `planned-but-not-executable` или `not_available`.

5. Diagnostics переносим:
- в отдельный `SchedulerDiagnosticsCard` или инженерную вкладку;
- только для ролей `engineer|admin`.

6. Добавляем тесты:
- feature tests для `schedule-workspace` и `executions/{id}`;
- component tests новой вкладки;
- integration tests на соответствие `plan window` и фактического dispatch key.

### Критерии приёмки

- вкладка зоны больше не использует `scheduler-tasks`;
- основной операторский сценарий отвечает на два вопроса:
  “что запланировано?” и “что реально исполняется?”;
- detail-view опирается на `executionId = ae_tasks.id`, а не на historical task snapshot;
- UI может без breaking changes принять новые lane `climate` и `lighting`;
- `scheduler_logs` отсутствуют в operator UI path полностью.

### Stop criteria

Этап не считается завершённым, если:

- в основном UI остался хотя бы один запрос к `scheduler-tasks`;
- active/recent execution собираются из `scheduler_logs`, а не из `ae_tasks`/`zone_events`;
- engineer diagnostics по-прежнему смешаны с operator UX.

---

## Этап 3. Hard cleanup and legacy removal

### Цель

Удалить legacy public contract и зачистить остаточные зависимости, чтобы система пришла
к устойчивому zero-legacy состоянию.

### Что делаем

1. Удаляем public legacy routes и code path:
- `GET /api/zones/{id}/scheduler-tasks`
- `GET /api/zones/{id}/scheduler-tasks/{taskId}`
- соответствующие controllers, formatters, tests, Vue types, mocks

2. Проводим cleanup-аудит Laravel scheduler:
- нет operational reads из `scheduler_logs`;
- нет принятия решений operator/runtime path на основании legacy snapshot;
- `laravel_scheduler_active_tasks` используется только как dispatcher operational state.

3. Проводим cleanup-аудит docs:
- удалить historical ссылки, где old contract фигурирует как рабочий operator path;
- оставить `scheduler_logs` только как historical diagnostics storage, если таблица
  ещё нужна для retention/аудита;
- если таблица больше не нужна operationally и организационно, планировать отдельное
  удаление storage в независимой миграции.

4. Проводим capability review:
- если к этому моменту `ae3` научился исполнять новые task types канонически,
  расширяем workspace lanes;
- если нет, workspace остаётся честно ограниченным `irrigation`.

5. При готовности runtime включаем новые lane по тому же контракту:
- сначала `lighting`, если его planner/dispatcher/runtime-state проще стабилизировать;
- затем `climate`, если его execution semantics выровнены и не конфликтуют с greenhouse/global climate model;
- каждое новое включение сопровождается feature flag только на rollout-уровне, но не через новый API shape.

### Критерии приёмки

- legacy public endpoints отсутствуют;
- code search по operator path не показывает использования `scheduler-tasks`;
- `scheduler_logs` не участвуют ни в operator UI, ни в runtime-dispatch logic;
- `climate` и `lighting` могут быть включены без redesign public contract;
- документация, тесты и UI vocabulary согласованы между собой.

### Stop criteria

Этап не считается завершённым, если:

- legacy endpoint оставлен “временно на всякий случай”;
- в документации или тестах old contract всё ещё фигурирует как canonical;
- новая система требует fallback на historical snapshots для штатного operator UX.

---

## 8. Последовательность работ по слоям

### 8.1. Backend / Laravel

Обязательные изменения:

- новый workspace controller;
- новый execution detail controller;
- новый diagnostics controller;
- общий builder для `PlanWindow` из scheduler domain path;
- перенос `last_run` off `scheduler_logs`;
- feature/integration tests.

Требования на расширяемость:

- registry/task metadata по lane должен быть data-driven;
- `ScheduleWorkspaceBuilder` принимает набор поддержанных task types;
- parser/builder для `lighting` и `climate` подключаются как модули того же pipeline.

### 8.2. Python / runtime

Обязательные изменения только если выявится разрыв контрактов:

- дополнительные поля в `zone_events` или `ae_tasks` для execution detail;
- без изменения command pipeline;
- без изменения `POST /zones/{id}/start-cycle` как единственной wake-up точки.

### 8.3. Frontend / Vue

Обязательные изменения:

- новый workspace composable;
- новые types `ScheduleWorkspace`, `PlanWindow`, `ExecutionRun`;
- переработка `ZoneSchedulerTab.vue`;
- вынос diagnostics из operator flow;
- component tests.

Требования на расширяемость:

- lane rendering только через массив `plan.lanes[]`;
- label/color/icon для lane задаются через registry, а не через жёсткий `if irrigation`;
- timeline и summary допускают одновременно `irrigation`, `climate`, `lighting`.

### 8.4. Documentation

Обязательные документы на обновление:

- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- `doc_ai/07_FRONTEND/FRONTEND_UI_UX_SPEC.md`

---

## 9. Риски

### Риск 1. Drift между `plan` и реальным dispatch

Причина:
- отдельная логика вычисления окон для UI.

Снижение:
- reuse только реального scheduler domain path;
- snapshot tests на `ScheduleItem -> PlanWindow`.

### Риск 2. Ложное обещание capability

Причина:
- UI показывает lanes, которые `ae3` ещё не исполняет канонически.

Снижение:
- explicit `capabilities.executable_task_types`;
- запуск workspace v1 только для `irrigation`;
- `climate` и `lighting` добавлять только после readiness checklist по planner/runtime/API/tests.

### Риск 2.1. Неправильное расширение на climate/light

Причина:
- новые lane добавляются через особые ветки кода или новый API shape.

Снижение:
- один workspace-contract для всех lane;
- shared lane registry;
- обязательные contract tests: `irrigation`, `climate`, `lighting`.

### Риск 3. Неполный cleanup legacy

Причина:
- `scheduler_logs` остаются скрытым dependency в scheduler internals.

Снижение:
- отдельный cleanup-аудит в конце этапа 1 и этапа 3;
- code search и integration tests.

### Риск 4. Расхождение identity model

Причина:
- разные идентификаторы для plan window, intent и execution.

Снижение:
- заранее зафиксировать:
  - `plan_window_id = zone_id + schedule_key + trigger_at`
  - `execution_id = ae_tasks.id`
  - `intent_id = zone_automation_intents.id`

### Риск 5. Ошибки времени и catchup

Причина:
- DST, timezone, replay, missed-window semantics.

Снижение:
- timezone брать из greenhouse/zone context;
- semantics `planned/missed/suppressed/dispatched` зафиксировать в API spec до cutover UI;
- покрыть тестами переходы через границы суток и catchup-policy.

---

## 10. Минимальный definition of done

Rollout считается завершённым только когда выполнены все условия:

1. Вкладка зоны работает через `schedule-workspace`.
2. Detail-view работает через `executions/{id}`.
3. Public `scheduler-tasks` endpoints удалены.
4. Operator UI не читает `scheduler_logs`.
5. Laravel scheduler не зависит от `scheduler_logs` для operational решений.
6. Diagnostics отделены от operator UX.
7. Спеки backend/frontend/data model не противоречат друг другу.
8. Включение `climate` и `lighting` не требует нового публичного API или redesign вкладки.

---

## 10.1. Readiness checklist для включения нового lane

Каждый новый lane (`climate`, `lighting`) разрешается включать только если выполнены все условия:

1. Есть planner path, который порождает тот же `ScheduleItem`/эквивалентный canonical plan primitive,
   что и реальный dispatcher.
2. Есть canonical execution source of truth, эквивалентный `ae_tasks`/`zone_events`,
   без опоры на `scheduler_logs`.
3. Есть capability declaration в backend workspace contract.
4. Есть frontend rendering без special-case layout.
5. Есть feature/integration tests для:
   - plan generation
   - execution detail
   - timeline consistency
6. Нет конфликта с существующей доменной моделью:
   - для `lighting` с recipe/phase light profile
   - для `climate` с greenhouse/global climate authority

---

## 11. Короткая рекомендация по исполнению

Самый безопасный порядок:

1. Сначала закончить этап 1 полностью.
2. Не начинать UI cutover, пока backend не умеет честно отдавать `schedule-workspace`
   без опоры на legacy operator-contract.
3. Не удалять legacy endpoints до завершения этапа 2.
4. Не растягивать этап 3: hard cleanup должен идти сразу после успешного cutover,
   иначе legacy снова станет “временной нормой”.
5. `climate` и `lighting` подключать только после завершения zero-legacy базиса,
   а не параллельно с первичным cutover `irrigation`.
