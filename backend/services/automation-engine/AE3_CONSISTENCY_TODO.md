# AE3 Consistency — что сделано, что осталось

**Ветка:** `ae3`
**Цель сессии:** довести автоматику AE3 до консистентного состояния после аудита.

---

## ✅ Сделано (Batch A — critical стейл-таск)

Все правки — расширение паттерна `task_override` из `CommandHandler` на остальные места, где handler публикует команды и/или мутирует task через репозиторий, после чего возвращает `StageOutcome`.

### Код

1. **`ae3lite/application/handlers/irrigation_check.py`** — `_solution_min_low_outcome` пробрасывает `updated` из `update_irrigation_runtime` через `task_override=updated`. Было: stale task с устаревшим `irrigation_replay_count` после его обновления.

2. **`ae3lite/application/handlers/prepare_recirc_window.py`** — `_run_commands` изменён с `-> None` на `-> Any`, возвращает `result.get("task") or task`. Handler `run` теперь треdит `current_task` и передаёт его в `task_override` для `transition` и `fail` outcomes.

3. **`ae3lite/application/handlers/correction.py`** — все 6 сайтов `run_batch` обновлены:
   - `_run_activate`
   - `_run_dose_ec` (обе ветки: multi-component seq и single)
   - `_run_dose_ph`
   - `_run_deactivate`
   - helper `_ensure_sensor_mode_active_for_dosing` (`-> None` → `-> Any`)
   - helper `_maybe_reactivate_sensor_mode_after_empty_window`

   Паттерн: `current_task = result.get("task") or current_task`, далее `task_override=current_task if current_task is not task else None` в финальном `StageOutcome`.

4. **`ae3lite/application/handlers/correction.py`** — `_enter_correction_after_delay_or_interrupt` и `_interrupt_for_imminent_retry_then_probe_deadline` получили опциональный параметр `task_override`, который пробрасывается во все возвращаемые `StageOutcome`.

### Тесты

5. **`test_ae3lite_workflow_router.py`** — добавлены 5 новых тестов для `task_override` во всех kinds:
   - `test_router_poll_uses_task_override_owner_from_command_reconcile`
   - `test_router_enter_correction_uses_task_override_owner_from_command_reconcile`
   - `test_router_exit_correction_uses_task_override_owner_from_command_reconcile`
   - `test_router_complete_uses_task_override_owner_from_command_reconcile`
   - `test_router_fail_uses_task_override_for_metrics`

6. **`test_ae3lite_workflow_router.py`** — рефакторинг: `_make_task(...)` разделён на `_make_task_row(...)` (возвращает dict) и тонкий wrapper `_make_task(**kwargs)`. Это починило существующий тест `test_router_transition_uses_task_override_owner_from_command_reconcile`, который падал с `AttributeError: 'AutomationTask' object has no attribute 'to_row'`.

### Проверка

- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q --ignore-glob='*integration*' -p no:cacheprovider`
- **880 passed, 1 warning** (warning не связан с нашими правками — в `common/test_commands.py`)

---

## 🔄 В процессе (Batch F / Gap 7 cleanup) — начато, не доделано

**Задача:** удалить мёртвый fallback-путь в `StartupRecoveryUseCase._recover_task`, который идёт через `ReconcileCommandUseCase`. Этот путь срабатывает только если `command_gateway is None` ИЛИ `task.topology` не входит в `{"two_tank", "two_tank_drip_substrate_trays"}`. В реальности:
- bootstrap всегда передаёт `command_gateway`
- `TopologyRegistry` содержит только two_tank топологии

→ fallback путь никогда не исполняется в production.

### Что надо удалить

**`ae3lite/application/use_cases/startup_recovery.py`:**
- Импорт `CommandReconcileError` (строка 12)
- Параметр `reconcile_command_use_case` в `__init__` (строки 30, 37)
- Fallback блок в `_recover_task` (строки 104–144):
  - `try: result = await self._reconcile_command_use_case.run(...)` + except
  - `if result.is_terminal: ...`
  - `if result.legacy_status is None: ...`
  - `if task.status in {"claimed", "running"}: ...`
- Helper методы (становятся dead code):
  - `_missing_command_error_code` (426–429)
  - `_reconcile_error_code` (431–434)
  - `_missing_command_error_message` (436–439)
- После удаления: проверка `if self._command_gateway is not None and self._is_two_tank_task(task):` становится безусловной. Рассмотреть: убрать guard или оставить как защитный.

**`ae3lite/runtime/bootstrap.py`:**
- Импорт `ReconcileCommandUseCase` (строка 20)
- Блок создания `reconcile_command_use_case = ReconcileCommandUseCase(...)` (строки 89–92)
- Аргумент `reconcile_command_use_case=reconcile_command_use_case` в конструкторе `StartupRecoveryUseCase` (строка 140)

**`ae3lite/application/use_cases/__init__.py`:**
- Импорт `ReconcileCommandUseCase` (строка 12)
- Экспорт `"ReconcileCommandUseCase"` (строка 27)

**`ae3lite/application/use_cases/reconcile_command.py`:** полностью удалить файл (после удаления всех ссылок).

**`ae3lite/domain/errors.py`:** удалить класс `CommandReconcileError` (строка 190).

**`ae3lite/application/dto/command_reconcile_result.py`:** удалить файл (DTO используется только в `reconcile_command.py` и его тестах).

**`ae3lite/application/dto/__init__.py`:** удалить экспорт `CommandReconcileResult`.

### Тесты — обновить или удалить

- **`test_ae3lite_reconcile_command_integration.py`** — удалить файл полностью (тестирует только удаляемый `ReconcileCommandUseCase`).
- **`test_ae3lite_startup_recovery_integration.py`** — убрать конструкцию `ReconcileCommandUseCase` и аргумент из `StartupRecoveryUseCase(...)` (строки 259, 263, 379, 383, 564). Проверить, что тесты всё ещё валидны (они должны тестировать только native two_tank путь).
- **`test_ae3lite_recovery_topology.py`** — удалить класс `_MockReconcileUseCase` и убрать аргумент `reconcile_command_use_case=...` из всех вызовов `_make_use_case`/`StartupRecoveryUseCase` (строки 235, 296, 344, 364). Убрать импорт `CommandReconcileResult` если есть.
- **`test_ae3lite_startup_recovery_metrics.py`** — убрать аргумент `reconcile_command_use_case=object()` (строка 31).
- **`test_ae3lite_runtime_worker_integration.py`** — убрать `reconcile_command_use_case=type("ReconcileNoop", ...)()` (строка 353).
- **`test_ae3lite_two_tank_cycle_start_integration.py`** — убрать `reconcile_command_use_case=type("ReconcileNoop", ...)()` (строка 435).

### Как проверять после cleanup

```bash
# Unit тесты
docker compose -f backend/docker-compose.dev.yml exec -T automation-engine \
  pytest -q --ignore-glob='*integration*' -p no:cacheprovider

# Integration тесты startup_recovery (более длинные — нужен БД)
docker compose -f backend/docker-compose.dev.yml exec -T automation-engine \
  pytest test_ae3lite_startup_recovery_integration.py \
         test_ae3lite_startup_recovery_metrics.py \
         test_ae3lite_recovery_topology.py \
         test_ae3lite_runtime_worker_integration.py \
         test_ae3lite_two_tank_cycle_start_integration.py -q

