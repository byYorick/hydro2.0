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
        // Единственный runtime в БД — ae3 (CHECK). Отдельной матрицы AE2/legacy нет.
        $executable = ['irrigation', 'lighting', 'solution_topup', 'solution_change', 'diagnostics'];
        $nonExecutablePlanned = array_values(array_diff($plannedTaskTypes, $executable));

        return [
            'executable_task_types' => $executable,
            'planned_task_types' => $plannedTaskTypes,
            // Историческое имя API-поля: «ограниченный набор типов под автодиспатч на AE3».
            // Не переименовывать — контракт Vue / schedule-workspace.
            'ae3_irrigation_only_dispatch' => $zone->automation_runtime === 'ae3',
            'non_executable_planned_task_types' => $nonExecutablePlanned,
            'diagnostics_available' => true,
        ];
    }
}
