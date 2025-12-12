<?php

namespace App\Events;

use App\Services\EventSequenceService;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class CommandFailed implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public string $queue = 'broadcasts';

    public int|string $commandId;

    public string $message;

    public ?string $error;

    public ?int $zoneId;

    public int $eventId;

    public int $serverTs;

    public function __construct(
        int|string $commandId,
        string $message,
        ?string $error = null,
        ?int $zoneId = null
    ) {
        $this->commandId = $commandId;
        $this->message = $message;
        $this->error = $error;
        $this->zoneId = $zoneId;
        
        // Генерируем event_id и server_ts для reconciliation
        $sequence = EventSequenceService::generateEventId();
        $this->eventId = $sequence['event_id'];
        $this->serverTs = $sequence['server_ts'];
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
        return 'CommandFailed';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'commandId' => $this->commandId,
            'status' => \App\Models\Command::STATUS_FAILED,
            'message' => $this->message,
            'error' => $this->error,
            'zoneId' => $this->zoneId,
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }
}
