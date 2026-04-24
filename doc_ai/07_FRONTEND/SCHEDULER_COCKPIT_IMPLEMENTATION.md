# Scheduler Cockpit UI — руководство для ИИ-агента по внедрению

**Дата:** 2026-04-24
**Версия:** 1.0
**Статус:** Готово к реализации
**Compatible-With:** Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

## 0. Роль и цель

**Роль:** senior full-stack разработчик (Vue 3 + TS + Laravel + Python).
**Цель:** заменить одноколоночный `ZoneSchedulerTab.vue` на 3-колоночную cockpit-раскладку с причинно-следственной цепочкой решений (A+C гибрид). Пользователь — `operator/agronomist/engineer/admin` зоны теплицы.
**Референс UI:** `Scheduler Redesign.html` в design-проекте, артборд "Гибрид A + C · живой прототип". Исходник React-компонентов: `scenes/04-hybrid-ac.jsx`.

## 1. Инварианты (НЕ ТРОГАТЬ)

- Пайплайн команд: `Laravel scheduler-dispatch → automation-engine → history-logger → MQTT → ESP32`
- Композабл `useZoneScheduleWorkspace` — публичный API не менять, только расширять типы
- Inertia props текущих контроллеров — сохранить обратную совместимость через fallback
- Формат MQTT-топиков, `message_type`, схемы БД — не меняются
- Роли/политики `canDiagnose`, `canEditAutomation` — зеркалятся 1:1
- История Docker-разработки (`backend/docker-compose.dev.yml`) — все команды выполняются в контейнерах

## 2. Что нужно прочитать перед началом

**Обязательно:**
- `doc_ai/INDEX.md`
- `doc_ai/SYSTEM_ARCH_FULL.md`
- `doc_ai/ARCHITECTURE_FLOWS.md`
- `doc_ai/DEV_CONVENTIONS.md`
- `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- `doc_ai/04_BACKEND_CORE/ae3lite.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
- `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneSchedulerTab.vue`
- `backend/laravel/resources/js/composables/useZoneScheduleWorkspace.ts`
- `backend/laravel/resources/js/Components/Scheduler/*.vue`
- `Scheduler Redesign.html` + `scenes/04-hybrid-ac.jsx` (референс)

**Проверить локальные `AGENTS.md`** в `backend/`, `backend/laravel/`, `backend/services/`.

## 3. Фазы внедрения

### Фаза 0 — Подготовка (0.5 дня)

1. `git checkout -b feature/scheduler-cockpit-ui`
2. Создать `doc_ai/07_FRONTEND/SCHEDULER_COCKPIT_REDESIGN.md` со ссылкой на этот документ, целями и скриншотами.
3. В `backend/laravel/config/features.php` (или где хранятся feature-flags) добавить:
   ```php
   'scheduler_cockpit_ui' => env('FEATURE_SCHEDULER_COCKPIT_UI', false),
   ```
4. Проверить, что `make up` и `make logs-core` работают без ошибок.

**Критерий приёмки Ф0:** ветка создана, документ зафиксирован, флаг доступен во фронте через Inertia shared props.

### Фаза 1 — Cockpit layout (1–2 дня, только фронтенд)

#### 1.1 Новые компоненты

Путь: `backend/laravel/resources/js/Components/Scheduler/Cockpit/`

Создать `.vue` SFC (Composition API + `<script setup lang="ts">`):

**`CockpitLayout.vue`** — 3-колоночная обёртка.
```
<template>
  <div class="grid gap-3" style="grid-template-columns: 340px 1fr 360px; min-height: 0">
    <div class="flex flex-col gap-2.5"><slot name="left" /></div>
    <div class="flex flex-col gap-2.5"><slot name="center" /></div>
    <div class="flex flex-col gap-2.5"><slot name="right" /></div>
  </div>
</template>
```

**`HeroCountdown.vue`** — крупный таймер активного run.
- Props: `run: ActiveRun | null`
- Live-обновление через `useRafInterval` (1s)
- Segmented progress по `run.progress_steps`
- Пустое состояние: "Нет активных исполнений"

