# Рефакторинг вкладки Автоматика (ZoneAutomationTab)

> Статус: PARTIALLY IMPLEMENTED / SUPERSEDED BY SCHEDULE WORKSPACE
> Ветка: ae3
> Связано с: аудит зоны 447, исправления #2/#3/#7/#8

---

## 1. Контекст и мотивация

Текущая вкладка `ZoneAutomationTab.vue` (747 строк) и сопутствующий orchestrator
`useZoneAutomationTab.ts` накопили технический долг:

| Проблема | Где |
|---|---|
| Монолит 747 строк | `ZoneAutomationTab.vue` |
| Производный код `SetupStages` парсит `reason_code` из WebSocket-событий | `useAutomationPanel.ts:174+` |
| SetupStageCode не совпадает с реальными workflow_phase | `Automation.ts:95` vs `api_automation_state_constants.py` |
| Новые события (stale reset, recovery) не отображаются в timeline | `AUTOMATION_EVENT_LABELS` |
| pH tolerance (5%) не показывается в UI | `ZoneAutomationTab.vue` |
| Developer-инструменты (Scheduler / Intent Lifecycle) смешаны с операционным UI | `ZoneAutomationTab.vue:443+` |
| `useZoneAutomationTab` экспортирует >30 сущностей из одного файла | `useZoneAutomationTab.ts` |

После исправлений #2/#3/#7/#8 backend изменился:
- `workflow_state_store.get_with_stale_reset()` — авто-сброс залипших зон (новые события: `WORKFLOW_RECOVERY_STALE_STOPPED`, `stale_safety_reset`)
- `check_water_level()` bypass при `level==0.0` в фазах `irrig_recirc`/`irrigating`
- `ph_pct` default снижен с 15% до 5% → другой допуск при оценке готовности раствора

---

## 2. Что НЕ меняется

- Маршруты Laravel API для automation runtime (`/api/zones/{zone}/state`, `/control-mode`, `/manual-step`)
- Контракт `AutomationState` — AE отдаёт те же поля
- WebSocket каналы и имена событий (`Echo`, `Reverb`)
- `AutomationProcessDiagram.vue` — оставить как есть (SVG-диаграмма 2-баков)
- `PidConfigForm`, `RelayAutotuneTrigger`, `PumpCalibrationsPanel` — не трогать

Отдельное уточнение после zero-legacy cutover:
- scheduler/execution operator UI вынесен в `ZoneSchedulerTab.vue`;
- публичный контракт `/api/zones/{zone}/scheduler-tasks*` удалён и заменён на `schedule-workspace` + `executions/{executionId}`.

---

## 3. Целевая структура вкладки

```
ZoneAutomationTab.vue  (orchestrator, ~150 строк)
├── AutomationWorkflowCard.vue           [NEW] — текущий workflow phase + метки
│     ├── Pill: state_label (IDLE / TANK_FILLING / ...)
│     ├── Stale-reset badge (если state_meta.is_stale)
│     └── AutomationProcessPanel (раскрывающийся, без изменений)
│
├── AutomationProfileCard.vue            [NEW] — KPI параметры (было hero-секция)
│     ├── Климат (мин/макс %, интервал)
│     ├── Вода (pH target, EC target, tolerance%, объёмы)
│     └── Кнопка "Редактировать" → ZoneAutomationEditWizard
│
├── AutomationQuickActionsCard.vue       [NEW] — операционные быстрые команды
│     └── Полив / Климат / Свет / pH / EC
│
├── AutomationControlModeCard.vue        [EXTRACT из вкладки]
│     ├── Переключатель auto/semi/manual
│     └── Ручные шаги (grid 4 колонки)
│
├── PidConfigForm, RelayAutotuneTrigger, PumpCalibrationsPanel  [без изменений]
│
├── AutomationSchedulerDevCard.vue       [EXTRACT + свернуть по умолчанию]
│     └── <details> collapsed by default — developer tool
│
└── AIPredictionsSection                 [без изменений]
```

---

## 4. Задачи

### 4.1 Типы — выровнять с backend (`Automation.ts`)

