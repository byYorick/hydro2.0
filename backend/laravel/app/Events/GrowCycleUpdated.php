<?php

namespace App\Events;

use App\Models\GrowCycle;
use App\Services\EventSequenceService;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class GrowCycleUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public GrowCycle $cycle;

    public string $action;

    public int $eventId;

    public int $serverTs;

    public function __construct(GrowCycle $cycle, string $action = 'updated')
    {
        $this->cycle = $cycle;
        $this->action = $action;
        
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
        return new PrivateChannel("hydro.zones.{$this->cycle->zone_id}");
    }

    /**
     * The event's broadcast name.
     */
    public function broadcastAs(): string
    {
        return 'GrowCycleUpdated';
    }

    /**
     * Get the data to broadcast.
     */
    public function broadcastWith(): array
    {
        return [
            'cycle' => [
                'id' => $this->cycle->id,
                'zone_id' => $this->cycle->zone_id,
                'status' => $this->cycle->status->value,
                'current_stage_code' => $this->cycle->current_stage_code,
                'current_stage_started_at' => $this->cycle->current_stage_started_at?->toIso8601String(),
                'started_at' => $this->cycle->started_at?->toIso8601String(),
                'expected_harvest_at' => $this->cycle->expected_harvest_at?->toIso8601String(),
                'actual_harvest_at' => $this->cycle->actual_harvest_at?->toIso8601String(),
                'batch_label' => $this->cycle->batch_label,
            ],
            'action' => $this->action,
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
            $this->cycle->zone_id,
            "CYCLE_{$this->action}",
            'grow_cycle',
            (string) $this->cycle->id,
            [
                'cycle_id' => $this->cycle->id,
                'status' => $this->cycle->status->value,
                'action' => $this->action,
            ],
            $this->eventId,
            $this->serverTs
        );
    }
}

