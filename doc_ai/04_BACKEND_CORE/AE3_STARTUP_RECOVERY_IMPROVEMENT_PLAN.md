# План улучшения startup recovery AE3-Lite

**Версия:** 1.0  
**Дата:** 2026-06-29  
**Статус:** PLAN (implementation roadmap)  
**Владелец слоя:** `backend/services/automation-engine/ae3lite/`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Цель

Устранить операционные инциденты после рестарта `automation-engine`, когда цикл зоны **физически выполнен**, но runtime переводит задачу в `failed` (`startup_recovery_unconfirmed_command`) или оставляет её **без исполнителя** в `waiting_command`.

План не меняет защищённый пайплайн команд (`Laravel → AE → history-logger → MQTT`) и не допускает повторную MQTT-публикацию из recovery без явного безопасного основания.

**Связанные документы:**
- `doc_ai/04_BACKEND_CORE/ae3lite.md` — §9 Recovery и failure model (канонический контракт)
- `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` — коды startup recovery
- `doc_ai/08_SECURITY_AND_OPS/RUNBOOKS.md` — операции при рестарте AE
- `doc_ai/08_SECURITY_AND_OPS/SYSTEM_FAILURE_RECOVERY.md` — L3 Python-сервисы

---

## 2. Контекст (as-is)

### 2.1 Поток при старте контейнера

```
FastAPI lifespan
  → get_pool (retry)
  → Ae3RuntimeWorker.recover_on_startup()
       → StartupRecoveryUseCase.run()
  → worker.kick()  // drain только pending-задач
```

Ключевые файлы:
| Компонент | Путь |
|-----------|------|
| Lifespan | `ae3lite/runtime/app.py` |
| Worker | `ae3lite/runtime/worker.py` |
| Startup recovery | `ae3lite/application/use_cases/startup_recovery.py` |
| Command reconcile | `ae3lite/infrastructure/gateways/sequential_command_gateway.py` |
| Task scan | `PgAutomationTaskRepository.list_for_startup_recovery()` |
| Bootstrap | `ae3lite/runtime/bootstrap.py` |
| Алерт task-failed | `ae3lite/application/services/task_failed_alert.py` |

### 2.2 Что recovery делает сейчас

1. `release_expired` для `ae_zone_leases`.
2. Сканирует `ae_tasks` со статусами `claimed | running | waiting_command`.
3. Для каждой задачи:
   - **`claimed` / `running`** → безусловный `fail` с `startup_recovery_unconfirmed_command`.
   - **`waiting_command`** → `recover_waiting_command` (чтение legacy `commands`, без republish):
     - terminal `DONE` → topology transition → `pending` на следующем stage (`recovered_waiting_command`);
     - ещё не terminal → остаётся `waiting_command`;
     - terminal error → `failed` через gateway.
4. Reconcile: `pending` + `zone_workflow_state.workflow_phase=idle` + terminal stage в payload → fail.
5. Синхронизация terminal intents (только outcomes с `intent_id`).

### 2.3 Внешние контуры

- **Laravel watchdog:** `ae3:reap-stale-tasks` — fail зависших `claimed|running|waiting_command` (дефолт 15 мин без прогресса).
- **UI observability:** hint `waiting_command_stuck`, `workflow_snapshot_stale`.
- **Алерты:** `biz_ae3_task_failed` при fail через `_fail_task` (с `recovery_source: startup_recovery`).

---

## 3. Выявленные проблемы

### P1 — Ложный fail для `running` после DONE (критично для операторов)

