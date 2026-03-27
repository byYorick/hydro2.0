<?php

namespace Tests\Feature\AutomationScheduler;

use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\ScheduleLoader;
use App\Services\AutomationScheduler\SchedulerCycleFinalizer;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use App\Models\Zone;
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
        $firstZone = Zone::factory()->create();
        $secondZone = Zone::factory()->create();

        DB::table('laravel_scheduler_active_tasks')->insert([
            [
                'task_id' => '1',
                'zone_id' => $firstZone->id,
                'task_type' => 'irrigation',
                'schedule_key' => sprintf('zone:%d|type:irrigation|time=None|start=None|end=None|interval=60', $firstZone->id),
                'correlation_id' => sprintf('sch:z%d:irrigation:a', $firstZone->id),
                'status' => 'completed',
                'accepted_at' => '2026-03-03 11:59:00',
                'terminal_at' => '2026-03-03 12:00:00',
                'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => '2026-03-03 11:59:00',
                'updated_at' => '2026-03-03 12:00:00',
            ],
            [
                'task_id' => '2',
                'zone_id' => $firstZone->id,
                'task_type' => 'lighting',
                'schedule_key' => sprintf('zone:%d|type:lighting|time=None|start=None|end=None|interval=60', $firstZone->id),
                'correlation_id' => sprintf('sch:z%d:lighting:b', $firstZone->id),
                'status' => 'failed',
                'accepted_at' => '2026-03-03 11:57:00',
                'terminal_at' => '2026-03-03 11:58:00',
                'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => '2026-03-03 11:57:00',
                'updated_at' => '2026-03-03 11:58:00',
            ],
            [
                'task_id' => '3',
                'zone_id' => $firstZone->id,
                'task_type' => 'lighting',
                'schedule_key' => sprintf('zone:%d|type:lighting|time=None|start=None|end=None|interval=60', $firstZone->id),
                'correlation_id' => sprintf('sch:z%d:lighting:c', $firstZone->id),
                'status' => 'running',
                'accepted_at' => '2026-03-03 12:05:00',
                'terminal_at' => null,
                'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => '2026-03-03 12:05:00',
                'updated_at' => '2026-03-03 12:05:00',
            ],
        ]);

        $schedules = [
            new ScheduleItem(zoneId: $firstZone->id, taskType: 'irrigation', intervalSec: 60),
            new ScheduleItem(zoneId: $firstZone->id, taskType: 'lighting', intervalSec: 60),
            new ScheduleItem(zoneId: $firstZone->id, taskType: 'mist', intervalSec: 60),
            new ScheduleItem(zoneId: $secondZone->id, taskType: 'mist', intervalSec: 60),
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
            'laravel_scheduler_task_irrigation_zone_'.$firstZone->id,
            60,
            $now,
            $lastRunByTaskName,
        ));
        $this->assertTrue($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_lighting_zone_'.$firstZone->id,
            60,
            $now,
            $lastRunByTaskName,
        ));
        $this->assertTrue($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_mist_zone_'.$firstZone->id,
            60,
            $now,
            $lastRunByTaskName,
        ));
        $this->assertCount(0, DB::getQueryLog());
    }
}