**`NextUpCard.vue`** — очередь ближайших окон.
- Props: `windows: ExecutableWindow[]`, `formatRelative: fn`
- Первое окно подсвечено зелёным; остальные — нейтральные

**`SwimlaneTimeline.vue`** — swimlane-лента по lanes.
- Props: `lanes: LaneHistory[]`, `horizon: '24h'|'7d'`
- Маркер «сейчас» на 50%
- Клик по блоку → `emit('select-run', runId)`

**`RecentRunsTable.vue`** — интерактивная таблица.
- Props: `runs: Execution[]`, `selectedId?: string`
- Emits: `select(runId: string)`
- Колонки: ID, Lane, Decision, `correction_window_id · N шагов`, Δ
- `data-testid="runs-row"` на каждую строку
- Левый рельс окрашивается по статусу

**`ConfigOnlyFooter.vue`** — бейджи lanes вне runtime.

**`KpiRow.vue`** — 4 KPI-карточки.

Референсные реализации этих компонентов — в `scenes/04-hybrid-ac.jsx` (читать как спецификацию, переписать на Vue 3 SFC).

#### 1.2 Правки существующих файлов

**`Pages/Zones/Tabs/ZoneSchedulerTab.vue`:**
- Добавить computed `cockpitEnabled` из Inertia shared prop `features.scheduler_cockpit_ui`
- В template: `<CockpitSchedulerTab v-if="cockpitEnabled" ... /> <LegacySchedulerTab v-else ... />`
- **Composable `useZoneScheduleWorkspace` НЕ ТРОГАТЬ** — он уже даёт все нужные данные
- Старый template переименовать в `LegacySchedulerTab.vue` (скопировать текущий template как есть)

**Новый `CockpitSchedulerTab.vue`:**
```
<template>
  <div class="space-y-3">
    <SchedulerHeader ... /> <!-- переиспользуем -->
    <CockpitLayout>
      <template #left>
        <HeroCountdown :run="activeRun" />
        <NextUpCard :windows="nextExecutableWindows" ... />
        <ConfigOnlyFooter :lanes="configOnlyLanes" />
      </template>
      <template #center>
        <KpiRow :counters="executionCounters" :slo="sloValue" />
        <SwimlaneTimeline :lanes="lanesHistory" :horizon="horizon" />
        <RecentRunsTable :runs="recentRuns" :selected-id="selectedExecutionId" @select="fetchExecution" />
      </template>
      <template #right>
        <SchedulerAttentionPanel :items="attentionItems" /> <!-- переиспользуем -->
        <CausalChainPanel v-if="selectedExecution" :run="selectedExecution" @close="clearSelectedExecution" />
      </template>
    </CockpitLayout>
    <SchedulerDiagnostics ... /> <!-- переиспользуем -->
  </div>
</template>
```

#### 1.3 TypeScript

В `composables/zoneAutomationTypes.ts` добавить:
```
export interface LaneHistoryPoint { t: number; s: 'ok'|'err'|'skip'|'run'|'warn' }
export interface LaneHistory { lane: string; runs: LaneHistoryPoint[] }
```

Если `lanes_history` ещё нет в workspace-ответе — временно вычислять во фронте из `recentRuns` (функция `deriveLaneHistory(runs, horizon)`); в Фазе 2 backend начнёт отдавать готовые бакеты.

#### 1.4 Тесты

- `tests/Unit/Components/Scheduler/Cockpit/*.spec.ts` (Vitest) — рендер каждого компонента с fixture
- `tests/e2e/scheduler-cockpit.spec.ts` (Playwright): открыть зону → увидеть 3 колонки → кликнуть run → chain справа (пока заглушка)

**Критерий приёмки Ф1:**
- При `FEATURE_SCHEDULER_COCKPIT_UI=true` зона показывает cockpit, иначе — старый UI
- `make test` (Laravel) + `npm run test:unit` + Playwright все зелёные
- `npm run type-check` (vue-tsc) — 0 ошибок
- ESLint/Prettier — чисто

