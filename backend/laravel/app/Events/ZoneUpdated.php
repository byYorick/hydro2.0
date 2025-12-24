<?php

namespace App\Events;

use App\Models\Zone;
use App\Services\EventSequenceService;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class ZoneUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public Zone $zone;

    public int $eventId;

    public int $serverTs;

    public function __construct(Zone $zone)
    {
        $this->zone = $zone;
        
        // Генерируем event_id и server_ts для reconciliation
        $sequence = EventSequenceService::generateEventId();
        $this->eventId = $sequence['event_id'];
        $this->serverTs = $sequence['server_ts'];
    }

    public function broadcastOn(): Channel
    {
        return new PrivateChannel("hydro.zones.{$this->zone->id}");
    }

    public function broadcastWith(): array
    {
        return [
            'zone' => [
                'id' => $this->zone->id,
                'name' => $this->zone->name,
                'status' => $this->zone->status,
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
        $this->recordZoneEvent(
            zoneId: $this->zone->id,
            type: 'zone_updated',
            entityType: 'zone',
            entityId: $this->zone->id,
            payload: [
                'name' => $this->zone->name,
                'status' => $this->zone->status,
            ],
            eventId: $this->eventId,
            serverTs: $this->serverTs
        );
    }
}
