# План унификации настроек полива и автоматики в Setup Wizard и Start Cycle

**Версия:** 1.0
**Дата:** 2026-04-17
**Автор:** инженерный план, executor-first
**Статус:** draft — требует ack пользователя перед исполнением

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Контекст

Два front-end flow задают одну и ту же подсистему зоны разными формами и payload-shape:

| Flow | Entry | Где сохраняется |
|------|-------|-----------------|
| **Setup Wizard** (6 шагов) | [resources/js/Pages/Setup/Wizard.vue](../../backend/laravel/resources/js/Pages/Setup/Wizard.vue) | `zone.logic_profile`, `zone.pid.{ph,ec}`, pump calibration, sensor calibration |
| **Start Cycle** (7 шагов, modal) | [resources/js/Components/GrowCycle/GrowthCycleWizard.vue](../../backend/laravel/resources/js/Components/GrowCycle/GrowthCycleWizard.vue) | `zone.logic_profile` (re-write), `grow_cycles.*` |

Аудит 2026-04-17 показал ~12 расхождений между flow: асимметричные поля в UI, поля без привязки к API, двойная запись `zone.logic_profile`, неиспользуемые fields в `WaterFormState`, hardcoded defaults для irrigation decision / correction params.

Эталон (ground truth для унификации) — **типизированная `RuntimePlan` Pydantic-модель** после рефакторинга:
- [ae3lite/config/schema/runtime_plan.py](../../backend/services/automation-engine/ae3lite/config/schema/runtime_plan.py) — Pydantic canonical shape
- [schemas/zone_correction.v1.json](../../schemas/zone_correction.v1.json), [schemas/recipe_phase.v1.json](../../schemas/recipe_phase.v1.json), [schemas/zone_logic_profile.v1.json](../../schemas/zone_logic_profile.v1.json), [schemas/zone_process_calibration.v1.json](../../schemas/zone_process_calibration.v1.json)
- [_test_support_runtime_plan.py::make_runtime_plan_dict](../../backend/services/automation-engine/_test_support_runtime_plan.py) — canonical baseline payload для тестов (100+ полей)
- [AUTOMATION_CONFIG_AUTHORITY.md](../04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) — summary authority namespaces

---

## 1. Цели рефакторинга

1. **Единый ground-truth shape** для обоих flow: формы frontend'а генерируют payload, структурно идентичный `RuntimePlan` (с конверсией единиц: минуты↔секунды).
2. **Убрать dead-fields** в `WaterFormState` (поля которые не отправляются в API).
3. **Убрать двойную запись `zone.logic_profile`** — Start-Cycle не должен перетирать Wizard-настройки без явного user intent.
4. **Добавить недостающее в UI**: irrigation decision config, correction retry params, day/night overrides — всё что живёт в `RuntimePlan`, но отсутствует в UI.
5. **Унифицировать device binding** между Setup Wizard и Start-Cycle.
6. **Shared компоненты** вместо дублирования: один Vue-компонент для irrigation settings, один для automation settings, один для pump calibration.

### 1.1 Anti-goals

- ❌ Не менять backend API контракты в этом PR — только frontend-side унификация. Backend изменяется только если обнаружится отсутствующий endpoint (Phase 6).
- ❌ Не добавлять новый Flow C (e.g. «unified wizard»). Сохраняем оба flow, но с shared компонентами.
- ❌ Не трогать Python `RuntimePlan` Pydantic shape — он authority. Подстраиваем frontend, не наоборот.
- ❌ Не объединять Pinia stores двух flow в один (разные жизненные циклы).

---

## 2. Эталон: поля RuntimePlan → UI mapping

