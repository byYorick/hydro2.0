# План унификации мастера запуска: `<GrowCycleLauncher>` как single flow

**Версия:** 2.0
**Дата:** 2026-04-19
**Статус:** DONE — все 6 фаз реализованы 2026-04-19
**Подход:** архитектурный rewrite, не iterative patching

## Результат

| Метрика | Цель | Факт |
|---------|------|------|
| Удалить legacy wizard code | ≥ 5 000 строк | **≈ 22 500 строк** (23 173 − 648 diff документа) |
| Новый добавленный код (prod) | ≤ 2 500 строк | 2 505 строк (controllers/services/vue/composables) |
| Новые тесты | ≥ 30 кейсов | 56 кейсов (45 vitest + 11 phpunit) — все green |
| TypeScript strict | pass | `vue-tsc --noEmit` — 0 ошибок |
| Полный vitest run | 0 регрессий | 139 файлов / 1 223 теста — все green |
| PHPUnit LaunchFlowManifestControllerTest | 11/11 pass | ✅ |
| Single entry point | `/launch/:zoneId?` | ✅ — Setup Wizard / GrowthCycleWizard удалены |

## Ключевые созданные артефакты

### Frontend
- [resources/js/schemas/growCycleLaunch.ts](../../backend/laravel/resources/js/schemas/growCycleLaunch.ts) — Zod single-source-of-truth
- [resources/js/composables/useFormSchema.ts](../../backend/laravel/resources/js/composables/useFormSchema.ts) — reactive Zod integration
- [resources/js/Components/Launch/Shell/](../../backend/laravel/resources/js/Components/Launch/Shell/) — embedded shell (`LaunchShell`, topbar, stepper, footer) внутри `AppLayout`
- [resources/js/Pages/Launch/Index.vue](../../backend/laravel/resources/js/Pages/Launch/Index.vue) — `<GrowCycleLauncher>` entry
- [resources/js/Components/Launch/](../../backend/laravel/resources/js/Components/Launch/) — Zone/Recipe/Automation/Calibration/Preview step components + `<DiffPreview/>`
- [resources/js/services/queries/launchFlow.ts](../../backend/laravel/resources/js/services/queries/launchFlow.ts) — TanStack Query bindings

### Backend
- [app/Http/Controllers/LaunchFlow/LaunchFlowManifestController.php](../../backend/laravel/app/Http/Controllers/LaunchFlow/LaunchFlowManifestController.php)
- [app/Services/LaunchFlow/LaunchFlowManifestBuilder.php](../../backend/laravel/app/Services/LaunchFlow/LaunchFlowManifestBuilder.php)
- [app/Services/LaunchFlow/LaunchFlowReadinessEnricher.php](../../backend/laravel/app/Services/LaunchFlow/LaunchFlowReadinessEnricher.php) — blocker → action.route mapping
- [routes/api.php](../../backend/laravel/routes/api.php) — `GET /api/launch-flow/manifest`
- [routes/web.php](../../backend/laravel/routes/web.php) — `/launch/{zoneId?}` + 301 редиректы с `/setup/wizard` и `/grow-cycle-wizard`

