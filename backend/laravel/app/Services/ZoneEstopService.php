<?php

namespace App\Services;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Illuminate\Http\Exceptions\HttpResponseException;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class ZoneEstopService
{
    public function __construct(
        private readonly SafetyAuditLogger $audit,
        private readonly ZoneEstopDispatchService $dispatch,
    ) {}

    public function status(Zone $zone): array
    {
        $idle = ['active' => false, 'source' => null, 'since' => null, 'node_uid' => null,
            'event_id' => null, 'stop_status' => 'not_requested', 'release_status' => 'not_requested'];
        if (! Schema::hasTable('zone_events')) {
            return $idle;
        }
        $events = ZoneEvent::query()->where('zone_id', $zone->id)
            ->whereIn('type', ['EMERGENCY_STOP_ACTIVATED', 'EMERGENCY_STOP_RELEASED']);
        $operator = (clone $events)->where('payload_json->source', 'operator')
            ->orderByDesc('created_at')->orderByDesc('id')->first();
        // Node and operator latches have independent owners. A release from
        // either cannot mask an active latch belonging to the other.
        $physical = (clone $events)
            ->selectRaw("DISTINCT ON (COALESCE(payload_json->>'node_uid', 'unknown')) zone_events.*")
            ->whereRaw("COALESCE(payload_json->>'source', '') <> 'operator'")
            ->orderByRaw("COALESCE(payload_json->>'node_uid', 'unknown')")
            ->orderByDesc('created_at')->orderByDesc('id')->get()
            ->firstWhere('type', 'EMERGENCY_STOP_ACTIVATED');
        if ($operator?->type === 'EMERGENCY_STOP_RELEASED') {
            $operatorPayload = $operator->payload_json ?? [];
            $idle['release_status'] = $this->dispatch->outcome($operatorPayload['dispatch'] ?? null);
        }
        $event = $operator?->type === 'EMERGENCY_STOP_ACTIVATED' ? $operator : $physical;
        if ($event === null) {
            return $idle;
        }
        $payload = is_array($event->payload_json) ? $event->payload_json : [];
        $outcome = $this->dispatch->outcome(is_array($payload['dispatch'] ?? null) ? $payload['dispatch'] : null);

        return [
            'active' => true,
            'source' => is_string($payload['source'] ?? null) ? $payload['source'] : 'node',
            'since' => $event->created_at?->toIso8601String(),
            'node_uid' => is_string($payload['node_uid'] ?? null) ? $payload['node_uid'] : null,
            'event_id' => (int) $event->id,
            'stop_status' => ($payload['source'] ?? null) === 'operator' ? $outcome : 'not_requested',
            'release_status' => $idle['release_status'],
        ];
    }

    public function canRelease(Zone $zone): bool
    {
        return ! DB::table('ae_zone_leases')->where('zone_id', $zone->id)->where('leased_until', '>', now())->exists()
            && ! DB::table('ae_tasks')->where('zone_id', $zone->id)
                ->whereIn('status', ['pending', 'claimed', 'running', 'waiting_command'])->exists()
            && (! $zone->greenhouse_id || (! DB::table('greenhouse_automation_leases')
                ->where('greenhouse_id', $zone->greenhouse_id)->where('leased_until', '>', now())->exists()
                && ! DB::table('greenhouse_automation_tasks')->where('greenhouse_id', $zone->greenhouse_id)
                    ->whereIn('status', ['pending', 'claimed', 'running', 'waiting_command'])->exists()));
    }

    public function apply(Zone $zone, string $action, ?User $user, ?string $reason): array
    {
        // Session lock spans the committed latch and network dispatch without
        // holding a zone-row/FK lock against HL's command insert.
        $key = 'zone-estop:'.$zone->id;
        DB::select('SELECT pg_advisory_lock(hashtextextended(?, 0))', [$key]);
        try {
            if ($action === 'release' && ! $this->canRelease($zone)) {
                throw new HttpResponseException(response()->json([
                    'status' => 'error', 'code' => 'ae3_zone_lease_held',
                    'message' => 'Снятие E-STOP разрешено после завершения/разблокировки AE3.',
                ], 409));
            }

            return $this->applyLocked($zone, $action, $user, $reason);
        } finally {
            DB::select('SELECT pg_advisory_unlock(hashtextextended(?, 0))', [$key]);
        }
    }

    private function applyLocked(Zone $zone, string $action, ?User $user, ?string $reason): array
    {
        // Commit the admission latch before any network side effect. A failed
        // stop keeps it engaged; node safe_mode fences already queued commands.
        [$event, $result] = DB::transaction(function () use ($zone, $action, $user, $reason): array {
            Zone::query()->whereKey($zone->id)->lockForUpdate()->firstOrFail();
            $current = $this->status($zone);
            $result = $action === 'engage'
                ? ($current['active'] ? 'already_active' : 'engaged')
                : ($current['active'] ? 'released' : 'already_released');
            $event = ZoneEvent::query()->create([
                'zone_id' => $zone->id,
                'type' => $action === 'engage' ? 'EMERGENCY_STOP_ACTIVATED' : 'EMERGENCY_STOP_RELEASED',
                'payload_json' => [
                    'source' => 'operator', 'channel' => 'storage_state', 'action' => $action,
                    'reason' => $reason, 'user_id' => $user?->id, 'user_name' => $user?->name,
                ],
                'created_at' => now(),
            ]);

            if ($action === 'engage') {
                // PostgreSQL delivers NOTIFY only after this latch commits.
                DB::select('SELECT pg_notify(?, ?)', ['ae_zone_event', json_encode([
                    'zone_id' => (int) $zone->id, 'event_type' => $event->type,
                    'source' => 'operator', 'channel' => 'storage_state',
                ], JSON_THROW_ON_ERROR)]);
            }

            return [$event, $result];
        });
        $payload = $event->payload_json;
        $payload['dispatch'] = $this->dispatch->dispatch($zone, $action);
        $event->forceFill(['payload_json' => $payload])->save();
        $status = $this->status($zone);
        $this->audit->write('zone_estop', (int) $zone->id, $result, [
            'action' => $action, 'reason' => $reason, 'estop_active' => $status['active'],
            'source' => $status['source'], 'stop_status' => $status['stop_status'],
            'release_status' => $status['release_status'],
        ], $user);

        return ['zone_id' => (int) $zone->id, 'action' => $action, 'result' => $result, 'estop' => $status];
    }
}
