<?php

namespace App\Events;

use App\Services\EventSequenceService;
use App\Services\TelemetryLedgerFilter;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class TelemetryBatchUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public int $eventId;

    public int $serverTs;

    /**
     * @param array<int, array{node_id:int, channel:string|null, metric_type:string, value:float, ts:int}> $updates
     */
    public function __construct(
        public int $zoneId,
        public array $updates
    ) {
        $sequence = EventSequenceService::generateEventId();
        $this->eventId = $sequence['event_id'];
        $this->serverTs = $sequence['server_ts'];
    }

    public function broadcastOn(): PrivateChannel
    {
        return new PrivateChannel("hydro.zones.{$this->zoneId}");
    }

    public function broadcastAs(): string
    {
        return 'telemetry.batch.updated';
    }

    public function broadcastWith(): array
    {
        return [
            'zone_id' => $this->zoneId,
            'updates' => $this->updates,
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }

    public function broadcasted(): void
    {
        $filter = app(TelemetryLedgerFilter::class);

        foreach ($this->updates as $update) {
            $metricType = (string) ($update['metric_type'] ?? '');
            $value = (float) ($update['value'] ?? 0);
            if (! $filter->shouldRecord($this->zoneId, $metricType, $value)) {
                continue;
            }

            $this->recordZoneEvent(
                zoneId: $this->zoneId,
                type: 'telemetry_updated',
                entityType: 'telemetry',
                entityId: $update['node_id'] ?? null,
                payload: [
                    'channel' => $update['channel'] ?? null,
                    'metric_type' => $metricType,
                    'value' => $value,
                    'ts' => $update['ts'] ?? null,
                ],
                eventId: $this->eventId,
                serverTs: $this->serverTs
            );
        }
    }
}
