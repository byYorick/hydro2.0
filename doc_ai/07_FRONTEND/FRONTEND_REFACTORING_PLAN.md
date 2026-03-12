# FRONTEND_REFACTORING_PLAN.md
# План рефакторинга, декомпозиции и исправления багов фронтенда

**Дата:** 2026-02-18
**Обновлено:** 2026-02-19
**Ветка:** AE2
**Статус:** IN PROGRESS — Фаза 0 завершена, Фаза 1 завершена, Фаза 2 частично, Фаза 3 частично
**Приоритет:** Фазы 1–3

---

## 0. Контекст и метрики текущего состояния

| Метрика | Исходное | Текущее | Цель |
|---------|---------|---------|------|
| Локальных типов в компонентах | 210 | ~195 | < 15 |
| Использование `as any` в `.vue` (prod) | 217 | ~52 | < 20 |
| Прямые `fetch()` вне `useApi` | 5+ файлов | 5+ файлов | 0 |
| Неиспользуемые компоненты | 2 | 0 | 0 |
| Composables > 600 строк | 3 | 0 | 0 |
| Компоненты > 600 строк (скрипт+шаблон) | 12 | ~8 | 0 |
| Подтверждённых утечек памяти | 3 | 0 | 0 |
| Race condition | 1 | 0 | 0 |
| Логических багов | 1 | 0 | 0 |

**Frontend:** `backend/laravel/resources/js/`

---

## ФАЗА 0 — Исправление багов ✅ ЗАВЕРШЕНА (2026-02-19)

### BUG-1 ✅ [КРИТИЧНЫЙ] Утечка памяти — EventListener без cleanup

**Файл:** [Components/ChartBase.vue](../../backend/laravel/resources/js/Components/ChartBase.vue) строки 94–107

**Проблема:** `window.addEventListener('resize', onResize)` добавляется в `onMounted` безусловно, но `removeEventListener` вызывается только внутри условного блока `if (window.ResizeObserver)`. При отсутствии `ResizeObserver` (или при быстром unmount до входа в ветку) слушатель остаётся висеть навсегда. Каждый новый mount добавляет ещё один.

**Исправление:**
```typescript
// БЫЛО — небезопасно:
onMounted(() => {
  window.addEventListener('resize', onResize)
  if (window.ResizeObserver && el.value) {
    const ro = new ResizeObserver(onResize)
    ro.observe(el.value)
    onBeforeUnmount(() => {
      ro.disconnect()
      window.removeEventListener('resize', onResize) // только здесь!
    })
  }
  // Ветка else — утечка!
})

// СТАЛО — безопасно:
onMounted(() => {
  window.addEventListener('resize', onResize)

  if (window.ResizeObserver && el.value) {
    const ro = new ResizeObserver(onResize)
    ro.observe(el.value)
    onBeforeUnmount(() => ro.disconnect())
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize) // всегда
})
```

---

### BUG-2 ✅ [ВЫСОКИЙ] Утечка памяти — setTimeout при rate-limit без cleanup

**Файл:** [composables/useSystemStatus.ts](../../backend/laravel/resources/js/composables/useSystemStatus.ts) строки 223–248

**Проблема:** При получении HTTP 429 создаётся `setTimeout(() => { checkHealth(); setInterval... })`. Если компонент размонтирован до срабатывания таймера — таймер срабатывает, запускает `checkHealth` и **создаёт новый `setInterval`** в несуществующем контексте. При повторных rate-limit событиях таймеры накапливаются.

**Исправление:**
```typescript
// Добавить отмену предыдущего таймера перед созданием нового:
if (sharedState.rateLimitTimeout !== null) {
  clearTimeout(sharedState.rateLimitTimeout)
  sharedState.rateLimitTimeout = null
}
sharedState.rateLimitTimeout = setTimeout(() => {
  sharedState.rateLimitTimeout = null
  if (!sharedState.disposed) { // добавить флаг disposed
    checkHealth()
    sharedState.healthInterval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL)
  }
}, backoffMs)

// В cleanup (onScopeDispose / stop()):
sharedState.disposed = true
if (sharedState.rateLimitTimeout !== null) {
  clearTimeout(sharedState.rateLimitTimeout)
}
```

---

### BUG-3 ✅ [ВЫСОКИЙ] Логический баг — двойной rollback в useOptimisticUpdate

**Файл:** [composables/useOptimisticUpdate.ts](../../backend/laravel/resources/js/composables/useOptimisticUpdate.ts) строки 153–175