### Фаза 2 — Causal chain (2–3 дня, backend + frontend)

#### 2.1 Backend (Laravel)

**Файлы:**
- `backend/laravel/app/Http/Controllers/Api/ZoneScheduleController.php` (или как называется у вас)
- `backend/laravel/app/Http/Controllers/Api/RunsController.php`
- `backend/laravel/app/Services/Scheduler/ExecutionChainAssembler.php` (новый)
- `backend/laravel/app/Http/Resources/ExecutionResource.php`

**Задача:** в ответ `GET /api/zones/{id}/executions/{execId}` (и в `workspace.activeRun`) добавить массив `chain`:
```json
{
  "chain": [
    { "step": "SNAPSHOT",  "at": "2026-04-24T12:33:52Z", "ref": "ev-8821",  "detail": "pH=6.4 · EC=1.52", "status": "ok" },
    { "step": "DECISION",  "at": "2026-04-24T12:33:55Z", "ref": "cw-118",   "detail": "DOSE_ACID 2.3 ml", "status": "ok" },
    { "step": "TASK",      "at": "2026-04-24T12:33:56Z", "ref": "T-551",    "detail": "ae_task → dosing_acid", "status": "ok" },
    { "step": "DISPATCH",  "at": "2026-04-24T12:34:07Z", "ref": "cmd-9931", "detail": "history-logger → MQTT", "status": "ok" },
    { "step": "RUNNING",   "at": "2026-04-24T12:34:08Z", "ref": "ex-2042",  "detail": "pump_acid активен", "status": "run", "live": true }
  ]
}
```

**Источники данных (уже существуют в БД, НОВЫХ миграций НЕ ТРЕБУЕТСЯ):**
- `correction_windows` → шаг `SNAPSHOT` (по `snapshot_id`) + `DECISION` (`decision_outcome`, `decision_reason_code`)
- `ae_tasks` → шаг `TASK` (по `correction_window_id`)
- `commands` / `history_logger_commands` → шаг `DISPATCH`
- `executions` → шаги `RUNNING`, `COMPLETE`, `FAIL` (по `status`, `error_code`, `error_message`, `completed_at`)

**`ExecutionChainAssembler`** — сервис, который по `execution_id` собирает цепочку:
```php
public function assemble(int $executionId): array
{
    $exec = Execution::with(['correctionWindow.snapshot', 'aeTask.command'])
        ->findOrFail($executionId);
    $chain = [];
    if ($exec->correctionWindow?->snapshot) {
        $chain[] = $this->snapshotStep($exec->correctionWindow->snapshot);
    }
    if ($exec->correctionWindow) {
        $chain[] = $this->decisionStep($exec->correctionWindow);
    }
    if ($exec->aeTask) {
        $chain[] = $this->taskStep($exec->aeTask);
    }
    if ($exec->aeTask?->command) {
        $chain[] = $this->dispatchStep($exec->aeTask->command);
    }
    $chain = array_merge($chain, $this->executionSteps($exec));
    return $chain;
}
```

**Важно:** SKIP-execution может иметь только `SNAPSHOT` + `DECISION` без `TASK/DISPATCH` — это нормально.

**API-тесты** в `backend/laravel/tests/Feature/Api/ExecutionChainTest.php`:
- chain для успешного run (6 шагов)
- chain для FAIL (error_code в последнем шаге)
- chain для SKIP (2 шага)
- chain для активного run (последний шаг `status=run`, `live=true`)

#### 2.2 WebSocket

**Файл:** `backend/laravel/app/Events/ExecutionChainUpdated.php` (новое событие).

При добавлении нового шага в цепочку (из `automation-engine` → `history-logger` → Laravel webhook или listener на model events `Execution`, `AeTask`, `Command`) — broadcast:
```php
broadcast(new ExecutionChainUpdated($execution, $newStep))->toOthers();
```
Payload:
```json
{ "execution_id": 2042, "step": { "step": "DISPATCH", "at": "...", "ref": "cmd-9931", ... } }
```

