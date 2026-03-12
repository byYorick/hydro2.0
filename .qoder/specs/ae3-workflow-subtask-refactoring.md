# AE3-Lite v2: JSONB payload → Explicit Columns + Topology-Driven Routing

---

## ГЛУБОКИЙ АУДИТ АРХИТЕКТУРЫ v2

**Дата:** 2026-03-07
**Цель:** Критический анализ предложенной v2 архитектуры относительно текущей реализации.
Выявление пробелов, рисков и архитектурных проблем до начала реализации.

---

### КРИТИКА 1: Ключевой инвариант `_run_command_stage` НЕ ОТРАЖЁН в v2

**Проблема:** В текущем коде `_run_command_stage()` (строки 125-148) после `run_batch()` читает
`_FAILURE_KEY` и `_NEXT_PAYLOAD_KEY` **из обновлённого payload задачи** (`current_task.payload`),
а не из исходного. Это критично, потому что `run_batch()` возвращает task **после всех
внутренних transitions** (running → waiting_command → running).

В v2 `_handle_command` должен работать аналогично: после `run_batch()` task вернётся в `running`
с **тем же** `current_stage` (потому что `run_batch()` не меняет stage). Затем handler читает
`stage_def.next_stage` или `stage_def.terminal_error` из topology registry — это корректно,
потому что эти данные теперь в registry, а не в payload.

**Вердикт:** Этот переход **корректен**, но в плане это нигде явно не зафиксировано.
Нужно добавить: "После `run_batch()` task возвращается в `running` с тем же `current_stage`.
Handler берёт routing из `StageDef`, а не из task state."

**Риск:** НИЗКИЙ. Архитектура v2 правильно устраняет чтение из payload.

---

### КРИТИКА 2: Startup handler делает probe + routing, а v2 упрощает до одного handler

**Проблема:** Текущий `_run_startup()` (строки 74-123) содержит нетривиальную логику:
1. `_probe_irr_state()` — отправляет команду probe и проверяет состояние клапанов
2. `_read_level()` — читает уровень чистого бака
3. Sensor consistency check (max=1, min=0 → error)
4. **Если бак полный** → skip clean_fill, сразу `solution_fill_start` с deadline
5. **Если бак не полный** → `clean_fill_start` с `clean_fill_cycle=1` и deadline

В v2 topology `startup` имеет `handler: "startup"`, но план **НЕ ОПИСЫВАЕТ** эту логику.
Просто написано `_handle_startup` в списке handlers WorkflowRouter. А между тем этот handler
должен вернуть `StageOutcome(kind="transition", next_stage="clean_fill_start")` ИЛИ
`StageOutcome(kind="transition", next_stage="solution_fill_start")` — это **условный routing**,
который не кодифицирован в topology graph.

**Вердикт:** Topology registry описывает **статический** граф переходов (`StageDef.next_stage`),
но startup — это **динамический** routing. Это нормально и правильно (handler решает),
но план должен **явно** перечислить все handler-ы с их логикой и possible outcomes.

**Риск:** СРЕДНИЙ. Без явного описания handler logic можно забыть про probe_irr_state
и sensor consistency checks при реализации.

---

### КРИТИКА 3: Deadline computation — timing gap НЕ УСТРАНЁН, а перемещён

**Проблема:** План утверждает: "deadline вычисляется В МОМЕНТ ВХОДА в stage, а не pre-computed
в nested payload" — и это правда. Но в текущем коде deadline вычисляется в **момент построения
payload для check stage**, то есть ТОЖЕ в момент входа в check:

```python
# _build_clean_fill_start_meta (строка 381-389):
clean_fill_deadline_at=(now + timedelta(seconds=int(runtime["clean_fill_timeout_sec"]))).isoformat()
```

Это значит, что deadline вычисляется в `_run_startup()` при переходе startup → clean_fill_start.
В v2 он вычисляется в `_compute_deadline()` при переходе clean_fill_start → clean_fill_check
(или при entry в clean_fill_check). Разница — одна итерация stage machine. Но clean_fill_start
это command stage (открытие клапана), которая занимает ~1-5 секунд — разница мизерная.

Но ЕСТЬ НЮАНС: в текущем коде deadline хранится **внутри payload** самого check stage
(`clean_fill_deadline_at` ключ), и при каждом poll `_run_clean_fill_check()` парсит его.
В v2 deadline хранится в `stage_deadline_at` колонке и **НЕ ПЕРЕЗАПИСЫВАЕТСЯ** при poll
(потому что `outcome.kind == "poll"` не меняет `stage_deadline_at`). Это правильнее.

**Вердикт:** Подход v2 корректен и даже лучше. Критика снята.

**Риск:** НИЗКИЙ.

---

### КРИТИКА 4: `clean_fill_retry` — топология НЕ ПОЛНАЯ

**Проблема:** В текущем коде есть `_build_clean_fill_retry_stop_payload()` (строка 327-333),
который строит payload для `clean_fill_stop_to_solution` с `_NEXT_PAYLOAD_KEY` →
`clean_fill_start` (retry). Это используется, когда clean fill прошёл, но `clean_fill_check`
решил повторить.

В v2 topology есть `clean_fill_retry_stop` → `StageDef(..., next_stage="clean_fill_start")`.
Но в `clean_fill_check` handler текущий код имеет **ТРИ исхода:**
1. Бак полный → `clean_fill_stop_to_solution` (→ solution_fill_start)
2. Timeout → `clean_fill_timeout_stop` (→ terminal error)
3. **Retry** → `clean_fill_retry_stop` (→ clean_fill_start с увеличенным cycle counter)

Но подождём — в текущем коде (строки 150-181):
```python
async def _run_clean_fill_check(self, *, task, plan, now):
    clean_max = await self._read_level(...)
    if clean_max["is_triggered"]:
        # check min sensor consistency, then:
        return await self._requeue(..., payload=self._build_clean_fill_stop_payload(...))
    deadline = self._parse_deadline(task.payload.get("clean_fill_deadline_at"))
    if deadline is not None and now >= deadline:
        cycle = int(task.payload.get("clean_fill_cycle") or 1)
        max_cycles = int(runtime.get("clean_fill_max_cycles") or 1)
        if cycle >= max_cycles:
            return await self._requeue(..., payload=self._build_clean_fill_timeout_stop_payload(...))
        return await self._requeue(..., payload=self._build_clean_fill_retry_stop_payload(
            ..., cycle=cycle + 1, ...))
    return await self._requeue(..., "clean_fill_check", due_delay_sec=poll_interval)
```

Итого 4 исхода: (1) полный → stop, (2) timeout + max cycles → terminal, (3) timeout + retry →
retry stop, (4) ещё ждём → poll. В v2 topology handler должен возвращать один из четырёх
`StageOutcome`:
- `transition("clean_fill_stop_to_solution")`
- `transition("clean_fill_timeout_stop")` — terminal
- `transition("clean_fill_retry_stop")` — с увеличением cycle counter и НОВЫМ deadline
- `poll(due_delay_sec=poll_interval)`

**Вердикт:** Topology graph в v2 имеет все нужные stages, но **handler logic не описана**.
Нужно добавить описание handler `_handle_clean_fill` с 4 исходами и упомянуть, что при
retry `clean_fill_cycle` увеличивается и `stage_deadline_at` пересчитывается.

**Риск:** СРЕДНИЙ. Неочевидная retry-логика может быть потеряна.

---

### КРИТИКА 5: `_run_command_stage` + `_NEXT_PAYLOAD_KEY` — recovery invariant

**Проблема:** Критически важный паттерн в текущем коде:

1. **Normal flow:** `_run_command_stage()` вызывает `run_batch()` → batch поллит → task
   возвращается в `running` → handler берёт `_NEXT_PAYLOAD_KEY` из payload → requeue.
   Задача НИКОГДА не остаётся в `waiting_command` после `run_batch()`.

2. **Crash during batch:** Task застряла в `waiting_command`. При startup recovery:
   `_recover_native_two_tank_task()` вызывает `command_gateway.recover_waiting_command()`
   → если `DONE` → `_apply_native_done_transition()` читает `_NEXT_PAYLOAD_KEY` из payload.

Ключевой момент: **recovery** читает `_NEXT_PAYLOAD_KEY` который уже записан в payload ДО
начала `run_batch()`. Это работает, потому что текущий `_run_command_stage()` сначала
`_build_*_payload()` записывает `_NEXT_PAYLOAD_KEY` в payload через `_stage_payload()`,
потом `_requeue()` сохраняет в БД, а при СЛЕДУЮЩЕМ claim `_run_command_stage()` вызывает
`run_batch()` — но payload **уже содержит** `_NEXT_PAYLOAD_KEY`.

