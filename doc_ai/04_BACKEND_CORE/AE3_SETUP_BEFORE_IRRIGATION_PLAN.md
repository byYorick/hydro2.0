# AE3 SETUP-BEFORE-IRRIGATION PLAN
# План: гарантировать, что setup системы (cycle_start) выполняется раньше первого полива

**Дата:** 2026-04-29
**Статус:** реализовано (2026-04-29).
**Авторы:** автоматический аудит pipeline `Laravel scheduler-dispatch → AE3 → history-logger`.
**Связано с:** `ae3lite.md` §2.1, §5, §7.2; `SCHEDULER_ENGINE.md`; `SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md`; `ZoneReadinessService`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. TL;DR

Сейчас инвариант «сначала setup, потом полив» обеспечивается только тем, что `irrigation_start` на стадии `await_ready` поллит `zone_workflow_state.workflow_phase` до 30 минут и при отсутствии `ready` падает с `irrigation_wait_ready_timeout`. Сама задача setup (`cycle_start`) **не инициируется** ни scheduler-ом, ни AE3 — только Laravel-стороной (`GrowCycleAutomationDispatcher`), у которой есть несколько молчаливых отказов (console-guard, runtime-флаг, race с scheduler). При старте grow cycle оператор может видеть «полив идёт раньше сетапа» на уровне scheduler-логов и timeout-ов, хотя физического полива не происходит.

План закрывает 4 вектора одновременно (комбинация из Предложений 1–4 предыдущего аудита):

1. **Laravel scheduler не шлёт `start-irrigation` на зону, у которой `workflow_phase != 'ready'`** (fail-fast, retryable).
2. **AE3 fail-closed отклоняет `POST /zones/{id}/start-irrigation`, если `workflow_phase != 'ready'`** и отсутствует активный `cycle_start` task (защита от устаревших scheduler-ов и ручных вызовов).
3. **`GrowCycleAutomationDispatcher` дисциплинированно отправляет `cycle_start` независимо от console/cli-режима**; гарантия идемпотентного `gcs:zN:cM:hash`.
4. **UI/operator visibility:** добавить в Cockpit/scheduler причину `setup_pending` и event `IRRIGATION_BLOCKED_SETUP_PENDING`, чтобы оператор не путался с `irrigation_wait_ready_timeout`.

---

## 1. Контекст (что есть сейчас)

### 1.1 Канал A — setup системы (`cycle_start`)

`backend/laravel/app/Services/GrowCycle/GrowCycleLifecycleService.php:99` →
`GrowCycleAutomationDispatcher::dispatchAutomationStartCycle()` →
`POST /zones/{id}/start-cycle` →
AE3 `compat_endpoints.py:zone_start_cycle` →
canonical task `task_type=cycle_start`, topology `two_tank_drip_substrate_trays`.

Workflow в AE3 (`workflow_topology.py`):

```
startup
  → clean_fill_start → clean_fill_check
  → solution_fill_start → solution_fill_check (coррекция EC/pH в prepare-режиме)
  → prepare_recirculation_start → prepare_recirculation_check (доведение pH/EC до ready band)
  → complete_ready                       (workflow_phase = 'ready')
```

Только после `complete_ready` зона помечена готовой к поливу.

### 1.2 Канал B — полив (`irrigation_start`)

Laravel scheduler (`automation:dispatch-schedules`, `SchedulerCycleOrchestrator` → `ScheduleDispatcher`) по расписанию из `effective_targets.irrigation_schedule` шлёт
`POST /zones/{id}/start-irrigation` →
AE3 создаёт `task_type=irrigation_start` →
workflow:

```
await_ready (poll workflow_phase=='ready', deadline 30 мин)
  → decision_gate
  → irrigation_start → irrigation_check (correction inline)
  → irrigation_stop_to_ready | irrigation_stop_to_recovery
```

### 1.3 Текущая защита

- `await_ready.py` поллит `workflow_phase`; при таймауте — `irrigation_wait_ready_timeout` + zone event + biz alert.
- `compat_endpoints.py:zone_start_irrigation` — single-writer per zone через `ae_zone_leases`; при коллизии возвращает 409 `start_irrigation_zone_busy`.

---

## 2. Текущие проблемы

### 2.1 Console-guard в `GrowCycleAutomationDispatcher::isEnabled()`

```php
// backend/laravel/app/Services/GrowCycle/GrowCycleAutomationDispatcher.php:135-141
if (app()->runningInConsole()) {
    return false;
}
return (bool) $this->runtimeConfig->automationEngineValue('grow_cycle_start_dispatch_enabled', false);
```