Канал: `zone.{zoneId}.executions` (уже должен быть).

**Фронт** — в `ws/scheduler.ts` добавить слушатель: при получении `chain_delta` патчить `selectedExecution.chain` через `fast-json-patch` (`[{ op: 'add', path: '/chain/-', value: step }]`).

#### 2.3 Frontend

**`CausalChainPanel.vue`** — новый компонент. Референс: `CausalChainPanel` в `scenes/04-hybrid-ac.jsx` (функция с тем же именем).
- Props: `run: Execution`
- Emits: `close`
- Рендер chain с timeline (точки + линии)
- FAIL-блок сверху, если `run.error_code`
- Кнопки: «Повторить» (только для FAIL, вызывает `POST /api/executions/{id}/retry`), «В Events →» (deep-link на `/audit?execution_id=...`), copy-button для `correction_window_id`

**`composables/useZoneScheduleWorkspace.ts`:**
- В тип `Execution` добавить `chain?: ChainStep[]`
- В `fetchExecution` ожидать `chain` в ответе (уже будет благодаря Ф2.1)
- Новая reactive-ссылка `selectedExecution` уже есть — не менять

**Zod-схема:**
```ts
// schemas/execution.ts
export const ChainStepSchema = z.object({
  step: z.enum(['SNAPSHOT', 'DECISION', 'TASK', 'DISPATCH', 'RUNNING', 'COMPLETE', 'FAIL', 'SKIP']),
  at: z.string().datetime(),
  ref: z.string(),
  detail: z.string(),
  status: z.enum(['ok', 'err', 'skip', 'run', 'warn']),
  live: z.boolean().optional(),
});
export const ExecutionSchema = z.object({
  // ... existing fields
  chain: z.array(ChainStepSchema).optional(),
});
```

#### 2.4 Документация