# Smoke: сервис поднимается без ошибок
docker compose -f backend/docker-compose.dev.yml logs automation-engine | tail -50
```

---

## ❓ Что ещё проверить перед коммитом

1. **Прогнать весь unit-набор AE3 после cleanup:**
   ```bash
   docker compose -f backend/docker-compose.dev.yml exec -T automation-engine \
     pytest -q -p no:cacheprovider
   ```
   Ожидать ~880 passed (возможно меньше на сумму удалённых тестов `test_ae3lite_reconcile_command_integration.py` — проверить число).

2. **Integration тесты** (требуют запущенную БД):
   ```bash
   docker compose -f backend/docker-compose.dev.yml exec -T automation-engine \
     pytest -q -p no:cacheprovider
   ```
   Обратить внимание на:
   - `test_ae3lite_startup_recovery_integration.py` — проверить обе ветки (recovery DONE → next stage, recovery waiting → stays waiting).
   - `test_ae3lite_recovery_topology.py` — проверить, что тесты не полагались на fallback путь.
   - `test_ae3lite_runtime_worker_integration.py` — полный цикл claim → execute → recovery.

3. **E2E smoke (опционально):**
   ```bash
   # Двух-баковый workflow
   cd tests/e2e && ./run_e2e.sh E83_clean_water_fill
   # Коррекция pH/EC
   ./run_e2e.sh E86_correction_cycle
   # Recovery
   ./run_e2e.sh E109_ae3_irrigation_runtime_test_node
   ```

4. **Линтинг Python** (если настроен):
   ```bash
   docker compose -f backend/docker-compose.dev.yml exec -T automation-engine \
     python -m compileall ae3lite
   ```

5. **Protocol contract тесты** (на случай если удаление затронуло что-то):
   ```bash
   make protocol-check
   ```

---

## 📊 Финальный реестр gap'ов из аудита

Из 15 gap'ов, найденных Explore-агентом, **4 оказались реальными** (все исправлены в Batch A), **10 — ложные срабатывания** (подтверждено верификацией кода), **1 — dead code** (Gap 7, в процессе cleanup).

| # | Gap | Severity (аудит) | Статус | Комментарий |
|---|---|---|---|---|
| 1,4 | correction.py stale task | critical | ✅ исправлен | Batch A |
| 2 | `_probe_irr_state` stale | critical | ❌ ложный | `track_task_state=False` — gateway возвращает исходный task, никакой mutation не происходит |
| 3 | `prepare_recirc_window` stale | critical | ✅ исправлен | Batch A |
| 5 | `AwaitReadyHandler` stale phase | major | ❌ ложный | snapshot перезагружается на каждом вызове `execute_task.run()` через worker loop |
| 6 | task_override тесты неполные | minor | ✅ исправлен | Batch A (5 новых тестов) |
| 7 | `StartupRecovery` не покрывает все topology | major | ⚠️ dead code | Только two_tank существует; fallback путь не исполняется. В процессе удаления. |
| 8 | `exit_correction` пересчитывает deadline | major | ❌ ложный | `solution_fill_check` и `irrigation_check` имеют `on_corr_success=self`, значит `same_stage=True` в `_apply_transition` → deadline preserved |
| 9 | Lease heartbeat отсутствует | major | ❌ ложный | `worker.py:123` уже стартует `_lease_heartbeat` background task с `lease_lost_event` |
| 10 | Snapshot stale между poll | major | ❌ ложный | Worker loop — единственный механизм итерации; каждый `execute_task.run()` строит snapshot заново |
| 11 | Correction re-entry сбрасывает attempt | major | ❌ ложный | `solution_fill.py:215` явно проверяет `stage_retry_count > 0` и возвращает poll вместо новой коррекции |
| 12 | `_fail_task` не синхронизирует phase | major | ❌ ложный | `execute_task.py:822` `_sync_workflow_failure_state` уже вызывается в `_fail_closed` → `upsert_phase("idle")` |
| 13 | `irrigation_check` теряет replay_count | critical | ✅ исправлен | Batch A |
| 14 | `AwaitReadyHandler` timeout tests | minor | ❌ ложный | `test_await_ready_fails_on_deadline_exceeded` и др. уже существуют |
| 15 | `recover_waiting_command` stale | major | ❌ ложный | Возвращает свежий task из `resume_after_waiting_command`/`mark_failed`; в waiting_command пути task в БД не меняется |

**Вывод:** аудит Explore-агента был поверхностным — ~67% findings оказались false positives. Агент не проследил полные цепочки снаружи `ae3lite/application/handlers/` (worker loop, read_models, error handling в execute_task). Batch A закрыл все реальные баги. Дальнейшие батчи B, C, D, E — не требуются.

---

## 🚀 Рекомендуемый порядок действий

1. **Завершить Gap 7 cleanup** (см. раздел "В процессе") — ~15 файлов под правку/удаление, но механические изменения.
2. **Прогнать unit-тесты** → ожидать ~880 passed минус удалённые интеграционные тесты.
3. **Прогнать integration-тесты** startup_recovery.
4. **Коммит** с разделением на две группы (если нужна аккуратная история):
   - `refactor: propagate task_override from all command-publishing handlers (AE3 consistency Batch A)`
   - `refactor: remove dead ReconcileCommandUseCase fallback from startup recovery (Gap 7 cleanup)`
5. Опционально: E2E smoke (E83/E86/E109).

---

## 📁 Файлы, затронутые в сессии

### Модифицированы (Batch A)
- `ae3lite/application/dto/stage_outcome.py` (pre-existing — `task_override` поле)
- `ae3lite/application/handlers/command.py` (pre-existing — проброс `task_override`)
- `ae3lite/application/handlers/correction.py` ⭐ новое
- `ae3lite/application/handlers/irrigation_check.py` ⭐ новое
- `ae3lite/application/handlers/prepare_recirc_window.py` ⭐ новое
- `ae3lite/application/use_cases/workflow_router.py` (pre-existing — `current_task = task_override or task`)
- `test_ae3lite_workflow_router.py` ⭐ новое (5 тестов + refactor)

### Будут затронуты (Gap 7 cleanup)
- `ae3lite/application/use_cases/startup_recovery.py`
- `ae3lite/application/use_cases/reconcile_command.py` (удалить)
- `ae3lite/application/use_cases/__init__.py`
- `ae3lite/application/dto/command_reconcile_result.py` (удалить)
- `ae3lite/application/dto/__init__.py`
- `ae3lite/runtime/bootstrap.py`
- `ae3lite/domain/errors.py`
- `test_ae3lite_reconcile_command_integration.py` (удалить)
- `test_ae3lite_startup_recovery_integration.py`
- `test_ae3lite_recovery_topology.py`
- `test_ae3lite_startup_recovery_metrics.py`
- `test_ae3lite_runtime_worker_integration.py`
- `test_ae3lite_two_tank_cycle_start_integration.py`
