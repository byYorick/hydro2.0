# Audit: Phase 5 config modes (locked/live)

**Дата аудита:** 2026-04-15
**Scope:** Phase 5 (backend migration + controllers + policy + TTL cron + AE3 _checkpoint) и Phase 5.1 (revision bump в unified API) и Phase 5.5 (actual hot-swap)
**Состояние:** все findings исправлены и зафиксированы тестами
**Parent plan:** [AE3_CONFIG_REFACTORING_PLAN.md](AE3_CONFIG_REFACTORING_PLAN.md)

---

## Сводка

3 CRITICAL + 2 MAJOR = 5 реальных bugs найдены после первичной реализации. Все исправлены в том же дне. Все остальные ранее-выделенные замечания оказались MINOR/NIT и закрыты документацией.

| # | Severity | Finding | Root cause | Fix |
|---|---|---|---|---|
| 1 | CRITICAL | `bundle_revision` vs `config_revision` confusion | В Phase 5.5 `_checkpoint` сравнивал `runtime.bundle_revision` (content hash string, формата `abc123-deadbeef`) через `int()` парс → всегда ValueError → fallback 0 → hot-reload не триггерился | Добавлено отдельное поле `config_revision: int \| None` в `RuntimePlan`. `ZoneSnapshot` расширен, `PgZoneSnapshotReadModel` читает `z.config_revision`, `cycle_start_planner` инжектит в runtime dict. `_checkpoint` сравнивает integer counter, не hash. |
| 2 | CRITICAL | Helpers used stale runtime | `_workflow_ready_reached` и `_targets_reached` в `base.py` делали `runtime = plan.runtime` внутри себя, игнорируя hot-swapped runtime из handler-level `_checkpoint()` | Добавлен optional kwarg `runtime: Any = None` в обе функции + fallback на `plan.runtime`. Handler call sites передают `runtime=runtime`. Позже унифицировано Phase 5.5+ через `dataclasses.replace(plan, runtime=...)` — эти kwargs остались backward-compat, но больше не нужны функционально. |
| 3 | CRITICAL | `bumpAndAudit` race | `(int) ($zone->config_revision ?? 1) + 1` без row lock → конкурентные PUT создавали revision holes или duplicate `(zone_id, revision)` ключи | Заменено на атомарный SQL `UPDATE zones SET config_revision = COALESCE(config_revision, 0) + 1 WHERE id = ? RETURNING config_revision` внутри `DB::transaction`. Unique constraint `zone_config_changes (zone_id, revision)` — correctness net. |
| 4 | MAJOR | `extend` TTL race | `ZoneConfigModeController::extend` читал `zone->config_mode` без lock, параллельный cron `RevertExpiredLiveModesCommand` мог flip в locked между проверкой и save → `config_mode=locked + live_until != NULL` нарушал CHECK `zones_live_requires_until` | Wrapped в `DB::transaction` → `Zone::lockForUpdate()->find($id)` → double-check `config_mode == 'live'` внутри lock → save. 409 `NOT_IN_LIVE_MODE` если state race'нулся. |
| 5 | MAJOR | revert cron race | `Zone::where('config_mode','live')->whereNotNull('live_until')->where('live_until','<',$now)->get()` без lock → второй cron instance мог double-revert → duplicate audit rows | Заменено на `->pluck('id')` candidates без lock + per-zone цикл с `Zone::lockForUpdate()->find($zoneId)` + inside-lock re-check `config_mode == 'live' AND live_until < now`. Race-proof с любыми параллельными cron instances (deployment race, manual triggering). |

---

## Дополнительные заметки (MINOR / NIT)

- **Idempotent PUT bumps revision**: если PUT с тем же payload — revision всё равно инкрементируется и hot-reload триггерится. Harmless (metric `applied` отражает activity, handler rebuild ничего не меняет по сути). Optimization: сравнить previous/new payload и skip bump при identical. Не сделано — оставлено как документированная особенность.
- **Event contract docs**: добавлены `CONFIG_HOT_RELOADED`/`CONFIG_MODE_AUTO_REVERTED`/`ZONE_CONFIG_CHANGED` в `AE3_RUNTIME_EVENT_CONTRACT.md` §4.6–4.8.
- **`_checkpoint` DB-pool failure**: логирует `warning` + `result=error` metric, возвращает original runtime (fail-safe). Handler execution продолжается без hot-swap.
- **operator попадает в route middleware** `role:operator,...` для PATCH `/config-mode`: controller затем rejects live (via `setLive` policy). operator может только revert locked. Документировано в `AUTOMATION_CONFIG_AUTHORITY.md` §8.

---

## Регрессионные тесты, закрывающие findings

- `test_ae3lite_checkpoint_hot_swap.py` — 5 unit tests: disabled/zero zone_id/DB failure/locked/revision-not-advanced семантика
- `test_ae3lite_live_reload.py` — 6 tests
- `test_ae3lite_config_modes.py` — 10 parametrized tests для `ConfigMode.parse`
- Laravel `ZoneConfigModeControllerTest` — 9 feature tests (TTL bounds, 409 conflict, extend require live, policy rejection, revert audit)
- Laravel `ZoneConfigRevisionBumpTest` — 1 E2E (PUT zone.correction → revision++ + audit)
- Laravel `GrowCyclePhaseConfigControllerTest` — 5 feature tests
- AE3 full suite: `make test-ae` → 1273 passed (включая интеграционные handler тесты, получающие plan через real snapshot)

---

## Что НЕ было проверено в этом аудите

1. **Real production live-mode under active correction**: все тесты на hot-swap purely unit — проверяют return contract, но не фактическое поведение correction handler с изменением target_ec mid-dose. Нужен characterization test с `live_until` сдвигом во время work-loop. Deferred до нужды.
2. **Cron single-instance invariant**: Laravel scheduler default — single-instance, но при manual triggering (oncall runbook) возможно. Lock-based impl справится, но не воссоздано в тестах.
3. **Playwright E2E**: Vue components покрыты Vitest; интеграция с реальным сетевым flow (PATCH → poll → hot-swap) — не воссоздана. Phase 6 UI shipped без Playwright coverage (accepted trade-off).

---

**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
