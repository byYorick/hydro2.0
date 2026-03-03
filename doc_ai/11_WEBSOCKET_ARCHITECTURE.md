# WebSocket Architecture

**Stack:** Laravel Reverb (self-hosted Pusher-compatible, port 6001) + Laravel Echo (Pusher.js) on frontend.
**Queue:** All broadcasts use Redis queue `broadcasts`.
**Auth:** All channels are `private` — require `POST /broadcasting/auth` with Sanctum session or Bearer token.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## Channels

| Channel | Renamed from | Events broadcast | Who subscribes |
|---------|-------------|-----------------|----------------|
| `hydro.zones.{zoneId}` | — | TelemetryBatchUpdated, NodeTelemetryUpdated, NodeConfigUpdated, AlertCreated, AlertUpdated, GrowCycleUpdated, ZoneUpdated | Users with zone access |
| `hydro.commands.{zoneId}` | `commands.{zoneId}` | CommandStatusUpdated, CommandFailed | Users with zone access |
| `hydro.commands.global` | `commands.global` | CommandStatusUpdated, CommandFailed (no zone) | All authenticated users |
| `hydro.events.global` | `events.global` | EventCreated | All authenticated users |
| `hydro.alerts` | — | AlertCreated, AlertUpdated | All authenticated users |
| `hydro.devices` | — | NodeTelemetryUpdated, NodeConfigUpdated (no zone) | All authenticated users |

**Authorization** (`backend/laravel/routes/channels.php`):
- Zone channels check `ZoneAccessHelper::canAccessZone()` + role in `['viewer', 'operator', 'admin', 'agronomist', 'engineer']`
- Global channels require authenticated user + valid role
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
**Source:** `CommandObserver::created()` / `CommandObserver::updated()` / `PythonIngestController::commandAck()`

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
**Source:** `CommandObserver::updated()` / `PythonIngestController::commandAck()`

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

**Channel:** `hydro.events.global`
**Source:** System event service

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

All WebSocket subscriptions should use the `useWebSocket()` composable:

```typescript
const {
  subscribeToZoneCommands,   // channel: hydro.commands.{zoneId}
  subscribeToGlobalEvents,   // channel: hydro.events.global
  subscribeToZoneUpdates,    // channel: hydro.zones.{zoneId} → ZoneUpdated
  subscribeToAlerts,         // channel: hydro.alerts → AlertCreated
} = useWebSocket()
```

> **Deprecated:** `subscribeZone()` and `subscribeAlerts()` from `ws/subscriptions.ts`.
> Use `subscribeToZoneUpdates()` and `subscribeToAlerts()` from `useWebSocket()` instead.

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
6. If zone-specific: use `RecordsZoneEvent` trait in `broadcasted()` for audit trail
7. Add frontend subscription in `useWebSocket.ts`
8. Update this documentation
