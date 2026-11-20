# API_MAPPING.md
# Frontend ↔ Laravel: действующие точки интеграции

**Сверено с кодом:** 2026-11-07. Карта описывает текущие клиенты и consumers; полный перечень маршрутов и прав — [REST_API_REFERENCE.md](../04_BACKEND_CORE/REST_API_REFERENCE.md).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## HTTP-клиент

Компоненты используют `api` из [services/api/index.ts](../../backend/laravel/resources/js/services/api/index.ts).
Доменные модули обращаются к `_client.ts`, который распаковывает response envelope.
[utils/apiClient.ts](../../backend/laravel/resources/js/utils/apiClient.ts) добавляет `/api`, cookies/CSRF и обработку ошибок. Web UI работает с Laravel-сессией; служебные токены Python не передаются браузеру.

Пути в таблице указаны с `/api`; аргументы клиента могут задаваться без этого префикса.

| Сценарий | Consumer / клиент | Маршрут Laravel |
|---|---|---|
| Поиск зон, нод, рецептов | [useCommandPaletteSearch.ts](../../backend/laravel/resources/js/composables/useCommandPaletteSearch.ts) | `GET /api/zones`, `/api/nodes`, `/api/recipes` с `search` |
| Мастер запуска | [launchFlow.ts](../../backend/laravel/resources/js/services/api/launchFlow.ts), `Pages/Launch/Index.vue` | `GET /api/launch-flow/manifest`, `POST /api/zones/{id}/grow-cycles` |
| Жизненный цикл выращивания | [growCycles.ts](../../backend/laravel/resources/js/services/api/growCycles.ts) | `POST /api/grow-cycles/{id}/{start,pause,resume,advance-phase,harvest,abort,change-recipe-revision}` |
| Состояние автоматики | [useAutomationPanel.ts](../../backend/laravel/resources/js/composables/useAutomationPanel.ts), [zones.ts](../../backend/laravel/resources/js/services/api/zones.ts) | `GET /api/zones/{id}/state`, `/control-mode`, `/health`, `/snapshot` |
| Запуск и ручные этапы | `zones.ts` | `POST /api/zones/{id}/{start-cycle,start-irrigation,start-solution-topup,start-solution-change,control-mode,manual-step}` |
| Scheduler workspace | [useZoneScheduleWorkspace.ts](../../backend/laravel/resources/js/composables/useZoneScheduleWorkspace.ts), `zones.ts` | `GET /api/zones/{id}/schedule-workspace`, `/executions/{executionId}` |
| Повтор execution | `zones.ts` | `POST /api/zones/{id}/executions/{executionId}/retry` |
| Scheduler diagnostics | `zones.ts` | `GET /api/zones/{id}/scheduler-diagnostics` (`admin/engineer`) |
| Команды и их статусы | [useCommands.ts](../../backend/laravel/resources/js/composables/useCommands.ts), [commands.ts](../../backend/laravel/resources/js/services/api/commands.ts) | `POST /api/zones/{id}/commands`, `/api/nodes/{id}/commands`; `GET /api/commands/{id}/status` |
| Ноды, config, каналы | [nodes.ts](../../backend/laravel/resources/js/services/api/nodes.ts) | `/api/nodes`, `/api/nodes/{id}`, `/config`, `/config/publish`, `/live-mqtt-status` с методами из клиента |
| История телеметрии | [useTelemetry.ts](../../backend/laravel/resources/js/composables/useTelemetry.ts) | `GET /api/zones/{id}/telemetry/history` (`useTelemetry`), `/api/nodes/{id}/telemetry/history` (`nodes.ts`) |
| Агрегаты Dashboard | [telemetry.ts](../../backend/laravel/resources/js/services/api/telemetry.ts) | `GET /api/telemetry/aggregates` |
| Климат теплицы | [greenhouses.ts](../../backend/laravel/resources/js/services/api/greenhouses.ts) | `GET /api/greenhouses/{id}/climate/state`; `POST /climate/control-mode`, `POST/DELETE /climate/manual-override` под тем же greenhouse prefix |
| Authority документы | [automationConfigs.ts](../../backend/laravel/resources/js/services/api/automationConfigs.ts), [automationBundles.ts](../../backend/laravel/resources/js/services/api/automationBundles.ts) | `/api/automation-configs/{scopeType}/{scopeId}/{namespace}`, `/api/automation-bundles/{scopeType}/{scopeId}` |
| Алерты | [alerts.ts](../../backend/laravel/resources/js/services/api/alerts.ts) | `GET /api/alerts`, `PATCH /api/alerts/{id}/ack` (статус остаётся ACTIVE), `PATCH /api/alerts/{id}/resolve` |

Поиск, `telemetry/aggregates`, Echo и scheduler workspace уже реализованы. Списки «недостающих endpoints для волн» из прежнего документа не являются текущими требованиями. `scheduler-tasks`, `attach-recipe` и `automation/manual-resume` не используются как канонический production flow.

## Realtime

Laravel Echo/Pusher настраивается в [echoClient.ts](../../backend/laravel/resources/js/utils/echoClient.ts).
Подписками и их очисткой управляют [managedChannelEvents.ts](../../backend/laravel/resources/js/ws/managedChannelEvents.ts) и shared-channel helpers. Авторизацию каналов задаёт [routes/channels.php](../../backend/laravel/routes/channels.php).

| Канал (имя без транспортного `private-`) | Назначение |
|---|---|
| `hydro.zones.{zoneId}` | Состояние зоны, telemetry и zone events |
| `hydro.commands.{zoneId}`, `hydro.commands.global` | Изменения статуса команд |
| `hydro.events.global` | Глобальные события |
| `hydro.devices` | Обновления устройств |
| `hydro.alerts` | Изменения алертов |
| `hydro.zone.executions.{zoneId}` | Causal chain execution |

`commands.{zoneId}` и `commands.global` также зарегистрированы в backend как aliases; новые consumers используют актуальные `hydro.*` имена. Наличие канала не даёт доступ ко всем зонам: backend проверяет пользователя и scope.

`useAutomationPanel` подписывается на command status, `useZoneScheduleWorkspace` — на zonal control-mode events и обновляет REST workspace. REST snapshot/polling остаётся частью синхронизации; payload WebSocket нельзя подменять выдуманной структурой из примера.

## Проверка изменений

При изменении клиента сверяй метод, URL, request/response и права с `routes/api.php`, контроллером и типами DTO. Для событий дополнительно сверяй `broadcastOn`, `broadcastAs`, channel authorization и consumer. Рабочие сценарии тестирования — [FRONTEND_TESTING.md](FRONTEND_TESTING.md).