| RuntimePlan секция | Поля | Сейчас в UI | Целевое место в UI |
|---|---|---|---|
| `target_{ph,ec}` + `target_{ph,ec}_{min,max}` | pH/EC targets | ✅ readonly из recipe | Keep readonly + **добавить live-edit** через phase_overrides (Phase 6) |
| `target_ec_prepare{,_min,_max}`, `npk_ec_share` | EC для prepare-фазы | ❌ скрыто | Новая «Advanced EC» secция |
| `irrigation_execution` (duration_sec, interval_sec, correction_during_irrigation, correction_slack_sec) | Timing полива | ✅ в WaterForm | Shared `<IrrigationTimingForm/>` |
| `irrigation_decision.strategy` + `irrigation_decision.config` (lookback, min_samples, stale_after_sec, hysteresis_pct, spread_alert_threshold_pct) | Стратегия решения | ⚠️ strategy есть, config hardcoded | Новая `<IrrigationDecisionAdvanced/>` (expandable) |
| `irrigation_recovery` (max_continue_attempts, timeout_sec, auto_replay_after_setup, max_setup_replays) | Recovery | ❌ | Новая `<IrrigationRecoveryForm/>` (expert/engineer only) |
| `irrigation_safety.stop_on_solution_min` | Safety flag | ✅ | Keep, но в shared component |
| `correction` (max_{ph,ec}_correction_attempts, stabilization_sec, telemetry_stale_retry_sec, decision_window_retry_sec, solution_volume_l, max_{ec,ph}_dose_ml) | Correction tuning | ❌ hardcoded | Новая `<CorrectionTuningForm/>` (agronomist/engineer) |
| `correction.controllers.{ph,ec}` (PID: kp/ki/kd, deadband, observe block, anti_windup, overshoot_guard, no_effect) | PID | ✅ в Setup Wizard шаг 5 | Keep, но перенести в shared component |
| `correction.ec_dosing_mode`, `ec_component_ratios`, `ec_component_policy` | Multi-component dosing | ❌ | Новая `<MultiComponentDosing/>` (если multi_parallel) |
| `process_calibrations.{solution_fill,tank_recirc,irrigation,generic}` (ec_gain, ph_gain, transport_delay, settle_sec, confidence) | Pump calibration | ✅ run-time в Setup Wizard | Keep, но shared `<PumpCalibrationCard/>` |
| `prepare_tolerance.{ph_pct,ec_pct}` + `prepare_tolerance_by_phase` | Prepare tolerance | ⚠️ в WaterForm, не шлётся | Fix: либо убрать из формы, либо **отправлять в zone.correction.tolerance** |
| `day_night_enabled` + `day_night_config` (lighting, ph/ec day/night overrides) | Day/night | ❌ Phase 5 TODO | Новая `<DayNightTargetsForm/>` (live-edit через phase-config) |
| `fail_safe_guards` (clean_fill_min_check_delay_ms, estop_debounce_ms, recirculation_stop_on_solution_min и др) | Failsafe | ❌ | Новая `<FailsafeGuardsForm/>` (engineer/admin only) |
| `pid_state.{ph,ec}` | Runtime state | ❌ (не настраивается) | **read-only** в Zone Diagnostics page |
| `soil_moisture_target.{unit,min,max,target}` | Soil moisture | ⚠️ binding есть, target нет | Расширить soil_moisture modal |
| `clean_{min,max}_sensor_labels`, `solution_{min,max}_sensor_labels` | Level switch labels | ⚠️ через device binding | Keep через binding |

**Легенда:** ✅ = в UI; ⚠️ = частично (есть поле, но не шлётся); ❌ = полностью отсутствует.

---

## 3. Executable runbook

Каждая фаза = отдельный PR, независимо revert-able, между фазами прогон `npm run test && npm run typecheck && php artisan test`.

### Phase 1 — Shared form types + canonical payload builder (1 день, 1 PR, low-risk)

**Цель:** зафиксировать единый TypeScript shape для automation-форм, соответствующий `RuntimePlan`.

**Actions:**
1. Создать [resources/js/types/runtimePlan.ts](../../backend/laravel/resources/js/types/runtimePlan.ts) — TypeScript mirror of `RuntimePlan` Pydantic (auto-generatable из JSON Schema через `json-schema-to-typescript`, либо manual).
2. Создать [resources/js/services/automation/runtimePlanPayload.ts](../../backend/laravel/resources/js/services/automation/runtimePlanPayload.ts) с функциями:
   - `fromWaterFormState(form: WaterFormState): Partial<RuntimePlan>` — serializer
   - `toWaterFormState(plan: RuntimePlan): WaterFormState` — deserializer
   - `mergeIntoLogicProfile(plan: Partial<RuntimePlan>, existing: ZoneLogicProfile): ZoneLogicProfile` — non-destructive merge
3. Написать **Vitest** unit-тесты для round-trip: `toWaterFormState(fromWaterFormState(form)) === form` + edge cases.
4. Ничего не менять в существующих компонентах в этом PR — только добавить типы и builder.

**DoD:**
- `npm run typecheck` — green
- `npm run test -- --run runtimePlanPayload` — 20+ кейсов green
- No behavior changes in production code

