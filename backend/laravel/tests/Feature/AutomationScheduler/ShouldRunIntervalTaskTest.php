<?php

namespace Tests\Feature\AutomationScheduler;

use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\ScheduleLoader;
use App\Services\AutomationScheduler\SchedulerCycleFinalizer;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ShouldRunIntervalTaskTest extends TestCase
{
    use RefreshDatabase;

    private ScheduleLoader $scheduleLoader;

    private SchedulerCycleFinalizer $finalizer;

    protected function setUp(): void
    {
        parent::setUp();

        $activeTaskStore = new ActiveTaskStore;
        $zoneCursorStore = new ZoneCursorStore;
        $this->scheduleLoader = new ScheduleLoader(
            effectiveTargetsService: Mockery::mock(EffectiveTargetsService::class),
            zoneCursorStore: $zoneCursorStore,
        );
        $this->finalizer = new SchedulerCycleFinalizer(
            zoneCursorStore: $zoneCursorStore,
            activeTaskStore: $activeTaskStore,
        );
    }

    public function test_interval_tasks_use_single_batch_query_for_last_terminal_runs(): void
    {
        DB::table('scheduler_logs')->insert([
            [
                'task_name' => 'laravel_scheduler_task_irrigation_zone_1',
                'status' => 'completed',
                'details' => json_encode(['task_id' => 'a'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => '2026-03-03 12:00:00',
            ],
            [
                'task_name' => 'laravel_scheduler_task_lighting_zone_1',
                'status' => 'failed',
                'details' => json_encode(['task_id' => 'b'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => '2026-03-03 11:58:00',
            ],
            [
                'task_name' => 'laravel_scheduler_task_lighting_zone_1',
                'status' => 'running',
                'details' => json_encode(['task_id' => 'c'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => '2026-03-03 12:05:00',
            ],
        ]);

        $schedules = [
            new ScheduleItem(zoneId: 1, taskType: 'irrigation', intervalSec: 60),
            new ScheduleItem(zoneId: 1, taskType: 'lighting', intervalSec: 60),
            new ScheduleItem(zoneId: 1, taskType: 'mist', intervalSec: 60),
            new ScheduleItem(zoneId: 2, taskType: 'mist', intervalSec: 60),
        ];

        $taskNames = $this->scheduleLoader->collectIntervalTaskNames($schedules);
        $this->assertCount(4, $taskNames);

        DB::flushQueryLog();
        DB::enableQueryLog();

        $lastRunByTaskName = $this->scheduleLoader->loadLastRunBatch($taskNames);
        $this->assertCount(1, DB::getQueryLog());
        DB::flushQueryLog();

        $now = CarbonImmutable::parse('2026-03-03 12:00:30', 'UTC');
        $this->assertFalse($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_irrigation_zone_1',
            60,
            $now,
            $lastRunByTaskName,
        ));
        $this->assertTrue($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_lighting_zone_1',
            60,
            $now,
            $lastRunByTaskName,
        ));
        $this->assertTrue($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_mist_zone_1',
            60,
            $now,
            $lastRunByTaskName,
        ));
        $this->assertCount(0, DB::getQueryLog());
    }
}
