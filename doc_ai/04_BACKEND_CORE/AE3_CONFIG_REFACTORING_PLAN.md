# План рефакторинга: каноническая система конфигурирования AE3

**Версия:** 3.6 (merge: Phase 4/6.2 hardening + 2026-04-17 audit follow-ups: R12 metric, dead-code cleanup, phase_overrides partial validation, doc sync)
**Дата:** 2026-04-17
**Автор:** инженерный план, executor-first
**Статус:** end-to-end config modes (locked/live) работают в backend + AE3 + UI; legacy/shim слой Phase 4 удалён; Phase 6.2 (full correction fine-tuning live edit) закрыт вместе с hardening: AE3 `_checkpoint()` integration coverage + browser E2E live-edit flow; R12 mitigation (`ae3_zone_config_auto_reverts_total` + liveness panel) закрыт; phase_overrides теперь валидируется как partial diff (fix Phase 6.2 regression)

## Статус фаз

| Phase | Status | Artifact |
|---|---|---|
| 0: Discovery | ✅ completed 2026-04-15 | [AE3_CONFIG_PARAMETER_INVENTORY.md](AE3_CONFIG_PARAMETER_INVENTORY.md) |
| 1: JSON Schema | ✅ completed 2026-04-15 | [schemas/](../../schemas/), [ValidateZoneConfigsCommand](../../backend/laravel/app/Console/Commands/ValidateZoneConfigsCommand.php), [JsonSchemaValidator](../../backend/laravel/app/Services/JsonSchemaValidator.php) |
| 2: Pydantic + shadow loader | ✅ completed 2026-04-15 | [ae3lite/config/](../../backend/services/automation-engine/ae3lite/config/), shadow hook in [cycle_start_planner.py](../../backend/services/automation-engine/ae3lite/domain/services/cycle_start_planner.py), metric `ae3_shadow_config_validation_total` |
| 0–2 audit | ✅ completed 2026-04-15 | [AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md](AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md) — 12 findings (2 CRITICAL, 5 MAJOR, 5 MINOR) |
| Audit fixes (CRITICAL + MAJOR) | ✅ completed 2026-04-15 | A1+A2+A3 + B1-B5 |
| 3.1 P1 (pre-flight resync) | ✅ completed 2026-04-15 | [ResyncAutomationConfigDefaultsCommand](../../backend/laravel/app/Console/Commands/ResyncAutomationConfigDefaultsCommand.php) |
| 3.1 B-2/B-3/B-4 (RuntimePlan model + typed wrapper) | ✅ completed 2026-04-15 | [runtime_plan.py](../../backend/services/automation-engine/ae3lite/config/schema/runtime_plan.py), `resolve_two_tank_runtime_plan()` |
| 3.1 B-5a–d (Variant 3 + transition shim) | ✅ completed 2026-04-15 | `_DictShim` mixin, CommandPlan typed runtime |
| 3.1 B-5e/B-6 (hardcoded defaults removal) | ✅ completed 2026-04-15 | correction.py retry defaults + base.py `_OBSERVE_DEFAULT_*` |
| 3.1 B-7 (strict-required runtime reads) | ✅ completed 2026-04-15 | 5 handlers migrated (clean_fill, solution_fill, prepare_recirc, irrigation_check, startup); `_DEFAULT_PREPARE_RECIRCULATION_MAX_ATTEMPTS` deleted |
| 4: shim removal | ✅ completed 2026-04-16 | [runtime_plan_builder.py](../../backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py), [workflow_topology.py](../../backend/services/automation-engine/ae3lite/application/services/workflow_topology.py), [env.py](../../backend/services/automation-engine/ae3lite/runtime/env.py), [ae3_config_lint.py](../../tools/ae3_config_lint.py), renamed tests [test_ae3lite_runtime_plan_builder.py](../../backend/services/automation-engine/test_ae3lite_runtime_plan_builder.py) and [test_ae3lite_workflow_topology.py](../../backend/services/automation-engine/test_ae3lite_workflow_topology.py) |
| 5: Config modes backend (locked/live) | ✅ completed 2026-04-15 | migration + ZoneConfigModeController + ZonePolicy::setLive + RevertExpiredLiveModesCommand + AE3 `config/modes.py`/`live_reload.py` + `BaseStageHandler._checkpoint()` |
| 5 audit + fixes | ✅ completed 2026-04-15 | [AE3_CONFIG_REFACTORING_AUDIT_PHASE_5.md](AE3_CONFIG_REFACTORING_AUDIT_PHASE_5.md) — 3 CRITICAL + 2 MAJOR fixes |
| 5.1 (revision bump в unified API) | ✅ completed 2026-04-15 | `ZoneConfigRevisionService::bumpAndAudit` + wiring в `AutomationConfigController::update` |
| 5.5 (actual hot-swap) | ✅ completed 2026-04-15 | `_checkpoint` rebuilds via `PgZoneSnapshotReadModel` + `resolve_two_tank_runtime_plan`; unified pattern `replace(plan, runtime=...)` во ВСЕХ 5 handlers (включая correction.py) |
| 5.6 (recipe.phase live edit endpoint) | ✅ completed 2026-04-15 | `PUT /api/grow-cycles/{id}/phase-config` — whitelist 12 safe setpoint полей |
| 6: Config modes UI | ✅ completed 2026-04-15 | `ConfigModeCard.vue` + `ConfigChangesTimeline.vue` + integration в ZoneAutomationTab |
| 6.1: Recipe phase inline editor | ✅ completed 2026-04-15 | `RecipePhaseLiveEditCard.vue` — compact pH/EC targets editor в live mode |
| 7: Observability + doc gen | ✅ completed 2026-04-15 | Prometheus metrics `ae3_zone_config_mode` gauge + `ae3_zone_config_live_edits_total` + `ae3_zone_config_invalid_total` counters в `infrastructure/metrics.py`; Grafana dashboard `backend/configs/prod/grafana/dashboards/zone-configs.json`; `tools/generate_authority.py` + `make generate-authority`/`make authority-check` (CI guard); `AUTOMATION_CONFIG_AUTHORITY.md` автогенерируемая секция §«Автогенерируемые таблицы параметров» (6.3KB) |
| 6.2: full fine-tuning live edit correction/PID/calibration | ✅ fully closed 2026-04-16 | Backend `ZoneCorrectionLiveEditController` + `PUT /api/zones/{zone}/correction/live-edit`, UI `CorrectionLiveEditCard.vue`, Vitest component tests, AE3 integration test `test_ae3lite_checkpoint_hot_swap_integration.py`, browser E2E `13-correction-authority-flows.spec.ts`, timeline wiring `zone.correction.live`, docs sync (`ae3lite.md`, `ERROR_CODE_CATALOG.md`). |

**Tests state (2026-04-16):** исторический snapshot на 2026-04-15/16: ранее зелёными были 1273 AE (automation-engine) + 19 Laravel feature (Phase 5/5.1/5.6) + 1262 Vitest (145 files, incl. 14 Phase 6/6.1 unit tests). Для полного закрытия Phase 6.2 добавлены AE3 integration test на `_checkpoint()` live hot-reload и browser E2E live-edit flow; дополнительно после runtime typed cutover подтверждён расширенный AE rerun: `226 passed` по 12 профильным pytest-файлам (`await_ready`, `irrigation_runtime_integration`, `irrigation_check_correction`, `cycle_start_planner`, `workflow_router`, `irrigation_recovery`, `probe_backoff`, `correction_handler_multi_dose`, `irrigation_decision_controller`, `solution_fill`, `prepare_recirc_check`, `correction_handler`).

## Audit follow-ups shipped 2026-04-17

Аудит плана выявил 4 оперативных хвоста; все закрыты в одной итерации:

1. **R12 metric gap closed** — декларированная в Phase 5 / Risk R12 метрика
   `ae3_zone_config_auto_reverts_total` теперь реально экспортируется
   Laravel-ом ([SchedulerPrometheusMetricsExporter::renderZoneConfigAutoRevertsCounter](../../backend/laravel/app/Services/AutomationScheduler/SchedulerPrometheusMetricsExporter.php)),
   через audit trail `zone_config_changes` (без отдельной counter-таблицы).
   В [zone-configs.json](../../backend/configs/prod/grafana/dashboards/zone-configs.json)
   добавлены 3 панели: cumulative per zone, 24h rate stat, liveness indicator
   (`STUCK` если live-зоны есть, но rate=0 за 24ч). Feature test
   `SchedulerMetricsControllerTest::test_metrics_endpoint_renders_zone_config_auto_reverts_counter`.