**Проблема:** Когда `setTimeout` срабатывает раньше завершения запроса (`timeoutError = true`), вызывается первый `rollback()`. Затем запрос завершается с ошибкой, попадает в `catch`. Условие `if (!timeoutError)` должно защитить от второго `rollback()`, но неверный отступ (4 пробела вместо 6) нарушает логику вложенности — `rollback()` оказывается вне условия и вызывается снова.

**Исправление:** Проверить и исправить отступы в `catch`-блоке, убедиться что `rollback()` внутри `if (!timeoutError)`.

---

### BUG-4 ✅ [ВЫСОКИЙ] Race condition — версионирование запросов при смене зоны

**Файл:** [composables/useZoneAutomationTab.ts](../../backend/laravel/resources/js/composables/useZoneAutomationTab.ts) строки 1410–1437

**Проблема:** `schedulerTaskListRequestVersion` и `schedulerTaskLookupRequestVersion` — переменные на уровне модуля (не сбрасываются при создании нового экземпляра composable). При быстрой смене `zoneId` несколько запросов летят параллельно, а сравнение версий может дать некорректный результат из-за общего счётчика.

**Исправление:**
```typescript
// Перенести счётчики внутрь функции composable:
export function useZoneAutomationTab(props) {
  let schedulerTaskListRequestVersion = 0  // локально, сбрасывается при каждом вызове
  let schedulerTaskLookupRequestVersion = 0
  // ...
}
```

---

### BUG-5 ✅ [СРЕДНИЙ] Утечка памяти — накопление таймеров в useKeyboardShortcuts

**Файл:** [composables/useKeyboardShortcuts.ts](../../backend/laravel/resources/js/composables/useKeyboardShortcuts.ts) строки 71–99

**Проблема:** `visitTimers: Map<string, ReturnType<typeof setTimeout>>` — Map на уровне модуля. При быстрых навигациях одновременно висит множество таймеров. Нет очистки завершённых таймеров из Map при unmount.

**Исправление:** Добавить очистку всех pending таймеров в `onScopeDispose`:
```typescript
onScopeDispose(() => {
  visitTimers.forEach((timer) => clearTimeout(timer))
  visitTimers.clear()
})
```

---

## ФАЗА 1 — Критичные архитектурные исправления ✅ ЗАВЕРШЕНА (2026-02-19)

### R1-1 ✅ Типизировать `Zone.activeGrowCycle` (удалить TODO)

**Файл:** [types/Zone.ts](../../backend/laravel/resources/js/types/Zone.ts) строка 29

```typescript
// БЫЛО:
activeGrowCycle?: any // TODO: Define proper type

// СТАЛО:
activeGrowCycle?: GrowCycle | null
```

Проверить `GrowCycle.ts` — если там `targets?: Record<string, any>`, конкретизировать под `ZoneTargets`.

---

### R1-2 ✅ Запретить прямые `fetch()` вне `useApi` — заменить в 5 местах

Все API-запросы должны идти через `useApi()` composable для централизованной обработки ошибок, toast и типизации.

| Файл | Строка | Действие |
|------|--------|---------|
| [Components/AutomationProcessPanel.vue](../../backend/laravel/resources/js/Components/AutomationProcessPanel.vue) | 464 | Заменить `fetch('/api/zones/...')` на `useApi().get(...)` |
| [Components/ZoneComparisonModal.vue](../../backend/laravel/resources/js/Components/ZoneComparisonModal.vue) | — | Заменить все `fetch` на `useApi` |
| [Pages/Zones/Index.vue](../../backend/laravel/resources/js/Pages/Zones/Index.vue) | — | Заменить `fetch` на `useApi` |
| [Pages/Logs/Index.vue](../../backend/laravel/resources/js/Pages/Logs/Index.vue) | — | Заменить `fetch` на `useApi` |
| [Pages/Dashboard/Dashboards/AgronomistDashboard.vue](../../backend/laravel/resources/js/Pages/Dashboard/Dashboards/AgronomistDashboard.vue) | — | Заменить `fetch` на `useApi` |

---

### R1-3 ✅ Удалить неиспользуемые компоненты (мёртвый код)

| Файл | Причина | Действие |
|------|---------|---------|
| [Components/DataTable.vue](../../backend/laravel/resources/js/Components/DataTable.vue) | Все потребители используют `DataTableV2` | Удалить файл |
| [Components/Wizards/GrowCycleWizard.vue](../../backend/laravel/resources/js/Components/Wizards/GrowCycleWizard.vue) | Пустой прокси, не импортируется | Удалить файл + директорию Wizards/ если пустая |

