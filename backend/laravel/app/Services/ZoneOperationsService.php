<?php

namespace App\Services;

use App\Enums\ZoneStatus;
use App\Helpers\ZoneAccessHelper;
use App\Models\TelemetryLast;
use App\Models\Zone;
use App\Services\ZoneReadinessService;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Log;

class ZoneOperationsService
{
    public function __construct(
        private ZoneReadinessService $readinessService
    ) {}

    /**
     * Выполнить операцию fill зоны
     */
    public function fill(Zone $zone, array $data): string
    {
        $this->validateZoneOperation($zone, 'fill');

        $jobId = \Illuminate\Support\Str::uuid()->toString();
        \App\Jobs\ZoneOperationJob::dispatch($zone->id, 'fill', $data, $jobId);

        return $jobId;
    }

    /**
     * Выполнить операцию drain зоны
     */
    public function drain(Zone $zone, array $data): string
    {
        $this->validateZoneOperation($zone, 'drain');

        $jobId = \Illuminate\Support\Str::uuid()->toString();
        \App\Jobs\ZoneOperationJob::dispatch($zone->id, 'drain', $data, $jobId);

        return $jobId;
    }

    /**
     * Выполнить калибровку потока
     */
    public function calibrateFlow(Zone $zone, array $data): string
    {
        $this->validateZoneOperation($zone, 'calibrate_flow');

        $jobId = \Illuminate\Support\Str::uuid()->toString();
        \App\Jobs\ZoneOperationJob::dispatch($zone->id, 'calibrate_flow', $data, $jobId);

        return $jobId;
    }

    /**
     * Получить состояние здоровья зоны
     */
    public function getHealth(Zone $zone): array
    {
        $health = $this->readinessService->getZoneHealth($zone);

        // Добавляем телеметрию для зоны
        $telemetryRaw = $this->getZoneTelemetry($zone->id);

        return array_merge($health, [
            'telemetry' => $telemetryRaw,
        ]);
    }

    /**
     * Получить телеметрию для зоны
     */
    private function getZoneTelemetry(int $zoneId): array
    {
        // Получаем последние значения телеметрии для зоны (per node/channel)
        $telemetryRaw = TelemetryLast::query()
            ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
            ->where('sensors.zone_id', $zoneId)
            ->whereNotNull('sensors.zone_id')
            ->select([
                'sensors.node_id',
                'sensors.label as channel',
                'sensors.type as metric_type',
                'telemetry_last.last_value as value',
                'telemetry_last.updated_at'
            ])
            ->orderBy('telemetry_last.updated_at', 'desc')
            ->get();

        // Группируем по node_id, затем по channel
        $telemetry = [];
        foreach ($telemetryRaw as $metric) {
            $nodeId = $metric->node_id;
            $channel = $metric->channel ?: 'default';

            if (!isset($telemetry[$nodeId])) {
                $telemetry[$nodeId] = [];
            }

            $telemetry[$nodeId][$channel] = [
                'metric_type' => $metric->metric_type,
                'value' => (float) $metric->value,
                'updated_at' => $metric->updated_at?->toIso8601String(),
            ];
        }

        return $telemetry;
    }

    /**
     * Валидировать возможность выполнения операции над зоной
     */
    private function validateZoneOperation(Zone $zone, string $operation): void
    {
        if ($zone->status !== ZoneStatus::ONLINE->value) {
            throw new \DomainException("Zone must be online to perform {$operation} operation");
        }

        // Дополнительные проверки для конкретных операций
        if ($operation === 'fill' || $operation === 'drain') {
            if (!$zone->activeGrowCycle) {
                throw new \DomainException("Zone must have an active grow cycle to perform {$operation} operation");
            }
        }
    }
}