В v2 этого НЕТ. `current_stage` в БД указывает на command stage (например `clean_fill_start`).
`StageDef.next_stage` в registry → `clean_fill_check`. При crash во время run_batch, recovery
должна:
1. Найти что task в `waiting_command` с `current_stage="clean_fill_start"`
2. Reconcile command → `DONE`
3. Прочитать `StageDef("clean_fill_start").next_stage` → `"clean_fill_check"`
4. Requeue с `current_stage="clean_fill_check"`

**Вердикт:** v2 recovery ПРОЩЕ и ЧИЩЕ — не нужны nested payloads, successor берётся
из topology registry. Но `_apply_native_done_transition()` нужно ПОЛНОСТЬЮ ПЕРЕПИСАТЬ:
вместо чтения `_NEXT_PAYLOAD_KEY` из payload, она должна:
- Прочитать `task.current_stage`
- Найти `StageDef` в registry
- Если `terminal_error` → fail
- Если `next_stage` → transition к next_stage с новым deadline
- Если handler stage (startup, check) → это невозможно при crash в command batch

Эта логика **НЕ ОПИСАНА** в плане. Секция "Startup Recovery" говорит только
"current_stage + topology дают ту же информацию", но не описывает алгоритм.

**Риск:** ВЫСОКИЙ. Recovery при crash — критическая функция. Без явного описания
нового алгоритма recovery можно допустить регрессию.

---

### КРИТИКА 6: Correction coupling — `corr_return_stage_success/fail` vs nested dict

**Проблема:** В текущем коде correction exit (`_run_deactivate`, строки 420-453) работает так:
```python
return_payload = task.payload.get(_CORR_RETURN_PAYLOAD_SUCCESS)  # полный dict!
return await self._requeue(..., payload=dict(return_payload), ...)
```

Этот `return_payload` — это **полный staged payload**, включающий:
- `ae3_cycle_start_stage` (целевой stage)
- `ae3_next_payload_on_done` (nested next-step для command stage)
- deadline keys
- `ae3_workflow_phase_on_done`

То есть correction exit выполняет **полную замену payload** — всё состояние корректно
восстанавливается, включая вложенные next-payloads для command stages.

В v2 `corr_return_stage_success/fail` — это просто `VARCHAR(64)` с именем stage.
Correction exit вернёт `StageOutcome(kind="exit_correction", next_stage="solution_fill_stop_to_ready")`.
`_apply_outcome` создаст `WorkflowState(current_stage="solution_fill_stop_to_ready", ...)`.

Это ПРОЩЕ и ПРАВИЛЬНЕЕ — потому что `solution_fill_stop_to_ready` в topology registry
уже содержит все данные: `command_plans=("solution_fill_stop", "sensor_mode_deactivate")`,
`next_stage="complete_ready"`, `workflow_phase="ready"`. Не нужно хранить nested dict.

**Вердикт:** v2 подход корректен и значительно чище. Критика снята.

Но НЮАНС: при correction fail → `corr_return_stage_fail="solution_fill_stop_to_prepare"`,
и `StageDef` этого stage содержит `next_stage="prepare_recirculation_start"`. Для
prepare_recirculation_start нужен **новый deadline** (computed from runtime config).
В v2 это обеспечивается `_compute_deadline()` при входе в `prepare_recirculation_check`
через transition chain. Это работает.

**Риск:** НИЗКИЙ.

---

### КРИТИКА 7: `_probe_irr_state` — паттерн "probe + assert" не описан в v2

**Проблема:** Текущий код перед каждым check stage вызывает `_probe_irr_state()`:
```python
await self._probe_irr_state(task, plan, now, expected={"pump_main": False})           # startup
await self._probe_irr_state(task, plan, now, expected={"valve_clean_supply": True...}) # solution_fill_check
await self._probe_irr_state(task, plan, now, expected={"valve_solution_supply": True...}) # prepare_recirc_check
```

Это отправляет **реальную команду** probe через `run_batch()`, читает ответ через
`runtime_monitor.read_latest_irr_state()`, и проверяет что физическое состояние клапанов
соответствует ожиданиям.

В v2 плане **НИГДЕ** не упоминается probe_irr_state. Ни в WorkflowRouter, ни в handlers,
ни в stage_outcome types. Это важная defensive check, которая ловит inconsistencies
между ожидаемым и фактическим состоянием hardware.

**Вердикт:** Пробел в плане. Handlers `_handle_startup`, `_handle_solution_fill`,
`_handle_prepare_recirc` ДОЛЖНЫ вызывать probe перед проверкой уровня/targets.

**Риск:** ВЫСОКИЙ. Потеря defensive hardware проверок может привести к silent failures
в production.

---

### КРИТИКА 8: `_targets_reached` + `_read_level` — sensor read pattern не описан

**Проблема:** Текущие check handlers (`_run_solution_fill_check`, `_run_prepare_recirculation_check`)
содержат complex sensor-reading logic:
- `_read_level()` — чтение level switch, проверка `has_level`, `is_stale`, raise на error
- `_targets_reached()` — чтение pH/EC metric, tolerance comparison с % от target
- Sensor consistency checks (max=1, min=0 → error)

В v2 эти паттерны не описаны. `_handle_solution_fill` и `_handle_prepare_recirc` просто
перечислены как handlers без деталей.

**Вердикт:** Plan должен явно указать, что handlers переиспользуют существующую логику
sensor reading. Можно извлечь в helper methods WorkflowRouter или в отдельный SensorChecker.

**Риск:** СРЕДНИЙ. Логика не потеряется при копировании, но plan должен это зафиксировать.

---

### КРИТИКА 9: WorkflowRouter смешивает orchestration и domain logic

**Проблема:** Текущая архитектура разделена:
- `TwoTankCycleStartExecutor` — orchestration + domain logic (sensor reads, level checks)
- `CorrectionExecutor` — domain logic correction cycle

В v2 **ВСЁ** помещается в `WorkflowRouter`:
- Orchestration (dispatch по handler, apply_outcome, requeue)
- Domain logic (sensor reads, level checks, probe_irr_state)
- Correction logic (8 шагов correction state machine)

Это создаёт god-class ~500+ строк вместо двух файлов по 400-550 строк.

**Вердикт:** Стоит вынести domain logic в отдельные handler классы:
- `StartupHandler` — probe + level read → route
- `CleanFillHandler` — level read + deadline + retry logic → route
- `SolutionFillHandler` — level read + targets + correction entry → route
- `PrepareRecircHandler` — targets + correction entry → route
- `CorrectionHandler` — 8-step correction state machine
- `CommandHandler` — run_batch + route to next

WorkflowRouter остаётся чистым orchestrator: dispatch + apply_outcome + requeue.

**Риск:** СРЕДНИЙ. God-class снижает тестируемость и читаемость. Но это вопрос
организации кода, не архитектурной корректности.

---

### КРИТИКА 10: 25+ nullable колонок vs JSONB — trade-off не оценён

**Проблема:** v2 заменяет 1 колонку `payload JSONB` на 25+ explicit columns, из которых
~18 nullable (все `corr_*`). Это:

**Плюсы:**
- Type safety на уровне БД
- Индексы на `current_stage`, `topology`
- Нет nested dicts
- Audit trail через `ae_stage_transitions`

**Минусы:**
- 25+ columns усложняют `SELECT *`, `INSERT`, `UPDATE` statements
- `requeue_pending v2` UPDATE содержит 26 параметров — легко ошибиться при маппинге
- Все `corr_*` columns NULL когда correction неактивна — wasted space (минимальный, но есть)
- При добавлении нового состояния нужна Laravel-миграция (vs просто новый ключ в JSONB)

**Вердикт:** Trade-off оправдан. Type safety и explicit schema важнее, чем удобство
добавления ключей. Но 26-параметровый UPDATE — это реальный risk. Рекомендация:
использовать named parameters или builder pattern для SQL, не позиционные $1-$26.

**Риск:** НИЗКИЙ (архитектурно), СРЕДНИЙ (при реализации SQL).

---

### КРИТИКА 11: `workflow_repository.upsert_phase()` — не описан в v2

**Проблема:** Текущий код вызывает `workflow_repository.upsert_phase()` при каждом requeue
и при complete/fail. Это обновляет zone workflow status для внешних наблюдателей
(Laravel dashboard, scheduler). Вызов:
```python
await self._workflow_repository.upsert_phase(
    zone_id=task.zone_id,
    workflow_phase="tank_filling",
    payload={_STAGE_KEY: "clean_fill_check"},
    scheduler_task_id=str(task.id),
    now=now,
)
```

