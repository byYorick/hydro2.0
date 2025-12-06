<?php

namespace App\Events;

use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class NodeTelemetryUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public string $queue = 'broadcasts';

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
        //
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
        ];
    }
}