**Текущая проблема:**
```typescript
// Automation.ts:95 — SetupStageCode не совпадает с workflow_phase
export type SetupStageCode = 'clean_fill' | 'solution_fill' | 'parallel_correction' | 'setup_transition'

// Backend (api_automation_state_constants.py) — реальные фазы:
// IDLE → TANK_FILLING → TANK_RECIRC → READY → IRRIGATING → IRRIG_RECIRC
```

**Исправление:**
1. Переименовать `SetupStageCode` → `WorkflowStageCode` и выровнять с backend:
   ```typescript
   export type WorkflowStageCode =
     | 'tank_filling'   // было: clean_fill
     | 'tank_recirc'    // было: solution_fill
     | 'ready'          // было: parallel_correction
     | 'irrigating'     // было: setup_transition
     | 'irrig_recirc'   // NEW
   ```
2. Маппинг `AutomationStateType` → `WorkflowStageCode` сделать через словарь, не через парсинг `reason_code`.
3. Добавить новые события в `AUTOMATION_EVENT_LABELS`:
   ```typescript
   WORKFLOW_RECOVERY_STALE_STOPPED: 'Залипшая фаза сброшена (авто-восстановление)',
   WORKFLOW_RECOVERY_ENQUEUED: 'Рабочий процесс возобновлён после рестарта',
   WORKFLOW_RECOVERY_WORKFLOW_FALLBACK: 'Workflow переключён на резервный при восстановлении',
   ```

**Файлы:** `types/Automation.ts`, `composables/useAutomationPanel.ts`

---

### 4.2 `useAutomationPanel.ts` — убрать хрупкое производное состояние SetupStages

**Текущая проблема:** `setupStageCodeFromReason()` парсит `reason_code` из событий (`clean_fill_`, `solution_fill_`, etc.) → ломается при изменении reason_code.

**Решение:** Выводить стадии напрямую из `state: AutomationStateType`:

```typescript
function deriveWorkflowStages(state: AutomationStateType): WorkflowStageView[] {
  const ALL_STAGES: WorkflowStageCode[] = ['tank_filling', 'tank_recirc', 'ready', 'irrigating', 'irrig_recirc']
  const ORDER: Record<AutomationStateType, number> = {
    IDLE: -1, TANK_FILLING: 0, TANK_RECIRC: 1, READY: 2, IRRIGATING: 3, IRRIG_RECIRC: 4,
  }
  const current = ORDER[state]
  return ALL_STAGES.map((code, idx) => ({
    code,
    label: WORKFLOW_STAGE_LABELS[code],
    status: idx < current ? 'completed' : idx === current ? 'running' : 'pending',
  }))
}
```

**Файлы:** `composables/useAutomationPanel.ts`, `types/Automation.ts`

---

### 4.3 `AutomationWorkflowCard.vue` — новый компонент статуса workflow

Вынести блок "workflow / Процесс выполнения автоматизации" в отдельный компонент.

**Содержимое:**
```vue
<template>
  <section class="surface-card ...">
    <!-- Заголовок с текущей фазой -->
    <div class="flex items-center gap-3">
      <WorkflowPhasePill :state="automationState.state" />
      <span class="text-sm text-dim">{{ automationState.state_label }}</span>
      <!-- Stale badge — NEW: показываем когда is_stale -->
      <Badge v-if="automationState.state_meta?.is_stale" variant="warning" class="text-xs">
        кэш{{ staleDuration ? ` · ${staleDuration}` : '' }}
      </Badge>
    </div>

    <!-- Прогресс-бар (если есть estimated_completion_sec) -->
    <ProgressBar v-if="hasProgress" :percent="progressPercent" />

    <!-- Индикатор ноды (irr_node_state) -->
    <IrrNodeStatusRow v-if="irrNodeState" :state="irrNodeState" />

    <!-- Раскрывающийся AutomationProcessPanel -->
    <Disclosure>
      <AutomationProcessPanel ... />
    </Disclosure>
  </section>
</template>
```

**Файлы:** `Components/AutomationWorkflowCard.vue` [NEW]

---

### 4.4 `AutomationProfileCard.vue` — KPI с отображением tolerance

Вынести KPI-секцию ("Профиль управления") и добавить отображение pH tolerance.