**Acceptance commands:**
```bash
cd backend/laravel
npm run typecheck
npm run test -- --run runtimePlanPayload
```

**Rollback:** revert PR — ничего не использует новые типы.

**Риски:** 0.

---

### Phase 2 — Dead fields cleanup в WaterFormState (1 день, 1 PR)

**Цель:** удалить поля формы, которые не отправляются в API, или начать их отправлять.

**Находки аудита (что мертво):**
- `WaterFormState.phPct` / `ecPct` — не шлётся (runtime читает из `zone.correction.tolerance`)
- `WaterFormState.irrigationDecisionLookbackSeconds`, `irrigationDecisionMinSamples`, `irrigationDecisionStaleAfterSec`, `hysteresisPct`, `spreadAlertThresholdPct` — заполняются defaults, не редактируются, не шлются
- `WaterFormState.irrigationRecoveryMaxContinueAttempts`, `timeoutSec`, `autoReplayAfterSetup`, `maxSetupReplays` — defaults, dead

**Actions (два варианта, выбрать по консультации с product-owner):**

**Вариант A — удалить dead-fields (рекомендуется для MVP):**
1. Удалить перечисленные поля из `WaterFormState` (type + factory).
2. Удалить `<input>`/`<Field/>` из Vue-компонентов (если были).
3. Обновить `useAutomationDefaults()` — перестать возвращать эти поля.
4. Удалить связанные Vitest unit-тесты.

**Вариант B — начать отправлять (для полноценной UI):**
1. Добавить эти поля в payload → `subsystems.irrigation.decision.config` / `recovery` + `subsystems.irrigation.safety.prepare_tolerance`.
2. Обновить backend `SetupController::storeZoneLogicProfile` / `GrowCycleController::store` чтобы принимать эти поля (см. Phase 5 плана AE3_CONFIG_REFACTORING).
3. Сохранение → recompile bundle → AE3 подхватит.

**Рекомендация:** Вариант A сейчас (быстро), Вариант B вынесено в **Phase 3** (Advanced UI).

**DoD (Вариант A):**
- `grep -rn "phPct\|irrigationDecisionLookback\|irrigationRecovery" backend/laravel/resources/js/` → только в удаляемых местах или `runtime.*` paths
- `npm run test && npm run typecheck` — green
- Backend Laravel tests unchanged

**Rollback:** revert PR.

**Риски:** низкие. Митигация: проверить через `git log --all --source -- <file>` не использовал ли кто-то эти поля в другой ветке.

---

### Phase 3 — Advanced Irrigation panel (irrigation_decision config + recovery) (2 дня, 1 PR)

**Цель:** добавить UI для irrigation decision config + recovery params, которые сейчас hardcoded в backend defaults.

**Актуально только для Вариант B из Phase 2 или как отдельное расширение.**

**Actions:**
1. Создать [Components/AutomationForms/IrrigationDecisionAdvanced.vue](../../backend/laravel/resources/js/Components/AutomationForms/IrrigationDecisionAdvanced.vue):
   - Collapsible panel «Advanced: Decision tuning»
   - Визуально разделён по strategy (если strategy='task' — скрыть config, если smart_soil_v1 — показать lookback/min_samples/hysteresis)
   - Inputs с min/max hints из JSON Schema (через `v-model` → TypeScript validation)
2. Создать [Components/AutomationForms/IrrigationRecoveryAdvanced.vue](../../backend/laravel/resources/js/Components/AutomationForms/IrrigationRecoveryAdvanced.vue):
   - Engineer/admin role gate (через `useRole()`)
   - max_continue_attempts, timeout_sec, auto_replay_after_setup, max_setup_replays
3. Встроить оба компонента в:
   - [Pages/Setup/Wizard.vue](../../backend/laravel/resources/js/Pages/Setup/Wizard.vue) шаг 4 — в секции water
   - [Components/GrowCycle/WizardAutomationStep.vue](../../backend/laravel/resources/js/Components/GrowCycle/WizardAutomationStep.vue) — в water секции
4. Backend: убедиться что `SetupController::applyDeviceBindings` + `GrowCycleController::store` принимают и сохраняют `subsystems.irrigation.decision.config` / `recovery`.
5. Vitest unit тесты: render / collapse / v-model round-trip.
6. Playwright e2e scenario: open wizard → expand Advanced → change lookback → save → verify in API response.