**Перед удалением:** убедиться `grep -r "DataTable[^V]" resources/js/` вернёт 0 результатов.

---

### R1-4 ✅ Устранить `as any` в критичных местах

Приоритетные файлы (наибольшее число `any`):

```
useZoneShowPage.ts:  строки 179, 288, 294, 298, 301, 419, 420
useCommands.ts:      строки 108, 190
usePlantCreateModal.ts: строка 324
AgronomistDashboard.vue: 13 вхождений
Recipes/Edit.vue:    14 вхождений
```

**Подход:**
1. Определить реальный тип из API-ответа или Inertia props
2. Добавить интерфейс в `types/`
3. Заменить `as any` на правильный тип

---

## ФАЗА 2 — Декомпозиция больших файлов (частично завершена)

### R2-1 ✅ Декомпозиция `useZoneAutomationTab.ts` (1703 строки → 4 composable)

**Файл:** [composables/useZoneAutomationTab.ts](../../backend/laravel/resources/js/composables/useZoneAutomationTab.ts)

**Предлагаемое разделение:**

```
useZoneAutomationTab.ts           ← точка входа (< 150 строк, только оркестрация)
├── useZoneAutomationState.ts     ← реактивное состояние форм + watcher'ы (~300 строк)
├── useZoneAutomationApi.ts       ← все API вызовы (load, save, fetch) (~400 строк)
├── useZoneAutomationScheduler.ts ← логика scheduler tasks (~400 строк)
└── useZoneAutomationEvents.ts    ← обработка WebSocket событий (~300 строк)
```

**Критерии выделения:**
- Состояние (ref/reactive) → `useZoneAutomationState`
- `await api.*()` вызовы → `useZoneAutomationApi`
- Всё связанное с `schedulerTask*` → `useZoneAutomationScheduler`
- `onWebSocketEvent`, `watch(wsEvent)` → `useZoneAutomationEvents`

---

### R2-2 ✅ Декомпозиция `AutomationProcessPanel.vue` (1576 строк → 4 компонента)

**Файл:** [Components/AutomationProcessPanel.vue](../../backend/laravel/resources/js/Components/AutomationProcessPanel.vue)

**Предлагаемое разделение:**

```
AutomationProcessPanel.vue           ← оболочка + fetch состояния (<150 строк)
├── AutomationStatusHeader.vue       ← статус enabled/disabled + кнопки (~200 строк)
├── AutomationPidSection.vue         ← секция PID логов + конфигурации (~400 строк)
├── AutomationCooldownSection.vue    ← cooldown + trend данные (~300 строк)
└── AutomationAnomalySection.vue     ← equipment anomaly guard секция (~300 строк)
```

**Заменить:** `fetch('/api/zones/{zoneId}/state')` на `useApi().get(...)`.

---

### R2-3 ✅ Декомпозиция `useZoneShowPage.ts` (1037 строк → 3 composable)

**Файл:** [composables/useZoneShowPage.ts](../../backend/laravel/resources/js/composables/useZoneShowPage.ts)

```
useZoneShowPage.ts             ← точка входа (~100 строк)
├── useZonePageData.ts         ← нормализация Inertia props + derived вычисления (~350 строк)
├── useZonePageActions.ts      ← действия (открыть модаль, запустить команду и т.д.) (~350 строк)
└── useZonePageRealtime.ts     ← WebSocket подписки + обновления в реальном времени (~200 строк)
```

---

### R2-4 Декомпозиция больших страниц (> 600 строк) — частично

Приоритет по убыванию:

| Файл | Строк исх. | Строк сейчас | Цель декомпозиции |
|------|-----------|-------------|-------------------|
| [Pages/Recipes/Edit.vue](../../backend/laravel/resources/js/Pages/Recipes/Edit.vue) | 1097 | **641** ✅ | Логика вынесена в `useRecipeEdit.ts` |
| [Pages/Alerts/Index.vue](../../backend/laravel/resources/js/Pages/Alerts/Index.vue) | 1031 | **487** ✅ | Логика вынесена в `useAlertsPage.ts` |
| [Pages/Setup/Wizard.vue](../../backend/laravel/resources/js/Pages/Setup/Wizard.vue) | 963 | 963 | Выделить отдельные `Step*` компоненты |
| [Pages/Dashboard/Dashboards/AgronomistDashboard.vue](../../backend/laravel/resources/js/Pages/Dashboard/Dashboards/AgronomistDashboard.vue) | 686 | 686 | Выделить виджеты в отдельные компоненты |
| [Pages/Devices/Show.vue](../../backend/laravel/resources/js/Pages/Devices/Show.vue) | 680 | 680 | Выделить `DeviceChannelsPanel`, `DeviceConfigPanel` |

