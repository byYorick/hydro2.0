<?php

namespace App\Events;

use App\Models\DeviceNode;
use App\Services\EventSequenceService;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class NodeConfigUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public int $eventId;

    public int $serverTs;

    /**
     * Create a new event instance.
     */
    public function __construct(
        public DeviceNode $node
    ) {
        // Генерируем event_id и server_ts для reconciliation
        $sequence = EventSequenceService::generateEventId();
        $this->eventId = $sequence['event_id'];
        $this->serverTs = $sequence['server_ts'];
    }

    /**
     * Get the channels the event should broadcast on.
     */
    public function broadcastOn(): PrivateChannel
    {
        if ($this->node->zone_id) {
            return new PrivateChannel("hydro.zones.{$this->node->zone_id}");
        }

        return new PrivateChannel('hydro.devices');
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'device.updated';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'device' => [
                'id' => $this->node->id,
                'uid' => $this->node->uid,
                'name' => $this->node->name,
                'type' => $this->node->type,
                'status' => $this->node->status,
                'lifecycle_state' => $this->node->lifecycle_state?->value ?? 'UNPROVISIONED',
                'fw_version' => $this->node->fw_version,
                'hardware_id' => $this->node->hardware_id,
                'zone_id' => $this->node->zone_id,
                'last_seen_at' => $this->node->last_seen_at?->toIso8601String(),
                'first_seen_at' => $this->node->first_seen_at?->toIso8601String(),
                'was_recently_created' => $this->node->wasRecentlyCreated,
            ],
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }

    /**
     * Записывает событие в zone_events после успешного broadcast.
     */
    public function broadcasted(): void
    {
        if ($this->node->zone_id) {
            $this->recordZoneEvent(
                zoneId: $this->node->zone_id,
                type: 'device_status',
                entityType: 'device',
                entityId: $this->node->id,
                payload: [
                    'uid' => $this->node->uid,
                    'status' => $this->node->status,
                    'lifecycle_state' => $this->node->lifecycle_state?->value ?? 'UNPROVISIONED',
                ],
                eventId: $this->eventId,
                serverTs: $this->serverTs
            );
        }
    }
}