**Эффект:** запуск `GrowCycleLifecycleService::startCycle()` из artisan/queue/cron не отправляет `cycle_start`. Скрипты `scripts/run_launch_cycle_dev.mjs` / `scripts/run_setup_wizard_cycle.mjs` обходят это, явно форся флаг — это симптом проблемы. `automationEngineValue(..., false)` имеет fail-closed default: даже при `AUTOMATION_GROW_CYCLE_START_DISPATCH_ENABLED=true` в `.env` runtime-конфиг в БД может перебить.

### 2.2 Race scheduler ↔ start-cycle при первом цикле

При старте grow cycle через UI:
1. Транзакция `startCycle()` коммитится; в effective targets полив уже active.
2. Параллельно scheduler-cron (`automation:dispatch-schedules`, every 60s или по `dispatch_interval_sec`) может в первом же тике отправить `start-irrigation`.
3. Если `dispatchAutomationStartCycle()` упёрся в connection retry (3×150–750ms backoff) — `irrigation_start` берёт zone-lease раньше.
4. Когда retry закончится — `cycle_start` получит **HTTP 409 `start_cycle_zone_busy`** и intent помечается `failed`.
5. Уже захваченный `irrigation_start` зависает в `await_ready` 30 минут → fail.

**Это deadlock-подобный режим без авто-восстановления:** для починки оператор должен вручную дёрнуть `start-cycle` через UI (Launch tab) после остывания lease.

### 2.3 Scheduler не читает `workflow_phase`

`ScheduleDispatcher::dispatch()` фильтрует только:

- whitelist task type (`isSchedulerTaskTypeDispatchableForAe3`),
- наличие активной задачи по тому же `schedule_key` (`isScheduleBusy`).

`zone_workflow_state.workflow_phase` не используется. Любая зона с включённым irrigation schedule получает запросы независимо от того, прошёл ли setup. Это:
- генерирует лишние intents → tasks → fail-closed с alert spam,
- занимает zone-lease, блокируя нормальный `cycle_start`.

### 2.4 Operator UX

`irrigation_wait_ready_timeout` и `start_cycle_zone_busy` оператору непонятны без чтения логов AE3. Cockpit / SchedulerLog / Events показывают цепочку failed-irrigation, но не «зона ещё не подготовлена; запустите cycle_start».

---

## 3. Целевое поведение

После реализации плана:

| Сценарий | Поведение |
|----------|-----------|
| Старт grow cycle через UI | `dispatchAutomationStartCycle()` отправляет `cycle_start` сразу после commit транзакции, независимо от console-режима; scheduler в этом окне irrigation **не шлёт**, потому что зона `workflow_phase != 'ready'` |
| Старт grow cycle из artisan/queue | То же поведение; console-guard снят |
| Scheduler-tick до завершения setup | `ScheduleDispatcher` логирует `skipped` с `reason=zone_setup_pending`, intent **не создаётся**, lease не берётся |
| Прямой POST `start-irrigation` (старый клиент / агент / тест) на не-ready зону | AE3 возвращает 409 `start_irrigation_setup_pending` (новый код) и **не** создаёт `irrigation_start` task |
| Setup завершился (`workflow_phase='ready'`) | Следующий scheduler-tick шлёт `start-irrigation` штатно |
| UI оператора | Cockpit видит причину `zone_setup_pending`; на zone page есть бейдж «ожидает завершения setup» |

---

## 4. План изменений по слоям

### 4.1 Backend / Laravel

#### 4.1.1 `GrowCycleAutomationDispatcher`

- Снять `if (app()->runningInConsole()) { return false; }`. Console-режим больше не должен подавлять dispatch.
- Поведение в тестах сохранить через override `services.automation_engine.grow_cycle_start_dispatch_enabled` (как уже делается).
- В `dispatchAutomationStartCycle` поднять `maxAttempts()` с 3 до **5** и расширить условие retry: помимо 404 `Zone '%d' not found` ретраить также **409 `start_cycle_zone_busy`** с backoff до 1.5 с (накопленных), потому что зона может быть занята только что захваченным irrigation_start (см. 4.1.2 — это станет редкостью, но защита on-the-side).
- В `markIntentFailed` записывать структурированный `error_code` `automation_engine_start_cycle_zone_busy` вместо обобщённого `dispatch_failed`.

**Файл:** `backend/laravel/app/Services/GrowCycle/GrowCycleAutomationDispatcher.php`.

#### 4.1.2 `ScheduleDispatcher` — workflow_phase guard

Перед HTTP-вызовом `start-irrigation` (а также `start-cycle` через `diagnostics`) выполнить guard:

