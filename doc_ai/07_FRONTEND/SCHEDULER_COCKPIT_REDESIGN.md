# Scheduler Cockpit UI — Redesign Changelog

**Дата старта:** 2026-04-24
**Статус:** В разработке (Фаза 1)
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
| 0    | PR1 | Feature-flag `scheduler_cockpit_ui`, Inertia share | ✅ |
| 1    | PR1 | 3-колоночная раскладка, 7 новых SFC, legacy fallback | 🚧 |
| 2    | PR2 | Eloquent-модели (`Execution`, `CorrectionWindow`, `AeTask`, `Snapshot`), `ExecutionChainAssembler`, webhook `POST /internal/webhooks/history-logger/execution-event`, `ExecutionChainUpdated` broadcast, `CausalChainPanel.vue` | — |
| 3    | PR3 | Live countdown (RAF), горячие клавиши, Playwright 4 сценария, Lighthouse ≥85 | — |
| 4    | PR4 | Удаление legacy-компонентов, удаление feature-flag | — |

## Инварианты (НЕ ТРОГАТЬ)

- Пайплайн команд: `Laravel scheduler-dispatch → automation-engine → history-logger → MQTT → ESP32`.
- Композабл `useZoneScheduleWorkspace` — публичный API не меняется.
- Формат MQTT-топиков, `message_type`, схемы БД не меняются.
- Роли/политики `canDiagnose`, `canEditAutomation` зеркалятся 1:1.
- `SchedulerHeader`, `SchedulerAttentionPanel`, `SchedulerDiagnostics` переиспользуются.

## Переключение

- `FEATURE_SCHEDULER_COCKPIT_UI=true` в `.env` → cockpit.
- Без переменной или `false` → legacy UI (поведение по умолчанию).
- Rollout поэтапный: dev → engineer → agronomist → operator.
- Откат: сбросить переменную и перезапустить Laravel.

## Файловая карта (Фаза 1)

```
backend/laravel/
├── config/features.php                                  [new]
├── app/Http/Middleware/HandleInertiaRequests.php        [+features share]
└── resources/js/
    ├── composables/
    │   ├── useFeatureFlag.ts                            [new]
    │   ├── deriveLaneHistory.ts                         [new]
    │   └── zoneScheduleWorkspaceTypes.ts                [+LaneHistory types]
    ├── Components/Scheduler/Cockpit/
    │   ├── CockpitLayout.vue                            [new]
    │   ├── HeroCountdown.vue                            [new]
    │   ├── NextUpCard.vue                               [new]
    │   ├── SwimlaneTimeline.vue                         [new]
    │   ├── RecentRunsTable.vue                          [new]
    │   ├── ConfigOnlyFooter.vue                         [new]
    │   └── KpiRow.vue                                   [new]
    └── Pages/Zones/Tabs/
        ├── ZoneSchedulerTab.vue                         [switcher]
        ├── CockpitSchedulerTab.vue                      [new]
        └── LegacySchedulerTab.vue                       [new, копия старого]
```

## Compatible-With

Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