**Симптом:** после рестарта AE задача в `failed` / `startup_recovery_unconfirmed_command`, хотя последняя команда в `commands` уже `DONE` (пример: `prepare_recirculation_start`, task #3).

**Причина:** ветка `claimed|running` fail'ится до проверки `ae_commands` / legacy status.

**Риск fail-open:** handler мог выполнить неидемпотентную логику между DONE и transition — нужна явная матрица «безопасно продолжить / только fail».

---

### P2 — `waiting_command` без runtime reconcile после старта

**Симптом:** recovery оставил задачу в `waiting_command` (команда ещё не terminal); worker claim'ит только `pending` → опрос legacy-команды не идёт.

**Окно:** команда завершается **после** прохода startup recovery, но **до** следующего рестарта — задача зависает до watchdog / ручного вмешательства.

**На старте** delayed terminal покрыт (при рестарте с уже DONE recovery продвигает stage).

---

### P3 — Lease не снимается при recovery-fail

**Симптом:** task `failed`, но `ae_zone_leases` ещё занят dead owner до `leased_until` (до 300 с по умолчанию).

**Эффект:** новый claim / start-cycle может получить `start_cycle_zone_busy`.

---

### P4 — Нет graceful shutdown

**Симптом:** `SIGTERM` не drain'ит in-flight tasks; lifespan не ждёт worker.

**Эффект:** каждый deploy увеличивает число recovery-fail.

---

### P5 — Пробелы observability и алертов

- `result["state"] == "failed"` из gateway в recovery не всегда даёт `biz_ae3_task_failed`.
- Нет единого `zone_event` / service-log на outcome recovery.
- Intent при `waiting_command` outcome не синхронизируется (scheduler видит `running`).

---

### P6 — Спека vs тесты

`ae3lite.md` §9.2 задаёт 5 crash windows; в CI нет единого контрактного suite как gate.

---

### P7 — Multi-instance recovery (prod)

Несколько реплик AE при старте гоняют recovery параллельно; идемпотентность частичная, workflow/alert dedupe не гарантированы.

---

## 4. Матрица состояний (target)

| Статус до crash | `ae_commands` / legacy | Сейчас | Target (после плана) |
|-----------------|------------------------|--------|----------------------|
| `waiting_command` | не terminal | остаётся, нет poll | background reconcile → DONE → `pending` |
| `waiting_command` | `DONE` | → `pending` next stage | requeue текущего command-stage; RuntimePlan подтверждает весь batch |
| `running` | последняя `DONE` | **fail** | requeue текущего command-stage; завершённые `planner_step` не republish'ятся |
| `running` | in-flight, не terminal | **fail** | → `waiting_command` + reconcile |
| `running` | нет ae_command | **fail** | fail или requeue `pending` (см. фазу 2) |
| `claimed` | нет ae_command | **fail** | fail (crash до publish) |
| любой | `correction != null` | fail | fail (без изменений) |

---

## 5. Фазы реализации

Рекомендуемый порядок: **один PR на фазу**, каждая фаза самодостаточна для merge.

### Фаза 0 — Зафиксировано (baseline)

- [x] Общий helper `emit_task_failed_alert` (`task_failed_alert.py`).
- [x] Алерт при fail через `_fail_task` в startup recovery.
- [x] `alert_repository` в `StartupRecoveryUseCase` + bootstrap.

---

### Фаза 1 — Quick wins (низкий риск, 1–2 дня) ✅

**Цель:** убрать «залипшие» зоны и закрыть дыры в сигнализации.

| # | Задача | Статус |
|---|--------|--------|
| 1.1 | Release lease при recovery-fail | ✅ `release_if_owner_or_expired` |
| 1.2 | Алерт на gateway-fail path | ✅ |
| 1.3 | `AE_STARTUP_RECOVERY_OUTCOME` + service-log | ✅ |
| 1.4 | RUNBOOK §3.2 | ✅ |

---

### Фаза 2 — Умный recovery для `running` + DONE (главный fix, 2–4 дня) ✅

**Цель:** не fail'ить задачи, где MQTT-команда уже подтверждена, но handler не успел сделать stage transition.

**Алгоритм (псевдокод):**

```
if task.correction: fail correction_interrupted  // без изменений
try recover_waiting_command (для claimed|running|waiting_command)
  missing ae_command + claimed|running → fail startup_recovery_unconfirmed_command
  waiting_command → fail ae3_missing_ae_command (как раньше)
  state waiting_command + in-flight legacy → persist waiting_command для claimed|running
  state done → requeue текущего command-stage
    → handler восстанавливает RuntimePlan
    → gateway пропускает совпавшие terminal DONE planner_step
    → topology transition только после полного batch
  state failed → _finalize_recovery_failure
```

**Ограничения:**
- Только stages из topology registry; command-stage после recovery обязательно
  проходит повторную проверку полного RuntimePlan batch.
- Запрет auto-resume для stages с side-effect между DONE и transition (если появятся — whitelist в registry).

**Файлы:**
- `ae3lite/application/use_cases/startup_recovery.py` — `_handle_recovery_gateway_result`, `_persist_waiting_command_status`

**Тесты:**
- [x] Unit: `running` + legacy DONE → `pending` текущий stage
- [x] Unit: `running` + legacy pending → `waiting_command`, не fail
- [x] Integration: `prepare_recirculation_start` + DONE
- [x] Негатив: `running` + нет ae_command → fail
- [x] Crash-window: первая `DONE` из multi-command `irrigation_start` не
  переводит задачу в `irrigation_check`; повторный batch не публикует первый step

**Обновлено:** `ae3lite.md` §9.1 п.4–5.

---

### Фаза 3 — Background reconcile для `waiting_command` (2–3 дня) ✅

**Цель:** закрыть P2 — команда завершилась после startup recovery.

**Реализация (вариант A):**
- `WaitingCommandReconcileUseCase` — batch reconcile через `StartupRecoveryUseCase.reconcile_waiting_command_task`
- фоновый loop в `Ae3RuntimeWorker` (`AE_RECONCILE_POLL_INTERVAL_SEC`, wake на `kick`)
- `list_waiting_command_for_reconcile(limit)` в `PgAutomationTaskRepository`
- skip при foreign active lease; `kick` при `progressed_tasks > 0`
- метрика `ae3_waiting_command_reconcile_total{outcome}`
- `recovery_source=waiting_command_reconcile` в outcome events/alerts

**Тесты:**
- [x] integration: delayed DONE после ACK pass
- [x] integration: foreign lease skip

---

### Фаза 4 — Graceful shutdown (2 дня) ✅

**Цель:** снизить частоту recovery-fail при deploy.

**Статус:** реализовано.

1. Lifespan `finally`: `bundle.worker.shutdown(grace_sec=AE_SHUTDOWN_GRACE_SEC)`.
2. Worker: перестать claim новых tasks; `asyncio.wait(inflight, timeout=AE_SHUTDOWN_GRACE_SEC)`.
3. In-flight `claimed|running` без `ae_commands` → `requeue_unpublished_execution` → `pending` (+ release zone lease).

**Env:** `AE_SHUTDOWN_GRACE_SEC` (default 30).

**Файлы:** `ae3lite/runtime/app.py`, `ae3lite/runtime/worker.py`, `ae3lite/runtime/env.py`, `test_ae3lite_worker_shutdown.py`.

**Не цель:** гарантировать завершение длинных pump-команд — только корректная фиксация состояния.

---

### Фаза 5 — Crash-window contract suite (1–2 дня) ✅

**Цель:** формализовать `ae3lite.md` §9.2 в CI.

**Статус:** реализовано.

Новый файл: `backend/services/automation-engine/test_ae3lite_startup_recovery_crash_windows.py`

| # | Crash window | Ожидание | Тест |
|---|--------------|----------|------|
| W1a | crash до `ae_commands` insert | fail на startup recovery | `test_w1_crash_before_ae_commands_insert_fails_on_startup_recovery` |
| W1b | crash до `ae_commands` insert | requeue `pending` (phase 4) | `test_w1_crash_before_ae_commands_insert_requeues_on_graceful_shutdown` |
| W2 | crash после insert, до publish | `waiting_command` | `test_w2_crash_after_ae_commands_insert_before_publish_waits` |
| W3 | crash после publish, до `waiting_command` | `waiting_command` | `test_w3_crash_after_publish_before_waiting_command_persists_waiting` |
| W4 | crash в `waiting_command` | recovery без republish | `test_w4_crash_in_waiting_command_recovers_without_republish` |
| W5 | delayed terminal после restart | DONE → next stage | `test_w5_delayed_terminal_done_after_restart_advances_stage` |

**CI/Makefile:** `make test-ae-crash-windows` (также входит в `make test-ae` и `make protocol-check`).

---

### Фаза 6 — Multi-instance hardening (опционально, prod) ✅

**Статус:** реализовано.

- `pg_try_advisory_lock` на `StartupRecoveryUseCase.run()` (ключ: `zlib.crc32("ae3_startup_recovery")`).
- Пропуск прохода при занятом lock (`skipped_due_to_lock`, метрика `ae3_startup_recovery_skipped_total`).
- Dedupe key для recovery alerts: `biz_ae3_task_failed:{zone_id}:{task_id}:{recovery_source}`.
- Документировано в `ae3lite.md` §9.1 п.10: AE в prod — single active writer на зону или coordinated recovery.

**Файлы:** `ae3lite/infrastructure/advisory_locks.py`, `startup_recovery.py`, `task_failed_alert.py`, `test_ae3lite_startup_recovery_multi_instance.py`.

---

## Не входит в scope

- Изменение MQTT payload / топиков.
- Автоматический republish «застрявших» команд.
- Resume mid-dose коррекции после interrupt (остаётся fail-closed для dosing step).
  После interrupt: deferred hardware verify + optional irrigation replay (см. § ниже).
- Переписывание FSM на event sourcing.

### Дополнение (2026-07-22) — power-loss / correction interrupt

После `startup_recovery_correction_interrupted` на dose-step:
1. Task fail-closed (без resume дозирования).
2. Workflow rollback (irrigation → `ready`).
3. **Deferred verify** (grace `AE_CORRECTION_INTERRUPT_VERIFY_GRACE_SEC`, default 120s):
   ждать online `irrig/ph/ec` + свежий `IRR_STATE_SNAPSHOT` OFF для stage.
4. Safe → event `AE_CORRECTION_INTERRUPT_HARDWARE_SAFE`; для `irrigation_start`
   auto-replay intent (`AE_CORRECTION_INTERRUPT_REPLAY_IRRIGATION=1`).
5. Unsafe / timeout → critical `biz_flow_stop_failed_hardware_may_be_active`.

Это закрывает ложные critical после brownout, когда AE поднимается раньше узлов.

---

## 7. Риски и митигации

| Риск | Митигация |
|------|-----------|
| Fail-open при resume `running` после DONE | Requeue текущего stage + полная сверка RuntimePlan по `planner_step`; topology transition только из handler |
| Двойной reconcile двумя worker'ами | lease + `UPDATE … WHERE status` guards; фаза 6 advisory lock |
| Retry storm при background reconcile | batch limit, exponential backoff, метрики |
| Ложные алерты после deploy | dedupe_key; resolve при успешном recover |

---

## 8. Критерии готовности программы (Definition of Done)

1. Сценарий «рестарт AE во время `prepare_recirculation_start` с DONE в commands» → зона продолжает цикл **без** ложного `startup_recovery_unconfirmed_command`.
2. `waiting_command` с delayed DONE продвигается в течение `2 × AE_RECONCILE_POLL_INTERVAL_SEC` без рестарта.
3. После recovery-fail lease зоны свободен ≤ 1 с.
4. Все crash windows §9.2 зелёные в CI.
5. RUNBOOK обновлён; оператор видит `AE_STARTUP_RECOVERY_OUTCOME` в events.
6. Строка `Compatible-With` в PR каждой фазы.

---

## 9. Чек-лист для ИИ-агента (по фазе)

```
Контекст: doc_ai/04_BACKEND_CORE/AE3_STARTUP_RECOVERY_IMPROVEMENT_PLAN.md, ae3lite.md §9
Цель: <номер фазы>
Вход: перечисленные файлы из таблицы фазы
Ограничения: no MQTT republish from recovery; migrations только при необходимости
Критерии: таблица фазы + make test-ae PYTEST_ARGS="..."
Формат ответа: diff файлов, команды тестов, обновления doc_ai при изменении контракта
```

---

## 10. История изменений

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-06-29 | 1.0 | Первичный план по результатам архитектурного аудита рестарта AE |
| 2026-06-29 | 1.1 | Фаза 1 реализована (lease release, gateway alert, outcome events, RUNBOOK) |
| 2026-06-29 | 1.2 | Фаза 2: умный recovery `running|claimed` + DONE / in-flight |
| 2026-06-29 | 1.3 | Фаза 3: background `waiting_command` reconcile loop в worker |
| 2026-06-30 | 1.4 | Фазы 4–6: graceful shutdown, crash-window suite, multi-instance advisory lock |
