# Scheduler Cockpit UI — Redesign Changelog

**Дата старта:** 2026-04-24
**Статус:** ✅ Завершён (Фазы 1-4)
**Первоисточник требований:** [SCHEDULER_COCKPIT_IMPLEMENTATION.md](SCHEDULER_COCKPIT_IMPLEMENTATION.md)

## Цель

Заменить одноколоночный `ZoneSchedulerTab.vue` на 3-колоночную cockpit-раскладку
с причинно-следственной цепочкой решений (гибрид A+C).

- **A (Cockpit)** — лицо экрана: слева «сейчас» (таймер + очередь), центр
  (KPI + swimlane + recent runs), справа (attention + causal chain).
- **C (Causal chain)** — drill-down при клике по run: snapshot → decision →
  task → dispatch → running/complete/fail.

## Roadmap

| Фаза | PR | Основное содержимое | Статус |
|------|----|--------------------|--------|
| 0    | PR1 | Feature-flag `scheduler_cockpit_ui`, Inertia share | ✅ (удалено в Ф4) |
| 1    | PR1 | 3-колоночная раскладка, 7 новых SFC, legacy fallback | ✅ |
| 2    | PR2 | Eloquent-модели `AeTask` + `ZoneAutomationIntent`, `ExecutionChainAssembler`, webhook `POST /api/internal/webhooks/history-logger/execution-event`, `ExecutionChainUpdated` broadcast, `CausalChainPanel.vue`, Python `chain_webhook.py` | ✅ |
| 3    | PR3 | Live countdown (RAF), `useSchedulerHotkeys` (J/K/Enter/R/Esc), Playwright 4 сценария, расширенные data-testid | ✅ |
| 3bis | PR3b | Role-aware rollout (`App\Support\FeatureFlags`), когорта 1 по дефолту | ✅ (удалено в Ф4) |
| 4    | PR4 | Rollout завершён: удалены 8 legacy-компонентов, feature-flag, `LegacySchedulerTab`, `FeatureFlags` класс, `useFeatureFlag` composable. Cockpit переименован в `ZoneSchedulerTab`. | ✅ |

## Финальное состояние (после Фазы 4)

- **`ZoneSchedulerTab.vue`** = cockpit-раскладка (раньше `CockpitSchedulerTab.vue`). Никакого switcher'а, один компонент для всех ролей.
- **Фич-флаг `scheduler_cockpit_ui` удалён** полностью: `config/features.php`, `App\Support\FeatureFlags`, `FEATURE_SCHEDULER_COCKPIT_UI*` переменные окружения, shared prop `features`, composable `useFeatureFlag`.
- **Удалённые компоненты:** `LegacySchedulerTab`, `SchedulerStatusStrip`, `SchedulerNextWindow`, `SchedulerRunsColumn`, `SchedulerRunsPanel`, `SchedulerCurrentStateCard`, `SchedulerExecutableWindows`, `SchedulerRunDetail`.
- **Сохранены в `Components/Scheduler/`:** `SchedulerHeader`, `SchedulerStatCounters` (через Header), `SchedulerAttentionPanel`, `SchedulerDiagnostics` — используются cockpit-табом.

## Решения по фазам

### Фаза 2 — отклонения от исходного плана

1. **Нет таблиц `executions`/`correction_windows`/`snapshots`.** Реальная схема БД: `ae_tasks` (главная сущность = "Execution"), `zone_automation_intents` (correlation_id), `zone_events` (snapshot), `commands`. CorrectionWindow — **не отдельная модель**, а группировка полей `ae_tasks.corr_*` + `corr_snapshot_event_id`. Созданы Eloquent-модели `AeTask`, `ZoneAutomationIntent`; `ZoneEvent` и `Command` уже существовали.
2. **`ExecutionChainAssembler` собирает chain из одного `AeTask`-а + linked `ZoneEvent` + ближайшей `Command`.** Для SKIP-решений RUNNING-шаг не добавляется — это сделано явно в `runningStep()`.
3. **WebSocket канал:** `hydro.zone.executions.{zoneId}`, событие `ExecutionChainUpdated`, авторизация переиспользует `authorizeCommandsZone`.
4. **Webhook от history-logger:** `POST /api/internal/webhooks/history-logger/execution-event`, HMAC-SHA256 в заголовках `X-Hydro-Signature` + `X-Hydro-Timestamp` (replay-защита ±300 сек). Debouncing 250мс через `Cache::lock`.
5. **Python `chain_webhook.py` — opt-in helper**, а не вшит в hot-path `command_service.py`. Hook-points включаются постепенно.