В v2 плане `workflow_repository` упомянут в конструкторе WorkflowRouter, но **НИГДЕ**
не описано, когда и как вызывается `upsert_phase()`. Текущий контракт передаёт
`payload={_STAGE_KEY: ...}` — это mini-JSONB с именем stage для zone workflow tracker.

**Вердикт:** Plan должен описать:
1. `upsert_phase()` вызывается в `_apply_outcome` при каждом transition
2. `payload` параметр содержит `{ae3_cycle_start_stage: current_stage}` (backward compat)
   или переходит на explicit field

**Риск:** ВЫСОКИЙ. Без workflow_repository Laravel dashboard не будет обновляться.

---

### КРИТИКА 12: `clean_fill_retry_stop` маршрутизация — неверный `next_stage` в topology

**Проблема:** В v2 topology:
```python
"clean_fill_retry_stop": StageDef(
    "clean_fill_retry_stop", "command",
    workflow_phase="tank_filling",
    command_plans=("clean_fill_stop",),
    next_stage="clean_fill_start",  # retry → back to fill start
),
```

Но после retry `clean_fill_start` нужен **новый deadline** для `clean_fill_check`.
`_compute_deadline()` вычисляет deadline при входе в stage с `timeout_key`. Но
`clean_fill_start` — это command stage, у неё НЕТ `timeout_key`. Deadline нужен
для `clean_fill_check`, а не для `clean_fill_start`.

Цепочка: `clean_fill_retry_stop` → `clean_fill_start` → `clean_fill_check`.
`clean_fill_check` имеет `timeout_key="clean_fill_timeout_sec"`. При transition
в `clean_fill_check`, `_compute_deadline()` вычислит новый deadline. Это ПРАВИЛЬНО.

**Вердикт:** Архитектура корректна. Критика снята.

Но нужно проверить: при `clean_fill_retry_stop` → `clean_fill_start`, `clean_fill_cycle`
должен быть УВЕЛИЧЕН. В текущем коде это делается через nested payload:
```python
_NEXT_PAYLOAD_KEY=self._stage_payload(..., "clean_fill_start", clean_fill_cycle=cycle+1, ...)
```

В v2 handler `_handle_clean_fill` должен при retry return
`StageOutcome(kind="transition", next_stage="clean_fill_retry_stop",
clean_fill_cycle=current_cycle + 1)`. И `_apply_outcome` при transition должен
записать `clean_fill_cycle` в новый `WorkflowState`.

Это описано в `StageOutcome.clean_fill_cycle`, но **не описано** в handler logic.

**Риск:** СРЕДНИЙ. Нужно добавить в handler description.

---

### ИТОГОВАЯ ОЦЕНКА

| # | Критика | Риск | Статус |
|---|---------|------|--------|
| 1 | Command stage post-batch invariant | НИЗКИЙ | Корректно, но нужно зафиксировать |
| 2 | Startup handler dynamic routing | СРЕДНИЙ | Нужно описать handler logic |
| 3 | Deadline timing gap | НИЗКИЙ | v2 лучше, критика снята |
| 4 | Clean fill retry — 4 outcome handler | СРЕДНИЙ | Нужно описать handler logic |
| 5 | **Recovery после crash — алгоритм** | **ВЫСОКИЙ** | **Нужно описать новый recovery алгоритм** |
| 6 | Correction coupling via stage name | НИЗКИЙ | v2 чище, критика снята |
| 7 | **probe_irr_state не описан** | **ВЫСОКИЙ** | **Пробел в плане** |
| 8 | Sensor read patterns | СРЕДНИЙ | Нужно зафиксировать |
| 9 | God-class WorkflowRouter | СРЕДНИЙ | Рекомендация: вынести handlers |
| 10 | 25+ columns trade-off | НИЗКИЙ | Оправдано |
| 11 | **workflow_repository.upsert_phase()** | **ВЫСОКИЙ** | **Пробел в плане** |
| 12 | Clean fill retry cycle counter | СРЕДНИЙ | Нужно добавить в handler desc |

**Блокирующие проблемы (ВЫСОКИЙ РИСК):**
1. Recovery алгоритм при crash не описан — нужен explicit pseudocode
2. `_probe_irr_state()` отсутствует в v2 — hardware safety regression
3. `workflow_repository.upsert_phase()` отсутствует — Laravel dashboard regression

**Рекомендации:**
1. Добавить секцию "Handler Logic" с описанием каждого handler и его possible outcomes
2. Переписать секцию "Startup Recovery" с explicit алгоритмом через topology registry
3. Добавить probe_irr_state в handler descriptions
4. Добавить workflow_repository.upsert_phase() в _apply_outcome
5. Рассмотреть разделение WorkflowRouter на orchestrator + handler classes

---

## Контекст

Текущая state machine AE3-Lite хранит **всё** состояние в `ae_tasks.payload JSONB` — 22+ ключей,
атомически перезаписываемых на каждом `requeue_pending()`. Это порождает фундаментальные проблемы:

1. **JSONB как god-object** — нет схемы, нет валидации, нет типизации. Каждый handler
   использует `payload.get("key")` с defensive defaults — ошибки в именах ключей ловятся
   только в рантайме.
2. **Nested payload coupling** — command-stages хранят полный dict следующего состояния
   в `ae3_next_payload_on_done`. Correction хранит полные return-payloads
   (`corr_return_payload_success/fail`) как вложенные JSONB-дикты. Это делает debugging
   и трассировку крайне сложными.
3. **Нет audit trail** — payload перезаписывается на каждом poll, история переходов теряется.
4. **Нет переиспользуемости** — добавление `three_tank_nft` требует клонирования 980 строк
   (TwoTankCycleStartExecutor + CorrectionExecutor).

**Решение:** Полная замена JSONB payload на явные колонки ae_tasks + topology-driven routing.
Clean break — без feature flag, без обратной совместимости со старым кодом.

## Решения пользователя

1. **`payload` убрать полностью** — intent metadata → explicit columns, state → explicit columns
2. **Correction state** — nullable колонки на ae_tasks (не отдельная таблица)
3. **Clean break** — без feature flag, сразу замена старого кода

---

## Архитектура v2: Topology-Driven State Columns

### Ключевое изменение

**Было:** `requeue_pending()` атомически заменяет весь `payload JSONB` (22+ ключей, вложенные дикты).

**Стало:** `requeue_pending()` обновляет типизированные колонки:
`current_stage`, `workflow_phase`, `stage_deadline_at`, `corr_step`, `corr_attempt`, ...

Payload колонка удаляется. Nested payloads (`ae3_next_payload_on_done`, `corr_return_payload_success/fail`)
**полностью устраняются** — successor вычисляется из topology registry.

### Четыре архитектурных слоя

```
TopologyRegistry     ─── StageDef-ы определяют граф переходов, successor-ы, command-планы
WorkflowRouter       ─── Orchestrator: dispatch → handler → apply_outcome → requeue/complete/fail
StageHandlers (6 шт) ─── Domain logic: sensor reads, level checks, probe → возвращает StageOutcome
CorrectionHandler    ─── 8-step correction state machine → возвращает StageOutcome
```

