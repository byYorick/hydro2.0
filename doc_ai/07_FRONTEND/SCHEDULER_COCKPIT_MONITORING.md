# Scheduler Cockpit UI — мониторинг

**Дата:** 2026-04-24
**Дашборд:** добавляется в `configs/dev/grafana/dashboards/` (следующий PR инфры).

Документ собирает метрики и алерты, через которые операторы и инженеры
контролируют здоровье cockpit-UI планировщика в production.

## 1. Ключевые метрики

Все метрики **уже экспортируются** существующими сервисами — специально для
cockpit новых счётчиков не создавали. Ниже — PromQL-запросы для типовых
вопросов.

### 1.1 WebSocket broadcast cockpit-chain

Счётчик broadcast-событий `ExecutionChainUpdated` (trait `RecordsWsBroadcastMetric`):

```promql
# Events/sec отправленных шагов chain в Reverb
sum by (zone) (rate(laravel_ws_broadcasts_total{event="ExecutionChainUpdated"}[1m]))

# Успех доставки (если есть latency-метрика):
histogram_quantile(0.95,
  sum by (le) (rate(laravel_ws_broadcast_latency_seconds_bucket{event="ExecutionChainUpdated"}[5m])))
```

### 1.2 Webhook от history-logger → Laravel

```promql
# Rate входящих webhook-событий (по шагам chain)
sum by (step) (rate(laravel_api_requests_total{route="/api/internal/webhooks/history-logger/execution-event"}[1m]))

# 5xx на webhook (алерт при >0 в течение 5 мин)
sum(rate(laravel_api_requests_total{route="/api/internal/webhooks/history-logger/execution-event",status=~"5.."}[5m]))

# 401/422 (auth-drift или misalignment с контрактом)
sum(rate(laravel_api_requests_total{route="/api/internal/webhooks/history-logger/execution-event",status=~"401|422"}[5m]))
```

### 1.3 Latency chain-API для UI

```promql
# p95 GET /api/zones/{id}/executions/{id}
histogram_quantile(0.95,
  sum by (le) (rate(laravel_api_duration_seconds_bucket{route=~".*executions/.*"}[5m])))

# p95 GET /api/zones/{id}/schedule-workspace
histogram_quantile(0.95,
  sum by (le) (rate(laravel_api_duration_seconds_bucket{route=~".*schedule-workspace"}[5m])))
```

### 1.4 Retry endpoint

```promql
# Count retry запросов за час
sum(rate(laravel_api_requests_total{route=~".*executions/.*retry",status="201"}[1h])) * 3600

# Отклонения retry (409/422/404)
sum by (status) (rate(laravel_api_requests_total{route=~".*executions/.*retry",status=~"4.."}[5m]))
```

### 1.5 AE3 / Command pipeline (уже есть в проде)

```promql
# Команды/сек, отправленные из history-logger в MQTT
sum by (metric) (rate(history_logger_commands_sent_total[1m]))

# FAIL-runs на зону (из AE3 task-ов)
sum by (zone) (increase(ae_tasks_terminal_total{status="failed"}[1h]))
```

## 2. Алерты (Prometheus rule stubs)

Добавить в `configs/dev/alertmanager/rules/cockpit.yml`:

```yaml
groups:
  - name: scheduler_cockpit
    rules:
      - alert: CockpitWebhook5xx
        expr: |
          sum(rate(laravel_api_requests_total{
            route="/api/internal/webhooks/history-logger/execution-event",
            status=~"5.."
          }[5m])) > 0
        for: 5m
        labels:
          severity: warning
          component: scheduler-cockpit
        annotations:
          summary: "history-logger webhook возвращает 5xx"
          description: |
            Webhook от history-logger в Laravel возвращает ошибки 5xx. Live-обновления
            chain в cockpit-UI могут не работать. Проверить логи laravel + history-logger.

      - alert: CockpitExecutionLatencyP95
        expr: |
          histogram_quantile(0.95,
            sum by (le) (rate(laravel_api_duration_seconds_bucket{
              route=~".*executions/.*"
            }[5m]))
          ) > 0.5
        for: 10m
        labels:
          severity: warning
          component: scheduler-cockpit
        annotations:
          summary: "GET /executions p95 > 500ms"
          description: |
            ExecutionChainAssembler медленно собирает цепочку (возможно N+1).
            Проверить `DB::enableQueryLog()` + eager-load в AeTask/Command.

      - alert: CockpitRetrySpike
        expr: |
          sum(rate(laravel_api_requests_total{
            route=~".*executions/.*retry",
            status="201"
          }[1h])) * 3600 > 20
        for: 15m
        labels:
          severity: info
          component: scheduler-cockpit
        annotations:
          summary: "Много retry'ев — возможна регрессия AE3"
          description: |
            >20 retry запросов за час. Посмотреть FAIL-trends по зоне + logs AE3.
```

## 3. Grafana dashboard — что показать

Минимальный набор панелей для `Scheduler Cockpit Health`:

| Панель | Запрос | Цель |
|---|---|---|
| WS broadcasts rate | `sum(rate(laravel_ws_broadcasts_total{event="ExecutionChainUpdated"}[1m]))` | Видно что live-обновления идут |
| Webhook rate / status | `sum by (status) (rate(laravel_api_requests_total{route="/api/internal/webhooks/history-logger/execution-event"}[1m]))` | Health канала Python → Laravel |
| Execution GET p50/p95 | histogram_quantile от `laravel_api_duration_seconds_bucket` | Скорость открытия chain в UI |
| FAIL runs / retry rate | см. §1.4, §1.5 | Сколько пользователи жмут retry |
| JS errors (Sentry) | Sentry panel, tag: `component=scheduler-cockpit` | Exceptions на фронте |

## 4. Операционные runbook-шаги

**Если `CockpitWebhook5xx` загорелся:**
1. `docker compose ... logs --tail=200 history-logger | grep chain_webhook` — посмотреть ошибки клиента.
2. `docker compose ... logs --tail=200 laravel | grep "history-logger webhook"` — ошибки на стороне Laravel.
3. Проверить `HISTORY_LOGGER_WEBHOOK_SECRET` одинаков в обеих средах.
4. Если есть 401 — секрет разошёлся; если 422 — контракт не совпал (возможно, обновить `chain_webhook.py` / PHP controller совместно).
5. Временный воркараунд: `HISTORY_LOGGER_WEBHOOK_ENABLED=0` в env history-logger → live-обновления выключатся, chain подгружается только polling'ом.

**Если `CockpitExecutionLatencyP95` загорелся:**
1. Проверить размер `ae_tasks` и `zone_events` (скорее всего retention cleanup отстал).
2. Проверить `ExecutionChainAssembler` на N+1 (`DB::enableQueryLog()`).
3. Добавить missing indexes на `ae_tasks.corr_snapshot_cmd_id`, `ae_tasks.intent_id`, `commands.cmd_id`.

## 5. Что ещё не покрыто метрикой

- **Task-chain orphan rate** — webhook с `unresolved=true` (cmd_id не найден). Если увеличивается — indicates сбои в pipeline AE3 (команды публикуются раньше чем task создаётся). Пока логируется info-level в Laravel; при необходимости — добавить counter `scheduler_cockpit_webhook_unresolved_total`.
- **UI engagement** — сколько раз открывают chain, сколько retry-кликов. Можно добавить frontend-events через `PipelineMetricsService::trackUiAction()` (если такая facility есть).

## 6. Changelog метрик

| Дата | Изменение |
|---|---|
| 2026-04-24 | Первый выпуск после Фазы 4 rollout + webhook hook-points |
