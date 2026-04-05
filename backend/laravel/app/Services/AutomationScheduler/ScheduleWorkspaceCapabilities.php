<?php

namespace App\Services\AutomationScheduler;

use App\Models\Zone;

/**
 * Расчёт полей `capabilities` для GET /api/zones/{id}/schedule-workspace.
 * Вынесено для unit-тестов (в БД сейчас допустим только `automation_runtime=ae3`, см. миграции).
 */
final class ScheduleWorkspaceCapabilities
{
    /**
     * @param  array<int, string>  $plannedTaskTypes
     * @return array<string, mixed>
     */
    public static function build(Zone $zone, array $plannedTaskTypes): array
    {
        $isAe3 = $zone->automation_runtime === 'ae3';
        $executable = $isAe3
            ? ['irrigation', 'lighting', 'diagnostics']
            : array_values($plannedTaskTypes);
        $nonExecutablePlanned = array_values(array_diff($plannedTaskTypes, $executable));

        return [
            'executable_task_types' => $executable,
            'planned_task_types' => $plannedTaskTypes,
            'ae3_irrigation_only_dispatch' => $isAe3,
            'non_executable_planned_task_types' => $nonExecutablePlanned,
            'diagnostics_available' => true,
        ];
    }
}