**DoD:**
- `/api/automation-configs/zone/{id}/zone.logic_profile` payload содержит `subsystems.irrigation.decision.config` после save в Wizard
- Runtime plan (через `make_runtime_plan(irrigation_decision={...})`) принимает те же поля
- Vitest 10+ тестов green
- Playwright e2e scenario green

**Rollback:** revert PR. Сохранённые advanced-params остаются в БД, читаются старым кодом как defaults.

**Риски:**
- Средний: операторы могут поменять params без понимания — митигация через role-gate (engineer+) и warning tooltip.

---

### Phase 4 — Unified CorrectionTuningForm (2-3 дня, 1 PR)

**Цель:** вывести в UI поля `zone.correction`, которые сейчас полностью hardcoded в backend defaults.

**Scope:** max_{ph,ec}_correction_attempts, stabilization_sec, telemetry_stale_retry_sec, decision_window_retry_sec, low_water_retry_sec, solution_volume_l, max_{ec,ph}_dose_ml + PID controllers block (kp/ki/kd/deadband/observe/anti_windup/overshoot_guard/no_effect).

**Actions:**
1. Создать [Components/AutomationForms/CorrectionTuningForm.vue](../../backend/laravel/resources/js/Components/AutomationForms/CorrectionTuningForm.vue):
   - Три секции: «Retry & timing», «pH controller», «EC controller»
   - Привязка к `zone.correction.base_config` (а не к `zone.logic_profile`)
   - Предустановки через `automation_config_presets` (уже есть в backend)
2. Заменить существующий PID-блок из [ZoneCorrectionCalibrationStack.vue](../../backend/laravel/resources/js/Components/ZoneAutomation/ZoneCorrectionCalibrationStack.vue) на этот shared component (или wrap).
3. Добавить form в Setup Wizard шаг 5 (после калибровки) и доступ через zone edit page.
4. **Не добавлять в Start-Cycle** — в Start-Cycle форма только read-only summary (agronomist не редактирует correction на запуске).
5. API: использовать существующий [PUT /api/automation-configs/zone/{id}/zone.correction](../../backend/laravel/app/Http/Controllers/AutomationConfigController.php) (уже реализован).
6. Vitest + Playwright тесты.

**DoD:**
- zone edit page показывает Correction Tuning form
- Сохранение → `zone.correction` document bumped → AE3 `_checkpoint` подхватывает (Phase 5 refactoring plan)
- Role gate: form visible для agronomist/engineer/admin, read-only для operator/viewer

**Rollback:** revert PR; все saved correction tunings остаются в БД.

**Риски:**
- Operator может накрутить kp/ki до нереалистичных значений — митигация: input range validation + explicit confirmation modal для critical params (kp, ki, kd, hard_min, hard_max).

---

### Phase 5 — Non-destructive `zone.logic_profile` merge в Start-Cycle (1 день, 1 PR)

**Цель:** устранить баг «Start-Cycle перетирает Wizard-настройки».

**Текущее поведение:** [useGrowthCycleWizard::persistLaunchPrerequisites](../../backend/laravel/resources/js/composables/useGrowthCycleWizard.ts) делает `PUT /api/automation-configs/zone/{id}/zone.logic_profile` с полным payload `{ active_mode, profiles: { setup: {...} } }`. Если Setup Wizard до этого установил поле X, которое сейчас не показано в Start-Cycle UI — оно стирается.

**Actions:**
1. В `persistLaunchPrerequisites` перед PUT сделать GET текущего `zone.logic_profile`.
2. Использовать `mergeIntoLogicProfile()` из Phase 1 — deep merge Start-Cycle overrides в существующий payload вместо replace.
3. Backend: убедиться что endpoint принимает partial payload (сейчас он accept full — возможно надо расширить validator для patch-mode).
4. Если backend не поддерживает patch — добавить flag `?mode=merge` в endpoint (или new route `PATCH /api/automation-configs/zone/{id}/zone.logic_profile`).
5. Vitest unit-тест для `mergeIntoLogicProfile`: проверить что non-overlapping поля сохраняются.
6. Playwright e2e: Setup Wizard → save → Start-Cycle → save → verify Setup Wizard settings сохранились.

**DoD:**
- Start-Cycle PUT не теряет поля, не редактируемые в Start-Cycle UI
- 10+ unit-тестов merge-поведения
- e2e scenario green