Обновить:
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md` — секция `GET /api/zones/{id}/executions/{execId}` с примером `chain`
- `doc_ai/04_BACKEND_CORE/ae3lite.md` — схема AE3 с новым сервисом `ExecutionChainAssembler`
- `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md` — раздел «Causal chain panel»
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — связи `correction_window → ae_task → command → execution`

В PR зафиксировать строку:
`Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`

**Критерий приёмки Ф2:**
- `docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=ExecutionChain` — зелёно
- Клик по run в UI → через < 300 мс видна chain
- Live-обновление шага `RUNNING → COMPLETE` во время активного run (проверить ручным E2E)
- Zod-валидация не падает на всех 4 кейсах (ok/err/skip/run)

### Фаза 3 — Polish (1 день)

1. **Live countdown** в `HeroCountdown`: `useRafInterval(() => updateRemaining(), 1000)` с graceful pause при `document.hidden`.
2. **Горячие клавиши** в `CockpitSchedulerTab`:
   - `J` / `K` — навигация по `RecentRunsTable.rows`
   - `Enter` — открыть chain для выбранной строки
   - `R` — `refreshWorkspace()`
   - `Esc` — `clearSelectedExecution()`
   - Реализовать через новый composable `useSchedulerHotkeys` + `@vueuse/core`'s `useMagicKeys`
3. **`data-testid`** на всё:
   - `scheduler-cockpit-root`
   - `scheduler-runs-row-{id}`
   - `scheduler-chain-step-{step}`
   - `scheduler-hero-countdown`
4. **Playwright e2e** `tests/e2e/scheduler-cockpit.spec.ts`:
   - `expect chain shown for active run on load`
   - `select FAIL run → error_code visible + retry button`
   - `select SKIP run → 2 steps only`
   - `hotkey R refreshes workspace`

**Критерий приёмки Ф3:** все тесты зелёные, `npm run lint` чисто, Lighthouse перфоманс зоны ≥ 85.

### Фаза 4 — Rollout

1. Merge в `main` за feature-flag (OFF по умолчанию)
2. Неделя 1: включить `FEATURE_SCHEDULER_COCKPIT_UI=true` для dev + engineer-аккаунтов
3. Неделя 2: agronomist
4. Неделя 3: operator (основной пользователь)
5. Неделя 4: удалить legacy-код (`LegacySchedulerTab.vue`, `SchedulerRunsColumn.vue`, `SchedulerNextWindow.vue`, `SchedulerStatusStrip.vue`) + feature-flag

## 4. Чек-лист для PR

### PR 1 (Фаза 1)
- [ ] Ветка `feature/scheduler-cockpit-ui-layout`
- [ ] 7 новых Vue SFC в `Components/Scheduler/Cockpit/`
- [ ] `CockpitSchedulerTab.vue` + `LegacySchedulerTab.vue`
- [ ] Feature-flag `scheduler_cockpit_ui` подключён
- [ ] Vitest coverage ≥ 80% для новых компонентов
- [ ] Playwright smoke-тест проходит
- [ ] `doc_ai/07_FRONTEND/SCHEDULER_COCKPIT_REDESIGN.md` обновлён
- [ ] Скриншот cockpit-UI в PR description
- [ ] `Compatible-With: ...` в описании PR

### PR 2 (Фаза 2)
- [ ] Ветка `feature/scheduler-cockpit-chain`
- [ ] `ExecutionChainAssembler` + Feature-тесты
- [ ] `ExecutionResource` расширен полем `chain`
- [ ] WS `ExecutionChainUpdated` + listener на фронте
- [ ] `CausalChainPanel.vue` + Vitest
- [ ] `composables/useZoneScheduleWorkspace.ts` — тип `Execution.chain`
- [ ] Zod-схема `ChainStepSchema`
- [ ] `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md` обновлён
- [ ] `Compatible-With: ...` в описании PR

### PR 3 (Фаза 3)
- [ ] Ветка `feature/scheduler-cockpit-polish`
- [ ] Live countdown на RAF
- [ ] `useSchedulerHotkeys`
- [ ] Все `data-testid` на месте
- [ ] 4+ Playwright-сценария
- [ ] Lighthouse ≥ 85

### PR 4 (Фаза 4 — cleanup)
- [ ] Удалены legacy-компоненты
- [ ] Убран feature-flag из config + ENV
- [ ] `doc_ai/07_FRONTEND/` — история редизайна в changelog

## 5. Риски и откат

| Риск | Митигация |
|---|---|
| Медленный `ExecutionChainAssembler` (N+1 запросы) | Eager-load `with(['correctionWindow.snapshot', 'aeTask.command'])`, замерить p95 ≤ 80 мс |
| WS-штормы при активном run | Debounce `ExecutionChainUpdated` на 250 мс на backend |
| Legacy-пользователи в зонах с кривыми данными | Feature-flag + `v-if="cockpitEnabled"` fallback |
| Неполная chain для SKIP-runs | Тест-кейс покрывает; UI корректно рендерит 2 шага |
| Конфликт feature-flag shared prop | Проверить `HandleInertiaRequests::share()` — добавить `features` ключ |

**Откат:** выставить `FEATURE_SCHEDULER_COCKPIT_UI=false` в `.env` → перезапустить Laravel → UI моментально вернётся к legacy. Кода на backend не откатываем (chain-endpoint обратно-совместим).

## 6. Ссылки

- Дизайн-макет: `Scheduler Redesign.html` (design-проект)
- React-референс: `scenes/04-hybrid-ac.jsx`
- CSS-токены: `scheduler-tokens.css`
- Текущий UI: `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneSchedulerTab.vue`
- AE3 спецификация: `doc_ai/04_BACKEND_CORE/ae3lite.md`
- Correction cycle: `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`

## 7. Формат ответа для ИИ-агента

После каждой фазы присылать:
1. Список изменённых/созданных файлов
2. Diff ключевых мест (composable, контроллер, новый сервис)
3. Команды для проверки: `make test`, `npm run test:unit`, `npx playwright test`
4. Ссылку на PR + строку `Compatible-With`
5. Скриншот нового UI (только для Ф1 и Ф2)

**Язык общения с пользователем:** русский. Технические идентификаторы (имена API, классов, файлов) — как есть.