```text
IF zones.automation_runtime = 'ae3' AND task_type = 'irrigation' THEN
    SELECT workflow_phase FROM zone_workflow_state WHERE zone_id = $1
    IF workflow_phase != 'ready' OR row missing
        return [
            dispatched=false,
            retryable=true,
            reason='zone_setup_pending'
        ]
        write SchedulerLog skipped with workflow_phase + last_cycle_start_task_id
```

- Чтение должно быть **direct SQL** (`Illuminate\Support\Facades\DB::selectOne`), без зависимостей от автоматики/Inertia, чтобы не лазить в AE3.
- Кэшировать в пределах одного `runCycle()` через `$context` или новый `WorkflowPhaseStore`, чтобы не делать N запросов.
- `reason='zone_setup_pending'` добавить в `BACKPRESSURE_REASONS` (`SchedulerCycleOrchestrator.php:13-18`) и `ZONE_BUSY_ERRORS` (`ScheduleDispatcher.php:18-22`) для metrics/log консистентности.

**Файлы:**
- `backend/laravel/app/Services/AutomationScheduler/ScheduleDispatcher.php`
- `backend/laravel/app/Services/AutomationScheduler/SchedulerCycleOrchestrator.php`
- (опционально) `backend/laravel/app/Services/AutomationScheduler/WorkflowPhaseStore.php` — новый класс, batch-load `workflow_phase` для списка zone_id перед циклом, hold в `ScheduleCycleContext`.

#### 4.1.3 Frontend / Cockpit

- В `App\Services\Scheduler\ExecutionChainAssembler` добавить шаг `SETUP_PENDING` (status=`warn`), если последняя attempted dispatch отдала reason `zone_setup_pending`.
- На zone page (`Pages/Launch/Index.vue`, `Components/Launch/Automation/AutomationHub.vue`) показать бейдж/баннер: «Setup системы выполняется (фаза clean_fill / solution_fill / prepare_recirc) — полив запустится автоматически после готовности зоны». Источник — `zone_workflow_state.workflow_phase`.
- В тесте `tests/Feature/SchedulerExecutionChainTest.php` добавить кейс `zone_setup_pending`.

### 4.2 Backend / AE3 (`automation-engine`)

#### 4.2.1 Fail-closed guard в `start-irrigation`

В `backend/services/automation-engine/ae3lite/api/compat_endpoints.py:zone_start_irrigation`, после `validate_scheduler_security_baseline_fn` и до `claim_start_irrigation_intent_fn`:

```python
phase = await load_zone_workflow_phase(zone_id=zone_id)  # SELECT workflow_phase FROM zone_workflow_state
if phase != 'ready':
    raise HTTPException(
        status_code=409,
        detail={
            "error": "start_irrigation_setup_pending",
            "zone_id": zone_id,
            "workflow_phase": phase or "missing",
            "message": "Зона не готова к поливу: дождитесь завершения cycle_start (workflow_phase='ready')."
        },
    )
```

- Не зависит от наличия `cycle_start` task: единственный source of truth — `workflow_phase`.
- Никаких side-effects: intent не создаётся, lease не берётся, `ae_tasks` не пишется. Только counter `ae3_start_irrigation_setup_pending_total{zone_id}` в Prometheus.
- Соответствует §2.1 `ae3lite.md` (поле `zone_workflow_phase` — источник истины для `ready`).

**Влияние на §2.1:** `await_ready` стадия остаётся в коде как safety-net для уже созданных tasks (recovery, миграции), но при штатной работе будет редко достигаться, потому что фильтрация теперь выполняется раньше — на API ingress.

#### 4.2.2 Новый error code

Добавить в `backend/services/automation-engine/ae3lite/domain/errors.py`:

```python
START_IRRIGATION_SETUP_PENDING = "start_irrigation_setup_pending"
```

Добавить в `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` (раздел AE3).

#### 4.2.3 Observability event

В `compat_endpoints.py` при возврате 409 `start_irrigation_setup_pending` писать `zone_event` `IRRIGATION_BLOCKED_SETUP_PENDING` с payload `{zone_id, workflow_phase, source, idempotency_key, requested_mode}`. Через `common.db.create_zone_event`.

Прометей-метрика: `ae3_start_irrigation_blocked_total{reason="setup_pending"}` (label по reason, чтобы переиспользовать на будущее).

### 4.3 База данных

**Миграции не требуются.** Новый код использует существующие таблицы `zone_workflow_state`, `zone_events`, `scheduler_logs`, `zone_automation_intents`. Нужно только убедиться, что row в `zone_workflow_state` существует на момент guard-а — для этого `compileZoneCascade` уже создаёт zone row через `ZoneAutomationIntentService::ensureZoneWorkflowState()`. Если строки нет — guard трактует как `phase=missing`, что эквивалентно `not ready`.

