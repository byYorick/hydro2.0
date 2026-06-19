<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Services\AutomationScheduler\ScheduleSpecHelper;
use App\Services\AutomationScheduler\SchedulerCycleFinalizer;
use Carbon\CarbonImmutable;
use Tests\TestCase;

class ScheduleSpecHelperTest extends TestCase
{
    public function test_normalize_days_of_week_filters_invalid_values(): void
    {
        $this->assertSame([1, 3, 5], ScheduleSpecHelper::normalizeDaysOfWeek([1, 3, 5, 9, 0]));
        $this->assertSame([], ScheduleSpecHelper::normalizeDaysOfWeek(null));
    }

    public function test_matches_day_of_week_empty_means_all_days(): void
    {
        $monday = CarbonImmutable::parse('2026-06-15 10:00:00', 'UTC');

        $this->assertTrue(ScheduleSpecHelper::matchesDayOfWeek($monday, []));
        $this->assertTrue(ScheduleSpecHelper::matchesDayOfWeek($monday, [1]));
        $this->assertFalse(ScheduleSpecHelper::matchesDayOfWeek($monday, [2]));
    }

    public function test_once_ready_to_dispatch_when_run_at_crossed(): void
    {
        $finalizer = new SchedulerCycleFinalizer(
            zoneCursorStore: $this->createMock(\App\Services\AutomationScheduler\ZoneCursorStore::class),
            activeTaskStore: $this->createMock(\App\Services\AutomationScheduler\ActiveTaskStore::class),
        );

        $last = CarbonImmutable::parse('2026-06-19 10:00:00', 'UTC');
        $now = CarbonImmutable::parse('2026-06-19 10:05:00', 'UTC');

        $this->assertTrue($finalizer->onceReadyToDispatch($last, $now, '2026-06-19T10:02:00Z'));
        $this->assertFalse($finalizer->onceReadyToDispatch($last, $now, '2026-06-19T11:00:00Z'));
    }

    public function test_manual_interval_task_log_name_is_distinct_per_manual_schedule(): void
    {
        $recipe = \App\Services\AutomationScheduler\SchedulerRuntimeHelper::intervalTaskLogName(3, 'irrigation');
        $manual = \App\Services\AutomationScheduler\SchedulerRuntimeHelper::intervalTaskLogName(3, 'irrigation', 12);

        $this->assertSame('laravel_scheduler_task_irrigation_zone_3', $recipe);
        $this->assertSame('laravel_scheduler_task_irrigation_manual_12_zone_3', $manual);
        $this->assertNotSame($recipe, $manual);
    }
}
