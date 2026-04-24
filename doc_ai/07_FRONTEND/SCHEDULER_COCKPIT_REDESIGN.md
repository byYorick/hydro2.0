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
| 1    | PR1 | 3-колоночная раскладка, 7 новых SFC, legacy fallback | ✅ |
| 2    | PR2 | Eloquent-модели `AeTask` + `ZoneAutomationIntent`, `ExecutionChainAssembler`, webhook `POST /api/internal/webhooks/history-logger/execution-event`, `ExecutionChainUpdated` broadcast, `CausalChainPanel.vue`, Python `chain_webhook.py` | ✅ |
| 3    | PR3 | Live countdown (RAF), горячие клавиши, Playwright 4 сценария, Lighthouse ≥85 | — |
| 4    | PR4 | Удаление legacy-компонентов, удаление feature-flag | — |

## Решения Фазы 2 (отклонения от исходного плана)

1. **Нет таблиц `executions`/`correction_windows`/`snapshots`.** Реальная схема БД: `ae_tasks` (главная сущность = "Execution"), `zone_automation_intents` (correlation_id), `zone_events` (snapshot), `commands`. CorrectionWindow — **не отдельная модель**, а группировка полей `ae_tasks.corr_*` + `corr_snapshot_event_id`. Соответственно создали Eloquent-модели `AeTask`, `ZoneAutomationIntent`, а `ZoneEvent` и `Command` уже существовали.
2. **`ExecutionChainAssembler` собирает chain из одного `AeTask`-а + linked `ZoneEvent` (snapshot) + ближайшей `Command` (dispatch).** Для SKIP-решений RUNNING-шаг не добавляется — это сделано явно в `runningStep()`.
3. **WebSocket канал:** `hydro.zone.executions.{zoneId}`, событие `ExecutionChainUpdated`, авторизация переиспользует `authorizeCommandsZone` (тот же ZoneAccess-чек).
4. **Webhook от history-logger:** `POST /api/internal/webhooks/history-logger/execution-event`, HMAC-SHA256 в заголовках `X-Hydro-Signature` + `X-Hydro-Timestamp` (replay-защита ±300 сек). Secret: `services.history_logger.webhook_secret`. Debouncing 250мс через `Cache::lock`.
5. **Python `chain_webhook.py` сделан opt-in helper**, а не вшит в hot-path `command_service.py`. Конкретные hook-points (DISPATCH/RUNNING/COMPLETE/FAIL) включаются по мере валидации пайплайна и отдельными коммитами — чтобы не внести регрессию в production-публикацию команд.
6. **CausalChainPanel.vue встроен в `CockpitSchedulerTab`** — при клике на run в `RecentRunsTable` справа открывается chain с живыми обновлениями через WS-подписку.

## Файловая карта (Фаза 2, PR2)

```
backend/laravel/
├── app/
│   ├── Events/ExecutionChainUpdated.php                    [new]
│   ├── Http/
│   │   ├── Controllers/Api/Internal/HistoryLoggerWebhookController.php  [new]
│   │   ├── Controllers/ScheduleExecutionController.php     [+chain]
│   │   ├── Controllers/ScheduleWorkspaceController.php     [+chain в active_run]
│   │   └── Middleware/VerifyHistoryLoggerWebhook.php       [new]
│   ├── Models/AeTask.php                                   [new]
│   ├── Models/ZoneAutomationIntent.php                     [new]
│   └── Services/Scheduler/ExecutionChainAssembler.php      [new]
├── bootstrap/app.php                                        [+middleware alias, csrf except]
├── config/services.php                                      [+history_logger.webhook_secret]
├── routes/api.php                                           [+webhook route]
├── routes/channels.php                                      [+executions channel]
└── resources/js/
    ├── Components/Scheduler/Cockpit/CausalChainPanel.vue    [new]
    ├── composables/zoneScheduleWorkspaceTypes.ts            [+ChainStep types]
    ├── schemas/execution.ts                                 [new Zod schemas]
    ├── ws/schedulerChainChannel.ts                          [new WS client]
    └── Pages/Zones/Tabs/CockpitSchedulerTab.vue             [+WS subscription + panel]

backend/services/history-logger/
├── chain_webhook.py                                         [new Laravel webhook client]
└── test_chain_webhook.py                                    [new pytest]
```

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
