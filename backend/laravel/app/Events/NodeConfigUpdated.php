<?php

namespace App\Events;

use App\Models\DeviceNode;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class NodeConfigUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    /**
     * Create a new event instance.
     */
    public function __construct(
        public DeviceNode $node
    ) {
        //
    }

    /**
     * Get the channels the event should broadcast on.
     */
    public function broadcastOn(): Channel
    {
        // Публичный канал для всех устройств
        return new Channel('hydro.devices');
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
        ];
    }
}