**Rollback:** revert PR; Start-Cycle возвращается к replace behavior.

**Риски:** низкие. Митигация: feature flag `ENABLE_LOGIC_PROFILE_MERGE` для быстрого отката в production.

---

### Phase 6 — Phase overrides в Start-Cycle (live-edit recipe targets) (2 дня, 1 PR)

**Цель:** разрешить оператору override pH/EC/irrigation targets из рецепта **при запуске конкретного цикла**, не меняя сам рецепт.

**Контекст:** сейчас recipe phase targets readonly в UI обоих flow. [AE3_CONFIG_REFACTORING_PLAN Phase 5.6](../04_BACKEND_CORE/AE3_CONFIG_REFACTORING_PLAN.md) реализовал backend endpoint `PUT /api/grow-cycles/{id}/phase-config` для live-edit, но UI не использует его для **запуска**.

**Actions:**
1. В [WizardAutomationStep.vue](../../backend/laravel/resources/js/Components/GrowCycle/WizardAutomationStep.vue) добавить toggle «Override recipe targets for this cycle».
2. Toggle ON → unlock pH/EC/irrigation_duration/interval поля (с показом recipe defaults как placeholder).
3. На submit (после POST grow-cycle) — если были overrides → PUT /api/grow-cycles/{id}/phase-config с `{ base_config: { target_ph, target_ec, irrigation_duration_sec, ... }, phase: null }`.
4. UI показывает badge «Cycle customised — based on Recipe v{revision}» после запуска.
5. Reuse [RecipePhaseLiveEditCard.vue](../../backend/laravel/resources/js/Components/ZoneAutomation/RecipePhaseLiveEditCard.vue) подкомпонентом (он уже умеет live-edit через тот же endpoint).
6. Vitest + Playwright тесты.

**DoD:**
- Start-Cycle с overrides → создаёт cycle + phase-config bump → AE3 читает overrides
- Recipe не меняется (проверить что `recipes.payload.phases[0].ph_target` не затронут)
- Audit trail: `zone_config_changes` содержит namespace `recipe.phase` для override

**Rollback:** revert PR; override-toggle пропадает, recipe values используются как есть.

**Риски:**
- Operator может накрутить нереалистичные targets — митигация: валидация ranges из `schemas/recipe_phase.v1.json` на стороне frontend + backend.

---

### Phase 7 — Shared компоненты вместо дубликатов (2 дня, 1 PR)

**Цель:** убрать дубликаты Vue-компонентов между Setup Wizard и Start-Cycle.

**Дубликаты (находки аудита):**
- Setup Wizard `ZoneAutomationProfileSections.vue` vs Start-Cycle `WizardAutomationStep.vue` — частично дублируют irrigation/lighting/climate forms
- `useSetupWizard::loadAutomationProfile` vs `useGrowthCycleWizard::loadAutomationProfile` — ~50 строк дублированной логики
- Два места `syncFormsFromRecipePhase` в разных файлах

**Actions:**
1. Создать [composables/useAutomationProfileLoader.ts](../../backend/laravel/resources/js/composables/useAutomationProfileLoader.ts) — shared logic: `loadAutomationProfile`, `syncFormsFromRecipePhase`, `buildGrowthCycleConfigPayload` (если не все уже shared).
2. Обновить `useSetupWizard` и `useGrowthCycleWizard` на использование этого composable.
3. Создать [Components/Shared/AutomationForm/](../../backend/laravel/resources/js/Components/Shared/AutomationForm/) с подкомпонентами:
   - `<IrrigationTimingForm/>` (duration/interval/correction_during_irrigation)
   - `<IrrigationDecisionBasic/>` (strategy selector)
   - `<ClimateTargetsForm/>` (temp/humidity/co2)
   - `<LightingScheduleForm/>` (day_start_time/photoperiod)
4. Заменить существующие inline-формы на shared.
5. Visual regression tests через Playwright snapshot comparison.

**DoD:**
- `grep -c "loadAutomationProfile\b" backend/laravel/resources/js/composables/` = 1 (только shared)
- Setup Wizard и Start-Cycle визуально идентичны в секциях irrigation/lighting (через shared components)
- Bundle size delta ≤ +5 KB
- `npm run test` all green (включая 80+ wizard unit-тестов)

**Rollback:** revert PR; inline formss возвращаются.

