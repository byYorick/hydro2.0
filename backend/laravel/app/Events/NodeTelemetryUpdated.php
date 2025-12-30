<?php

namespace App\Events;

use App\Models\DeviceNode;
use App\Services\EventSequenceService;
use App\Traits\RecordsZoneEvent;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class NodeTelemetryUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels, RecordsZoneEvent;

    public string $queue = 'broadcasts';

    public int $eventId;
    public int $serverTs;

    /**
     * Create a new event instance.
     */
    public function __construct(
        public int $nodeId,
        public string $channel,
        public string $metricType,
        public float $value,
        public int $timestamp,
        public ?int $zoneId = null,
    ) {
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
        $zoneId = $this->zoneId;
        if (! $zoneId) {
            $zoneId = DeviceNode::query()
                ->whereKey($this->nodeId)
                ->value('zone_id');
        }

        if ($zoneId) {
            return new PrivateChannel("hydro.zones.{$zoneId}");
        }

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
            'event_id' => $this->eventId,
            'server_ts' => $this->serverTs,
        ];
    }

    /**
     * Записывает событие в zone_events только при значимых изменениях.
     * 
     * Использует TelemetryLedgerFilter для фильтрации незначимых изменений
     * и предотвращения раздувания ledger при высокой частоте телеметрии.
     */
    public function broadcasted(): void
    {
        // Получаем узел для определения zone_id
        $zoneId = $this->zoneId;
        if (! $zoneId) {
            $zoneId = DeviceNode::query()
                ->whereKey($this->nodeId)
                ->value('zone_id');
        }

        if (! $zoneId) {
            return;
        }

        // Проверяем, нужно ли записывать это событие в ledger
        // Записываем только значимые изменения (превышающие порог) и не чаще минимального интервала
        $filter = app(\App\Services\TelemetryLedgerFilter::class);
        if (! $filter->shouldRecord($zoneId, $this->metricType, $this->value)) {
            // Не записываем - это незначимое изменение или слишком часто
            return;
        }

        // Записываем только значимые изменения
        $this->recordZoneEvent(
            zoneId: $zoneId,
            type: 'telemetry_updated',
            entityType: 'telemetry',
            entityId: $this->nodeId,
            payload: [
                'channel' => $this->channel,
                'metric_type' => $this->metricType,
                'value' => $this->value,
                'ts' => $this->timestamp,
            ],
            eventId: $this->eventId,
            serverTs: $this->serverTs
        );
    }
}
