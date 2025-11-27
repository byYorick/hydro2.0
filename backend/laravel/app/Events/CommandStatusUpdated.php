<?php

namespace App\Events;

use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class CommandStatusUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public string $queue = 'broadcasts';

    public int|string $commandId;

    public string $status;

    public ?string $message;

    public ?string $error;

    public ?int $zoneId;

    public function __construct(
        int|string $commandId,
        string $status,
        ?string $message = null,
        ?string $error = null,
        ?int $zoneId = null
    ) {
        $this->commandId = $commandId;
        $this->status = $status;
        $this->message = $message;
        $this->error = $error;
        $this->zoneId = $zoneId;
    }

    /**
     * Get the channels the event should broadcast on.
     */
    public function broadcastOn(): Channel
    {
        // Если указана зона, отправляем в приватный канал зоны
        if ($this->zoneId) {
            return new PrivateChannel("commands.{$this->zoneId}");
        }

        // Иначе отправляем в глобальный канал команд
        return new PrivateChannel('commands.global');
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'CommandStatusUpdated';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'commandId' => $this->commandId,
            'status' => $this->status,
            'message' => $this->message,
            'error' => $this->error,
            'zoneId' => $this->zoneId,
        ];
    }
}