**Риски:**
- Regression в Setup Wizard, если новый shared component ведёт себя иначе. Митигация: characterization tests (snapshot JSON of payload) до рефакторинга, после — сравнение.

---

### Phase 8 — Device binding unification (1-2 дня, 1 PR)

**Цель:** унифицировать flow привязки устройств (pump channels, soil moisture sensor).

**Текущая асимметрия:**
- Setup Wizard шаг 4: explicit binding через `ZoneAutomationProfileSections` (pump_a/pump_base/pump_acid + soil_moisture_sensor)
- Start-Cycle шаг 5: implicit binding soil_moisture через отдельный modal, pump channels не переcпрашиваются

**Actions:**
1. Выбрать canonical flow — рекомендую Setup Wizard explicit (validates readiness заранее).
2. В Start-Cycle — перед submit запустить readiness check: если какой-то role binding missing → блокировать запуск и отправить user в zone edit page (или inline fix).
3. Удалить отдельный soil_moisture modal в Start-Cycle; объединить с device binding в общем `<DeviceBindingsReview/>` компоненте (read-only в Start-Cycle, edit в Setup Wizard).
4. Vitest тесты на missing-binding scenarios.

**DoD:**
- Start-Cycle не позволяет submit при missing pump channels (readiness error)
- Shared `<DeviceBindingsReview/>` используется в обоих flow
- Тесты + e2e

**Rollback:** revert PR.

**Риски:** medium — meняет user flow. Митигация: user-testing с пользователем (agronomist role) перед merge.

---

## 4. Таймлайн

| Фаза | Длительность | Риск | Зависит |
|------|--------------|------|---------|
| 1: Shared types + payload builder | 1 день | none | — |
| 2: Dead fields cleanup | 1 день | low | 1 |
| 3: Advanced Irrigation panel | 2 дня | medium | 1, 2 |
| 4: Unified CorrectionTuningForm | 2-3 дня | medium | 1 |
| 5: Non-destructive merge | 1 день | low | 1 |
| 6: Phase overrides в Start-Cycle | 2 дня | medium | 1, 5 |
| 7: Shared components | 2 дня | medium | 1, 3, 4 |
| 8: Device binding unification | 1-2 дня | medium | 7 |

**Итого:** ~12-14 дней на одного executor'а. Возможна параллелизация Phase 3/4 после Phase 1-2.

---

## 5. Risk register

| # | Риск | Вероятность | Импакт | Митигация |
|---|------|------------|--------|-----------|
| R1 | Dead fields удаляются, но какой-то e2e тест их использует | средняя | test breakage | Phase 2 acceptance: `grep` + full test suite |
| R2 | Advanced Irrigation UI сбивает operators без engineer-контекста | высокая | UX degradation | Role-gate + warning tooltip + defaults reset button |
| R3 | `zone.logic_profile` merge теряет поля (merge bug) | средняя | data loss | 10+ unit-тестов + Playwright e2e + feature flag |
| R4 | Phase overrides запутывают agronomist (override vs recipe update) | средняя | UX confusion | Explicit badge «customised for this cycle» + training |
| R5 | Shared components ломают Setup Wizard снимки | средняя | regression | Characterization tests перед рефакторингом |
| R6 | Backend не поддерживает partial payload (Phase 5) | низкая | blocker | Pre-check в Phase 1: проверить validator, расширить если надо |
| R7 | Pinia store зоны и цикла конфликтуют при shared composable | средняя | state corruption | Инварианты unit-тестов: store изоляция |
| R8 | Correction tuning form выставляет params, ломающие production zone | высокая | damage | Confirmation modal + audit trail (уже есть через `zone_config_changes`) |

---

## 6. Executor-specific

1. **Фронт-тесты:** `npm run test` (Vitest) + `npm run typecheck` + `npm run lint` перед каждым PR. Full Laravel feature suite — только если API контракт менялся.
2. **Playwright e2e:** запускаю `npm run e2e -- --grep="<scenario>"` для релевантного сценария каждого PR. Полный e2e — только Phase 4 и 8 (UX-critical).
3. **Dark mode:** каждый новый компонент должен поддерживать dark mode (проверка вручную через browser toggle).
4. **Browser testing:** Phase 3, 4, 6, 7, 8 требуют ручной верификации пользователем (по CLAUDE.md). Буду останавливаться и запрашивать.
5. **Pinia store:** не создавать новые stores; использовать существующие `useZoneStore`, `useGrowCycleStore`.
6. **TypeScript strict mode:** все новые файлы должны пройти strict typecheck.