**Правило:** Страница-контейнер ≤ 200 строк, содержит только оркестрацию и layout. Логика — в composable. Секции — в подкомпонентах.

---

### R2-5 Декомпозиция больших модальных окон — частично

| Компонент | Строк исх. | Строк сейчас | Действие |
|-----------|-----------|-------------|---------|
| [Components/PumpCalibrationModal.vue](../../backend/laravel/resources/js/Components/PumpCalibrationModal.vue) | 712 | **293** ✅ | Логика вынесена в `usePumpCalibration.ts` |
| [Components/PlantCreateModal.vue](../../backend/laravel/resources/js/Components/PlantCreateModal.vue) | 723 | 723 ✅ | Скрипт уже минимальный (51 строка), 671 — шаблон; `usePlantCreateModal.ts` существует |
| [Components/GrowthCycleModal.vue](../../backend/laravel/resources/js/Components/GrowthCycleModal.vue) | 673 | 673 | Вынести в `useGrowthCycleModal.ts` |
| [Components/ZoneSimulationModal.vue](../../backend/laravel/resources/js/Components/ZoneSimulationModal.vue) | 672 | 672 | Локальные интерфейсы → `types/Simulation.ts` |

---

## ФАЗА 3 — Типизация и архитектурная чистота (частично)

### R3-1 Вынести локальные типы из компонентов в `types/`

**Масштаб:** 210 локальных типов в 115 файлах (79 в Pages, 131 в Components).

**Приоритетные файлы (наибольшее число локальных типов):**

| Файл | Локальных типов | Целевой файл в types/ |
|------|-----------------|-----------------------|
| Components/ZoneSimulationModal.vue | 5 | types/Simulation.ts |
| Components/PumpCalibrationModal.vue | 5 | types/Calibration.ts |
| Pages/Zones/ZoneDetailModals.vue | 5 | types/Zone.ts (дополнить) |
| Pages/Zones/Tabs/ZoneTelemetryTab.vue | 5 | types/Telemetry.ts (дополнить) |
| Components/GrowCycle/CycleControlPanel.vue | 4 | types/GrowCycle.ts (дополнить) |
| Components/Infrastructure/ChannelBinder.vue | 4 | types/Infrastructure.ts (новый) |
| Components/AutomationProcessPanel.vue | 4 | types/Automation.ts (дополнить) |
| Components/AutomationEngine.vue | 3+ | types/Automation.ts |
| Pages/Recipes/Edit.vue | 4 | types/Recipe.ts (дополнить) |
| Pages/Alerts/Index.vue | 3 | types/Alert.ts (дополнить) |

**Новые файлы типов для создания:**
- `types/Simulation.ts` — типы симуляции зон
- `types/Calibration.ts` — типы калибровки насосов
- `types/Infrastructure.ts` — типы инфраструктуры (ChannelBinder, Planner)
- `types/PageProps.ts` — общие Inertia page props интерфейсы

**Процесс переноса:**
1. Создать/дополнить файл в `types/`
2. Добавить `export` для нового типа
3. Добавить реэкспорт в `types/index.ts`
4. Заменить локальный `interface` в компоненте на `import { ... } from '@/types'`

---

### R3-2 Устранить дублирование типов в Setup Wizard

**Файлы:** 14 файлов `setupWizard*.ts` — у каждого свои типы.

**Действие:** Консолидировать все типы Setup Wizard в `types/SetupWizard.ts`:
```typescript
// types/SetupWizard.ts
export interface SetupWizardStep { ... }
export interface SetupWizardState { ... }
export interface GreenhouseCreationPayload { ... }
export interface ZoneCreationPayload { ... }
// и т.д.
```

Удалить `composables/setupWizardTypes.ts`, заменить все импорты на `@/types`.

---

### R3-3 Унифицировать управление модальными окнами

**Текущая проблема:** Часть модалей управляется через `v-model:show`, часть — через `useModal()`, часть — через локальный `ref<boolean>`.

**Решение:** Принять единый паттерн — все модали через `useModal()`:
```typescript
// composables/useModal.ts — расширить для поддержки payload:
const { isOpen, open, close } = useModal<{ zoneId: number }>()
```

