<?php

namespace App\Events;

use App\Services\EventSequenceService;
use App\Traits\RecordsZoneEvent;
use App\Traits\RecordsWsBroadcastMetric;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class CommandFailed implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent, RecordsWsBroadcastMetric;

    public string $queue = 'broadcasts';

    public int|string $commandId;

    public string $message;

    public ?string $error;

    public ?string $errorCode;

    public string $status;

    public ?int $zoneId;

    public int $eventId;

    public int $serverTs;

    public function __construct(
        int|string $commandId,
        string $message,
        ?string $error = null,
        string $status = \App\Models\Command::STATUS_ERROR,
        ?int $zoneId = null,
        ?string $errorCode = null
    ) {
        $this->commandId = $commandId;
        $this->message = $message;
        $this->error = $error;
        $this->status = $status;
        $this->zoneId = $zoneId;
        $this->errorCode = $errorCode;
        
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
            return new PrivateChannel("hydro.commands.{$this->zoneId}");
        }

        // Иначе отправляем в глобальный канал команд
        return new PrivateChannel('hydro.commands.global');
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
            'status' => $this->status,
            'message' => $this->message,
            'error' => $this->error,
            'errorCode' => $this->errorCode,
            'zoneId' => $this->zoneId,
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }

    /**
     * Записывает событие в zone_events после успешного broadcast.
     */
    public function broadcasted(): void
    {
        $this->recordWsBroadcastMetric('CommandFailed');

        if ($this->zoneId) {
            $this->recordZoneEvent(
                zoneId: $this->zoneId,
                type: 'command_status',
                entityType: 'command',
                entityId: $this->commandId,
                payload: [
                    'status' => $this->status,
                    'message' => $this->message,
                    'error' => $this->error,
                    'error_code' => $this->errorCode,
                ],
                eventId: $this->eventId,
                serverTs: $this->serverTs
            );
        }
    }
}