**Stop-and-ask points:**
- Phase 2: перед выбором между Variant A / B (удалить vs отправлять dead fields)
- Phase 3: если irrigation_decision.config значения существующих zones в dev DB разойдутся с schema bounds — stop.
- Phase 4: перед merge — ручной тест critical PID ranges пользователем.
- Phase 6: перед merge — ручной тест override flow пользователем.
- Phase 8: перед merge — UX review пользователем (user flow изменение).

---

## 7. Success metrics

| Метрика | Команда / проверка | Цель |
|---------|-------------------|------|
| Dead fields в WaterFormState | `grep -c "phPct\|irrigationDecisionLookback\|irrigationRecovery" WaterFormState` | 0 |
| Shared composable usage | `grep -c "useAutomationProfileLoader" composables/` | 2 (Setup+Cycle) |
| Дубликаты inline-форм | manual audit irrigation forms | 0 (все через shared) |
| Advanced UI availability | Playwright `test('advanced panel expandable')` | pass |
| Non-destructive merge | Playwright: set field A in Setup Wizard, set field B in Start-Cycle, verify A kept | pass |
| Phase overrides round-trip | Playwright: create cycle with override, verify recipe unchanged | pass |
| TypeScript strict | `npm run typecheck` | exit 0 |
| Vitest coverage на automation payload builder | `npm run test:coverage -- runtimePlanPayload` | ≥ 85% |

---

## 8. Rollback strategy

| Фаза | Rollback | Impact |
|------|---------|--------|
| 1 | revert PR | none |
| 2 | revert PR | dead fields возвращаются, UI немного раздутая, но работает |
| 3 | revert PR | advanced params сохранённые в БД остаются — читаются runtime как есть, UI скрывает |
| 4 | revert PR | correction tuning form пропадает из zone edit; users возвращаются к hardcoded defaults |
| 5 | revert PR | Start-Cycle replace-behavior возвращается, возможна потеря Wizard-настроек |
| 6 | revert PR | Start-Cycle без override-toggle; пользователи редактируют через Zone→Automation tab live-edit card |
| 7 | revert PR | inline-формы возвращаются, дубликаты |
| 8 | revert PR | device binding flow асимметричен |

Каждая фаза independent. Phase 1 — foundation, revert единственной верхней фазы не ломает нижестоящие. Merge в порядке 1 → 2 → 3/4/5 (параллельно) → 6 → 7 → 8.

---

## 9. Post-completion invariants

После Phase 8 зафиксировать в CLAUDE.md / AGENTS.md:

1. **Любое новое automation-поле** в UI добавляется сначала в `runtimePlan.ts` (TypeScript type) — потом компонент.
2. **Shared Vue components** в `Components/Shared/AutomationForm/` используются в Setup Wizard и Start-Cycle; inline-формы запрещены.
3. **Start-Cycle не заменяет `zone.logic_profile` полностью** — только merge-mode.
4. **Phase overrides для cycles** — через `PUT /api/grow-cycles/{id}/phase-config`, не через zone.correction.
5. **Advanced settings (decision config, recovery, correction tuning)** доступны только engineer/admin/agronomist ролям.

---

## 10. Связанные документы

- [AE3_CONFIG_REFACTORING_PLAN.md](../04_BACKEND_CORE/AE3_CONFIG_REFACTORING_PLAN.md) — base backend refactoring (Phase 5-7 — live edit infrastructure, которую переиспользует Phase 6 здесь)
- [AUTOMATION_CONFIG_AUTHORITY.md](../04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) — config authority
- [AE_LEGACY_CLEANUP_PLAN.md](../04_BACKEND_CORE/AE_LEGACY_CLEANUP_PLAN.md) — backend cleanup (Phase 3 correction.py `.get()` затрагивает те же секции)
- [FRONTEND_ARCH_FULL.md](FRONTEND_ARCH_FULL.md) — frontend архитектура
- [FRONTEND_UI_UX_SPEC.md](FRONTEND_UI_UX_SPEC.md) — UI/UX guidelines
- [ROLE_BASED_UI_SPEC.md](ROLE_BASED_UI_SPEC.md) — role gates для advanced forms
- [EFFECTIVE_TARGETS_SPEC.md](../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md) — spec контроллеров, задаёт границы overrides
