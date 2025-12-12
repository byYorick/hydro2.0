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

class NodeTelemetryUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public int $eventId;
    public int $serverTs;

    /**
     * Create a new event instance.
     */
    public function __construct(
        public int $nodeId,
        public string $channel,
        public string $metricType,
        public float $value,
        public int $timestamp,
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
        return new PrivateChannel('hydro.devices');
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'node.telemetry.updated';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'node_id' => $this->nodeId,
            'channel' => $this->channel,
            'metric_type' => $this->metricType,
            'value' => $this->value,
            'ts' => $this->timestamp,
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }

    /**
     * Записывает событие в zone_events после успешного broadcast.
     */
    public function broadcasted(): void
    {
        // Получаем узел для определения zone_id
        $node = DeviceNode::find($this->nodeId);
        if ($node && $node->zone_id) {
            $this->recordZoneEvent(
                zoneId: $node->zone_id,
                type: 'telemetry_updated',
                entityType: 'telemetry',
                entityId: $this->nodeId,
                payload: [
                    'channel' => $this->channel,
                    'metric_type' => $this->metricType,
                    'value' => $this->value,
                    'ts' => $this->timestamp,
                ],
                eventId: $this->eventId,
                serverTs: $this->serverTs
            );
        }
    }
}

