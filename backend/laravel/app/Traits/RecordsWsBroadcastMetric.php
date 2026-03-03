<?php

namespace App\Traits;

use App\Services\PipelineMetricsService;

trait RecordsWsBroadcastMetric
{
    protected function recordWsBroadcastMetric(string $eventType): void
    {
        PipelineMetricsService::trackWsBroadcast($eventType);
    }
}