Обновить: `ZoneActionModal`, `GreenhouseCreateModal`, `AttachNodesModal`.

---

### R3-4 Убрать `as any` из API-обработчиков — частично ✅

**Файл:** [composables/useCommands.ts](../../backend/laravel/resources/js/composables/useCommands.ts) строки 108, 190

```typescript
// БЫЛО:
const raw = response.data as any

// СТАЛО:
interface CommandApiResponse {
  data: Command
}
const raw = response.data as CommandApiResponse
```

Типизировать все API-ответы через интерфейсы в `types/`.

---

## Приоритизированный порядок выполнения

```
НЕМЕДЛЕННО (блокируют стабильность в production):
  BUG-1 ✅  ChartBase.vue — утечка EventListener
  BUG-2 ✅  useSystemStatus.ts — утечка setTimeout при rate-limit
  BUG-3 ✅  useOptimisticUpdate.ts — двойной rollback

ВЫСОКИЙ (влияют на корректность функционала):
  BUG-4 ✅  useZoneAutomationTab.ts — race condition версий запросов
  BUG-5 ✅  useKeyboardShortcuts.ts — накопление таймеров
  R1-1 ✅   types/Zone.ts — типизировать activeGrowCycle
  R1-2 ✅   Заменить прямые fetch → useApi (5 файлов)
  R1-3 ✅   Удалить DataTable.vue и Wizards/GrowCycleWizard.vue
  R1-4 ✅   Устранить as any в useZoneShowPage, useCommands, usePlantCreateModal

СРЕДНИЙ (улучшают поддерживаемость):
  R2-1 ✅   Декомпозиция useZoneAutomationTab.ts
  R2-2 ✅   Декомпозиция AutomationProcessPanel.vue
  R2-3 ✅   Декомпозиция useZoneShowPage.ts
  R2-5 ✅   Вынести логику из больших модалей (PumpCalibrationModal, PlantCreateModal)

НИЗКИЙ (техдолг, плановый рефакторинг):
  R2-4 ⚠️   Декомпозиция больших страниц (Recipes/Edit ✅, Alerts/Index ✅, Setup/Wizard, Devices/Show)
  R2-5 ⚠️   GrowthCycleModal (673), ZoneSimulationModal (672) — ещё не декомпозированы
  R3-1      Вынести ~195 локальных типов в types/
  R3-2      Консолидация типов Setup Wizard
  R3-3      Унификация управления модалями
  R3-4 ⚠️   Устранение as any в prod .vue — осталось ~52 из 71 (Recipes/Edit ✅, Alerts ✅,
             HeaderStatusBar ✅, ZoneComparisonModal ✅, Devices/Add ✅)
```

---

## Критерии приёмки каждой фазы

### Фаза 0 (Баги):
- [ ] `npm run typecheck` проходит без новых ошибок
- [ ] В DevTools отсутствуют повторяющиеся EventListener при mount/unmount ChartBase
- [ ] При HTTP 429 интервал здоровья не дублируется
- [ ] Двойной rollback не происходит при timeout

### Фаза 1 (Критичные):
- [ ] `grep -r "\.fetch\(" resources/js/ | grep -v useApi | grep -v node_modules` — 0 результатов
- [ ] `grep -r "DataTable[^V2]" resources/js/` — 0 результатов
- [ ] `Zone.ts` не содержит `activeGrowCycle?: any`

### Фаза 2 (Декомпозиция):
- [ ] Ни один composable не превышает 600 строк
- [ ] Ни один компонент не превышает 400 строк шаблона + скрипта
- [ ] `AutomationProcessPanel.vue` не содержит прямых `fetch` вызовов

### Фаза 3 (Типизация):
- [ ] `grep -r ": any" resources/js/types/` — 0 результатов
- [ ] `grep -rn "as any" resources/js/ | wc -l` — менее 20
- [ ] Все Page компоненты не содержат локальных `interface` определений

---

## Что НЕ трогать

- Структуру `stores/` — хорошо разделена по доменам, не требует изменений
- `useApi.ts` — уже правильная архитектура
- `types/index.ts` — правильный паттерн реэкспорта
- `ws/` — WebSocket интеграция архитектурно корректна
- Базовые UI компоненты (Button, Card, Badge, Modal, Toast) — не требуют рефакторинга
- `composables/simulation/` — корректно декомпозированы (8 файлов, каждый < 300 строк)

---

*Compatible-With: Protocol 2.0, Backend >=3.0, Frontend >=3.0*