**Решение пользователя:** WorkflowRouter — чистый orchestrator. Domain logic вынесена
в отдельные handler-классы (по критике #9 аудита).

---

## Схема БД v2

### ae_tasks — изменения

```sql
-- УДАЛЯЕМ:
--   payload JSONB  ← больше нет

-- ДОБАВЛЯЕМ: Intent metadata (write-once, set при создании задачи)
intent_source       VARCHAR(64),           -- 'laravel_scheduler'
intent_trigger      VARCHAR(64),           -- 'start_cycle_api'
intent_id           BIGINT,                -- FK к zone_automation_intents
intent_meta         JSONB DEFAULT '{}',    -- оригинальный intent dict (для debugging)

-- ДОБАВЛЯЕМ: Workflow state machine (mutable)
topology            VARCHAR(64) NOT NULL,  -- 'two_tank_drip_substrate_trays'
current_stage       VARCHAR(64) NOT NULL DEFAULT 'startup',
workflow_phase      VARCHAR(32) NOT NULL DEFAULT 'idle',
stage_deadline_at   TIMESTAMPTZ,           -- NULL = нет дедлайна для текущего stage
stage_retry_count   SMALLINT NOT NULL DEFAULT 0,
stage_entered_at    TIMESTAMPTZ,           -- для вычисления длительности stage
clean_fill_cycle    SMALLINT NOT NULL DEFAULT 0,  -- retry counter для clean fill

-- ДОБАВЛЯЕМ: Correction state (all NULL когда коррекция не активна)
corr_step                 VARCHAR(32),     -- 'corr_check', 'corr_dose_ec', ...
corr_attempt              SMALLINT,
corr_max_attempts         SMALLINT,
corr_activated_here       BOOLEAN,         -- мы активировали сенсоры?
corr_stabilization_sec    SMALLINT,
corr_return_stage_success VARCHAR(64),     -- куда идти при success (вместо nested dict!)
corr_return_stage_fail    VARCHAR(64),     -- куда идти при fail
corr_outcome_success      BOOLEAN,         -- результат коррекции (для deactivate stage)
corr_needs_ec             BOOLEAN,
corr_ec_node_uid          VARCHAR(128),
corr_ec_channel           VARCHAR(64),
corr_ec_duration_ms       INTEGER,
corr_needs_ph_up          BOOLEAN,
corr_needs_ph_down        BOOLEAN,
corr_ph_node_uid          VARCHAR(128),
corr_ph_channel           VARCHAR(64),
corr_ph_duration_ms       INTEGER,
corr_wait_until           TIMESTAMPTZ,     -- wait-aware polling
```

**Что устраняется:**
| Старый payload ключ | Замена |
|---|---|
| `ae3_cycle_start_stage` | `current_stage VARCHAR(64)` |
| `ae3_cycle_start_mode` | `topology VARCHAR(64)` |
| `ae3_next_payload_on_done` (nested dict!) | Устранён — successor из `StageDef.next_stage` |
| `ae3_next_due_delay_sec_on_done` | Устранён — delay из topology `timeout_key` |
| `ae3_terminal_failure_on_done` (nested dict!) | Устранён — ошибка из `StageDef.terminal_error` |
| `ae3_workflow_phase_on_done` | `workflow_phase VARCHAR(32)` |
| `clean_fill_cycle` | `clean_fill_cycle SMALLINT` |
| `clean_fill_deadline_at` | `stage_deadline_at TIMESTAMPTZ` (единая колонка) |
| `solution_fill_deadline_at` | `stage_deadline_at TIMESTAMPTZ` |
| `prepare_recirculation_deadline_at` | `stage_deadline_at TIMESTAMPTZ` |
| `corr_return_payload_success` (nested dict!) | `corr_return_stage_success VARCHAR(64)` |
| `corr_return_payload_fail` (nested dict!) | `corr_return_stage_fail VARCHAR(64)` |
| `_corr_success` | `corr_outcome_success BOOLEAN` |
| `_corr_ec_*` (temp) | `corr_ec_* nullable columns` |
| intent keys (source, trigger...) | `intent_source`, `intent_trigger`, `intent_id` columns |

### ae_stage_transitions — новая таблица (audit trail)

```sql
CREATE TABLE ae_stage_transitions (
    id             BIGSERIAL PRIMARY KEY,
    task_id        BIGINT NOT NULL REFERENCES ae_tasks(id) ON DELETE CASCADE,
    from_stage     VARCHAR(64),            -- NULL для первого stage
    to_stage       VARCHAR(64) NOT NULL,
    workflow_phase VARCHAR(32),
    triggered_at   TIMESTAMPTZ NOT NULL,
    metadata       JSONB DEFAULT '{}',     -- diagnostics: deadline, correction attempt, error
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ae_stage_transitions_task_idx ON ae_stage_transitions (task_id, triggered_at);
```

- **INSERT-only** (append-only log), никогда не UPDATE
- Один INSERT на каждый переход между stage-ами
- `metadata` — снапшот: `{"deadline_at": "...", "corr_attempt": 3, "error_code": "timeout"}`
- Ретенция: `DELETE WHERE triggered_at < NOW() - INTERVAL '30 days'`

### ae_commands — изменения

```sql
ALTER TABLE ae_commands ADD COLUMN stage_name VARCHAR(64);
CREATE INDEX ae_commands_stage_idx ON ae_commands (task_id, stage_name) WHERE stage_name IS NOT NULL;
```

---

## Topology Registry

```python
@dataclass(frozen=True)
class StageDef:
    name: str              # "clean_fill_start", "clean_fill_check", ...
    handler: str           # "command", "startup", "clean_fill", "solution_fill",
                           # "prepare_recirc", "ready"
    workflow_phase: str = "idle"

    # Command stages
    command_plans: tuple[str, ...] = ()    # ключи из plan.named_plans
    next_stage: str | None = None          # successor после успешных команд

    # Terminal failure stages
    terminal_error: tuple[str, str] | None = None  # (error_code, error_message)

    # Check stages
    timeout_key: str | None = None         # runtime config key для deadline
    has_correction: bool = False
    on_corr_success: str | None = None
    on_corr_fail: str | None = None
```

### Two-tank topology (полный граф)

```python
TWO_TANK = {
    # === Startup ===
    "startup": StageDef("startup", "startup"),

    # === Clean fill path ===
    "clean_fill_start": StageDef(
        "clean_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_start",),
        next_stage="clean_fill_check",
    ),
    "clean_fill_check": StageDef(
        "clean_fill_check", "clean_fill",
        workflow_phase="tank_filling",
        timeout_key="clean_fill_timeout_sec",
    ),
    # Handler routes to one of:
    "clean_fill_stop_to_solution": StageDef(
        "clean_fill_stop_to_solution", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        next_stage="solution_fill_start",
    ),
    "clean_fill_retry_stop": StageDef(
        "clean_fill_retry_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        next_stage="clean_fill_start",        # retry → back to fill start
    ),
    "clean_fill_timeout_stop": StageDef(
        "clean_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        terminal_error=("clean_tank_not_filled_timeout",
                        "Clean fill timeout exceeded"),
    ),

    # === Solution fill path ===
    "solution_fill_start": StageDef(
        "solution_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("sensor_mode_activate", "solution_fill_start"),
        next_stage="solution_fill_check",
    ),
    "solution_fill_check": StageDef(
        "solution_fill_check", "solution_fill",
        workflow_phase="tank_filling",
        timeout_key="solution_fill_timeout_sec",
        has_correction=True,
        on_corr_success="solution_fill_stop_to_ready",
        on_corr_fail="solution_fill_stop_to_prepare",
    ),
    "solution_fill_stop_to_ready": StageDef(
        "solution_fill_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="complete_ready",
    ),
    "solution_fill_stop_to_prepare": StageDef(
        "solution_fill_stop_to_prepare", "command",
        workflow_phase="tank_recirc",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="prepare_recirculation_start",
    ),
    "solution_fill_timeout_stop": StageDef(
        "solution_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=("solution_tank_not_filled_timeout",
                        "Solution fill timeout exceeded"),
    ),

    # === Prepare recirculation path ===
    "prepare_recirculation_start": StageDef(
        "prepare_recirculation_start", "command",
        workflow_phase="tank_recirc",
        command_plans=("sensor_mode_activate", "prepare_recirculation_start"),
        next_stage="prepare_recirculation_check",
    ),
    "prepare_recirculation_check": StageDef(
        "prepare_recirculation_check", "prepare_recirc",
        workflow_phase="tank_recirc",
        timeout_key="prepare_recirculation_timeout_sec",
        has_correction=True,
        on_corr_success="prepare_recirculation_stop_to_ready",
        on_corr_fail="prepare_recirculation_timeout_stop",
    ),
    "prepare_recirculation_stop_to_ready": StageDef(
        "prepare_recirculation_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        next_stage="complete_ready",
    ),
    "prepare_recirculation_timeout_stop": StageDef(
        "prepare_recirculation_timeout_stop", "command",
        workflow_phase="tank_recirc",
        command_plans=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        terminal_error=("prepare_npk_ph_target_not_reached",
                        "Prepare recirculation timeout exceeded"),
    ),

    # === Terminal ===
    "complete_ready": StageDef("complete_ready", "ready", workflow_phase="ready"),
}
```

---

## Domain Types

### WorkflowState (value object)

```python
@dataclass(frozen=True)
class WorkflowState:
    current_stage: str
    workflow_phase: str
    stage_deadline_at: datetime | None
    stage_retry_count: int
    stage_entered_at: datetime | None
    clean_fill_cycle: int
```

### CorrectionState (value object)

```python
@dataclass(frozen=True)
class CorrectionState:
    corr_step: str
    attempt: int
    max_attempts: int
    activated_here: bool
    stabilization_sec: int
    return_stage_success: str
    return_stage_fail: str
    outcome_success: bool | None     # set before corr_deactivate
    needs_ec: bool
    ec_node_uid: str | None
    ec_channel: str | None
    ec_duration_ms: int | None
    needs_ph_up: bool
    needs_ph_down: bool
    ph_node_uid: str | None
    ph_channel: str | None
    ph_duration_ms: int | None
    wait_until: datetime | None
```

### StageOutcome (handler return)

```python
@dataclass(frozen=True)
class StageOutcome:
    kind: Literal["poll", "transition", "enter_correction",
                  "exit_correction", "complete", "fail"]
    next_stage: str | None = None
    commands: tuple[PlannedCommand, ...] = ()
    due_delay_sec: float = 0
    workflow_phase: str | None = None
    # State for new stage
    stage_deadline_at: datetime | None = None
    stage_retry_count: int | None = None
    clean_fill_cycle: int | None = None
    # Correction
    correction: CorrectionState | None = None  # None = clear all corr_*
    # Errors
    error_code: str | None = None
    error_message: str | None = None
```

---

## Repository API

### requeue_pending v2

```python
async def requeue_pending(
    self, *,
    task_id: int,
    owner: str,
    workflow: WorkflowState,
    correction: CorrectionState | None,  # None → SET all corr_* = NULL
    due_at: datetime,
    now: datetime,
) -> Optional[AutomationTask]:
    """UPDATE ae_tasks SET current_stage=$X, corr_step=$Y, ... WHERE id=$1 AND claimed_by=$2"""
```

SQL:
```sql
UPDATE ae_tasks SET
    status = 'pending',
    current_stage = $3,
    workflow_phase = $4,
    stage_deadline_at = $5,
    stage_retry_count = $6,
    stage_entered_at = $7,
    clean_fill_cycle = $8,
    -- correction (NULL when correction param is None)
    corr_step = $9,
    corr_attempt = $10,
    corr_max_attempts = $11,
    corr_activated_here = $12,
    corr_stabilization_sec = $13,
    corr_return_stage_success = $14,
    corr_return_stage_fail = $15,
    corr_outcome_success = $16,
    corr_needs_ec = $17,
    corr_ec_node_uid = $18,
    corr_ec_channel = $19,
    corr_ec_duration_ms = $20,
    corr_needs_ph_up = $21,
    corr_needs_ph_down = $22,
    corr_ph_node_uid = $23,
    corr_ph_channel = $24,
    corr_ph_duration_ms = $25,
    corr_wait_until = $26,
    due_at = $27,
    updated_at = $28
WHERE id = $1
  AND claimed_by = $2
  AND status IN ('claimed', 'running')
RETURNING *
```

### create_pending v2

```python
async def create_pending(
    self, *,
    zone_id: int,
    topology: str,
    intent_source: str | None,
    intent_trigger: str | None,
    intent_id: int | None,
    intent_meta: Mapping[str, Any],
    idempotency_key: str,
    scheduled_for: datetime,
    due_at: datetime,
    now: datetime,
) -> Optional[AutomationTask]:
```

### log_stage_transition

```python
async def log_stage_transition(
    self, *,
    task_id: int,
    from_stage: str | None,
    to_stage: str,
    workflow_phase: str,
    triggered_at: datetime,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """INSERT into ae_stage_transitions. Best-effort, non-blocking."""
```

---

## WorkflowRouter (orchestrator) + Handler Classes

Заменяет `TwoTankCycleStartExecutor` + `CorrectionExecutor`.

**Архитектурное решение:** WorkflowRouter — чистый orchestrator. Domain logic вынесена
в отдельные handler-классы. Каждый handler получает task/plan/now/stage_def, возвращает StageOutcome.

### WorkflowRouter — orchestrator

```python
class WorkflowRouter:
    def __init__(self, *, task_repo, workflow_repo, topology_registry,
                 command_gateway, stage_transition_repo,
                 startup_handler, clean_fill_handler, solution_fill_handler,
                 prepare_recirc_handler, correction_handler, command_handler):
        self._handlers = {
            "startup": startup_handler,
            "command": command_handler,
            "clean_fill": clean_fill_handler,
            "solution_fill": solution_fill_handler,
            "prepare_recirc": prepare_recirc_handler,
            "ready": None,  # handled inline (complete_task)
        }

    async def run(self, *, task: AutomationTask, plan: CommandPlan, now: datetime):
        stage_def = self._registry.get(task.topology, task.current_stage)

        # 1. Correction step (если correction активна и wait прошёл)
        if task.is_in_correction:
            if not (task.corr_wait_until and task.corr_wait_until > now):
                outcome = await self._correction_handler.run(task, plan, now, stage_def)
                return await self._apply_outcome(task, plan, now, stage_def, outcome)

        # 2. Ready stage → complete
        if stage_def.handler == "ready":
            return await self._complete_task(task, now)

        # 3. Dispatch к handler class
        handler = self._handlers[stage_def.handler]
        outcome = await handler.run(task=task, plan=plan, now=now, stage_def=stage_def)

        # 4. Применить outcome
        return await self._apply_outcome(task, plan, now, stage_def, outcome)
```

### _apply_outcome — центральная логика переходов

```python
async def _apply_outcome(self, task, plan, now, stage_def, outcome):
    match outcome.kind:
        case "poll":
            wf = task.workflow_state  # keep current
            await self._upsert_workflow_phase(task, wf.workflow_phase, wf.current_stage, now)
            return await self._requeue(task, now, wf, task.correction_state, outcome.due_delay_sec)

        case "transition":
            next_def = self._registry.get(task.topology, outcome.next_stage)
            wf = WorkflowState(
                current_stage=outcome.next_stage,
                workflow_phase=next_def.workflow_phase,
                stage_deadline_at=self._compute_deadline(next_def, plan.runtime, now),
                stage_retry_count=outcome.stage_retry_count or 0,
                stage_entered_at=now,
                clean_fill_cycle=outcome.clean_fill_cycle or task.clean_fill_cycle,
            )
            await self._log_transition(task, outcome.next_stage, next_def.workflow_phase, now)
            await self._upsert_workflow_phase(task, next_def.workflow_phase, outcome.next_stage, now)
            return await self._requeue(task, now, wf, correction=None, due_delay_sec=0)

        case "enter_correction":
            wf = task.workflow_state
            corr = outcome.correction
            await self._upsert_workflow_phase(task, wf.workflow_phase, wf.current_stage, now)
            return await self._requeue(task, now, wf, corr, due_delay_sec=0)

        case "exit_correction":
            next_def = self._registry.get(task.topology, outcome.next_stage)
            wf = WorkflowState(
                current_stage=outcome.next_stage,
                workflow_phase=next_def.workflow_phase,
                stage_deadline_at=self._compute_deadline(next_def, plan.runtime, now),
                stage_retry_count=0,
                stage_entered_at=now,
                clean_fill_cycle=task.clean_fill_cycle,
            )
            await self._log_transition(task, outcome.next_stage, next_def.workflow_phase, now)
            await self._upsert_workflow_phase(task, next_def.workflow_phase, outcome.next_stage, now)
            return await self._requeue(task, now, wf, correction=None, due_delay_sec=0)

        case "complete":
            await self._upsert_workflow_phase(task, "ready", "complete_ready", now)
            return await self._complete_task(task, now)

        case "fail":
            await self._upsert_workflow_phase(task, "idle", "failed", now)
            return await self._fail_task(task, now, outcome.error_code, outcome.error_message)
```

### _upsert_workflow_phase — zone workflow status (аудит критика #11)

```python
async def _upsert_workflow_phase(self, task, workflow_phase, stage_name, now):
    """Обновляет zone workflow status для Laravel dashboard / scheduler."""
    if self._workflow_repo is not None:
        await self._workflow_repo.upsert_phase(
            zone_id=task.zone_id,
            workflow_phase=workflow_phase,
            payload={"ae3_cycle_start_stage": stage_name},  # backward compat
            scheduler_task_id=str(task.id),
            now=now,
        )
```

### _compute_deadline — deadline из topology

```python
def _compute_deadline(self, stage_def: StageDef, runtime: Mapping, now: datetime):
    if stage_def.timeout_key:
        timeout_sec = int(runtime.get(stage_def.timeout_key, 0))
        return now + timedelta(seconds=timeout_sec) if timeout_sec > 0 else None
    return None
```

Deadline вычисляется В МОМЕНТ ВХОДА в stage (не pre-computed в nested payload).

---

## Handler Classes (domain logic)

Каждый handler — отдельный класс с методом `run()` → `StageOutcome`.
Все handlers получают одинаковую сигнатуру: `(task, plan, now, stage_def)`.

### Общий base: hardware probe + sensor reads

```python
class BaseStageHandler:
    """Общий функционал: probe_irr_state, read_level, targets_reached."""

    def __init__(self, *, command_gateway, runtime_monitor):
        self._command_gateway = command_gateway
        self._runtime_monitor = runtime_monitor

    async def probe_irr_state(self, task, plan, now, expected: dict[str, bool]):
        """Отправляет irr_state_probe, сверяет с expected. Raise TaskExecutionError при mismatch."""
        # Переносится 1:1 из TwoTankCycleStartExecutor._probe_irr_state()

    async def read_level(self, task, zone_id, labels, threshold, max_age, ...):
        """Чтение level switch с проверкой has_level, is_stale. Raise на error."""
        # Переносится 1:1 из TwoTankCycleStartExecutor._read_level()

    async def targets_reached(self, task, plan) -> bool:
        """Чтение PH/EC, сравнение с tolerance. Raise при unavailable/stale."""
        # Переносится 1:1 из TwoTankCycleStartExecutor._targets_reached()
```

### StartupHandler

```python
class StartupHandler(BaseStageHandler):
    """startup stage: probe → level check → route to clean_fill or solution_fill."""

    async def run(self, task, plan, now, stage_def) -> StageOutcome:
        # 1. Probe: pump_main must be OFF
        await self.probe_irr_state(task, plan, now, expected={"pump_main": False})

        # 2. Check clean tank max level
        clean_max = await self.read_level(task, ..., labels=runtime["clean_max_sensor_labels"], ...)

        if clean_max["is_triggered"]:
            # Sensor consistency check (max=1, min=0 → error)
            clean_min = await self.read_level(task, ..., labels=runtime["clean_min_sensor_labels"], ...)
            if not clean_min["is_triggered"]:
                return StageOutcome(kind="fail", error_code="sensor_state_inconsistent", ...)
            # Clean tank full → skip to solution_fill_start
            return StageOutcome(kind="transition", next_stage="solution_fill_start")

        # Clean tank not full → start clean fill
        return StageOutcome(kind="transition", next_stage="clean_fill_start",
                           clean_fill_cycle=1)
```

**Outcomes:** `transition("solution_fill_start")` | `transition("clean_fill_start")` | `fail`

### CommandHandler

```python
class CommandHandler(BaseStageHandler):
    """Generic command stage: run_batch → route via StageDef."""

    async def run(self, task, plan, now, stage_def) -> StageOutcome:
        # 1. Get commands from plan using stage_def.command_plans
        commands = []
        for plan_name in stage_def.command_plans:
            commands.extend(plan.named_plans.get(plan_name, ()))

        # 2. Execute synchronous batch
        result = await self._command_gateway.run_batch(task=task, commands=tuple(commands), now=now)
        if not result["success"]:
            return StageOutcome(kind="fail", error_code=result["error_code"],
                               error_message=result["error_message"])

        # 3. Route: terminal_error → fail, next_stage → transition
        if stage_def.terminal_error:
            code, msg = stage_def.terminal_error
            return StageOutcome(kind="fail", error_code=code, error_message=msg)

        if stage_def.next_stage:
            return StageOutcome(kind="transition", next_stage=stage_def.next_stage)

        return StageOutcome(kind="fail", error_code="ae3_missing_next_stage",
                           error_message=f"Stage {stage_def.name} has no next_stage")
```

**Инвариант (аудит критика #1):** После `run_batch()` task возвращается в `running`
с тем же `current_stage`. Handler берёт routing из `StageDef`, не из task state.

### CleanFillHandler

```python
class CleanFillHandler(BaseStageHandler):
    """clean_fill_check: level polling → 4 possible outcomes."""

    async def run(self, task, plan, now, stage_def) -> StageOutcome:
        runtime = plan.runtime

        # 1. Read clean tank max level
        clean_max = await self.read_level(task, ..., labels=runtime["clean_max_sensor_labels"], ...)

        if clean_max["is_triggered"]:
            # Sensor consistency check
            clean_min = await self.read_level(task, ..., labels=runtime["clean_min_sensor_labels"], ...)
            if not clean_min["is_triggered"]:
                return StageOutcome(kind="fail", error_code="sensor_state_inconsistent", ...)
            # FULL → stop fill, go to solution
            return StageOutcome(kind="transition", next_stage="clean_fill_stop_to_solution")

        # 2. Check deadline
        if task.stage_deadline_at and now >= task.stage_deadline_at:
            cycle = task.clean_fill_cycle
            max_cycles = int(runtime.get("clean_fill_max_cycles", 1))
            if cycle >= max_cycles:
                # MAX RETRIES → terminal error stop
                return StageOutcome(kind="transition", next_stage="clean_fill_timeout_stop")
            # RETRY → stop valve, restart fill with incremented cycle
            return StageOutcome(kind="transition", next_stage="clean_fill_retry_stop",
                               clean_fill_cycle=cycle + 1)

        # 3. Not full, not timeout → continue polling
        return StageOutcome(kind="poll",
                           due_delay_sec=int(runtime["level_poll_interval_sec"]))
```

**4 outcomes:** `transition("clean_fill_stop_to_solution")` | `transition("clean_fill_timeout_stop")` |
`transition("clean_fill_retry_stop", cycle+1)` | `poll`

### SolutionFillHandler

```python
class SolutionFillHandler(BaseStageHandler):
    """solution_fill_check: level + targets + correction entry."""

    async def run(self, task, plan, now, stage_def) -> StageOutcome:
        runtime = plan.runtime

        # 1. Probe irr state (аудит критика #7)
        await self.probe_irr_state(task, plan, now,
            expected={"valve_clean_supply": True, "valve_solution_fill": True, "pump_main": True})

        # 2. Read solution tank max level
        solution_max = await self.read_level(task, ..., labels=runtime["solution_max_sensor_labels"], ...)

        if solution_max["is_triggered"]:
            # Sensor consistency
            solution_min = await self.read_level(task, ..., labels=runtime["solution_min_sensor_labels"], ...)
            if not solution_min["is_triggered"]:
                return StageOutcome(kind="fail", error_code="sensor_state_inconsistent", ...)

            if await self.targets_reached(task, plan):
                # Targets OK → stop fill → ready
                return StageOutcome(kind="transition",
                                   next_stage="solution_fill_stop_to_ready")

            # Targets not met → enter correction (sensors already active)
            corr = self._build_correction_entry(
                task, plan, runtime,
                sensors_already_active=True,
                return_stage_success=stage_def.on_corr_success,  # "solution_fill_stop_to_ready"
                return_stage_fail=stage_def.on_corr_fail,        # "solution_fill_stop_to_prepare"
            )
            return StageOutcome(kind="enter_correction", correction=corr)

        # 3. Check deadline
        if task.stage_deadline_at and now >= task.stage_deadline_at:
            return StageOutcome(kind="transition", next_stage="solution_fill_timeout_stop")

        # 4. Not full → continue polling
        return StageOutcome(kind="poll",
                           due_delay_sec=int(runtime["level_poll_interval_sec"]))
```

**Outcomes:** `transition("solution_fill_stop_to_ready")` | `enter_correction` |
`transition("solution_fill_timeout_stop")` | `poll`

### PrepareRecircHandler

```python
class PrepareRecircHandler(BaseStageHandler):
    """prepare_recirculation_check: targets + correction entry."""

    async def run(self, task, plan, now, stage_def) -> StageOutcome:
        runtime = plan.runtime

        # 1. Probe irr state (аудит критика #7)
        await self.probe_irr_state(task, plan, now,
            expected={"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": True})

        # 2. Check deadline FIRST
        if task.stage_deadline_at and now >= task.stage_deadline_at:
            return StageOutcome(kind="transition",
                               next_stage="prepare_recirculation_timeout_stop")

        # 3. Check targets
        if await self.targets_reached(task, plan):
            return StageOutcome(kind="transition",
                               next_stage="prepare_recirculation_stop_to_ready")

        # 4. Targets not met → enter correction (sensors already active)
        corr = self._build_correction_entry(
            task, plan, runtime,
            sensors_already_active=True,
            return_stage_success=stage_def.on_corr_success,  # "prepare_recirculation_stop_to_ready"
            return_stage_fail=stage_def.on_corr_fail,        # "prepare_recirculation_timeout_stop"
        )
        return StageOutcome(kind="enter_correction", correction=corr)
```

**Outcomes:** `transition("prepare_recirculation_timeout_stop")` |
`transition("prepare_recirculation_stop_to_ready")` | `enter_correction`

### CorrectionHandler (8-step state machine)

```python
class CorrectionHandler:
    """8-step correction cycle. Operates on task.correction_state."""

    def __init__(self, *, command_gateway, runtime_monitor, correction_planner):
        ...

    async def run(self, task, plan, now, stage_def) -> StageOutcome:
        match task.corr_step:
            case "corr_activate":   return await self._activate(task, plan, now)
            case "corr_wait_stable": return await self._wait_stable(task, plan, now)
            case "corr_check":      return await self._check(task, plan, now, stage_def)
            case "corr_dose_ec":    return await self._dose_ec(task, plan, now)
            case "corr_wait_ec":    return await self._wait_ec(task, plan, now)
            case "corr_dose_ph":    return await self._dose_ph(task, plan, now)
            case "corr_wait_ph":    return await self._wait_ph(task, plan, now)
            case "corr_deactivate": return await self._deactivate(task, plan, now)

    # Each step returns StageOutcome with updated CorrectionState.
    # corr_check → if within tolerance or max attempts → exit_correction
    # corr_deactivate → exit_correction with success/fail routing
    # All others → enter_correction with updated corr_step/wait_until
```

**Логика переносится 1:1 из CorrectionExecutor, заменяя payload dict на CorrectionState fields.**

Key differences from current:
- `corr_deactivate` → `StageOutcome(kind="exit_correction", next_stage=corr_return_stage_success/fail)`
- No nested `return_payload_success/fail` dicts — just stage name from CorrectionState
- `corr_wait_*` stages → `StageOutcome(kind="enter_correction", correction=updated_corr)`
  с `corr.wait_until = now + mixing_delay`

---

## Файловая структура

### Новые файлы

```
ae3lite/
  domain/
    entities/
      workflow_state.py            # WorkflowState, CorrectionState (frozen dataclasses)
    services/
      topology_registry.py         # StageDef + TWO_TANK dict
  application/
    dto/
      stage_outcome.py             # StageOutcome
    use_cases/
      workflow_router.py           # WorkflowRouter (orchestrator)
    handlers/
      base_handler.py              # BaseStageHandler (probe_irr_state, read_level, targets_reached)
      startup_handler.py           # StartupHandler
      command_handler.py           # CommandHandler
      clean_fill_handler.py        # CleanFillHandler
      solution_fill_handler.py     # SolutionFillHandler
      prepare_recirc_handler.py    # PrepareRecircHandler
      correction_handler.py        # CorrectionHandler (8-step state machine)
  infrastructure/
    repositories/
      stage_transition_repository.py  # INSERT-only audit trail
  runtime/
    metrics.py                     # Prometheus counters, histograms, gauges
```

### Изменяемые файлы

| Файл | Изменения |
|------|-----------|
| `domain/entities/automation_task.py` | Удалить `payload: Mapping`. Добавить все explicit fields. Добавить `workflow_state`, `correction_state`, `is_in_correction` properties |
| `infrastructure/repositories/automation_task_repository.py` | Полная переработка: `requeue_pending()` обновляет колонки, `create_pending()` принимает explicit fields. Все SQL без JSONB |
| `application/use_cases/execute_task.py` | Заменить `payload`-based detection на `task.topology`. Вызов `workflow_router.run()` |
| `application/use_cases/startup_recovery.py` | `task.current_stage` вместо `payload.get(_STAGE_KEY)`. `task.topology` вместо `payload.get(_MODE_KEY)` |
| `application/use_cases/create_task_from_intent.py` | Передать explicit intent fields в `create_pending()` |
| `application/adapters/legacy_intent_mapper.py` | Вернуть structured dict вместо flat payload |
| `runtime/worker.py` | `task.intent_id` вместо `task.payload.get("intent_id")` |
| `infrastructure/read_models/task_status_read_model.py` | Добавить `current_stage`, `workflow_phase` в SELECT |
| `bootstrap.py` | Wiring WorkflowRouter, TopologyRegistry, StageTransitionRepository |
| Laravel migration | Новая миграция v2: add columns, drop payload, create ae_stage_transitions |

### Удаляемые файлы

| Файл | Строк | Заменяется на |
|------|-------|---------------|
| `two_tank_cycle_start_executor.py` | 417 | `workflow_router.py` (~120) + 6 handler files (~60-100 each) + `topology_registry.py` (~100) |
| `correction_executor.py` | 563 | `correction_handler.py` (~200) |

---

## Startup Recovery v2 (аудит критика #5 — explicit алгоритм)

**Ключевое изменение:** `_apply_native_done_transition()` больше НЕ читает nested payloads.
Вместо этого использует `task.current_stage` + `topology_registry` для routing.

### Алгоритм recovery для topology-aware tasks

```python
async def _recover_native_task(self, *, task, now):
    # 1. claimed/running → task crashed mid-execution → fail
    if task.status in {"claimed", "running"}:
        return await self._fail_task(task,
            error_code="startup_recovery_unconfirmed_command",
            error_message=f"Task {task.id} crashed in {task.status}")

    # 2. waiting_command → reconcile with legacy command table
    result = await self._command_gateway.recover_waiting_command(task=task, now=now)

    if result["state"] == "waiting_command":
        return "waiting_command", None  # command still pending in hardware

    if result["state"] == "failed":
        return "failed", self._build_terminal_outcome(task=result["task"])

    # 3. state == "done" → command succeeded, apply topology-driven transition
    recovered_task = result["task"]  # task back in "running" state
    return await self._apply_topology_done_transition(task=recovered_task, now=now)
```

### `_apply_topology_done_transition` (заменяет `_apply_native_done_transition`)

```python
async def _apply_topology_done_transition(self, *, task, now):
    """After a command completes during recovery, route to next stage via topology."""
    stage_def = self._topology_registry.get(task.topology, task.current_stage)

    # Case 1: Terminal error stage (e.g. clean_fill_timeout_stop)
    if stage_def.terminal_error:
        code, msg = stage_def.terminal_error
        failed = await self._task_repository.fail_for_recovery(
            task_id=task.id, error_code=code, error_message=msg, now=now)
        await self._upsert_workflow_phase(task, "idle", "failed", now)
        return "failed", self._build_terminal_outcome(task=failed)

    # Case 2: Command stage with next_stage → transition
    if stage_def.next_stage:
        next_def = self._topology_registry.get(task.topology, stage_def.next_stage)
        wf = WorkflowState(
            current_stage=stage_def.next_stage,
            workflow_phase=next_def.workflow_phase,
            stage_deadline_at=self._compute_deadline(next_def, task, now),
            stage_retry_count=0,
            stage_entered_at=now,
            clean_fill_cycle=task.clean_fill_cycle,
        )
        requeued = await self._task_repository.requeue_pending(
            task_id=task.id, owner=str(task.claimed_by or ""),
            workflow=wf, correction=None, due_at=now, now=now)
        await self._upsert_workflow_phase(task, next_def.workflow_phase, stage_def.next_stage, now)
        return "recovered_waiting_command", None

    # Case 3: No next_stage and no terminal_error → complete
    completed = await self._task_repository.mark_completed(
        task_id=task.id, owner=str(task.claimed_by or ""), now=now)
    await self._upsert_workflow_phase(task, "ready", "complete_ready", now)
    return "completed", self._build_terminal_outcome(task=completed)
```

**Почему это работает:**
- Task crash возможен только во время `run_batch()` (command execution)
- `run_batch()` вызывается только из `CommandHandler` для command stages
- Command stages ВСЕГДА имеют `next_stage` или `terminal_error` в topology registry
- Check/startup stages не вызывают `run_batch()` напрямую (только через probe_irr_state,
  который ТОЖЕ command, но probe crash → task fails → recovery = fail, корректно)
- При crash во время correction command: task в waiting_command с `current_stage`=parent stage,
  `corr_step`=correction step. Recovery: reconcile command → если DONE, fail task
  (нельзя безопасно продолжить correction посреди дозирования)

**Решение для correction crash:**
```python
# В _recover_native_task, после reconcile:
if task.is_in_correction:
    # Correction was interrupted mid-command → fail task (safe)
    # Cannot safely resume correction (dosing state unknown)
    return await self._fail_task(task,
        error_code="startup_recovery_correction_interrupted",
        error_message=f"Task {task.id} correction interrupted during {task.corr_step}")
```

### `_is_two_tank_task` замена

```python
# Было:
def _is_two_tank_task(self, task):
    return str(task.payload.get("ae3_cycle_start_mode") or "") == "two_tank"

# Стало:
def _is_topology_task(self, task):
    return bool(task.topology)  # any task with topology is handled natively
```

---

## Observability (логирование, метрики, алерты)

### Structured Logging

Тот же паттерн: `common/logging_setup.py`, JSON через `LOG_FORMAT=json`.

```python
# Transitions:
logger.info("AE3 transition: task=%d zone=%d %s→%s phase=%s",
            task.id, task.zone_id, from_stage, to_stage, phase)

# Correction:
logger.info("AE3 correction check: task=%d attempt=%d/%d ph=%.2f ec=%.1f",
            task.id, task.corr_attempt, task.corr_max_attempts, ph, ec)

# Commands:
logger.info("AE3 commands: task=%d stage=%s plans=%s",
            task.id, stage_def.name, stage_def.command_plans)
```

### Prometheus Metrics

Файл `ae3lite/runtime/metrics.py` — без изменений от предыдущего плана.
Counters, histograms, gauges для workflow/stage/correction.

### Infrastructure Alerts

Те же алерт-коды: `ae3_stage_failed`, `ae3_correction_failed`, `ae3_sensor_unavailable`,
`ae3_workflow_completed` (resolved). Через `common/infra_alerts.py`.

---

## Тестирование

### Стратегия

**Clean break** — все 17 существующих тестовых файлов обновляются для новой схемы.
Нет parity-тестов (старого кода не будет).

### Обновление существующих тестов

Каждый тест, создающий `AutomationTask` или выполняющий INSERT в ae_tasks,
обновляется: убрать `payload={}`, добавить explicit fields.

**Затронутые файлы (13 из 17):**

| Тест | Характер изменений |
|------|-------------------|
| `test_ae3lite_entities.py` | `AutomationTask(payload={})` → `AutomationTask(topology="two_tank", current_stage="startup", ...)` |
| `test_ae3lite_correction.py` | Полная переработка — CorrectionState вместо payload dicts |
| `test_ae3lite_two_tank_cycle_start_integration.py` | Полная переработка — WorkflowRouter вместо TwoTankExecutor |
| `test_ae3lite_claim_next_task_integration.py` | UPDATE SQL: убрать payload, добавить columns |
| `test_ae3lite_create_task_from_intent_integration.py` | intent fields вместо payload |
| `test_ae3lite_publish_planned_command_integration.py` | Минимально |
| `test_ae3lite_reconcile_command_integration.py` | Минимально |
| `test_ae3lite_runtime_worker_integration.py` | `task.intent_id` вместо payload |
| `test_ae3lite_startup_recovery_integration.py` | `current_stage` вместо payload stage |
| `test_ae3lite_task_status_read_model_integration.py` | Добавить current_stage в assertions |
| `test_ae3lite_compat_start_cycle.py` | intent fields assertions |
| `test_ae3lite_internal_task_endpoint.py` | Минимально |
| `test_ae3lite_cycle_start_planner.py` | Без изменений (planner не трогает task state) |

**Без изменений (4 файла):**
- `test_ae3lite_history_logger_client.py`
- `test_ae3lite_zone_snapshot_read_model_integration.py`
- `test_ae3lite_finalize_task.py`
- `test_ae3lite_cycle_start_planner.py`

### Новые тесты

| Файл | Тестов | Что проверяет |
|------|--------|---------------|
| `test_ae3lite_topology_registry.py` | 5 | Все stages валидны, нет dangling next_stage references, correction flags |
| `test_ae3lite_workflow_router.py` | 10 | Orchestration: dispatch, apply_outcome, requeue, upsert_phase, correction wait |
| `test_ae3lite_startup_handler.py` | 4 | Probe + level check → route to clean_fill or solution_fill |
| `test_ae3lite_command_handler.py` | 4 | run_batch → route via StageDef, terminal_error handling |
| `test_ae3lite_clean_fill_handler.py` | 5 | 4 outcomes + sensor consistency |
| `test_ae3lite_solution_fill_handler.py` | 5 | Level + targets + correction entry + deadline + poll |
| `test_ae3lite_prepare_recirc_handler.py` | 4 | Targets + correction entry + deadline |
| `test_ae3lite_correction_handler.py` | 8 | 8-step state machine, dose routing, exit with success/fail |
| `test_ae3lite_stage_transitions.py` | 3 | INSERT-only audit trail, metadata JSONB |
| `test_ae3lite_recovery_topology.py` | 5 | Recovery: command DONE → topology routing, correction crash → fail |

### E2E сценарии

Обновить существующие (E95, E96, E97):
- `ae_tasks` assertions: `current_stage`, `workflow_phase` вместо `payload->>'ae3_cycle_start_stage'`
- Добавить: `ae_stage_transitions` assertions (audit trail present)

---

## Фазы реализации

### Фаза 1: Типы + миграция

1. `domain/entities/workflow_state.py` — WorkflowState, CorrectionState dataclasses
2. `application/dto/stage_outcome.py` — StageOutcome
3. `domain/services/topology_registry.py` — StageDef + TWO_TANK
4. Laravel-миграция: add columns, drop payload, create ae_stage_transitions
5. `runtime/metrics.py` — Prometheus метрики
6. Тест: `test_ae3lite_topology_registry.py`

### Фаза 2: Entity + Repository

7. Переработка `AutomationTask` entity — убрать payload, добавить typed fields + properties
8. Переработка `PgAutomationTaskRepository` — requeue_pending v2, create_pending v2, все SQL
9. `infrastructure/repositories/stage_transition_repository.py` — INSERT-only audit
10. Обновить `task_status_read_model.py`
11. Тест: `test_ae3lite_stage_transitions.py`
12. Обновить: `test_ae3lite_entities.py`, `test_ae3lite_claim_next_task_integration.py`

### Фаза 3: Handler Classes + WorkflowRouter (ядро)

13. `application/handlers/base_handler.py` — BaseStageHandler:
    - `probe_irr_state()` — переносится 1:1 из TwoTankCycleStartExecutor
    - `read_level()` — переносится 1:1
    - `targets_reached()` — переносится 1:1
14. `application/handlers/startup_handler.py` — StartupHandler
15. `application/handlers/command_handler.py` — CommandHandler
16. `application/handlers/clean_fill_handler.py` — CleanFillHandler (4 outcomes)
17. `application/handlers/solution_fill_handler.py` — SolutionFillHandler (probe + correction)
18. `application/handlers/prepare_recirc_handler.py` — PrepareRecircHandler (probe + correction)
19. `application/handlers/correction_handler.py` — CorrectionHandler (8-step SM)
20. `application/use_cases/workflow_router.py` — orchestrator:
    - `run()`, `_apply_outcome()`, `_compute_deadline()`
    - `_upsert_workflow_phase()` — zone workflow status (критика #11)
    - `_log_transition()` — audit trail INSERT
    - `_requeue()`, `_complete_task()`, `_fail_task()`
21. Обновить `execute_task.py` — dispatch через WorkflowRouter
22. Обновить `startup_recovery.py` — `_apply_topology_done_transition()` (критика #5)
23. Обновить `bootstrap.py` — DI wiring (handler instances → WorkflowRouter)
24. Обновить `create_task_from_intent.py`, `legacy_intent_mapper.py`
25. Обновить `worker.py` — task.intent_id
26. Тесты: handlers (6 файлов ~30 тестов) + workflow_router (~10) + recovery (~5)
27. Обновить все integration-тесты (8 файлов)

### Фаза 4: Cleanup + E2E

28. Удалить `two_tank_cycle_start_executor.py` (417 строк)
29. Удалить `correction_executor.py` (563 строк)
30. Обновить E2E сценарии (E95, E96, E97)
31. `make test` + `make protocol-check`
32. Обновить `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

---

## Верификация

### 1. Миграция
```bash
make migrate  # новая миграция проходит
```

### 2. Unit-тесты
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine \
  pytest tests/ -x -v
```
Все тесты проходят (обновлённые + новые: topology_registry, 6 handlers, workflow_router, recovery).

### 3. Integration-тесты
```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine \
  pytest tests/ -x -v -k integration
```
8 обновлённых + 10 новых integration-теста проходят на реальной PostgreSQL.

### 4. E2E
```bash
make e2e  # или запуск через docker-compose.e2e.yml
```
Сценарии E95-E97 проходят с assertions на explicit columns.

### 5. Протокольные контракты
```bash
make protocol-check
```
Контрактные тесты проходят (API contract не меняется).

### 6. Ручная проверка audit trail
```sql
-- После запуска цикла:
SELECT * FROM ae_stage_transitions WHERE task_id = $1 ORDER BY triggered_at;
-- Ожидаем: startup → clean_fill_start → clean_fill_check → ... → complete_ready
```