### Удалено (Phase 6)
- `resources/js/Pages/Setup/` (Wizard.vue 1 135 строк + тесты)
- `resources/js/Pages/GrowCycles/Wizard.vue`
- `resources/js/Components/GrowCycle/GrowthCycleWizard.vue` + `steps/*`
- `resources/js/composables/useSetupWizard.ts` (1 177 строк)
- `resources/js/composables/useGrowthCycleWizard.ts` (1 511 строк)
- 14 `setupWizard*.ts` composables + `growthCycleWizardHelpers.ts` + `useWizardState/useWizardValidation`
- Все unit-тесты старых wizard'ов
- `resources/js/services/automation/recipePhaseSync.ts` (orphan после удаления wizard'ов)



Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми формами `Pages/Setup/Wizard.vue` и `Components/GrowCycle/GrowthCycleWizard.vue` не требуется — оба wizard'а удаляются после миграции.

---

## 0. Почему rewrite, не iterative fix

Версия 1.0 плана (8 phases iterative patching) базировалась на допущении **«сохранить оба flow с shared компонентами»**. Аудит 2026-04-18 (см. раздел 1 ниже) показал:

| Симптом | Причина |
|---|---|
| 2 688 строк composable логики (`useSetupWizard` 1177 + `useGrowthCycleWizard` 1511) | Параллельные state-machines для одного домена |
| 40-50% дубля между wizard'ами | Общий домен разложен на два разных UI без shared primitive |
| 12 вложенных `watch()` в GrowCycle | Ручная синхронизация form ↔ recipe ↔ zone ↔ automation |
| Phase 5 data-loss bug (replace вместо merge в `updateDocument()`) | Нет единой точки записи `zone.logic_profile` |
| 5+ dead fields в `WaterFormState` | Параллельные формы расходятся по содержимому, backend не принимает часть полей |
| Readiness errors cryptic (`process_calibration_generic`) | Нет структурированного error → action mapping |

Iterative patching 8 phases не устраняет **корневую причину** (два state-machine для одного домена) — только симптомы. Через 6 месяцев flow разойдутся снова.

**Новый подход:** один unified `<GrowCycleLauncher>`, backend-driven steps, schema-validated state, preview-before-submit.

---

## 1. Цели рефакторинга

1. **Один flow** — `<GrowCycleLauncher>` вместо `Setup Wizard` + `GrowthCycleWizard`. Entry point один (`/launch/:zoneId?`); шаги condition-based (если zone отсутствует — показываем шаги установки, иначе скрыты).
2. **Backend-driven steps manifest** — список шагов, валидация, can-proceed вычисляет backend (`GET /api/launch-flow/manifest`). Добавление нового шага = backend-only change.
3. **Schema-first state** — Zod/Valibot schema `growCycleLaunch.ts` как single source of truth. TypeScript type inferred. Runtime validation. Payload serialisation через `schema.parse()`. Dead fields физически невозможны.
4. **TanStack Query** вместо `Pinia store` + 12 вложенных `watch()`. Кеш per zone/recipe, auto-refetch on mutation, out-of-box loading/error state.
5. **Diff-preview before commit** — перед POST `/zones/{id}/grow-cycles` показывать side-by-side diff текущего `zone.logic_profile` и нового. Фиксит data-loss bug by design: user подтверждает конкретные изменения.
6. **Actionable readiness errors** — структурированный ответ `{code, message, action}` с clickable action items ("Выполните калибровку pH-насоса" → прямой переход).
7. **Embedded `LaunchShell` вместо full-screen flow** — progress/navigation/validation-display живут в launch shell внутри `AppLayout`, чтобы сохранять navigation, command palette, toast/error boundary и рабочий контекст оператора.

### 1.1 Anti-goals

- ❌ **Не сохранять** `Pages/Setup/Wizard.vue` и `Components/GrowCycle/GrowthCycleWizard.vue` после миграции — удаляются в Phase 6.
- ❌ **Не мигрировать** 2 688 строк composable логики — переписываем с нуля, используя schema + query.
- ❌ **Не добавлять** feature flags для параллельного сосуществования на production — проект в активной разработке, coord переключается в одном PR.
- ❌ **Не использовать** Pinia для ephemeral wizard state (TanStack Query + local `ref`). Pinia остаётся для `useZoneStore` / `useAlertsStore` (multi-page state).

---

## 2. Архитектура нового flow

### 2.1 High-level

```
┌────────────────────────────────────────────────────────────────┐
│ /launch/:zoneId?                  (single entry for any launch) │
│                                                                │
│ ┌──────────────────┐  ┌────────────────────────────────────┐   │
│ │ <AppLayout>      │  │ Backend manifest loader            │   │
│ │  └<LaunchShell>  │←─│ GET /api/launch-flow/manifest       │   │
│ │ (stepper, nav,   │  │  ?zone_id=5                         │   │
│ │  blocker footer) │  │ → [step{id, validation, required}]  │   │
│ └──────────────────┘  └────────────────────────────────────┘   │
│         │                       │                              │
│         ↓                       ↓                              │
│ ┌─────────────────────────────────────────────────────┐        │
│ │ Step components (rendered inside <LaunchShell>)     │        │
│ │  <ZoneStep/> <RecipeStep/> <AutomationStep/>        │        │
│ │  <CalibrationStep/> <PreviewStep/>                  │        │
│ └─────────────────────────────────────────────────────┘        │
│         │                                                      │
│         ↓                                                      │
│ ┌─────────────────────────────────────────────────────┐        │
│ │ Zod schema `growCycleLaunch.ts`                     │        │
│ │ (single source of truth for form state + payload)   │        │
│ └─────────────────────────────────────────────────────┘        │
│         │                                                      │
│         ↓                                                      │
│ ┌─────────────────────────────────────────────────────┐        │
│ │ TanStack Query                                      │        │
│ │  - useZone(id), useRecipe(id), useReadiness(id)     │        │
│ │  - useLaunchGrowCycleMutation()                     │        │
│ └─────────────────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Step components — shell-based

```vue
<!-- Pages/Launch/Index.vue -->
<AppLayout>
  <LaunchShell>
    <template #stepper>
      <LaunchStepper :steps="stepperSteps" :active="activeIndex" />
    </template>

    <StepHeader :step="currentStepDef" />
    <ZoneStep v-if="currentStep === 'zone'" />
    <RecipeStep v-else-if="currentStep === 'recipe'" />
    <AutomationStep v-else-if="currentStep === 'automation'" />
    <CalibrationStep v-else-if="currentStep === 'calibration'" />
    <PreviewStep v-else-if="currentStep === 'preview'" />

    <template #footer>
      <LaunchFooterNav :blocker-reason="footerBlockerReason" />
    </template>
  </LaunchShell>
</AppLayout>
```

Каждый `*Step` — **чистая UI компонент** без бизнес-логики: читает state из `schema`, валидация через `schema.safeParse()` на каждом change.

### 2.3 Schema shape

```ts
// resources/js/schemas/growCycleLaunch.ts
import { z } from 'zod';

export const growCycleLaunchSchema = z.object({
  zone_id: z.number().positive(),
  recipe_revision_id: z.number().positive(),
  plant_id: z.number().positive(),
  planting_at: z.string().datetime(),
  batch_label: z.string().max(100).optional(),
  notes: z.string().optional(),

  // Overrides (optional, merge non-destructively)
  overrides: z.object({
    irrigation: z.object({
      interval_sec: z.number().int().min(60).max(3600).optional(),
      duration_sec: z.number().int().min(1).max(600).optional(),
    }).optional(),
    correction: z.object({
      target_ph: z.number().min(3).max(9).optional(),
      target_ec: z.number().min(0).max(5).optional(),
    }).optional(),
  }).optional(),

  // Device bindings (if zone not fully configured)
  bindings: z.object({
    soil_moisture_sensor_id: z.number().optional(),
    // ... other conditional bindings
  }).optional(),
});

export type GrowCycleLaunchPayload = z.infer<typeof growCycleLaunchSchema>;
```

### 2.4 Backend manifest

```
GET /api/launch-flow/manifest?zone_id=5
→
{
  "steps": [
    {
      "id": "zone",
      "title": "Зона",
      "visible": false,  // zone уже передана
      "required": true
    },
    {
      "id": "recipe",
      "title": "Рецепт и растение",
      "visible": true,
      "required": true,
      "validation": { "required_fields": ["recipe_revision_id", "plant_id"] }
    },
    {
      "id": "automation",
      "title": "Автоматика",
      "visible": true,
      "required": true,
      "depends_on": ["recipe"],
      "conditional": { "show_if_readiness_missing": ["irrigation_role"] }
    },
    {
      "id": "calibration",
      "title": "Калибровка",
      "visible": false,  // skip если readiness ОК
      "required": false
    },
    {
      "id": "preview",
      "title": "Подтверждение",
      "visible": true,
      "required": true
    }
  ],
  "role_hints": {
    "operator": ["recipe", "preview"],  // прячем технические шаги
    "agronomist": ["recipe", "automation", "preview"],
    "engineer": ["zone", "recipe", "automation", "calibration", "preview"]
  }
}
```

Backend генерирует manifest на основе `Zone::readiness()`, role пользователя, и текущего state (есть/нет device bindings).

### 2.5 Readiness → action items

```
// backend readiness response (новый формат)
{
  "ready": false,
  "blockers": [
    {
      "code": "pump_calibration_missing",
      "message": "Требуется калибровка дозирующего насоса pH (node gh-1-ph-1)",
      "action": {
        "type": "open_calibration",
        "node_id": 5,
        "pump_channel": "ph_acid",
        "route": { "name": "zones.calibration", "params": { "zoneId": 5, "pump": "ph_acid" } }
      },
      "severity": "error"
    }
  ]
}
```

Frontend рендерит clickable cards; клик → `router.visit(route)` → страница калибровки с context.

---

## 3. Executable runbook

Каждая фаза = 1 PR, revert-able независимо. Merge порядок: 1 → 2 → 3 → 4 → 5 → 6.

---

### Phase 1 — Foundation: schema + launch shell primitives (2 дня)

**Цель:** заложить фундамент — Zod schema + embedded `LaunchShell` primitives + typed API client. Без замены существующих wizard'ов.

**Actions:**
1. Создать [resources/js/schemas/growCycleLaunch.ts](../../backend/laravel/resources/js/schemas/growCycleLaunch.ts) — Zod schema с `GrowCycleLaunchPayload` type.
2. Создать shell-компоненты в `resources/js/Components/Launch/Shell/`:
   - `LaunchShell.vue` — embedded wizard container внутри `AppLayout`;
   - `LaunchStepper.vue` (`HStepper` + `VStepper`);
   - `LaunchFooterNav.vue` — navigation, progress и blocker reason;
   - `StepHeader.vue` и `LaunchTopBar.vue`.
3. Создать [resources/js/composables/useFormSchema.ts](../../backend/laravel/resources/js/composables/useFormSchema.ts) — reactive Zod integration:
   - `const { state, errors, isValid } = useFormSchema(schema)`
   - SafeParse on every change, expose field-level errors.
4. Unit-тесты: shell render/navigation, `LaunchFooterNav` blocker reason, `useFormSchema` round-trip.

**DoD:**
- `npm run typecheck` — green
- `npm run test -- --run growCycleLaunch|LaunchShell|LaunchFooterNav|useFormSchema` — ≥30 кейсов
- **Zero изменений в существующих wizard'ах**

**Rollback:** revert PR.

**Риски:** 0.

---

### Phase 2 — Backend manifest endpoint + TanStack Query (2 дня)

**Цель:** backend endpoint для steps manifest + wire up TanStack Query для кеша/mutation.

**Actions:**
1. **Backend:**
   - Создать `App\Http\Controllers\LaunchFlowManifestController` с `GET /api/launch-flow/manifest?zone_id`.
   - Manifest builder использует `Zone::readiness()`, `useRole()`, device binding state.
   - Readiness enrichment: существующий `ZoneReadinessService` расширить на возврат `action` field в blockers.
2. **Frontend:**
   - Добавить `@tanstack/vue-query` в `package.json`.
   - В `app.ts` установить `VueQueryPlugin`.
   - Создать [resources/js/services/queries/launch.ts](../../backend/laravel/resources/js/services/queries/launch.ts):
     - `useLaunchManifest(zoneId)` — cached GET
     - `useLaunchMutation()` — POST `/zones/{id}/grow-cycles` с optimistic invalidation
     - `useReadinessQuery(zoneId)` — с refetch on mutation
3. PHPUnit: `LaunchFlowManifestControllerTest` — 10+ тестов (role variations, readiness states).
4. Vitest: `useLaunchManifest` — mock HTTP + verify cache behaviour.

**DoD:**
- `GET /api/launch-flow/manifest?zone_id=5` возвращает валидный manifest для разных ролей
- TanStack Query DevTools показывает cache entries для zones/recipes
- Phase 1 код остаётся unused (не сломано)

**Rollback:** revert PR; backend endpoint остаётся (не используется в runtime).

**Риски:**
- Medium: `Zone::readiness()` может не содержать нужную granularity для blockers — mitigation: pre-check в Phase 1, расширить при необходимости.

---

### Phase 3 — `<GrowCycleLauncher>` новый flow (3-4 дня)

**Цель:** построить новый Page + step components, интегрируя Phase 1-2.

**Actions:**
1. Создать [resources/js/Pages/Launch/Index.vue](../../backend/laravel/resources/js/Pages/Launch/Index.vue) — entry page:
   - route: `/launch/:zoneId?`
   - использует `useLaunchManifest(zoneId)` + `useFormSchema(growCycleLaunchSchema)`
   - рендерит `LaunchShell` внутри `AppLayout`, без full-screen режима
2. Создать step components в [resources/js/Components/Launch/](../../backend/laravel/resources/js/Components/Launch/):
   - `<ZoneStep/>` — выбор/создание зоны (только если не в manifest.skipped)
   - `<RecipeStep/>` — recipe + plant + preview recipe phases
   - `<AutomationStep/>` — climate/water/lighting из schema.overrides
   - `<CalibrationStep/>` — readiness blockers с clickable actions
   - `<PreviewStep/>` — diff preview + confirm button
3. Role-based step visibility через `useRole()` + `manifest.role_hints`.
4. Routing: добавить `/launch/:zoneId?` в Laravel routes (`routes/web.php`).
5. **Старые wizard'ы остаются работать** — новый flow пока за отдельным URL.
6. Playwright e2e: scenario "agronomist launches cycle for configured zone".

**DoD:**
- `/launch/5` работает: full flow от recipe → preview → launch cycle
- `GrowCycleLaunchPayload` проходит schema validation на каждом шаге
- Manifest-driven steps: скрытие/показ без frontend-if-ов
- Старые `Setup Wizard` и `GrowthCycleWizard` продолжают работать параллельно

**Rollback:** revert PR; новый URL недоступен, старые wizard'ы не затронуты.

**Риски:**
- High: новые step components с нуля — могут не покрывать edge cases из 2688 строк старой логики. Mitigation: characterisation tests (record payload от старых wizards, replay через новый schema — должен дать equivalent).

---

### Phase 4 — Diff-preview + clickable readiness actions (2 дня)

**Цель:** реализовать diff-preview step и clickable actions в readiness blockers.

**Actions:**
1. **Diff preview:**
   - Создать [Components/Launch/DiffPreview.vue](../../backend/laravel/resources/js/Components/Launch/DiffPreview.vue):
     - Fetch current `zone.logic_profile` через `GET /api/automation-configs/zone/{id}/zone.logic_profile`.
     - Compute computed diff между current + schema.overrides.
     - Визуализировать как side-by-side (левая колонка current, правая — new), подсветить changes.
   - Использовать `fast-json-patch` (RFC 6902) для structured diff.
2. **Clickable readiness:**
   - Backend: `ZoneReadinessService::blockers()` возвращает `action: { type, route }`.
   - Frontend `<CalibrationStep/>`: рендерит blockers как `<router-link :to="blocker.action.route">` cards.
3. **Merge submit:** `useLaunchMutation()` отправляет `{ ...core, overrides }` → backend применяет merge (не replace) в `zone.logic_profile`.
4. Backend endpoint обновить на poor merge support если нет:
   - `PATCH /api/automation-configs/zone/{id}/zone.logic_profile` с JSON Merge Patch semantics.
   - Или переиспользовать `PUT` с explicit `mode=merge` query param.
5. Vitest: diff computation unit tests (30+ кейсов — missing, added, modified, nested).

**DoD:**
- User перед submit видит точный diff changes
- Readiness blockers → clickable → переход к нужному UI
- Merge POST не теряет non-overriden поля
- E2e: Setup state → launch с overrides → verify non-overriden поля preserved

**Rollback:** revert PR; preview step пропускается, actions не clickable.

**Риски:**
- Medium: backend merge-support может не существовать для всех namespaces — mitigation: Phase 2 pre-check.

---

### Phase 5 — Migration: redirect old wizards + feature-parity check (1-2 дня)

**Цель:** все entry points теперь указывают на `/launch/:zoneId?`; старые routes redirect.

**Actions:**
1. **Route redirects:**
   - `/setup/wizard` → 301 `/launch` (без zoneId — показывает zone selection step)
   - `/cycles/wizard` или GrowthCycleModal entry → 301 `/launch/:zoneId`
   - Открытие Modal через kebab menu на zone card → вызывает `router.visit('/launch/${zoneId}')`
2. **UI entries:**
   - Dashboard "Запустить цикл" button → `/launch`
   - Zone card "Start cycle" → `/launch/${zoneId}`
   - Setup onboarding splash → `/launch`
3. **Feature parity audit:**
   - Pass через checklist всех input полей из Setup Wizard + GrowthCycleWizard — подтвердить все в новом `<AutomationStep/>`.
   - Sync с user (agronomist) — демо new flow, получить feedback.
4. Fix gaps по feedback (наверное 1-2 мелкие iterations).

**DoD:**
- Zero ссылок на `/setup/wizard` или GrowthCycleModal в коде (grep)
- Все e2e сценарии прошли на новом flow
- User sign-off на UX (demo call)

**Rollback:** revert redirects; старые wizard'ы снова активны.

**Риски:** High UX — feature parity. Mitigation: пользовательский user-testing session (не asynchronous).

---

### Phase 6 — Delete legacy wizards (1 день)

**Цель:** удалить старые wizard'ы и их dependencies.

**Actions:**
1. **Удалить Vue-файлы:**
   - `Pages/Setup/Wizard.vue`
   - `Components/GrowCycle/GrowthCycleWizard.vue`
   - `Components/GrowCycle/WizardAutomationStep.vue`
   - `Components/GrowCycle/steps/*`
2. **Удалить composables:**
   - `useSetupWizard.ts` (1177 строк)
   - `useGrowthCycleWizard.ts` (1511 строк)
   - `setupWizardDataLoaders.ts`, `setupWizardPlantNodeCommands.ts`, `setupWizardRecipeAutomationFlows.ts`, `growthCycleWizardHelpers.ts`, и другие `setupWizard*`
3. **Удалить types:**
   - `WaterFormState`, `ClimateFormState` (заменены Zod schema)
   - Любые типы, используемые только в удаляемых файлах
4. **Удалить тесты:**
   - `__tests__/useSetupWizard.spec.ts`, `__tests__/useGrowthCycleWizard.spec.ts`
   - Keep только новые тесты на `<GrowCycleLauncher>` / schema / launch shell
5. **Prune API modules:**
   - `services/api/setupWizard.ts` — удалить неиспользуемые endpoints (если backend их обслуживал только для Setup Wizard)
6. Grep sanity: `grep -r "useSetupWizard\|useGrowthCycleWizard\|WaterFormState" resources/js/` → empty
7. Bundle size check: new bundle должен быть меньше старого (legacy code удалён).

**DoD:**
- ~2 688 строк composable логики удалено
- ~2-3k строк Vue + tests удалено
- `npm run typecheck && npm run test && npm run e2e` — all green
- Bundle size ↓ (измерить до/после)

**Rollback:** revert — массивный rollback, ~5 файлов back. В exceptional cases можно hold Phase 6 еще спринт, использовать legacy код как backup.

**Риски:**
- Medium: какое-то скрытое usage не обнаружено grep'ом — mitigation: e2e full suite + staging deploy.

---

## 4. Таймлайн

| Фаза | Длительность | Риск | Зависит |
|------|--------------|------|---------|
| 1: Schema + launch shell primitives | 2 дня | none | — |
| 2: Backend manifest + TanStack Query | 2 дня | medium | 1 |
| 3: `<GrowCycleLauncher>` new flow | 3-4 дня | high | 1, 2 |
| 4: Diff-preview + readiness actions | 2 дня | medium | 3 |
| 5: Migration + feature parity | 1-2 дня | high (UX) | 3, 4 |
| 6: Delete legacy | 1 день | medium | 5 |

**Итого:** ~11-13 дней на одного executor'а. Критический путь: 1 → 2 → 3 → 5 → 6.

---

## 5. Risk register

| # | Риск | Вероятность | Импакт | Митигация |
|---|------|------------|--------|-----------|
| R1 | Новый flow не покрывает edge cases старого (hidden UX features) | высокая | UX regression | Characterisation tests + user-testing в Phase 5 |
| R2 | TanStack Query конфликтует с существующим Pinia/Inertia patterns | средняя | integration debt | Isolated namespace для launch queries; не мигрируем всё подряд |
| R3 | Backend manifest endpoint не готов дать достаточно granular readiness | средняя | blockers without actions | Phase 2 pre-check + расширить `ZoneReadinessService` если нужно |
| R4 | Diff-preview показывает false positive changes (JSON normalisation) | средняя | confusion | Канонический JSON compare (sorted keys, trimmed whitespace) |
| R5 | Merge в `zone.logic_profile` теряет поля | высокая | data loss | 20+ unit tests на merge; backend validator enforces preservation |
| R6 | Feature-parity user sign-off не получен | средняя | hold Phase 5-6 | Demo early (после Phase 3), iterate до Phase 5 |
| R7 | Bundle size unexpectedly grows (TanStack Query + Zod overhead) | низкая | perf degrade | Measure до/после; tree-shake unused schemas |
| R8 | `LaunchShell` слишком тесно связан с `/launch` и плохо переиспользуется | средняя | локальный tech debt | Держать shell scoped к `/launch`; reusable выносить только после второго реального flow |

---

## 6. Executor-specific

1. **Фронт-тесты:** `npm run test` + `typecheck` + `lint` перед каждым PR. Phase 3, 4, 5 — обязательно Playwright e2e.
2. **Demo checkpoints:**
   - После Phase 3 — скрин/video новой UX пользователю (может быть ≈20% готовности, но виден shape)
   - Перед Phase 5 — live demo с пользователем, записать feedback
   - Перед Phase 6 — final approval на удаление legacy
3. **Dark mode:** каждый новый компонент — dark mode by default (tailwind `dark:` utilities).
4. **TypeScript strict:** все новые файлы — strict mode, `any` запрещены.
5. **Pinia store:** **не создавать новые** для launch flow. Existing `useZoneStore`, `useAlertsStore` — остаются как есть.
6. **Accessibility:** keyboard navigation работает в `LaunchShell`/`LaunchStepper`/`LaunchFooterNav` (Tab между шагами, Enter для proceed).

**Stop-and-ask points:**
- **Phase 2:** перед написанием `LaunchFlowManifestController` — согласовать shape manifest с пользователем (какие шаги, как условность).
- **Phase 3:** перед завершением — демо новой UX пользователю.
- **Phase 5:** перед удалением legacy — final approval.

---

## 7. Success metrics

| Метрика | Команда / проверка | Цель |
|---------|-------------------|------|
| Composable lines of code | `wc -l resources/js/composables/useLaunch*.ts useSetupWizard.ts useGrowthCycleWizard.ts` | После Phase 6: ≤ 800 (было 2 688) |
| Wizard-related Vue files | `find resources/js -name "*Wizard*" -o -name "Launch*" \| wc -l` | После Phase 6: ≤ 15 (было ~30) |
| Dead form fields | `grep -c "phPct\|irrigationDecisionLookback\|hysteresisPct" resources/js/` | 0 |
| Data loss bug | Playwright: Setup overrides → launch cycle → verify overrides preserved | pass |
| Schema validation coverage | `npm run test:coverage -- schemas/growCycleLaunch` | ≥ 90% |
| TypeScript strict | `npm run typecheck` | exit 0 |
| Bundle size | `npm run build` + compare pre/post | ↓ или equal |
| User feedback | Demo session Phase 5 | sign-off |

---

## 8. Rollback strategy

| Фаза | Rollback | Impact |
|------|---------|--------|
| 1 | revert PR | none (unused code) |
| 2 | revert PR | backend endpoint не вызывается, TanStack Query deps остаются в package.json unused |
| 3 | revert PR | `/launch` route 404; старые wizard'ы продолжают работу |
| 4 | revert PR | launcher без preview step, merge replaced by PUT (data-loss bug возвращается в новом flow) |
| 5 | revert redirects | entry points снова указывают на legacy |
| 6 | revert delete | 5k+ строк legacy code возвращаются |

**Rolling back Phase 5-6 одновременно** — массивный rollback. Mitigation: hold Phase 6 ≥1 спринт после Phase 5 чтобы выявить hidden issues.

---

## 9. Post-completion invariants

После Phase 6 зафиксировать в [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md):

1. **Single entry для launch** — `/launch/:zoneId?`. Все другие UI entries делают `router.visit('/launch/...')`.
2. **Schema-first** — любое новое поле в launch flow добавляется в `schemas/growCycleLaunch.ts` первым; компонент читает из `useFormSchema()`.
3. **Backend-driven steps** — добавление/удаление шага = backend-only change в `LaunchFlowManifestController`. Frontend читает manifest.
4. **TanStack Query для launch-related data** — `useZone`, `useRecipe`, `useReadiness`. Pinia только для multi-page global state.
5. **Actionable readiness** — все readiness blockers возвращают `action.route` с прямым переходом; cryptic codes без UI mapping запрещены.
6. **Diff preview before merge** — любая мутация `zone.logic_profile` из launch flow проходит через `<DiffPreview/>`.
7. **Запрещено создавать новые wizard-like flows параллельно launcher'у** — если новый use case, расширять manifest.

---

## 10. Связанные документы

- [AUTOMATION_CONFIG_AUTHORITY.md](../04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) — config authority (live-edit infrastructure)
- [ae3lite.md](../04_BACKEND_CORE/ae3lite.md) — AE3 runtime spec
- [FRONTEND_ARCH_FULL.md](FRONTEND_ARCH_FULL.md) — frontend архитектура (обновить после Phase 6: удалить legacy wizard refs, добавить embedded LaunchShell)
- [ROLE_BASED_UI_SPEC.md](ROLE_BASED_UI_SPEC.md) — role gates (manifest.role_hints enforcement)
- [EFFECTIVE_TARGETS_SPEC.md](../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md) — границы overrides для schema validation

---

## 11. Почему этот план лучше v1.0

| Критерий | v1.0 (iterative) | v2.0 (rewrite) |
|---|---|---|
| Источники UX дубля | patch-over с shared компонентами | архитектурно устранены (single flow) |
| Data-loss bug (Phase 5 v1.0) | бейндэйд с merge helper | устранён by design (preview + diff UI) |
| Dead fields | ручное удаление, возможен возврат | невозможны (Zod schema — single source) |
| Extensibility (новый шаг) | frontend edit + test update | backend-only change в manifest |
| Maintainability через 6 мес | разбегание flows снова | единая точка модификации |
| Total LOC | осталось ~2 688 + shared abstractions | ≤ 800 |
| Время | 12-14 дней | 11-13 дней |
| Riск | distributed (8 PR) | concentrated (Phase 3, 5) |

v2.0 требует больше дисциплины и хорошей user-communication, но возвращает долг **полностью** вместо его реструктуризации.