### Фаза 3 — Polish

1. **`useRafCountdown`** — собственный composable вместо `@vueuse/core`. RAF + throttle 1 сек + auto-pause на `document.hidden`.
2. **`useSchedulerHotkeys`** — `J/K` (nav), `Enter` (open chain), `R` (refresh), `Esc` (close). Игнорируются внутри `input/textarea` и с модификаторами.
3. **Playwright** `tests/e2e/browser/specs/12-scheduler-cockpit.spec.ts` — 4 сценария.
4. **Lighthouse ≥ 85** — cockpit не уступает legacy (легковеснее, только Tailwind-утилиты).

### Фаза 4 — Cleanup

1. Rollout когорт 1→4 завершён, все роли используют cockpit-UI.
2. **Удалены 8 legacy SFC** + `LegacySchedulerTab.vue` + тесты.
3. **Переименован** `CockpitSchedulerTab.vue` → `ZoneSchedulerTab.vue`, testid `scheduler-cockpit-root` → `scheduler-root`.
4. **Удалена вся feature-flag инфраструктура:** `config/features.php`, `App\Support\FeatureFlags`, `useFeatureFlag.ts`, `FeatureFlagsTest.php`, `ZoneSchedulerTab.switcher.spec.ts`, env-переменные `FEATURE_SCHEDULER_COCKPIT_UI*`, shared prop `features`.
5. **Упрощён** `HandleInertiaRequests` — вернулся к базовому `auth.user` share.

## Инварианты (были сохранены в ходе редизайна)

- Пайплайн команд: `Laravel scheduler-dispatch → automation-engine → history-logger → MQTT → ESP32`.
- Композабл `useZoneScheduleWorkspace` — публичный API не менялся.
- Формат MQTT-топиков, `message_type`, схемы БД не менялись.
- Роли/политики `canDiagnose`, `canEditAutomation` зеркалятся 1:1.

## Current file map (production)

```
backend/laravel/
├── app/
│   ├── Events/ExecutionChainUpdated.php
│   ├── Http/
│   │   ├── Controllers/Api/Internal/HistoryLoggerWebhookController.php
│   │   ├── Controllers/ScheduleExecutionController.php
│   │   ├── Controllers/ScheduleWorkspaceController.php
│   │   └── Middleware/VerifyHistoryLoggerWebhook.php
│   ├── Models/AeTask.php
│   ├── Models/ZoneAutomationIntent.php
│   └── Services/Scheduler/ExecutionChainAssembler.php
├── config/services.php                                      [+history_logger.webhook_secret]
├── routes/api.php                                            [+webhook route]
├── routes/channels.php                                       [+executions channel]
├── tests/Feature/Scheduler/
│   ├── ExecutionChainTest.php
│   └── HistoryLoggerWebhookTest.php
└── resources/js/
    ├── Components/Scheduler/
    │   ├── SchedulerHeader.vue
    │   ├── SchedulerStatCounters.vue
    │   ├── SchedulerAttentionPanel.vue
    │   ├── SchedulerDiagnostics.vue
    │   └── Cockpit/
    │       ├── CockpitLayout.vue
    │       ├── HeroCountdown.vue
    │       ├── NextUpCard.vue
    │       ├── ConfigOnlyFooter.vue
    │       ├── KpiRow.vue
    │       ├── SwimlaneTimeline.vue
    │       ├── RecentRunsTable.vue
    │       └── CausalChainPanel.vue
    ├── composables/
    │   ├── useZoneScheduleWorkspace.ts
    │   ├── zoneScheduleWorkspaceTypes.ts
    │   ├── deriveLaneHistory.ts
    │   ├── useRafCountdown.ts
    │   └── useSchedulerHotkeys.ts
    ├── schemas/execution.ts
    ├── ws/schedulerChainChannel.ts
    └── Pages/Zones/Tabs/ZoneSchedulerTab.vue

backend/services/history-logger/
├── chain_webhook.py
└── test_chain_webhook.py

tests/e2e/browser/specs/
└── 12-scheduler-cockpit.spec.ts
```

## Compatible-With

Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
