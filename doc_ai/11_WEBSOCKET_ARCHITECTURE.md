# WebSocket Architecture

**Stack:** Laravel Reverb (self-hosted Pusher-compatible, port 6001) + Laravel Echo (Pusher.js) on frontend.
**Queue:** All broadcasts use Redis queue `broadcasts`.
**Auth:** Большинство каналов — `private` (требуют `POST /broadcasting/auth` с Sanctum session или Bearer token). Public: `hydro.alerts`; Conditionally public: `hydro.devices` (application-level role-gate `admin`/`agronomist`).
**Дата обновления:** 2026-05-28 (sync с реальным кодом: добавлен `hydro.zone.executions.*`, уточнены auth-уровни каналов, Laravel class-name event listeners).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## Channels

| Channel | Type | Renamed from | Events broadcast | Who subscribes |
|---------|------|-------------|-----------------|----------------|
| `hydro.zones.{zoneId}` | Private | — | TelemetryBatchUpdated, NodeTelemetryUpdated, NodeConfigUpdated, AlertCreated, AlertUpdated, GrowCycleUpdated, ZoneUpdated, EventCreated (zone-scoped) | Users with zone access |
| `hydro.zone.executions.{zoneId}` | Private | — | ExecutionChainUpdated (Scheduler Cockpit causal chain) | Users with zone access |
| `hydro.commands.{zoneId}` | Private | `commands.{zoneId}` *(deprecated alias)* | CommandStatusUpdated, CommandFailed | Users with zone access |
| `hydro.commands.global` | Private | `commands.global` *(deprecated alias)* | CommandStatusUpdated, CommandFailed (no zone) | All authenticated users |
| `hydro.events.global` | Private | `events.global` *(deprecated alias)* | EventCreated (global) | All authenticated users |
| `hydro.alerts` | Public | — | AlertCreated, AlertUpdated | Any (no auth needed) |
| `hydro.devices` | Public + app-gate | — | NodeTelemetryUpdated, NodeConfigUpdated (no zone) | `admin`, `agronomist` |

**Authorization** (`backend/laravel/routes/channels.php`):
- Zone channels (`hydro.zones.{id}`, `hydro.zone.executions.{id}`, `hydro.commands.{id}`) check `ZoneAccessHelper::canAccessZone()` + role in `['viewer', 'operator', 'admin', 'agronomist', 'engineer']`
- `hydro.devices` — public канал на уровне broadcasting, но клиент применяет role-check `admin`/`agronomist` (несёт unassigned device snapshot)
- Global private channels (`hydro.events.global`, `hydro.commands.global`) require authenticated user + valid role
- `hydro.alerts` — public, без auth, любой клиент может подписаться
- Auth failures return `false` (403), DB errors return `false` instead of throwing

---

## Events

### `telemetry.batch.updated` → `TelemetryBatchUpdated`

