<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleWorkspaceCapabilities;
use Tests\TestCase;

class ScheduleWorkspaceCapabilitiesTest extends TestCase
{
    public function test_ae3_marks_only_irrigation_executable_and_lists_non_executable_planned(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'ae3'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['irrigation', 'lighting']);

        $this->assertTrue($caps['ae3_irrigation_only_dispatch']);
        $this->assertSame(['irrigation'], $caps['executable_task_types']);
        $this->assertSame(['lighting'], $caps['non_executable_planned_task_types']);
        $this->assertTrue($caps['diagnostics_available']);
    }

    public function test_ae3_with_only_irrigation_planned_has_empty_non_executable_list(): void
    {
        $zone = new Zone;
        $zone->setRawAttributes(['automation_runtime' => 'ae3'], true);

        $caps = ScheduleWorkspaceCapabilities::build($zone, ['irrigation']);

        $this->assertSame([], $caps['non_executable_planned_task_types']);
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
