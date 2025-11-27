<?php

namespace App\Events;

use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class EventCreated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public string $queue = 'broadcasts';

    public int $id;

    public string $kind;

    public string $message;

    public ?int $zoneId;

    public string $occurredAt;

    public function __construct(
        int $id,
        string $kind,
        string $message,
        ?int $zoneId = null,
        ?string $occurredAt = null
    ) {
        $this->id = $id;
        $this->kind = $kind;
        $this->message = $message;
        $this->zoneId = $zoneId;
        $this->occurredAt = $occurredAt ?? now()->toIso8601String();
    }

    /**
     * Get the channels the event should broadcast on.
     */
    public function broadcastOn(): Channel
    {
        return new Channel('events.global');
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'EventCreated';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'id' => $this->id,
            'kind' => $this->kind,
            'message' => $this->message,
            'zoneId' => $this->zoneId,
            'occurredAt' => $this->occurredAt,
        ];
    }
}
