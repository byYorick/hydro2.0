<?php

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Models\Zone;

class ZoneLifecycleService
{
    public function __construct(
        private ZoneService $zoneService
    ) {}

    /**
     * Приостановить зону
     */
    public function pause(Zone $zone): void
    {
        if (! $zone->activeGrowCycle) {
            throw new \DomainException('No active grow cycle found for this zone');
        }

        if ($zone->activeGrowCycle->status !== GrowCycleStatus::RUNNING) {
            throw new \DomainException('Zone is not in RUNNING state');
        }

        $this->zoneService->pause($zone);
    }

    /**
     * Возобновить зону
     */
    public function resume(Zone $zone): void
    {
        if (! $zone->activeGrowCycle) {
            throw new \DomainException('No active grow cycle found for this zone');
        }

        if ($zone->activeGrowCycle->status !== GrowCycleStatus::PAUSED) {
            throw new \DomainException('Zone is not in PAUSED state');
        }

        $this->zoneService->resume($zone);
    }

    /**
     * Собрать урожай
     */
    public function harvest(Zone $zone): void
    {
        if (! $zone->activeGrowCycle) {
            throw new \DomainException('No active grow cycle found for this zone');
        }

        $this->zoneService->harvest($zone);
    }

    /**
     * Запустить зону
     */
    public function start(Zone $zone, array $data): void
    {
        // Проверяем готовность зоны
        $readiness = app(\App\Services\ZoneReadinessService::class)->checkZoneReadiness($zone);

        if (! $readiness['ready']) {
            throw new \DomainException('Zone is not ready to start: '.implode(', ', $readiness['errors']));
        }

        \Illuminate\Support\Facades\DB::transaction(function () use ($zone, $readiness) {
            // Если есть активный цикл выращивания - запускаем его
            $activeCycle = $zone->activeGrowCycle;
            if ($activeCycle && $activeCycle->status === \App\Enums\GrowCycleStatus::PLANNED) {
                // Запускаем цикл через GrowCycleService
                app(\App\Services\GrowCycleService::class)->startCycle($activeCycle);
            }

            // Обновляем статус зоны на RUNNING
            $zone->update(['status' => 'RUNNING']);
            $zone->refresh();
            $zone->load(['activeGrowCycle']);

            // Создаем zone_event
            $hasPayloadJson = \Illuminate\Support\Facades\Schema::hasColumn('zone_events', 'payload_json');

            $eventPayload = json_encode([
                'zone_id' => $zone->id,
                'status' => 'RUNNING',
                'warnings' => $readiness['warnings'],
            ]);

            $eventData = [
                'zone_id' => $zone->id,
                'type' => 'CYCLE_STARTED',
                'created_at' => now(),
            ];

            if ($hasPayloadJson) {
                $eventData['payload_json'] = $eventPayload;
            } else {
                $eventData['details'] = $eventPayload;
            }

            \Illuminate\Support\Facades\DB::table('zone_events')->insert($eventData);

            \Illuminate\Support\Facades\Log::info('Zone cycle started', [
                'zone_id' => $zone->id,
                'status' => 'RUNNING',
                'warnings_count' => count($readiness['warnings']),
            ]);
        });
    }
}
