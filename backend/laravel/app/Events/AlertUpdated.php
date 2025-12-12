<?php

namespace App\Events;

use App\Services\EventSequenceService;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class AlertUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public array $alert;

    public int $eventId;

    public int $serverTs;

    public function __construct(array $alert)
    {
        $this->alert = $alert;
        
        // Генерируем event_id и server_ts для reconciliation
        $sequence = EventSequenceService::generateEventId();
        $this->eventId = $sequence['event_id'];
        $this->serverTs = $sequence['server_ts'];
    }

    public function broadcastOn()
    {
        // Если есть zone_id, отправляем в канал зоны, иначе в глобальный канал
        if (isset($this->alert['zone_id']) && $this->alert['zone_id']) {
            return [
                new PrivateChannel('hydro.alerts'),
                new PrivateChannel("hydro.zones.{$this->alert['zone_id']}"),
            ];
        }
        
        return new PrivateChannel('hydro.alerts');
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'AlertUpdated';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return array_merge($this->alert, [
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ]);
    }

    /**
     * Записывает событие в zone_events после успешного broadcast.
     */
    public function broadcasted(): void
    {
        $zoneId = $this->alert['zone_id'] ?? null;
        if ($zoneId) {
            $this->recordZoneEvent(
                zoneId: $zoneId,
                type: 'alert_updated',
                entityType: 'alert',
                entityId: $this->alert['id'] ?? null,
                payload: [
                    'code' => $this->alert['code'] ?? null,
                    'severity' => $this->alert['severity'] ?? null,
                    'status' => $this->alert['status'] ?? null,
                ],
                eventId: $this->eventId,
                serverTs: $this->serverTs
            );
        }
    }
}