**Добавить в карточку "Коррекция pH/EC":**
```vue
<article class="ui-kpi-card">
  <div class="ui-kpi-label">Коррекция pH / EC</div>
  <div class="ui-kpi-value !text-lg">
    pH {{ waterForm.targetPh.toFixed(2) }} · EC {{ waterForm.targetEc.toFixed(1) }}
  </div>
  <!-- NEW: показывать tolerance -->
  <div class="ui-kpi-hint">
    Допуск pH ±{{ phToleranceAbs.toFixed(2) }} ({{ waterForm.phPct ?? 5 }}%)
    · EC ±{{ ecToleranceAbs.toFixed(2) }} ({{ waterForm.ecPct ?? 10 }}%)
  </div>
</article>
```

где `phToleranceAbs = waterForm.targetPh * (waterForm.phPct ?? 5) / 100`.

**Файлы:** `Components/AutomationProfileCard.vue` [NEW], `composables/zoneAutomationTypes.ts`

---

### 4.5 `AutomationControlModeCard.vue` — вынести управление режимом

Секция "Режим управления 2-баками" (строки 250–389 `ZoneAutomationTab.vue`) выносится в отдельный компонент.

Изменения внутри:
- Кнопки ручных шагов: убрать хардкод 8 кнопок, генерировать из `allowed_manual_steps` (приходит от AE):
  ```typescript
  const MANUAL_STEP_LABELS: Record<AutomationManualStep, string> = {
    clean_fill_start: 'Набрать чистую воду',
    clean_fill_stop: 'Стоп набор чистой',
    solution_fill_start: 'Набрать раствор',
    solution_fill_stop: 'Стоп набор раствора',
    prepare_recirculation_start: 'Старт рециркуляции setup',
    prepare_recirculation_stop: 'Стоп рециркуляции setup',
    irrigation_recovery_start: 'Старт рециркуляции полива',
    irrigation_recovery_stop: 'Стоп рециркуляции полива',
  }
  ```
- Показывать только те кнопки, что есть в `allowed_manual_steps` (сейчас показываются все 8, просто disabled).

**Файлы:** `Components/AutomationControlModeCard.vue` [NEW]

---

### 4.6 Scheduler lifecycle — вынести из Automation Tab

Итоговое направление после cutover:
- секция `Scheduler / Intent Lifecycle` не должна жить внутри `ZoneAutomationTab.vue`;
- operator flow `Plan + Execution` вынесен в отдельную вкладку `ZoneSchedulerTab.vue`;
- automation tab остаётся runtime-ориентированной и не содержит detail-view по execution run.

**Файлы:** `Pages/Zones/Tabs/ZoneSchedulerTab.vue`, `composables/useZoneScheduleWorkspace.ts`

---

### 4.7 Разбить `useZoneAutomationTab.ts`

Текущий `useZoneAutomationTab.ts` — god-composable: импортирует 3 composable и переэкспортирует 30+ сущностей.

**Стратегия:** Убрать транзитный экспорт. Компоненты импортируют напрямую нужные composable:

```
ZoneAutomationTab.vue
  ├── useZoneAutomationState()      → climateForm, waterForm, lightingForm
  ├── useZoneAutomationApi()        → applyAutomationProfile, runManualXxx
  └── useZoneAutomationScheduler()  → control-mode snapshot, manual-step sync

ZoneSchedulerTab.vue
  └── useZoneScheduleWorkspace()    → schedule workspace, recent runs, execution detail

AutomationControlModeCard.vue
  └── useAutomationPanel() → automationState, automationControlMode, setAutomationControlMode, runManualStep

AutomationWorkflowCard.vue
  └── useAutomationPanel() → automationState, stale, irrNodeState, workflowStages
```

**Файлы:** `composables/useZoneAutomationTab.ts` (упростить), `composables/useZoneAutomationState.ts`, `composables/useZoneAutomationApi.ts`, `composables/useZoneAutomationScheduler.ts`, `composables/useZoneScheduleWorkspace.ts`

---

### 4.8 Timeline — добавить новые события

В `useAutomationPanel.ts` и `Components/AutomationTimeline.vue` добавить лейблы для новых событий, возникших в ходе исправлений #2/#3:

```typescript
// useAutomationPanel.ts — AUTOMATION_EVENT_LABELS
WORKFLOW_RECOVERY_STALE_STOPPED: 'Залипшая фаза сброшена (авто-восстановление)',
WORKFLOW_RECOVERY_ENQUEUED: 'Workflow возобновлён после рестарта AE',
WORKFLOW_RECOVERY_WORKFLOW_FALLBACK: 'Workflow переключён на резервный',
```

**Файлы:** `composables/useAutomationPanel.ts`

---

## 5. Порядок реализации

| Шаг | Задача | Файлы | Тесты |
|-----|--------|-------|-------|
| 1 | Обновить типы `Automation.ts` (WorkflowStageCode + новые события) | `types/Automation.ts` | `ZoneAutomationTab.spec.ts` |
| 2 | Рефакторинг `useAutomationPanel` — заменить SetupStages → WorkflowStages из state | `composables/useAutomationPanel.ts` | `AutomationProcessPanel.spec.ts` |
| 3 | Создать `AutomationWorkflowCard.vue` — вынести workflow блок | `Components/AutomationWorkflowCard.vue` | visual |
| 4 | Создать `AutomationProfileCard.vue` — KPI + tolerance display | `Components/AutomationProfileCard.vue` | visual |
| 5 | Создать `AutomationControlModeCard.vue` — режим + ручные шаги | `Components/AutomationControlModeCard.vue` | `ZoneAutomationTab.spec.ts` |
| 6 | Создать `AutomationSchedulerDevCard.vue` — свернуть scheduler | `Components/AutomationSchedulerDevCard.vue` | — |
| 7 | Обновить `ZoneAutomationTab.vue` — заменить секции на компоненты | `Pages/Zones/Tabs/ZoneAutomationTab.vue` | `ZoneAutomationTab.spec.ts` |
| 8 | Упростить `useZoneAutomationTab.ts` — убрать транзитный реэкспорт | `composables/useZoneAutomationTab.ts` | typecheck |
| 9 | Добавить лейблы новых событий в `useAutomationPanel.ts` | `composables/useAutomationPanel.ts` | — |

---

## 6. Инварианты / что должно работать после рефакторинга

1. Workflow panel показывает текущую фазу (`state_label`) из `/zones/{id}/state`
2. Stale badge отображается когда `state_meta.is_stale = true`
3. Ручные шаги отображаются только те, что в `allowed_manual_steps` (от AE)
4. Timeline показывает новые события: `WORKFLOW_RECOVERY_STALE_STOPPED`, `WORKFLOW_RECOVERY_ENQUEUED`
5. KPI карточка Коррекция pH/EC показывает tolerance% (5% по умолчанию)
6. `npm run typecheck` — 0 ошибок
7. `npm run test` — все существующие тесты проходят

---

## 7. Что НЕ делается в этом рефакторинге

- Не изменяется backend API (только фронт)
- Не изменяется `AutomationProcessDiagram.vue` (SVG-диаграмма)
- Не изменяется `AutomationTimeline.vue` (только добавляются лейблы)
- Не изменяется мастер редактирования `ZoneAutomationEditWizard.vue`
- Не добавляются новые API endpoints
- Не делается i18n (только русские строки как сейчас)

---

## 8. Связанные файлы

### Frontend
- `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneAutomationTab.vue`
- `backend/laravel/resources/js/composables/useZoneAutomationTab.ts`
- `backend/laravel/resources/js/composables/useAutomationPanel.ts`
- `backend/laravel/resources/js/types/Automation.ts`
- `backend/laravel/resources/js/composables/zoneAutomationTypes.ts`

### Backend (источники данных)
- `backend/services/automation-engine/ae3lite/runtime/app.py` — `/state`, `/control-mode`, `/manual-step`
- `backend/services/automation-engine/ae3lite/application/use_cases/get_zone_automation_state.py` — runtime state/read-model
- `backend/services/automation-engine/ae3lite/infrastructure/repositories/zone_workflow_repository.py` — canonical `zone_workflow_state`

### Тесты frontend
- `backend/laravel/resources/js/Pages/Zones/Tabs/__tests__/ZoneAutomationTab.spec.ts`
- `backend/laravel/resources/js/Components/__tests__/AutomationProcessPanel.spec.ts`
- `backend/laravel/resources/js/Components/__tests__/AutomationProcessPanel.realtime.spec.ts`