**Channel:** `hydro.zones.{zoneId}`
**Source:** Two paths (see [Dual Dispatch](#telemetrybatchupdated-dual-dispatch))

```json
{
  "zone_id": 1,
  "updates": [
    {
      "node_id": 5,
      "channel": "ai2-ph-probe",
      "metric_type": "PH",
      "value": 6.8,
      "ts": 1704067200000
    }
  ],
  "event_id": 12345678,
  "server_ts": 1704067200123
}
```

Batch limits: max 200 updates, max 256 KB (`REALTIME_BATCH_MAX_UPDATES`, `REALTIME_BATCH_MAX_BYTES`).

---

### `node.telemetry.updated` → `NodeTelemetryUpdated`

**Channel:** `hydro.zones.{zoneId}` or `hydro.devices` (if no zone)
**Source:** `PythonIngestController::telemetry()`

```json
{
  "node_id": 5,
  "channel": "ai2-ph-probe",
  "metric_type": "PH",
  "value": 6.8,
  "ts": 1704067200000,
  "event_id": 12345678,
  "server_ts": 1704067200123
}
```

---

### `CommandStatusUpdated`

**Channel:** `hydro.commands.{zoneId}` or `hydro.commands.global`
**Source:** `CommandObserver::created()` / `CommandObserver::updated()` (`commandAck` только пишет в БД)

```json
{
  "commandId": "cmd-123",
  "status": "ACK",
  "message": "Command acknowledged by node",
  "error": null,
  "zoneId": 1,
  "event_id": 12345679,
  "server_ts": 1704067200124
}
```

**Status values:** `QUEUED` → `SENT` → `ACK` → `DONE` / `NO_EFFECT`

---

### `CommandFailed`

**Channel:** `hydro.commands.{zoneId}` or `hydro.commands.global`
**Source:** `CommandObserver::updated()` (terminal failure statuses)

```json
{
  "commandId": "cmd-123",
  "status": "TIMEOUT",
  "message": "No response from node within 30s",
  "error": "timeout",
  "zoneId": 1,
  "event_id": 12345680,
  "server_ts": 1704067200125
}
```

**Error statuses:** `ERROR`, `INVALID`, `BUSY`, `TIMEOUT`, `SEND_FAILED`

---

### `device.updated` → `NodeConfigUpdated`

**Channel:** `hydro.zones.{zoneId}` or `hydro.devices`
**Source:** Node config/status update handlers

```json
{
  "device": {
    "id": 5,
    "uid": "esp32-abc123",
    "name": "pH Node Zone A",
    "type": "ph_node",
    "status": "ONLINE",
    "lifecycle_state": "PROVISIONED",
    "fw_version": "1.2.3",
    "hardware_id": null,
    "zone_id": 1,
    "last_seen_at": "2024-01-01T00:00:00Z",
    "first_seen_at": "2024-01-01T00:00:00Z",
    "was_recently_created": false
  },
  "event_id": 12345681,
  "server_ts": 1704067200126
}
```

---

### `AlertCreated` / `AlertUpdated`

**Channel:** `hydro.alerts` (always) + `hydro.zones.{zoneId}` (if zone-specific)
**Source:** Alert repository on alert create/update

```json
{
  "id": 42,
  "code": "PH_OUT_OF_RANGE",
  "severity": "warning",
  "status": "active",
  "zone_id": 1,
  "message": "pH 8.2 exceeds target max 7.5",
  "event_id": 12345682,
  "server_ts": 1704067200127
}
```

---

### `GrowCycleUpdated`

**Channel:** `hydro.zones.{zoneId}`
**Source:** `GrowCycleService` (createCycle, pauseCycle, resumeCycle, harvestCycle, abortCycle, advancePhase)

```json
{
  "cycle": {
    "id": 10,
    "zone_id": 1,
    "status": "RUNNING",
    "current_phase": {
      "id": 3,
      "name": "Vegetative",
      "code": "veg"
    },
    "phase_started_at": "2024-01-01T00:00:00Z",
    "started_at": "2024-01-01T00:00:00Z",
    "expected_harvest_at": "2024-02-01T00:00:00Z",
    "actual_harvest_at": null,
    "batch_label": "Batch #12"
  },
  "action": "STAGE_ADVANCED",
  "event_id": 12345683,
  "server_ts": 1704067200128
}
```

**Actions:** `CREATED`, `PAUSED`, `RESUMED`, `HARVESTED`, `ABORTED`, `STAGE_ADVANCED`, `PHASE_ADVANCED`, `PHASE_SET`

---

### `ZoneUpdated`

**Channel:** `hydro.zones.{zoneId}`
**Source:** Zone repository on zone update

```json
{
  "zone": {
    "id": 1,
    "name": "Zone A",
    "status": "active"
  },
  "event_id": 12345684,
  "server_ts": 1704067200129
}
```

---

### `EventCreated`

**Channel:** `hydro.events.global` (global, без `zone_id`) или `hydro.zones.{zoneId}` (если `zone_id` известен)
**Source:** System event service / `EventCreated` Laravel event

```json
{
  "id": 100,
  "kind": "INFO",
  "message": "Irrigation cycle completed",
  "zoneId": 1,
  "occurredAt": "2024-01-01T00:00:00Z",
  "event_id": 12345685,
  "server_ts": 1704067200130
}
```

---

### `ExecutionChainUpdated`

**Channel:** `hydro.zone.executions.{zoneId}`
**Source:** Laravel `App\Services\Scheduler\ExecutionChainAssembler` (после webhook от history-logger или AE3 task lifecycle change)
**Purpose:** Real-time обновление Scheduler Cockpit "причинно-следственной цепочки" для зоны.

```json
{
  "zone_id": 1,
  "task_id": 42,
  "chain": [
    {"step": "SNAPSHOT", "at": "2026-05-28T10:00:00Z", "ref": "...", "status": "ok"},
    {"step": "DECISION", "at": "2026-05-28T10:00:01Z", "ref": "...", "status": "ok"},
    {"step": "TASK", "at": "2026-05-28T10:00:02Z", "ref": 42, "status": "ok"},
    {"step": "DISPATCH", "at": "2026-05-28T10:00:03Z", "ref": "cmd-123", "status": "ok"},
    {"step": "RUNNING", "at": "2026-05-28T10:00:04Z", "ref": "cmd-123", "status": "run", "live": true}
  ],
  "event_id": 12345686,
  "server_ts": 1704067200131
}
```

Frontend подписывается через `backend/laravel/resources/js/ws/schedulerChainChannel.ts` и рендерит таб «Планировщик» в `Pages/Zones/Tabs/ZoneSchedulerTab.vue`.

---

### Frontend event listener naming

Frontend слушает события **через имена Laravel-класса** (не только через broadcast name). Это допускается Laravel Echo и используется для тех событий, которые ещё не нормализованы в `useWebSocket()`.

```typescript
subscribeManagedChannelEvents({
  channelName: `hydro.zones.${zoneId}`,
  eventHandlers: {
    '.App\\Events\\GrowCycleUpdated': (payload) => { /* ... */ },
    '.App\\Events\\ZoneUpdated': (payload) => { /* ... */ },
    'telemetry.batch.updated': (payload) => { /* ... */ },  // broadcastAs() явно задан
  },
})
```

Точка `.` в начале — Laravel Echo синтаксис для escape namespace. Полный canonical name класса — `App\Events\GrowCycleUpdated`, в JSON он сериализуется как `App\\Events\\GrowCycleUpdated`.

---

## Data Flow

```mermaid
graph LR
    ESP32["ESP32 Nodes"] -->|MQTT| Broker["MQTT Broker :1883"]
    Broker -->|subscribe| HL["history-logger"]
    HL -->|save| DB["PostgreSQL/TimescaleDB"]
    HL -->|POST /api/internal/realtime/telemetry-batch| Laravel["Laravel"]

    MqttBridge["mqtt-bridge"] -->|POST /api/python/ingest/telemetry| Laravel
    AE["automation-engine"] -->|commands| HL2["history-logger API"]
    HL2 -->|POST /api/python/commands/ack| Laravel

    Laravel -->|event()| Queue["Redis queue=broadcasts"]
    Queue --> Reverb["Reverb :6001"]
    Reverb -->|WebSocket| Frontend["Vue Frontend"]

    GCS["GrowCycleService"] -->|broadcast()| Queue
    CO["CommandObserver"] -->|event()| Queue
```

---

## TelemetryBatchUpdated: Dual Dispatch

This event is dispatched from **two separate paths** — this is intentional:

### Path 1: Immediate (single sample)
```
mqtt-bridge → POST /api/python/ingest/telemetry
  └─ PythonIngestController::telemetry()
      ├─ Forwards to history-logger /ingest/telemetry
      └─ Immediately dispatches TelemetryBatchUpdated (for fast UI update)
```

### Path 2: Batch (from history-logger)
```
history-logger (subscribes to MQTT) → processes telemetry → saves to DB
  └─ Every ~100ms: _flush_realtime_updates_to_laravel()
      └─ POST /api/internal/realtime/telemetry-batch
          └─ InternalRealtimeController::telemetryBatch()
              └─ Dispatches TelemetryBatchUpdated per zone
```

**Important:** The same telemetry sample may arrive at the frontend **twice** with different `event_id` values. This does not cause state corruption (values are idempotent), but it should be kept in mind when debugging or adding deduplication logic.

The frontend does not deduplicate by content — it processes all incoming events. This is acceptable because telemetry updates are idempotent (latest value wins).

---

## Reconciliation Mechanism

Every broadcast event includes:
- `event_id` — monotonically increasing integer (generated by `EventSequenceService`)
- `server_ts` — server timestamp in milliseconds

On WebSocket reconnect, the frontend:
1. Re-subscribes to all channels
2. Fetches a REST snapshot (`/zones/{id}/snapshot`) for each active zone
3. Compares snapshot `server_ts` to the last received event `server_ts`
4. Ignores incoming events older than the snapshot

This prevents stale events from overwriting fresh REST state after a reconnect.

---

## Frontend Subscriptions

All WebSocket subscriptions should use one of two canonical frontend entry points:

```typescript
const {
  subscribeToZoneCommands,   // channel: hydro.commands.{zoneId}
  subscribeToGlobalEvents,   // channel: hydro.events.global
  subscribeToZoneUpdates,    // channel: hydro.zones.{zoneId} → ZoneUpdated
  subscribeToAlerts,         // channel: hydro.alerts → AlertCreated
} = useWebSocket()
```

For raw named events that are not normalized by `useWebSocket()` yet
(`GrowCycleUpdated`, `telemetry.batch.updated`, `device.updated`, etc.),
frontend code must use:

```typescript
subscribeManagedChannelEvents({
  channelName: 'hydro.zones.12',
  eventHandlers: {
    '.App\\Events\\GrowCycleUpdated': (payload) => { /* ... */ },
  },
})
```

Canonical rule:
- normalized domain events -> `useWebSocket()`
- raw channel/event listeners with reconnect/resubscribe -> `subscribeManagedChannelEvents()`

`subscribeManagedChannelEvents()` invariants:
- performs `leave(channel)` on cleanup by default;
- rebinds listeners after reconnect via `onWsStateChange`;
- ignores stale raw events when payload includes `server_ts` and zone can be resolved.

`ws/subscriptions.ts` removed. Direct `Echo.private(...)` / `Echo.channel(...)` in pages and composables is not allowed.

### Channel name constants (frontend)

Defined in `backend/laravel/resources/js/ws/webSocketRuntime.ts`:
```typescript
export const GLOBAL_EVENTS_CHANNEL = 'hydro.events.global'
// COMMANDS_GLOBAL_CHANNEL = 'hydro.commands.global'  (internal)
// Zone commands: `hydro.commands.${zoneId}`          (constructed in useWebSocket)
```

---

## Prometheus Metrics

WS broadcast and auth metrics are tracked via `PipelineMetricsService` → history-logger → Prometheus.

Exposed at `http://history-logger:9300/metrics` (scraped by Prometheus at `http://localhost:9090`):

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ws_broadcast_total` | Counter | `event_type` | Total WS events dispatched |
| `ws_auth_total` | Counter | `channel_type`, `result` | Channel auth attempts |

Internal write endpoints:
- `POST /internal/metrics/ws-event` with one of payloads:
  - `{ "event_type": "...", "count": 1 }`
  - `{ "channel_type": "...", "result": "...", "count": 1 }`
- `POST /internal/metrics/ws-broadcast` and `POST /internal/metrics/ws-auth` are compatibility wrappers.

**channel_type values:** `zone`, `commands`, `events`, `alerts`, `devices`  
**result values:** `success`, `denied`, `error`

---

## Adding New Events

Checklist:
1. Create `app/Events/MyEvent.php` implementing `ShouldBroadcast`
2. Set `public string $queue = 'broadcasts'`
3. Define `broadcastOn()` using existing channels or add new channel to `routes/channels.php`
4. Define `broadcastAs()` with a clear event name
5. Include `event_id` and `server_ts` from `EventSequenceService::generateEventId()`
6. If zone-specific audit trail is needed: write to `zone_events` from the domain observer/service (e.g. `CommandObserver` + `ZoneEventRecorder`), not from `broadcasted()` — Laravel 12 does not invoke `broadcasted()` on broadcast events
7. Add frontend subscription in `useWebSocket.ts` for normalized domain events, or in `ws/managedChannelEvents.ts` consumer-side if the event remains raw
8. Update this documentation