### 4.4 Документация

- **`doc_ai/04_BACKEND_CORE/ae3lite.md`** §2.1: добавить упоминание `start_irrigation_setup_pending` как ingress-уровневой защиты, перед `await_ready`. Уточнить, что `await_ready` остаётся safety-net для already-created tasks (recovery, prior-version intent).
- **`doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md`**: добавить `start_irrigation_setup_pending`.
- **`doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`**: новый раздел «Setup-pending guard» с объяснением `reason=zone_setup_pending` и retryable=true.
- **`doc_ai/04_BACKEND_CORE/AE3_RUNTIME_EVENT_CONTRACT.md`**: новое событие `IRRIGATION_BLOCKED_SETUP_PENDING`.
- **`doc_ai/INDEX.md`**: добавить ссылку на текущий план; после реализации план перенести в `doc_ai/00_ARCHIVE/` или пометить «реализовано».

---

## 5. Этапы (последовательно, каждый с stage-level tests)

В соответствии с §3.2 `ae3lite.md` (жёсткий порядок работ).

### Этап 1. Документация-первая

1. Создать этот файл (`AE3_SETUP_BEFORE_IRRIGATION_PLAN.md`) — done.
2. Обновить `ERROR_CODE_CATALOG.md`, `AE3_RUNTIME_EVENT_CONTRACT.md`, `ae3lite.md` §2.1.
3. PR review — закрепить контракт.

### Этап 2. AE3 ingress guard (fail-closed)

1. Добавить `START_IRRIGATION_SETUP_PENDING` error code.
2. Реализовать `load_zone_workflow_phase()` infra-utility (single SQL).
3. В `compat_endpoints.py:zone_start_irrigation` вставить guard + zone_event + metric.
4. Unit-тесты:
   - `tests/test_compat_start_irrigation_setup_pending.py` — phase=`idle` → 409, intent не создаётся.
   - phase=`ready` → 200 happy-path не сломан.
   - phase row missing → 409 с `workflow_phase=missing`.
5. Integration-тест в `tests/test_ae3_lite_runtime_irrigation_*.py`: `cycle_start_completed_then_irrigation_passes`.
6. `make test-ae PYTEST_ARGS="-q test_compat_start_irrigation_setup_pending.py"` зелёный.

### Этап 3. Laravel scheduler guard

1. Создать `App\Services\AutomationScheduler\WorkflowPhaseStore` с `loadForZones(array $zoneIds): array<int,string>`.
2. Внедрить в `ScheduleCycleContext`. Один SQL на `runCycle()` (`SELECT zone_id, workflow_phase FROM zone_workflow_state WHERE zone_id IN (...)`).
3. В `ScheduleDispatcher::dispatch` для AE3-зон + `task_type='irrigation'` проверять `workflow_phase=='ready'`; иначе вернуть `['dispatched'=>false,'retryable'=>true,'reason'=>'zone_setup_pending']`.
4. Расширить `BACKPRESSURE_REASONS` и dispatch-metrics (`SchedulerCycleOrchestrator::incrementDispatchMetric` уже читает reason).
5. Тесты:
   - `tests/Feature/AutomationScheduler/SetupPendingGuardTest.php` — phase=`idle` → skipped.
   - phase=`ready` → dispatched.
   - non-AE3 zone → guard не применяется (`legacy` runtime отсутствует, оставляем future-proof).
6. `php artisan test --filter=SetupPendingGuardTest` зелёный.

### Этап 4. `GrowCycleAutomationDispatcher` cleanup

1. Удалить `runningInConsole()` guard.
2. Поднять `maxAttempts` до 5, расширить `shouldRetry()` на 409 `start_cycle_zone_busy`.
3. Структурированные `error_code` в `markIntentFailed`.
4. Тесты:
   - `tests/Feature/GrowCycle/GrowCycleAutomationDispatcherConsoleTest.php` — `Artisan::call('grow:start-cycle', [...])` → dispatcher отправил cycle_start.
   - `tests/Unit/Services/GrowCycleAutomationDispatcherRetryTest.php` — 409 zone_busy ретраится 4 раза, потом fail.
5. `php artisan test --filter=GrowCycleAutomationDispatcher` зелёный.

### Этап 5. UI / Cockpit