2. **`live_reload.py` dead-code removed** — модуль `ae3lite/config/live_reload.py`
   и соответствующий `test_ae3lite_live_reload.py` удалены. Phase 5.5
   canonical hot-swap path — напрямую через
   `PgZoneSnapshotReadModel().load()` + `resolve_two_tank_runtime_plan()` в
   [base.py._checkpoint](../../backend/services/automation-engine/ae3lite/application/handlers/base.py#L83);
   параллельный `refresh_if_changed` был написан в Phase 5, но никогда не
   включался в production path после Phase 5.5 переписывания. Убран dead import.
   `load_recipe_phase` + `RecipePhase` сохранены в
   [loader.py](../../backend/services/automation-engine/ae3lite/config/loader.py)
   + `config/__init__.py` как публичный canonical API (под тестами).

3. **Doc sync §2.2** — пути Vue-компонентов актуализированы: фактически
   компоненты лежат в `resources/js/Components/ZoneAutomation/`, имена —
   `ConfigModeCard.vue`, `ConfigChangesTimeline.vue`, `RecipePhaseLiveEditCard.vue`,
   `CorrectionLiveEditCard.vue` (не `ConfigModeSwitch.vue`/`ChangesTimeline.vue`
   как планировалось).

4. **7-day cap semantics locked in** — §9 Q3.1 фиксирует поведение "per
   непрерывная live-сессия": `live_started_at` сбрасывается при любом
   live→locked (ручной или auto). Документированное поведение покрыто двумя
   тестами: сохранение при повторном PATCH внутри сессии + reset после locked.
   Alternative (persistent `first_live_started_at`) отвергнут.

## Phase 6.2 Delivered (2026-04-15)

Пользователь запросил **полный fine-tuning live edit** (не только targets, но и correction params — stabilization, retry delays, transport delay, settle time, decision window, PID, observe — всё связанное с коррекцией). Сделано:

**Done:**
- `backend/laravel/app/Http/Controllers/ZoneCorrectionLiveEditController.php` — controller с двумя whitelist'ами:
  - `LIVE_EDITABLE_CORRECTION_PATHS` (~40 путей) — покрывает `base_config.{timing|retry|dosing|safety|tolerance|controllers.{ph,ec}.{pid params, observe, anti_windup, overshoot_guard, no_effect}}`
  - `LIVE_EDITABLE_CALIBRATION_PATHS` — transport_delay_sec, settle_sec, confidence, gain params для `zone.process_calibration.{phase}`
- Route `PUT /api/zones/{zone}/correction/live-edit` с middleware `role:admin,agronomist,engineer` + policy `setLive`
- Invariant: `config_mode=live` обязателен (409 иначе)
- Path traversal: `base_config.*` (без phase) или `phase_overrides.{phase}.*` (с phase)
- Single `bumpAndAudit` на весь запрос (namespace `zone.correction.live`) даже при одновременном patch двух namespaces
- feature coverage для endpoint зафиксирована в `ZoneCorrectionLiveEditControllerTest`

**Delivered:**
1. **Backend path**: `ZoneCorrectionLiveEditController` + route `PUT /api/zones/{zone}/correction/live-edit` остаются canonical endpoint для whitelist-live-edit correction/process calibration.
2. **Frontend `CorrectionLiveEditCard.vue`**: comprehensive card с аккордеонными секциями, target selectors для `base/phase` и `process calibration`, client-side guard для конфликтных комбинаций общего `phase`, один submit → один API call.
3. **Vitest**: добавлены component tests для `CorrectionLiveEditCard`, обновлены mocks `zoneConfigModeApi`.
4. **Integration**: card встроен в `ZoneAutomationTab` и показывается только в `config_mode=live`; timeline теперь умеет фильтровать `zone.correction.live`.
5. **Docs**: синхронизированы `ae3lite.md` §7.5 и `ERROR_CODE_CATALOG.md`.

**Hardening closed 2026-04-16:**
1. Добавлен отдельный AE3 integration test `test_ae3lite_checkpoint_hot_swap_integration.py`, который проверяет реальный hot-reload nested correction/process calibration через `_checkpoint`.
2. Добавлен browser E2E сценарий `13-correction-authority-flows.spec.ts` для `CorrectionLiveEditCard`: live-mode preconditions, combined correction + calibration submit, persistence и timeline.

**Bug fix shipped the same session 2026-04-15 (не связан с Phase 6.2, но обнаружен при тестировании live edit):**
- [automation_task_repository.py:632](../../backend/services/automation-engine/ae3lite/infrastructure/repositories/automation_task_repository.py#L632) — `update_control_mode_snapshot_for_zone` вызывал `asyncpg.exceptions.AmbiguousParameterError: inconsistent types deduced for parameter $2 (text vs character varying)` → Laravel proxy 503. Fix: explicit casts `$2::varchar` для SET + `$2::text = 'auto'` для CASE. 1273 AE tests зелёные после fix'а.

**Phase 7 ops artifacts:**
- Prometheus: `ae3_config_hot_reload_total{result}`, `ae3_shadow_config_validation_total{result,namespace}`, `ae3_zone_config_mode{zone_id}` (gauge 0|1), `ae3_zone_config_live_edits_total{zone_id,handler}`, `ae3_zone_config_invalid_total{zone_id,topology}`
- Grafana: [zone-configs.json](../../backend/configs/prod/grafana/dashboards/zone-configs.json) — модальный распределение, rate hot-reload outcomes, live edits per handler, schema validation failures
- Doc gen: `python3 tools/generate_authority.py` (`--check` mode для CI) — Manual preamble сохраняется между маркерами `<!-- BEGIN:generated-parameters -->` / `<!-- END:... -->`. Wired в `make protocol-check` → CI red при несинхронизированном docs/schemas.

## Shipped feature summary (Phases 5/5.1/5.5/5.6/6/6.1)

**E2E flow config modes locked/live (2026-04-15):**

1. **Agronomist** (или engineer/admin) открывает zone page → Automation tab.
2. Видит `ConfigModeCard` — badge `🔒 Locked` (default) или `✏️ Live tuning` + countdown TTL.
3. Чтобы редактировать config mid-cycle:
   - Переключает `control_mode` → `manual` (через существующий `AutomationControlModeCard`).
   - Кликает `live` в `ConfigModeCard` — dialog с TTL (minutes, 5..10080) и reason.
   - Backend `PATCH /api/zones/{id}/config-mode {mode: "live", ...}` проверяет policy `setLive`, TTL bounds, conflict 409 при `control_mode=auto`, пишет audit row `zone_config_changes{namespace='zone.config_mode'}`.
4. Zone flips в `live` → появляется `RecipePhaseLiveEditCard` (только если активный grow_cycle).
5. Agronomist правит `ph_target`/`ec_target`/... + reason → `PUT /api/grow-cycles/{id}/phase-config`:
   - `GrowCyclePhaseConfigController` validates whitelist (12 safe fields), locks phase row, пишет `forceFill`, вызывает `AutomationConfigCompiler::compileGrowCycleBundle(cycle.id)`, затем `ZoneConfigRevisionService::bumpAndAudit(namespace='recipe.phase', diff=[before/after])`.
   - ИЛИ `PUT /api/automation-configs/zone/{id}/zone.correction` (существующий endpoint) также bump'ает revision через `ZoneConfigRevisionService`.
6. `ChangesTimeline.vue` рендерит новую audit entry (reload на `@changed` event).
7. AE3 на следующем handler.run() в любом из 5 handlers:
   ```python
   new_runtime = await self._checkpoint(task=task, plan=plan, now=now)
   if new_runtime is not plan.runtime:
       plan = replace(plan, runtime=new_runtime)
   runtime = plan.runtime
   ```
   - `_checkpoint` reads `zones.config_revision`, сравнивает с `plan.runtime.config_revision` (integer counter, отличный от `bundle_revision` content hash — см. Phase 5 audit finding #1)
   - **Identity check optimization**: если `_checkpoint` возвращает ту же ссылку что `plan.runtime` (no-change / locked / TTL expired), условие `is not` пропускается, `replace` не вызывается — zero overhead.
   - При advance в live mode → `PgZoneSnapshotReadModel.load()` + `resolve_two_tank_runtime_plan(snapshot)` → new `RuntimePlan` + `model_copy(update={"config_revision": new_revision})` чтобы последующие checkpoints в том же run() не re-trigger'или
   - Эмитит `CONFIG_HOT_RELOADED` zone_event + metric `ae3_config_hot_reload_total{result=applied}` + metric `ae3_zone_config_live_edits_total{zone_id,handler}` + gauge `ae3_zone_config_mode{zone_id}=1`
   - `dataclasses.replace(plan, runtime=new_runtime)` — создаёт новый immutable `CommandPlan` с fresh runtime; все downstream helpers (в correction.py 9 step methods, в base.py `_workflow_ready_reached`/`_targets_reached`) видят обновлённые targets через обычное чтение `plan.runtime` без изменений сигнатур
8. TTL expires → `RevertExpiredLiveModesCommand` (artisan `automation:revert-expired-live-modes`, cron `everyMinute`) — `Zone::lockForUpdate()` + double-check → flip в locked → `CONFIG_MODE_AUTO_REVERTED` event.

**Key safety invariants:**
- `control_mode=auto + config_mode=live` запрещён (409 в controller)
- TTL bounds: 5 min ≤ delta ≤ 7 days; total от первого включения ≤ 7 days
- Policy `setLive`: только agronomist/engineer/admin
- Frozen RuntimePlan + `model_copy(update={...})` — mutation-safe hot-swap
- Race-safe: `bumpAndAudit` использует атомарный `UPDATE ... RETURNING` (unique `(zone_id, revision)` constraint — correctness net), extend/revert — `lockForUpdate` + double-check

**Key files (Phase 5/5.1/5.5/5.6/6/6.1):**
- Laravel migration: `2026_04_15_142400_add_config_mode_to_zones.php`
- Laravel controllers: `ZoneConfigModeController.php`, `GrowCyclePhaseConfigController.php`
- Laravel services: `ZoneConfigRevisionService.php`
- Laravel command: `RevertExpiredLiveModesCommand.php`
- Laravel model: `ZoneConfigChange.php`; `Zone.php` расширен
- Laravel policy: `ZonePolicy::setLive`
- AE3 Python: `ae3lite/config/modes.py`, `ae3lite/config/live_reload.py`, `BaseStageHandler._checkpoint()`
- Vue: `ConfigModeCard.vue`, `ConfigChangesTimeline.vue`, `RecipePhaseLiveEditCard.vue`
- API client: `services/api/zoneConfigMode.ts`

## Phase 1 completion notes (2026-04-15)

**Shipped:**
- 7 JSON Schemas in `schemas/` (draft 2020-12, all validated by `make schemas-validate`):
  `zone_correction.v1.json`, `zone_correction_document.v1.json`, `recipe_phase.v1.json`,
  `zone_pid.v1.json`, `zone_process_calibration.v1.json`, `zone_logic_profile.v1.json`,
  `system_automation_defaults.v1.json`
- Python validator: `tools/validate_schemas.py` + `make schemas-validate` + wired into `make protocol-check`
- Laravel `JsonSchemaValidator` service (opis/json-schema 2.x, supports Draft 2020-12)
- `php artisan zones:validate-configs [--scope] [--namespace] [--json]` command
- Feature test `ValidateZoneConfigsCommandTest` — 4/4 green
- Docker bind mount `../schemas:/schemas:ro` for Laravel container
- Composer dep added: `opis/json-schema:^2.3`
- Python dep bumped: `jsonschema>=4.23.0`
- **PHP catalog patched** to close inventory gaps §9.5/§9.8:
  - `ZoneCorrectionConfigCatalog::defaults()` now includes `dosing.ec_dosing_mode = 'single'`
  - …and `retry.prepare_recirculation_correction_slack_sec = 0`

**Pre-flight finding (dev DB):**
`php artisan zones:validate-configs` on dev stack reports **6 of 9 existing documents invalid**
against new schemas (most missing `ec_dosing_mode`). This is expected — existing seeded
documents predate catalog patch. Before Phase 3 rollout: re-seed dev DB or add a
`automation_config:resync-defaults` artisan command to materialize new fields into existing
zone.correction documents. Decided in Phase 3 Sprint 3.x as acceptance gate.

**Design notes discovered during Phase 1:**
1. `justinrainbow/json-schema` does NOT support Draft 2020-12 (only Draft 3/4/6/7).
   Switched to `opis/json-schema:^2.3`.
2. `ZoneCorrectionConfigCatalog` wraps `zone.correction` document payload as
   `{preset_id, base_config, phase_overrides, resolved_config}` — this required
   a wrapper schema (`zone_correction_document.v1.json`) separate from the base
   correction schema.
3. JSON `{}` vs `[]` ambiguity in PHP: empty PHP array must be explicitly cast
   to `stdClass` or passed as raw JSON string to preserve object semantics.
4. Cross-field constraints (close_zone > dead_zone in zone.pid) not expressible
   in pure JSON Schema — deferred to loader-level validation (Pydantic in Phase 2,
   PHP validator in AutomationConfigRegistry stays as safety net).

## Audit fixes (post Phase 0–2, 2026-04-15)

После аудита фаз 0-2 (см. [AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md](AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md)) применены 8 фиксов:

**CRITICAL (gate Phase 3):**
- **A1** — `Percent` тип в Pydantic исправлен с `gt=0.0` на `ge=0.1` (parity с JSON Schema `minimum: 0.1`).
  [zone_correction.py:24-26](../../backend/services/automation-engine/ae3lite/config/schema/zone_correction.py#L24)
- **A2** — bind mount `../schemas:/schemas:ro` добавлен в 4 compose-файла:
  `docker-compose.ci.yml`, `docker-compose.prod.yml`, `docker-compose.dev.win.yml`,
  `tests/e2e/docker-compose.e2e.yml`. Также добавлен в `automation-engine` сервис dev compose
  (для parity test). Раньше mount был только в `laravel` секции `dev` compose.
- **A3** — re-run loader tests (15/15 green) + `make test-ae` (1150/1150 green).

**MAJOR:**
- **B1** — CI workflow [.github/workflows/protocol-check.yml](../../.github/workflows/protocol-check.yml):
  paths-trigger расширен `schemas/**` и `tools/validate_schemas.py`; добавлен
  step `python3 tools/validate_schemas.py schemas` перед runtime-parity check.
  Pip install обновлён на `jsonschema>=4.23` (было `jsonschema` без version pin).
- **B2** — 5 unit-тестов для `_shadow_validate_correction` в новом файле
  [test_ae3lite_shadow_config_validation.py](../../backend/services/automation-engine/test_ae3lite_shadow_config_validation.py).
  Покрывают: None payload, не-Mapping payload, отсутствующие base/phases, valid path с проверкой
  отсутствия WARNING, broken phase с проверкой WARNING + zone_id + namespace.
- **B3** — automated Pydantic↔JSON-Schema parity test
  [test_ae3lite_pydantic_jsonschema_parity.py](../../backend/services/automation-engine/test_ae3lite_pydantic_jsonschema_parity.py)
  (68 параметризованных проверок: type, bounds, enum). Тест skip-ит себя если schemas/ не
  доступен (graceful — для CI с отдельными compose).
- **B4** — добавлен Pydantic `RecipePhase`
  ([recipe_phase.py](../../backend/services/automation-engine/ae3lite/config/schema/recipe_phase.py))
  + `load_recipe_phase()` в loader. Это разблокирует Phase 5 live-mode hot-reload recipe
  (Q4-coverage). 11 unit-тестов в
  [test_ae3lite_recipe_phase_loader.py](../../backend/services/automation-engine/test_ae3lite_recipe_phase_loader.py).
- **B5** — этот раздел плана.

**Retroactive Phase 2 confirmation:**
Полный `make test-ae` прогон на 2026-04-15 — **1150 unit-тестов AE прошли**. Это закрывает
audit M-5 (incomplete Phase 2 DoD). Phase 2 acceptance валиден.

**Test count after audit fixes:**

| Suite | Count | Status |
|---|---|---|
| `test_ae3lite_config_loader.py` | 15 | green |
| `test_ae3lite_shadow_config_validation.py` (новое, B2) | 5 | green |
| `test_ae3lite_pydantic_jsonschema_parity.py` (новое, B3) | 68 | green |
| `test_ae3lite_recipe_phase_loader.py` (новое, B4) | 11 | green |
| Прочие AE unit-тесты | 1119 | green |
| **Total AE pytest** | **1218** | **green** |
| Laravel `ValidateZoneConfigsCommandTest` | 4 | green |

**MINOR status after full cutover:**
- `m-1` — закрыто: `ec_dosing_mode` добавлен в `ZoneCorrectionConfigCatalog::fieldCatalog()` (UI editor)
- `m-2` — закрыто: `.env.example` содержит `AUTOMATION_SCHEMAS_ROOT`
- `m-3` — закрыто: WARNING логи shadow validation rate-limited (не чаще 1 раза на зону в 60 сек)
- `m-4` — закрыто: runtime-side mapping compat удалён; `RuntimePlan` больше не использует `_DictShim`, runtime readers/tests переведены на attribute/typed access, `CommandPlan.runtime` narrowed до `RuntimePlan | None`. Оставшийся `_DictShim` в `zone_correction.py` — это raw authority-schema compat-слой, не runtime path и не часть этого хвоста.
- `m-5` — закрыто: `$defs/PhaseOverride` и sparse override semantics зафиксированы в authority/data-model docs
- Residual builder fallbacks — закрыто: `runtime_plan_builder.py` больше не подставляет silent defaults для `retry.prepare_recirculation_correction_slack_sec`, `diagnostics_execution.startup.irr_state_wait_timeout_sec` и `dosing.ec_dosing_mode`; runtime fail-closed читает schema-required поля из bundle.

---

## 0. Исходное положение (reality check)

### 0.1 Что УЖЕ есть в системе

Authority-инфраструктура существует **в Laravel**, не в Python:

| Компонент | Файл | LoC |
|---|---|---|
| Registry (18 namespaces) | [AutomationConfigRegistry.php](../../backend/laravel/app/Services/AutomationConfigRegistry.php) | 669 |
| Compiler (system → zone → cycle merge) | [AutomationConfigCompiler.php](../../backend/laravel/app/Services/AutomationConfigCompiler.php) | 425 |
| Defaults catalog (PHP-хардкод) | [ZoneCorrectionConfigCatalog.php](../../backend/laravel/app/Services/ZoneCorrectionConfigCatalog.php) | 557 |
| Таблицы БД | `automation_config_documents`, `automation_config_versions`, `automation_effective_bundles`, `automation_config_violations`, `automation_config_presets` | — |
| REST API | `/api/automation-configs/*`, `/api/automation-bundles/*`, `/api/automation-presets/*` | — |
| Control modes (auto/semi/manual) | [2026_03_09_200000_full_ae3_cutover_and_control_mode.php](../../backend/laravel/database/migrations/2026_03_09_200000_full_ae3_cutover_and_control_mode.php), [set_control_mode.py](../../backend/services/automation-engine/ae3lite/application/use_cases/set_control_mode.py) | — |
| AUTHORITY doc | [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) | 300 |

AE3 — **pure consumer** `automation_effective_bundles`:

| Компонент | Файл | LoC |
|---|---|---|
| Runtime plan builder | [runtime_plan_builder.py](../../backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py) | 1227 |
| Correction handler (biggest) | [correction.py](../../backend/services/automation-engine/ae3lite/application/handlers/correction.py) | 2359 |
| Остальные handlers | `clean_fill`, `solution_fill`, `prepare_recirc`, `irrigation_check`, `startup`, `base` | ~2500 |
| Tests | `test_*.py` | 93 файла |

### 0.2 Реальная проблема: двойной defaulting

Parameter path от создания до исполнения:

```
Laravel:
  ZoneCorrectionConfigCatalog::defaults()  ← PHP hardcoded defaults
  → automation_config_documents.payload     ← оператор override-ит через UI
  → AutomationConfigCompiler                ← мержит system → zone → cycle
  → automation_effective_bundles.config     ← compiled bundle (JSONB)
  → grow_cycles.settings.bundle_revision    ← immutable snapshot at cycle start

AE3 (Python):
  → runtime_plan_builder.resolve_*()        ← ВТОРОЙ уровень resolve
      + _DEFAULT_PREPARE_RECIRC_*          ← Python hardcoded defaults
      + cfg.get(key, default)               ← silent fallbacks
  → plan.runtime dict
  → handler reads dict
      + _STALE_RECHECK_DELAY_SEC=0.25       ← handler-level hardcoded
      + _DEFAULT_SOLUTION_VOLUME_L=100.0    ← planner-level hardcoded
```

**Корень**: AUTHORITY декларирует "один источник", но defaults живут в двух местах:
1. PHP catalog (`ZoneCorrectionConfigCatalog`)
2. Python constants (`_DEFAULT_*`, `cfg.get(key, default)`)

Silent Python fallbacks маскируют отсутствие полей в bundle, AUTHORITY-контракт нарушается незаметно.

### 0.3 Что НЕ является проблемой (не трогать)

- ✅ Bundle-архитектура (system → zone → cycle precedence) — правильная, оставить
- ✅ `automation_effective_bundles` как единственный read-path AE3 — оставить
- ✅ `grow_cycles.settings.bundle_revision` snapshot at cycle start — оставить
- ✅ Control modes (auto/semi/manual) — уже реализованы, только интегрировать с config_mode
- ✅ Laravel compiler pipeline — корректен концептуально
- ✅ pH/EC targets (эффективные) — читаются из recipe phase, не из zone.correction ✓

---

## 1. Цели рефакторинга

1. **Убрать двойной defaulting.** Defaults живут в одном месте (JSON Schema), оба слоя (PHP, Python) читают оттуда.
2. **Fail-closed enforcement в AE3.** Если compiled bundle не содержит required-поле — задача не стартует, loud error.
3. **Удалить silent Python fallbacks.** `_DEFAULT_*` константы и `cfg.get(key, default)` в handler-ах → вон.
4. **Добавить config_mode (locked/live).** Режим `locked` = текущее поведение; `live` = hot-reload bundle на checkpoint-ах.
5. **Frontend switch** для config_mode на zone page, с audit trail и interlock с control_mode.
6. **AUTHORITY.md = generated** из JSON Schema.

### 1.1 Anti-goals (не цели, не делаем)

- ❌ Переписать compile pipeline (Laravel) — рабочий, не трогать
- ❌ Удалить bundle snapshot (`grow_cycles.settings.bundle_revision`) — это фундамент determinism
- ❌ Заменить PHP validator на Pydantic end-to-end — schema-first не требует единого runtime
- ❌ Миграция существующих zone configs — после рефакторинга они должны продолжить работать; "без backward compat" относится к коду, не к данным операторов
- ❌ Большой UI rewrite — добавляем только switch + timeline, editors остаются

---

## 2. Целевая архитектура

### 2.1 Принципы

1. **Один schema-артефакт** (`schemas/zone_correction.v1.json`, JSON Schema 2020-12) — source of truth для обоих языков
2. **Laravel генерит bundle по этой schema** (валидация документов, compile)
3. **AE3 валидирует bundle этой же schema** при claim task → Pydantic model
4. **Handler-ы читают typed model, не dict**
5. **Никаких defaults в Python** — bundle либо полный, либо task не стартует (loud error)
6. **Два режима config_mode**: `locked` (snapshot) / `live` (current bundle + checkpoints)

### 2.2 Целевая структура

```
schemas/                                      # NEW — JSON Schema артефакты
├── zone_correction.v1.json                  # единый source of truth
├── zone_logic_profile.v1.json
├── system_automation_defaults.v1.json
└── ...

backend/services/automation-engine/ae3lite/
├── config/                                   # NEW
│   ├── schema/                              # Pydantic модели (generated из JSON Schema)
│   │   ├── __init__.py
│   │   ├── zone_correction.py
│   │   └── ...
│   ├── loader.py                            # единственная точка: bundle → typed model
│   ├── modes.py                             # ConfigMode enum + rules
│   ├── live_reload.py                       # hot-reload on checkpoints
│   ├── runtime_plan_builder.py              # канонический builder runtime/command plan
│   └── errors.py
│   ├── services/
│   │   ├── workflow_topology.py             # канонический topology graph
│   │   └── ...
│   └── handlers/                            # читают только typed spec
└── runtime/

backend/laravel/app/Services/
├── AutomationConfigRegistry.php             # читает defaults из JSON Schema
├── ZoneCorrectionConfigCatalog.php          # сокращается — defaults переезжают в schema
└── JsonSchemaValidator.php                  # NEW — один валидатор для всех namespaces

backend/laravel/resources/js/
├── Components/ZoneAutomation/               # shipped в Components/ZoneAutomation/, не ZoneConfig/
│   ├── ConfigModeCard.vue                   # Phase 6 (shipped)
│   ├── ConfigChangesTimeline.vue            # Phase 6 (shipped)
│   ├── RecipePhaseLiveEditCard.vue          # Phase 6.1 (shipped)
│   └── CorrectionLiveEditCard.vue           # Phase 6.2 (shipped)
└── schemas/                                 # NEW — JSON Schema копия для frontend
```

### 2.3 Граница config_mode × control_mode

Ортогональные оси. Матрица допустимости:

| control_mode \ config_mode | locked | live |
|---|---|---|
| `auto`   | ✓ | ✗ запрещено (API 409) |
| `semi`   | ✓ | ✓ |
| `manual` | ✓ | ✓ |

- **control_mode** — кто принимает решения (планировщик/оператор)
- **config_mode** — можно ли менять параметры зоны на лету

---

## 3. Executable runbook (фазы)

Каждая фаза = отдельный PR, мерджится независимо, имеет rollback plan.
Executor: я. Ожидаемый темп: 1 фаза = 2-4 дня работы.

### Phase 0 — Discovery & Design Lock (1 день, docs only)

**Цель:** зафиксировать все открытые вопросы, получить ack от пользователя.

**Actions:**
1. Прочитать полностью все три критических файла:
   - [AutomationConfigRegistry.php](../../backend/laravel/app/Services/AutomationConfigRegistry.php) (669 строк)
   - [AutomationConfigCompiler.php](../../backend/laravel/app/Services/AutomationConfigCompiler.php) (425 строк)
   - [runtime_plan_builder.py](../../backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py) (канонический runtime builder после Phase 4)
2. Собрать полный inventory параметров в таблицу `doc_ai/04_BACKEND_CORE/AE3_CONFIG_PARAMETER_INVENTORY.md`:
   - Для каждого параметра: namespace, path, текущий default (PHP), текущий default (Python), где читается (handler:line), required или optional
   - ~100-150 строк таблицы, 2-3 часа работы
3. Ответить на 5 открытых вопросов (раздел 9). Получить ack пользователя.
4. Обновить этот план (AE3_CONFIG_REFACTORING_PLAN.md) с зафиксированными решениями.

**DoD:**
- Inventory table merged
- Open questions closed
- Phase 1 branch готов к старту

**Rollback:** не нужен, docs only.

**Риски:** discovery может выявить параметры, про которые никто не помнит. Если таких >5 — stop and ask.

---

### Phase 1 — Extract JSON Schema (2-3 дня, 1 PR)

**Цель:** вытащить defaults и validation rules из `ZoneCorrectionConfigCatalog::defaults()` + `AutomationConfigRegistry::validate()` в JSON Schema файлы. Пока не подключать — оставить как docs.

**Actions:**
1. Создать каталог `schemas/` в корне проекта. Добавить в `.gitignore`? Нет, коммитить.
2. Написать `schemas/zone_correction.v1.json` (JSON Schema draft 2020-12):
   - Каждое поле из `ZoneCorrectionConfigCatalog::defaults()` → `properties`
   - `required: [...]` для всех бизнес-параметров
   - `additionalProperties: false` на верхнем уровне и в секциях
   - `$defs` для переиспользуемых типов (Seconds, Milliliters, PositiveCount)
   - `default` в JSON Schema для документирования current PHP defaults, но **на stage 1 не использовать для populate**
3. **`schemas/recipe_phase.v1.json`** (новое, по Q4 решению):
   - pH/EC targets (min/target/max), volume_ml, duration
   - Irrigation parameters (mode, interval, duration для timed; decision config для smart_soil_v1)
   - Lighting task parameters
   - Ссылается на active cycle phase payload
4. Добавить `schemas/zone_logic_profile.v1.json` (упрощённо)
5. Добавить `schemas/system_automation_defaults.v1.json`
5. В [requirements.txt](../../backend/services/automation-engine/requirements.txt) добавить `jsonschema>=4.23` и `datamodel-code-generator>=0.26`
6. В [composer.json](../../backend/laravel/composer.json) добавить `opis/json-schema:^2.3`
7. Создать Makefile target `make schemas-validate` — прогоняет все JSON Schemas через meta-schema validator
8. CI-шаг: `make schemas-validate` в `.github/workflows/` или `make protocol-check`
9. **Pre-flight артизан-команда** `php artisan zones:validate-configs` (Q5 решение):
   - Файл: `backend/laravel/app/Console/Commands/ValidateZoneConfigsCommand.php`
   - Флаги: `--scope=zone|system|grow_cycle`, `--fix-preview`, `--json`
   - Итерирует `automation_effective_bundles`, валидирует против новых JSON Schemas
   - Exit 0 при всех valid, 1 при blocking violations
   - Tests: `backend/laravel/tests/Feature/Console/ValidateZoneConfigsCommandTest.php`
   - Пишет counts в Prometheus через `/metrics` Laravel exporter (optional в Phase 1, обязательно в Phase 7)

**DoD:**
- `schemas/*.json` существует и валидно по meta-schema
- `make schemas-validate` зелёный
- Никаких изменений в runtime поведении (просто добавлены файлы)

**Acceptance commands:**
```bash
ls -la schemas/ | grep -c "\.json$"          # should be >= 3
make schemas-validate                         # should exit 0
git diff --stat main..HEAD                   # only new files, no code changes
```

**Rollback:** `git revert` PR целиком, ничего не ломает.

**Риски:** низкие. Самая рискованная часть — правильно выразить complex validation rules (deadband, hysteresis interdependencies) в JSON Schema. Если что-то не выражается — оставить как PHP-only validation на этой стадии, пометить TODO.

---

### Phase 2 — Pydantic schema + AE3 loader (3-4 дня, 1 PR)

**Цель:** AE3 получает typed spec из bundle, в shadow-режиме (параллельно со старым resolve, сравнение в логах).

**Actions:**
1. Сгенерировать Pydantic модели из JSON Schema:
   ```bash
   datamodel-codegen --input schemas/zone_correction.v1.json \
     --output backend/services/automation-engine/ae3lite/config/schema/zone_correction.py \
     --output-model-type pydantic_v2.BaseModel \
     --use-annotated --use-field-description --field-constraints
   ```
   Проверить вручную, подправить типы (Annotated, Literal), добавить `model_config = {"extra": "forbid", "frozen": True}`.
2. Создать `config/loader.py`:
   ```python
   def load_zone_correction(bundle_config: dict, zone_id: int) -> ZoneCorrection:
       try:
           return ZoneCorrection.model_validate(bundle_config)
       except ValidationError as e:
           raise ConfigValidationError(zone_id, e.errors()) from e
   ```
3. Создать `config/errors.py`: `ConfigValidationError`, `ConfigLoaderError`.
4. В `execute_task_use_case.py` добавить **shadow call** рядом с существующим `resolve_two_tank_runtime`:
   ```python
   shadow_spec = None
   try:
       shadow_spec = load_zone_correction(bundle_config, zone_id)
   except ConfigValidationError as e:
       logger.warning("ae3_shadow_config_validation_failed", zone_id=zone_id, errors=e.errors)
   # старый путь продолжает работать как раньше
   runtime = resolve_two_tank_runtime(snapshot)
   ```
5. Метрика Prometheus `ae3_shadow_config_validation_total{result="ok|invalid"}`
6. Тесты `config/test_loader.py`: happy path + 10+ кейсов invalid bundle (missing required, wrong type, extra field).

**DoD:**
- Новые файлы под `config/` существуют, тесты зелёные
- `execute_task_use_case.py` делает shadow-validation без влияния на runtime
- Метрика `ae3_shadow_config_validation_total` видна в Prometheus
- `make test-ae` зелёный

**Acceptance commands:**
```bash
find backend/services/automation-engine/ae3lite/config/ -name "*.py" | wc -l      # >= 5
make test-ae PYTEST_ARGS="-q ae3lite/config/"                                       # pass
make up && sleep 30 && curl -s localhost:9401/metrics | grep ae3_shadow_config     # metric exists
```

**Rollback:** revert PR, shadow-код удаляется, runtime не затронут.

**Риски:**
- datamodel-codegen может сгенерировать некрасивые типы → мягкий риск, правим руками
- Существующие bundles в dev БД могут fail shadow-validation → это ожидаемо на Phase 2, алерт не блокирующий

---

### Phase 3 — Migrate handlers (1 неделя, 3 PR: correction / clean_fill+solution_fill / prepare_recirc+irrigation_check+startup)

**Цель:** handler-ы читают typed spec, не dict. Удаляются `_DEFAULT_*` и hardcoded timings.

**Pre-req:** Phase 2 в shadow-mode работает ≥3 дня на dev без невалидных bundles.

**Actions (на примере correction.py — самый большой и рискованный):**

1. Переключить shadow на primary:
   ```python
   # было:
   runtime = resolve_two_tank_runtime(snapshot)
   # стало:
   spec = load_zone_correction(bundle_config, zone_id)  # raises on invalid
   runtime = resolve_two_tank_runtime(snapshot)          # оставляем, пока handler не переписан
   ```
2. В `CorrectionHandler.__init__` добавить параметр `spec: ZoneCorrection`.
3. Заменить чтения `runtime['correction'][phase]['retry']['telemetry_stale_retry_sec']` → `self._spec.phases[phase].retry.telemetry_stale_retry_sec`.
4. Удалить `_DEFAULT_*` константы в correction.py и correction_planner.py (linter-check).
5. Удалить `cfg.get(key, default)` — заменить на `self._spec.X.Y`.
6. Один handler = один PR:
   - **PR 3.1**: correction.py (~2359 LoC, 10+ методов) — самый рискованный, pair с автором если доступен
   - **PR 3.2**: clean_fill.py + solution_fill.py (~500 LoC)
   - **PR 3.3**: prepare_recirc.py + prepare_recirc_window.py + irrigation_check.py + startup.py + base.py
7. После каждого PR:
   - `make test-ae` зелёный
   - E2E `tests/e2e/scenarios/workflow/` для этого handler зелёные
   - grep проверка: `grep -rn "_DEFAULT_" ae3lite/application/handlers/<handler>.py` → empty

**DoD каждого PR:**
- Handler принимает `spec: ZoneCorrection`
- Нет `_DEFAULT_*` в файле
- Нет `cfg.get(` для config-параметров (whitelist = работа с node telemetry dicts)
- `make test-ae` зелёный
- Релевантный E2E-тест в `tests/e2e/scenarios/workflow/` зелёный

**Acceptance commands для каждого PR:**
```bash
handler=correction  # или другой
grep -rn "_DEFAULT_" backend/services/automation-engine/ae3lite/application/handlers/$handler.py | wc -l  # 0
grep -rn "\.get(" backend/services/automation-engine/ae3lite/application/handlers/$handler.py | grep -vE "(telemetry|node_|response)" | wc -l  # 0
make test-ae PYTEST_ARGS="-q test_${handler}"
```

**Rollback:** revert PR (каждый handler изолирован), остальные не затронуты.

**Риски:**
- correction.py огромный, высокая вероятность пропустить edge case
- Митигация: ДО рефакторинга написать characterization tests — сохранить текущее поведение в тестах, потом рефакторить
- Если характеризационные тесты обнаружат undocumented behavior — stop and ask, не решать самостоятельно

---

### Phase 4 — Delete legacy (2-3 дня, 1 PR)

**Цель:** удалить `two_tank_runtime_spec.py` (1157 строк) и `topology_registry.py`; оставить только новые файлы под `config/`.

**Status:** ✅ completed 2026-04-16

**Shipped artifacts:**
- runtime payload builder moved to [runtime_plan_builder.py](../../backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py)
- workflow topology graph moved to [workflow_topology.py](../../backend/services/automation-engine/ae3lite/application/services/workflow_topology.py)
- legacy test name replaced with [test_ae3lite_workflow_topology.py](../../backend/services/automation-engine/test_ae3lite_workflow_topology.py)
- runtime env moved to [env.py](../../backend/services/automation-engine/ae3lite/runtime/env.py) with `http_client_timeout_sec`
- legacy tests renamed to [test_ae3lite_runtime_plan_builder.py](../../backend/services/automation-engine/test_ae3lite_runtime_plan_builder.py)
- CI gate added in [ae3_config_lint.py](../../tools/ae3_config_lint.py) and wired into `make protocol-check`

**Pre-req:** Phase 3 полностью завершена, handler-ы работают на typed spec.

**Actions:**
1. Если `resolve_two_tank_runtime` всё ещё вызывается где-то (grep) — перенести эту логику в `config/loader.py` как pure dict→dict mapper, либо в domain services.
2. **Удалить** `domain/services/two_tank_runtime_spec.py` целиком.
3. **Удалить** `domain/services/topology_registry.py` (старый).
4. **Удалить** 80+ тестов в `test_ae3lite_two_tank_runtime_spec.py`. Заменить на новые тесты в `config/test_loader.py` с той же coverage (но на typed model, без dict).
5. `runtime/config.py` → переименовать в `runtime/env.py`, очистить от всего не-инфраструктурного.
6. Убрать hardcoded `httpx.AsyncClient(timeout=10.0)` в [bootstrap.py:73](../../backend/services/automation-engine/ae3lite/runtime/bootstrap.py#L73) → `env.http_client_timeout_sec`.
7. Добавить ruff custom rule (или simpler — файл `.ae3-config-lint.py` в CI):
   - Запрет numeric literal > 1 в `application/handlers/**`
   - Whitelist: `# config-literal: <reason>`
8. CI-gate: `make protocol-check` запускает линтер.

**DoD:**
- `two_tank_runtime_spec.py` физически отсутствует
- `topology_registry.py` физически отсутствует
- `runtime/config.py` переименован в `runtime/env.py`
- Линтер в CI проходит
- `make test` зелёный (Python + PHP + frontend unit)

**Acceptance commands:**
```bash
test ! -f backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py
test ! -f backend/services/automation-engine/ae3lite/domain/services/topology_registry.py
test ! -f backend/services/automation-engine/ae3lite/runtime/config.py
test -f backend/services/automation-engine/ae3lite/runtime/env.py
make test-ae
make protocol-check
```

**Rollback:** revert PR. Поскольку Phase 3 уже на typed spec, legacy-файлы просто возвращаются но не вызываются. Сломаются только тесты, которые к ним обращались.

**Риски:**
- 80+ тестов в `test_ae3lite_two_tank_runtime_spec.py` — переписать все = большая работа. Альтернатива: сохранить как golden tests, проверять что новая система даёт тот же результат для тех же inputs (один параметризованный тест поверх всего legacy набора).
- Этот вариант рекомендую.

---

### Phase 5 — Config modes: locked / live (backend) (3-4 дня, 1 PR)

**Цель:** AE3 + Laravel поддерживают два режима.

**Actions:**

**Laravel:**
1. Миграция БД:
   ```php
   Schema::table('zones', function (Blueprint $table) {
       $table->string('config_mode', 16)->default('locked');
       $table->timestamp('config_mode_changed_at')->nullable();
       $table->foreignId('config_mode_changed_by')->nullable()->constrained('users');
       $table->timestamp('live_until')->nullable();            // Q3: TTL auto-revert
       $table->unsignedBigInteger('config_revision')->default(1);
   });
   DB::statement("ALTER TABLE zones ADD CONSTRAINT zones_config_mode_check CHECK (config_mode IN ('locked','live'))");
   DB::statement("ALTER TABLE zones ADD CONSTRAINT zones_live_requires_until CHECK (config_mode = 'locked' OR live_until IS NOT NULL)");
   
   Schema::create('zone_config_changes', function (Blueprint $table) {
       $table->id();
       $table->foreignId('zone_id')->constrained()->cascadeOnDelete();
       $table->unsignedBigInteger('revision');
       $table->string('namespace', 64);                         // Q4: 'zone.correction' | 'recipe.phase'
       $table->jsonb('diff_json');
       $table->foreignId('user_id')->nullable()->constrained('users');
       $table->text('reason')->nullable();
       $table->timestamp('created_at')->useCurrent();
       $table->unique(['zone_id', 'revision']);
       $table->index(['zone_id', 'created_at']);
   });
   ```
2. Контроллер `ZoneConfigModeController`:
   - `PATCH /api/zones/{id}/config-mode`:
     - Body: `{mode: 'locked'|'live', reason: string, live_until?: ISO8601}` (live_until required при переходе в live)
     - Валидация TTL: 5 мин ≤ (live_until - now) ≤ 7 дней
     - 409 при `auto + live` (control_mode conflict)
     - 403 если роль не `agronomist|engineer|admin` (Q2)
   - `PATCH /api/zones/{id}/config-mode/extend`:
     - Body: `{live_until: ISO8601}` — продлить TTL, максимум +7 дней суммарно от первого включения
     - 409 если текущий config_mode='locked'
   - `GET /api/zones/{id}/config-changes` — timeline с фильтром `?namespace=zone.correction|recipe.phase`
3. **Authorization gate** `zone.config_mode.set_live` в `app/Policies/ZonePolicy.php`:
   ```php
   public function setLive(User $user, Zone $zone): bool {
       return $user->hasAnyRole(['agronomist', 'engineer', 'admin']);
   }
   ```
4. При записи config в режиме `live`:
   - **`PUT /api/automation-configs/zone/{id}/zone.correction`** — инкремент revision, запись `zone_config_changes{namespace='zone.correction'}`
   - **`PUT /api/grow-cycles/{id}/phase-config`** (новый endpoint для Q4) — правка активной phase текущего cycle, только в live mode, запись `zone_config_changes{namespace='recipe.phase'}`. Не меняет phase transitions — только параметры активной фазы.
   - Recompile bundle → AE3 читает current bundle на checkpoint (минуя cycle snapshot)
5. **TTL фоновая команда** `app/Console/Commands/RevertExpiredLiveModesCommand.php`:
   ```php
   // artisan automation:revert-expired-live-modes
   // Регистрация в routes/console.php: Schedule::command(...)->everyMinute();
   ```
   - Находит `zones WHERE config_mode='live' AND live_until < NOW()`
   - Переключает в locked, чистит `live_until`
   - Событие `config_mode_auto_reverted` в `zone_events`
   - Метрика `ae3_zone_config_auto_reverts_total`

**AE3 Python:**
1. `config/modes.py`: `class ConfigMode(str, Enum): LOCKED, LIVE`
2. `config/live_reload.py` (расширен по Q4 — покрывает recipe):
   ```python
   @dataclass(frozen=True)
   class HotReloadResult:
       zone_correction: ZoneCorrection | None  # None если без изменений
       recipe_phase: RecipePhase | None        # None если без изменений
       revision: int
   
   async def refresh_if_changed(
       zone_id: int,
       current_revision: int,
       current_cycle_id: int,
       db: Connection,
   ) -> HotReloadResult | None:
       row = await db.fetchrow(
           "SELECT config_revision, config_mode, live_until FROM zones WHERE id = $1",
           zone_id,
       )
       if row["config_mode"] != "live":
           return None
       if row["live_until"] is not None and row["live_until"] < datetime.utcnow():
           # TTL истёк — Laravel cron скоро переключит; AE3 не ждёт
           return None
       if row["config_revision"] <= current_revision:
           return None
       
       # читаем current bundle (минуя cycle snapshot)
       bundle = await _fetch_current_bundle(db, zone_id)
       zone_correction = load_zone_correction(bundle, zone_id)
       
       # читаем current effective recipe phase активного цикла
       recipe_phase = await load_effective_recipe_phase(db, zone_id, current_cycle_id)
       
       return HotReloadResult(
           zone_correction=zone_correction,
           recipe_phase=recipe_phase,
           revision=row["config_revision"],
       )
   ```
3. В BaseStageHandler добавить `async def _checkpoint(self)`:
   ```python
   async def _checkpoint(self) -> None:
       if self._mode != ConfigMode.LIVE:
           return
       result = await live_reload.refresh_if_changed(
           self._zone_id, self._spec_revision, self._cycle_id, self._db,
       )
       if result is None:
           return
       changed = []
       if result.zone_correction is not None:
           self._spec = result.zone_correction
           changed.append("zone.correction")
       if result.recipe_phase is not None:
           self._recipe_phase = result.recipe_phase
           changed.append("recipe.phase")
       self._spec_revision = result.revision
       await self._emit_event(
           "config_hot_reloaded",
           revision=result.revision,
           namespaces=changed,
       )
   ```
4. Вставить `await self._checkpoint()` в definded checkpoint-ы:
   - correction: перед каждой dose attempt (3 места)
   - irrigation_check: перед каждым state probe (1 место)
   - clean_fill / solution_fill: перед каждой level switch проверкой (2 места each)
   - prepare_recirc: перед каждой correction attempt (1 место)
5. События `zone_events`:
   - `config_mode_changed` (at mode switch)
   - `config_live_edit` (on field change в live режиме)
   - `config_hot_reloaded` (on AE3 checkpoint refresh)

**DoD:**
- Миграция применяется: `make migrate` зелёный
- `PATCH /api/zones/{id}/config-mode` работает, 409 при `auto + live`
- Hot-reload на checkpoint виден в логах
- Integration тест: переключение в live → правка конфига → задача подхватывает новые значения на следующем checkpoint
- Никаких изменений поведения в `locked` режиме (default для всех зон)

**Acceptance commands:**
```bash
make migrate
make test                                                                     # PHP + Python
make test-ae PYTEST_ARGS="-q test_config_mode_live_reload"
curl -X PATCH localhost:8080/api/zones/1/config-mode -d '{"mode":"live","reason":"tuning"}' # requires auth, semi/manual control mode
```

**Rollback:** revert PR + `php artisan migrate:rollback --step=1`. Все зоны остаются в locked (default).

**Риски:**
- Race condition при hot-reload посреди команды узлу. Митигация: checkpoints **не** во время `waiting_command` state.
- Пользователь забывает вернуть в locked → **TTL** (решение Q3 уже зафиксировано в разделе 9).

---

### Phase 6 — Frontend UI (3-4 дня, 1 PR, **требует browser testing с участием пользователя**)

**Цель:** switch + timeline + inline edits в live режиме.

**Actions:**
1. `resources/js/Components/ZoneConfig/ConfigModeSwitch.vue`:
   - Badge `🔒 Locked` / `✏️ Live tuning` (+ countdown до `live_until`)
   - Switch, disabled если: `control_mode='auto'` ИЛИ роль не в `agronomist|engineer|admin`
   - Modal подтверждения с reason + TTL picker (presets: 15m, 1h, 4h, 1d, custom ≤ 7d)
   - Кнопка `Extend TTL` в live режиме (если не превышает 7 дней суммарно)
2. `resources/js/Components/ZoneConfig/ChangesTimeline.vue`:
   - Список изменений из `/api/zones/{id}/config-changes?namespace=...`
   - Фильтр по namespace (`zone.correction` / `recipe.phase`), полю, пользователю
   - Polling каждые 30с (Inertia v2 deferred props)
   - Строка `config_mode_auto_reverted` показывается явно (серый фон, значок ⏱)
3. **Live-редактирование активной recipe phase** (по Q4) — новая вкладка/секция на zone page:
   - Видна только в live mode + активный цикл
   - Правит pH/EC targets, volume_ml, duration текущей фазы
   - НЕ правит phase transitions (это остаётся за phase planner)
   - Данные через `GET/PUT /api/grow-cycles/{id}/phase-config`
4. В существующий zone config editor (найти в Phase 0 — возможно [ZoneSchedulerTab.vue](../../backend/laravel/resources/js/Pages/Zones/Tabs/ZoneSchedulerTab.vue)):
   - В `locked` режиме поля read-only
   - В `live` режиме inline edit с debounce, optimistic UI
   - При validation error — откат + toast
5. `resources/js/schemas/zone_correction.v1.json` + `recipe_phase.v1.json` — копии JSON Schema, экспорт на build step
6. Frontend валидация: `ajv` или аналог, загружает schema, валидирует перед отправкой
7. Баннер `ConfigInvalidBanner.vue`: показывается при `config_validation_failed` event
8. Dark mode совместимость (обязательно по CLAUDE.md)
9. **Matrix-индикация** рядом с зональными контролами: состояние `control_mode × config_mode` ("Auto+Locked", "Semi+Live (2h 15m left)")

**DoD:**
- `npm run typecheck` зелёный
- `npm run lint` зелёный
- `npm run test` (Vitest) зелёный
- Playwright E2E: `tests/e2e/specs/zone_config_mode.spec.ts` — переключение режима, live edit, timeline
- **Ручное тестирование в браузере пользователем** (я попрошу проверить golden path)

**Acceptance commands:**
```bash
cd backend/laravel
npm run typecheck && npm run lint && npm run test
npm run e2e -- --grep "zone_config_mode"
```

**Rollback:** revert PR. Поскольку backend Phase 5 остаётся, API работает — просто нет UI.

**Риски:**
- Я **не могу** самостоятельно тестировать UI в браузере. По CLAUDE.md это обязательно. Митигация: по завершении сборки попрошу пользователя открыть zone page и проверить: (1) switch работает, (2) live edit применяется, (3) timeline показывает изменение, (4) dark mode корректен.
- Если пользователь не готов тестировать — Phase 6 не мержится.

---

### Phase 7 — Observability + Generated AUTHORITY.md (2 дня, 1 PR)

**Цель:** Prometheus-метрики, Grafana-панель, AUTHORITY.md генерируется из JSON Schema.

**Actions:**
1. Prometheus метрики (в AE3):
   - `ae3_zone_config_invalid_total{zone_id, topology}` counter
   - `ae3_zone_config_mode{zone_id}` gauge (0=locked, 1=live)
   - `ae3_zone_config_live_edits_total{zone_id, field}` counter
   - `ae3_zone_config_hot_reload_total{zone_id, handler}` counter
2. Grafana panel `configs/dev/grafana/dashboards/zone_configs.json`:
   - Режимы по зонам (pie)
   - Частота live-правок (rate)
   - Validation failures (alert threshold > 0)
3. Скрипт `backend/laravel/artisan authority:generate`:
   - Читает `schemas/*.json`
   - Генерирует markdown таблицы параметров (namespace, path, type, bounds, required, description)
   - Выводит в `doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md`
   - Сохраняет manual preamble (§1-4), генерит только таблицы параметров (§5+)
4. Makefile target `make generate-authority`
5. CI check: `make generate-authority && git diff --exit-code doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md` — если файл изменился без commit-а, CI red

**DoD:**
- Метрики в Prometheus
- Grafana dashboard импортируется
- `make generate-authority` регенерирует AUTHORITY.md без diff
- CI check зелёный

**Rollback:** revert PR. Метрики уходят, AUTHORITY.md остаётся прежней версии.

**Риски:** низкие.

---

## 4. Сводный таймлайн

| Фаза | Длительность | Тип PR | Зависит от |
|---|---|---|---|
| 0: Discovery + parameter inventory | 1-2 дня | docs | — |
| 1: JSON Schema (+ recipe_phase.v1 + pre-flight artisan) | 3-4 дня | code (docs-like + console cmd) | 0 |
| 2: Pydantic + shadow loader (zone.correction + recipe.phase) | 4-5 дней | code, no behavior change | 1 |
| 3.1: correction.py migration | 2-3 дня | code, behavior change | 2 |
| 3.2: clean_fill + solution_fill | 1-2 дня | code, behavior change | 3.1 |
| 3.3: prepare_recirc + irrigation_check + startup | 1-2 дня | code, behavior change | 3.2 |
| 4: Delete legacy | 2-3 дня | code, delete-only | 3.3 |
| 5: Config modes backend (+ TTL cron, recipe live API) | 4-5 дней | migration + code | 4 |
| 6: Config modes UI (+ TTL picker, recipe phase edit) | 4-5 дней | frontend, requires user testing | 5 |
| 7: Observability + AUTHORITY.md gen | 2 дня | obs + docs | 6 |

**Итого:** ~24-33 рабочих дня (5-7 недель при одном исполнителе).

Scope увеличился vs v2 из-за Q4 (recipe coverage) и Q3 (TTL infrastructure): +4-5 дней суммарно.

---

## 5. Risk register

| # | Риск | Вероятность | Импакт | Митигация |
|---|---|---|---|---|
| R1 | correction.py (2359 LoC) скрыто-зависимый | Высокая | Блокер | Characterization tests ДО рефакторинга; pair review |
| R2 | 80+ тестов `test_ae3lite_two_tank_runtime_spec.py` сломаются | Высокая | Delay | Golden-test approach: один параметризованный поверх legacy набора |
| R3 | Existing production zones не проходят schema validation | Средняя | Ops incident | Pre-flight скрипт: валидировать все bundles на dev/staging перед релизом Phase 2 |
| R4 | Live mode race condition при hot-reload в середине команды | Средняя | Данные | Checkpoints только на defined bounds, не во `waiting_command` |
| R5 | Я не могу тестировать UI в браузере | Высокая | Delay | Явно запросить пользователя на Phase 6; без его ack не мержить |
| R6 | PHP compiler и Python loader расходятся в валидации | Средняя | Runtime corruption | JSON Schema = single source, оба слоя читают её напрямую |
| R7 | datamodel-codegen генерит некрасивый код | Средняя | Readability | Ручная доводка после кодогенерации, check-in итог |
| R8 | Пользователь забывает вернуться из live в locked | Средняя | Security | TTL auto-revert (решение Q3) |
| R9 | Control_mode vs config_mode matrix путается в UI | Средняя | UX | Явные тексты interlock-а ("live запрещён в auto mode") |
| R10 | `make test-ae` долгий, тормозит итерации | Низкая | Delay | Фильтры `-k` по handler-name, параллельные pytest worker-ы |
| R11 | Live edit recipe phase конфликтует с auto phase transition | Высокая | Данные | Правка допустима только для **активной** фазы + lock проверки в checkpoint: если фаза переключилась между fetch и write — 409 |
| R12 | TTL cron не работает → live mode вечный | Средняя | Security | Alertmanager rule: `ae3_zone_config_auto_reverts_total` не растёт 24ч при наличии live zones = WARN |
| R13 | Agronomist правит PID параметры без понимания | Средняя | Damage к системе | UI показывает warning на критичных полях (kp, ki, kd, hard_min/max); audit покажет кого вызвать |
| R14 | Два namespace (`zone.correction` + `recipe.phase`) в одном revision → неатомарная правка | Средняя | Consistency | Каждая правка = отдельный revision с namespace; AE3 hot-reload атомарен на стороне checkpoint-а |

---

## 6. Executor-specific constraints

Я — исполнитель, работаю автономно. Важные ограничения:

1. **Не могу запускать браузерные E2E тесты визуально** (Phase 6). Нужен пользователь для manual verification.
2. **Миграции БД** на dev прогоняю через `make migrate`. На production не трогаю вообще.
3. **Docker сборки** запускаю через `make up`, но это долго — не делаю в каждом цикле, только при DoD-check.
4. **Большие файлы** (correction.py 2359 LoC) читаю в несколько Read-запросов с offset, не делаю allocation одним chunk-ом.
5. **AE3 тесты — `make test-ae`** (per memory), не `docker exec pytest` для integration.
6. **Git операции** только по explicit запросу пользователя (CLAUDE.md: только explicit commit-ы, не push, не force).
7. **CLAUDE.md запрет на создание .md без запроса** — этот документ разрешён явно, inventory (Phase 0) тоже разрешаю себе, остальные новые .md — спрашиваю.

**Stop-and-ask points:**
- Phase 0: при обнаружении >5 undocumented параметров
- Phase 1: если сложная validation rule не выражается в JSON Schema
- Phase 3: если characterization tests обнаруживают неожиданное поведение
- Phase 5: при обнаружении race condition в checkpoints
- Phase 6: перед мерджем — ручная верификация пользователя

---

## 7. Success metrics (проверяемые после Phase 7)

| Метрика | Команда проверки | Цель |
|---|---|---|
| Нет `_DEFAULT_*` в handlers | `grep -rn "_DEFAULT_" backend/services/automation-engine/ae3lite/application/ \| wc -l` | 0 |
| Нет silent cfg.get в handlers | `grep -rn "\.get(.*, " backend/services/automation-engine/ae3lite/application/handlers/` (после исключения telemetry) | 0 config-related |
| Legacy файлы удалены | `test ! -f .../two_tank_runtime_spec.py && test ! -f .../topology_registry.py` | true |
| Все zone bundles валидны | Prometheus `ae3_zone_config_invalid_total` | 0 за 7 дней |
| AUTHORITY.md сгенерирован | `make generate-authority && git diff --exit-code` | clean |
| Линтер в CI | `make protocol-check` | exit 0 |
| Тесты зелёные | `make test` | exit 0 |

---

## 8. Rollback strategy

| Фаза | Rollback | Impact на prod |
|---|---|---|
| 0 | revert docs | none |
| 1 | revert files | none |
| 2 | revert shadow code | none (shadow-only) |
| 3.x | revert PR конкретного handler | handler возвращается на legacy spec, другие работают |
| 4 | revert delete PR | legacy файлы возвращаются |
| 5 | revert + migrate:rollback | зоны теряют config_mode column, default locked (совместимо) |
| 6 | revert frontend | UI недоступен, backend API остаётся |
| 7 | revert obs | метрики уходят |

Каждая фаза независимо revert-able. Нельзя rollback-нуть Phase 4 без rollback Phase 3 (но это разумно — они логически связаны).

---

## 9. Зафиксированные решения (locked 2026-04-15)

**Q1: `config_mode` scope — per zone.** Колонка `zones.config_mode`. Переключение режима влияет на все активные циклы зоны.

**Q2: Авторизация live mode — `agronomist` + `engineer` (+ `admin` по умолчанию).**
В Laravel gate `zone.config_mode.set_live` → разрешено ролям `agronomist`, `engineer`, `admin`. Роли `operator`, `viewer` не могут включать live. Переход `live → locked` — любой из разрешённых.

**Q3: TTL auto-revert — да, обязательно.**
Колонка `zones.live_until TIMESTAMPTZ NULL`. При `PATCH /config-mode body.mode=live` обязателен `live_until` (диапазон 5 мин — 7 дней, default 1 час). Фоновая Laravel-команда `automation:revert-expired-live-modes` раз в минуту находит `config_mode='live' AND live_until < NOW()`, переключает в locked, пишет событие `config_mode_auto_reverted`. UI показывает countdown до auto-revert, разрешает extend (но не более 7 дней суммарно от момента включения).

**Q3.1 (уточнено 2026-04-17): семантика 7-дневного cap — per непрерывная live-сессия.**
`live_started_at` сбрасывается при **любом** переходе `live → locked` (ручной revert или auto-revert TTL). Следующая активация `locked → live` начинает новый отсчёт суммарного cap. Мотив: оператор, явно закрывший сессию, получает чистое окно без накопленного долга; защита от "вечного live" обеспечивается непрерывностью проверки + alert-правилом на `ae3_zone_config_auto_reverts_total` (R12). Альтернатива с persistent `first_live_started_at` отвергнута — сложнее UX, нет операционной ценности при наличии R12-мониторинга.
Tests: [ZoneConfigModeControllerTest::test_update_live_keeps_original_live_started_at_when_zone_is_already_live](../../backend/laravel/tests/Feature/ZoneConfigModeControllerTest.php) (continuity) + `test_live_started_at_resets_after_locked_revert` (reset).

**Q4: Live mode покрывает и recipe phase — да.**
Расширяет scope: hot-reload читает не только `zone.correction`, но и effective recipe phase payload для активного цикла. Это влияет на Phase 3/5:
- Schema Phase 1: добавить `schemas/recipe_phase.v1.json` с pH/EC targets, volume_ml, duration
- Loader Phase 2: `load_effective_recipe_phase(cycle_id, zone_id, db) → RecipePhase`
- Checkpoints Phase 5: hot-reload возвращает `(zone_correction, recipe_phase)` tuple
- Constraint: изменение recipe phase в live НЕ меняет саму фазу цикла (переход phase→phase) — только параметры текущей активной фазы. Переключение фаз остаётся за phase planner.
- Audit: `zone_config_changes.diff_json` включает namespace (`zone.correction` / `recipe.phase`)

**Q5: Pre-flight check — `php artisan zones:validate-configs` (принято).**

Мотивация: Phase 3 начинает переключать handlers на strict validation. До мерджа первого handler-PR нужен скрипт, показывающий, **сколько существующих zone bundles не пройдут новую валидацию**. Без этого релиз Phase 3 = stop-the-world на dev/staging/prod.

Предлагаемая команда:

```bash
php artisan zones:validate-configs \
  [--scope=zone|system|grow_cycle] \
  [--fix-preview] \
  [--json]
```

Что делает:
1. Итерирует все `automation_effective_bundles` (или subset по `--scope`)
2. Валидирует `config` против новой JSON Schema (`schemas/zone_correction.v1.json` + `schemas/recipe_phase.v1.json`)
3. Выводит таблицу:
   ```
   zone_id | zone_name | namespace          | path                          | violation
   42      | tomato-1  | zone.correction    | controllers.ph.kp             | required, missing
   43      | lettuce-A | recipe.phase       | targets.ec_target             | type:number, got:null
   ```
4. `--json` — machine-readable для CI
5. `--fix-preview` — показывает, какие значения из `ZoneCorrectionConfigCatalog::defaults()` были бы подставлены (если оператор захочет materialize defaults через UI)
6. Exit code: 0 если все валидны, 1 если есть blocking violations

Когда добавляется: **в Phase 1** (вместе с JSON Schema). Использование:
- Локально после Phase 1 — понять масштаб расхождения
- В CI на staging — blocking gate перед деплоем Phase 3
- На production — ручной пробег перед release, operations решает дорожную карту переконфигурирования

**Альтернативы, которые отбросил:**
- Делать pre-flight частью Phase 2 shadow-режима: shadow работает только для zones с активными задачами, а нам нужно проверить все — неподходит
- Не делать вообще: релиз Phase 3 ломает production — неприемлемо
- Делать как отдельный Python-скрипт в AE3: нужна PHP-сторона, потому что команда должна уметь проверять и system/greenhouse scopes, где живёт Laravel

Решение зафиксировано и включено в actions Phase 1.

---

## 10. Post-completion: новые инварианты

После завершения Phase 7 — для будущих изменений (CLAUDE.md update или отдельный ADR):

1. **Любой новый config-параметр** добавляется сначала в `schemas/*.json`, потом автогенерация Pydantic/PHP validator, потом runtime usage
2. **В handler-ах нельзя** использовать numeric literals > 1 (линтер)
3. **AUTHORITY.md не редактируется вручную** — только через `make generate-authority`
4. **Новая топология** = новый JSON Schema + TopologyDescriptor + handler chain, god-module не нужен
5. **JSON Schema = контракт** между Laravel compiler и AE3 loader; drift невозможен по CI
6. **Config mode switch** — операционный инструмент, только для `semi`/`manual`, логируется всё

---

## 11. Связанные документы (для читателя)

- [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) — текущий AUTHORITY, будет перегенерирован
- [AE3_CONFIG_PARAMETER_INVENTORY.md](AE3_CONFIG_PARAMETER_INVENTORY.md) — inventory параметров, создан в Phase 0
- [ae3lite.md](ae3lite.md) — runtime doc
- [AE_CANONICALIZATION_PLAN.md](AE_CANONICALIZATION_PLAN.md) — предыдущий plan (другой scope)
- [AE3_RUNTIME_EVENT_CONTRACT.md](AE3_RUNTIME_EVENT_CONTRACT.md) — добавить новые `config_*` события в Phase 5
