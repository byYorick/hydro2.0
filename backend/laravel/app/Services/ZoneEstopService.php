<?php

namespace App\Services;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Illuminate\Support\Facades\Schema;

class ZoneEstopService
{
    public function __construct(
        private readonly SafetyAuditLogger $audit,
    ) {}

    /**
     * E-STOP активен, если последнее релевантное событие зоны — активация.
     * Событие узла (любого) и операторский engage используют один тип.
     *
     * @return array{active: bool, source: ?string, since: ?string, node_uid: ?string, event_id: ?int}
     */
    public function status(Zone $zone): array
    {
        $idle = [
            'active' => false,
            'source' => null,
            'since' => null,
            'node_uid' => null,
            'event_id' => null,
        ];

        if (! Schema::hasTable('zone_events')) {
            return $idle;
        }

        $event = ZoneEvent::query()
            ->where('zone_id', $zone->id)
            ->whereIn('type', ['EMERGENCY_STOP_ACTIVATED', 'EMERGENCY_STOP_RELEASED'])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first();

        if ($event === null || $event->type === 'EMERGENCY_STOP_RELEASED') {
            return $idle;
        }

        $payload = is_array($event->payload_json) ? $event->payload_json : [];

        return [
            'active' => true,
            'source' => is_string($payload['source'] ?? null) ? $payload['source'] : 'node',
            'since' => $event->created_at?->toIso8601String(),
            'node_uid' => is_string($payload['node_uid'] ?? null) ? $payload['node_uid'] : null,
            'event_id' => (int) $event->id,
        ];
    }

    /**
     * @return array{zone_id: int, action: string, result: string, estop: array<string, mixed>}
     */
    public function apply(Zone $zone, string $action, ?User $user, ?string $reason): array
    {
        $current = $this->status($zone);
        $result = $action === 'engage'
            ? ($current['active'] ? 'already_active' : 'engaged')
            : ($current['active'] ? 'released' : 'already_released');

        if ($result === 'engaged' || $result === 'released') {
            ZoneEvent::query()->create([
                'zone_id' => $zone->id,
                'type' => $result === 'engaged' ? 'EMERGENCY_STOP_ACTIVATED' : 'EMERGENCY_STOP_RELEASED',
                'payload_json' => [
                    'source' => 'operator',
                    'action' => $action,
                    'reason' => $reason,
                    'user_id' => $user?->id,
                    'user_name' => $user?->name,
                ],
                'created_at' => now(),
            ]);
        }

        $status = $this->status($zone);
        $this->audit->write('zone_estop', (int) $zone->id, $result, [
            'action' => $action,
            'reason' => $reason,
            'estop_active' => $status['active'],
            'source' => $status['source'],
        ], $user);

        return [
            'zone_id' => (int) $zone->id,
            'action' => $action,
            'result' => $result,
            'estop' => $status,
        ];
    }
}
