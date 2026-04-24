<?php

declare(strict_types=1);

namespace App\Events;

use App\Services\EventSequenceService;
use App\Traits\RecordsWsBroadcastMetric;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

/**
 * Broadcast при добавлении нового шага в causal chain Cockpit-UI.
 *
 * Канал: `hydro.zone.executions.{zoneId}`.
 * Payload: `{ execution_id, step }`. `step` описывает один узел цепочки:
 * `{ step, at, ref, detail, status, live? }`.
 */
class ExecutionChainUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, RecordsWsBroadcastMetric, SerializesModels;

    public string $queue = 'broadcasts';

    public int $zoneId;

    public string $executionId;

    /**
     * @var array<string, mixed>
     */
    public array $step;

    public int $eventId;

    public int $serverTs;

    /**
     * @param  array<string, mixed>  $step
     */
    public function __construct(int $zoneId, string $executionId, array $step)
    {
        $this->zoneId = $zoneId;
        $this->executionId = $executionId;
        $this->step = $step;

        $sequence = EventSequenceService::generateEventId();
        $this->eventId = $sequence['event_id'];
        $this->serverTs = $sequence['server_ts'];
    }

    public function broadcastOn(): Channel
    {
        return new PrivateChannel("hydro.zone.executions.{$this->zoneId}");
    }

    public function broadcastAs(): string
    {
        return 'ExecutionChainUpdated';
    }

    /**
     * @return array<string, mixed>
     */
    public function broadcastWith(): array
    {
        return [
            'zone_id' => $this->zoneId,
            'execution_id' => $this->executionId,
            'step' => $this->step,
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }

    public function broadcasted(): void
    {
        $this->recordWsBroadcastMetric('ExecutionChainUpdated');
    }
}
