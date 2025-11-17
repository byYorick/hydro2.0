<?php

namespace App\Listeners;

use App\Events\ZoneUpdated;
use App\Services\PythonBridgeService;
use Illuminate\Support\Facades\Log;

class PublishZoneConfigUpdate
{
    public function __construct(
        private PythonBridgeService $pythonBridge
    ) {
    }

    /**
     * Handle the event.
     */
    public function handle(ZoneUpdated $event): void
    {
        try {
            // Уведомить Python-сервис об обновлении конфигурации зоны
            // Python-сервис должен перезагрузить конфигурацию через /api/system/config/full
            Log::info('Zone config updated, notifying Python service', [
                'zone_id' => $event->zone->id,
            ]);
            
            // Прямой вызов API Python-сервиса для уведомления об обновлении
            $this->pythonBridge->notifyConfigUpdate($event->zone);
        } catch (\Exception $e) {
            Log::error('Failed to publish zone config update', [
                'zone_id' => $event->zone->id,
                'error' => $e->getMessage(),
            ]);
        }
    }
}

