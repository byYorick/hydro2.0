<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleWorkspaceCapabilities;
use Tests\TestCase;

class ScheduleWorkspaceCapabilitiesTest extends TestCase
{
    public function test_ae3_marks_irrigation_lighting_and_diagnostics_executable(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'ae3'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['irrigation', 'lighting', 'diagnostics']);

        $this->assertTrue($caps['ae3_irrigation_only_dispatch']);
        $this->assertSame(['irrigation', 'lighting', 'diagnostics'], $caps['executable_task_types']);
        $this->assertSame([], $caps['non_executable_planned_task_types']);
        $this->assertTrue($caps['diagnostics_available']);
    }

    public function test_ae3_lists_other_planned_types_as_non_executable(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'ae3'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['irrigation', 'lighting', 'climate']);

        $this->assertSame(['climate'], $caps['non_executable_planned_task_types']);
    }

    public function test_ae3_with_only_irrigation_planned_has_empty_non_executable_list(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'ae3'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['irrigation']);

        $this->assertSame([], $caps['non_executable_planned_task_types']);
    }

    public function test_ae3_does_not_mark_diagnostics_as_non_executable(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'ae3'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['diagnostics', 'climate']);

        $this->assertSame(['irrigation', 'lighting', 'diagnostics'], $caps['executable_task_types']);
        $this->assertSame(['climate'], $caps['non_executable_planned_task_types']);
    }

    /**
     * В PostgreSQL для zones сейчас CHECK только на ae3; ветка «не ae3» — для совместимости кода и тестов без БД.
     */
    public function test_non_ae3_runtime_treats_all_planned_types_as_executable(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'legacy'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['irrigation', 'lighting', 'climate']);

        $this->assertFalse($caps['ae3_irrigation_only_dispatch']);
        $this->assertSame(['irrigation', 'lighting', 'climate'], $caps['executable_task_types']);
        $this->assertSame([], $caps['non_executable_planned_task_types']);
    }
}
