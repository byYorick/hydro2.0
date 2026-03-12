<?php

namespace App\Services\AutomationScheduler;

class SchedulerCycleService
{
    public function __construct(
        private readonly SchedulerCycleOrchestrator $orchestrator,
    ) {}

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<int, int>  $zoneFilter
     * @return array<string, mixed>
     */
    public function runCycle(array $cfg, array $zoneFilter): array
    {
        return $this->orchestrator->runCycle($cfg, $zoneFilter);
    }
}
