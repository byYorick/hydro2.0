<?php

namespace App\Services\AutomationScheduler;

/**
 * Диспетчер Laravel удалён волной 10. Класс оставлен как no-op для DI.
 * Wake-up зон ведёт automation-engine 1.0.0.
 */
class SchedulerCycleOrchestrator
{
    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<int, int>  $zoneFilter
     * @return array<string, mixed>
     */
    public function runCycle(array $cfg, array $zoneFilter): array
    {
        unset($cfg, $zoneFilter);

        return [
            'dispatch_mode' => 'none',
            'zones_total' => 0,
            'zones_with_targets' => 0,
            'schedules_total' => 0,
            'attempted_dispatches' => 0,
            'successful_dispatches' => 0,
            'skipped' => 'dispatcher_removed_wave10',
        ];
    }
}