1. `ExecutionChainAssembler` — шаг `SETUP_PENDING`.
2. Vue: бейдж в `AutomationHub.vue` / `Pages/Launch/Index.vue`, источник — Inertia prop с `workflow_phase` зоны.
3. Тесты Vitest на компоненте + `tests/Feature/SchedulerExecutionChainTest.php`.
4. `npm run test` + `npm run typecheck` зелёные.

### Этап 6. E2E smoke

`tests/e2e/specs/ae3-setup-before-irrigation.spec.ts`:

1. Создать grow cycle на AE3-зоне через API → ожидать `cycle_start` task создан.
2. До прихода `workflow_phase=ready` сделать tick scheduler-а вручную (`automation:dispatch-schedules --zone=ID`) → ожидать `scheduler_logs` row с `reason='zone_setup_pending'`, **никакого** `irrigation_start` task в AE3.
3. Сделать ready-fixture (mock или симулятор) → следующий tick шлёт `start-irrigation`, task проходит.

`npm run e2e -- ae3-setup-before-irrigation.spec.ts` зелёный.

---

## 6. Риски и митигация

| Риск | Митигация |
|------|-----------|
| Snapshot `zone_workflow_state` отстаёт от реального состояния (race с AE3 update) | CAS update по `version` в AE3 уже есть; читаем committed read; для guard допустим лаг до 1 поллинг-цикла (10 с) — это безопасно, отказ retryable |
| Старые intents (созданные до релиза) на не-ready зонах | `await_ready` остаётся safety-net; existing tasks доедут или упадут с `irrigation_wait_ready_timeout` как раньше |
| Console-guard был защитой от "double dispatch" в тестах | Заменить на feature-flag `services.automation_engine.grow_cycle_start_dispatch_enabled` (уже есть); тесты используют `config()->set` |
| Метрики Prometheus меняют label-набор | Добавляем новые метрики `ae3_start_irrigation_blocked_total{reason}` без поломки старых |
| Frontend дёргает start-irrigation вручную | Получит 409 `start_irrigation_setup_pending` — обработать в `services/api/nodes.ts` toast |
| Backward compat для не-AE3 зон | Guard в Laravel применяется только при `automation_runtime='ae3'`; AE3-API guard не затрагивает другие пути |

---

## 7. Критерии приёмки (Definition of Done)

1. Все этапы 2-6 закрыты с зелёными stage-level тестами.
2. На staging выполнен сценарий: новый grow cycle → setup → ready → irrigation; в логах нет ни одного `irrigation_wait_ready_timeout` и ни одного `start_cycle_zone_busy` от scheduler-а.
3. Console-инициированный старт цикла (`scripts/run_launch_cycle_dev.mjs` с убранным force-флагом) работает.
4. На zone page в UI видна фаза workflow и причина блокировки полива до ready.
5. `doc_ai/04_BACKEND_CORE/ae3lite.md` §2.1, `ERROR_CODE_CATALOG.md`, `AE3_RUNTIME_EVENT_CONTRACT.md`, `SCHEDULER_ENGINE.md` обновлены.
6. Метрики `ae3_start_irrigation_blocked_total`, `scheduler_dispatches_total{result="backpressure"}` (с reason `zone_setup_pending`) появляются в Grafana dashboard.
7. Не нарушены инварианты §2 `ae3lite.md`: команды только через history-logger, lease/CAS не ослаблены, новые task types не введены.

---

## 8. Нереализуемое в этом плане (out of scope)

- **Авто-цепочка `cycle_start` из `irrigation_start`** (вариант предыдущего «Предложения 1»). Это расширение AE3 runtime invariants; противоречит §2 ae3lite.md (one task per zone) и потребует отдельного RFC. Вместо этого выбран fail-closed подход: scheduler/AE3 отказывают, `cycle_start` остаётся ответственностью Laravel (`GrowCycleLifecycleService`).
- **Kick `cycle_start` при первом scheduler-tick для зоны без активного цикла** — это уже Laravel-side задача; покрывается этапом 4 (надёжность `GrowCycleAutomationDispatcher`).
- **Манипуляция приоритетами zone-lease** — оставлено как есть, single-writer per zone.
- **Изменения в two-tank workflow / handlers** — handlers не трогаем, только ingress.

---

## 9. Связанные документы

- `doc_ai/04_BACKEND_CORE/ae3lite.md` — canonical AE3 spec (§2.1 await_ready, §5 runtime flow, §7.2 start-irrigation).
- `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md` — Laravel scheduler-dispatch.
- `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_AE3_NON_IRRIGATION_DISPATCH.md` — про другие task types.
- `doc_ai/04_BACKEND_CORE/AE3_RUNTIME_EVENT_CONTRACT.md` — события AE3.
- `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` — error codes.
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` — REST API публикации команд (не затрагивается).
