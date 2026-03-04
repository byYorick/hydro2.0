<?php

namespace Tests\Feature\AutomationScheduler;

use App\Services\AutomationScheduler\ActiveTaskPoller;
use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\LightingScheduleParser;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Mockery;
use ReflectionClass;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ShouldRunIntervalTaskTest extends TestCase
{
    use RefreshDatabase;

    private SchedulerCycleService $service;

    private ReflectionClass $reflection;

    protected function setUp(): void
    {
        parent::setUp();

        $activeTaskStore = new ActiveTaskStore;
        $this->service = new SchedulerCycleService(
            effectiveTargetsService: Mockery::mock(EffectiveTargetsService::class),
            activeTaskStore: $activeTaskStore,
            zoneCursorStore: new ZoneCursorStore,
            lightingScheduleParser: new LightingScheduleParser,
            activeTaskPoller: new ActiveTaskPoller($activeTaskStore),
        );
        $this->reflection = new ReflectionClass($this->service);
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

        $taskNames = $this->invokePrivateMethod('collectIntervalTaskNames', [$schedules]);
        $this->assertCount(4, $taskNames);

        DB::flushQueryLog();
        DB::enableQueryLog();

        /** @var array<string, CarbonImmutable> $lastRunByTaskName */
        $lastRunByTaskName = $this->invokePrivateMethod('loadLastRunBatch', [$taskNames]);
        $this->assertCount(1, DB::getQueryLog());
        DB::flushQueryLog();

        $now = CarbonImmutable::parse('2026-03-03 12:00:30', 'UTC');
        $this->assertFalse($this->invokePrivateMethod('shouldRunIntervalTask', [
            'laravel_scheduler_task_irrigation_zone_1',
            60,
            $now,
            $lastRunByTaskName,
        ]));
        $this->assertTrue($this->invokePrivateMethod('shouldRunIntervalTask', [
            'laravel_scheduler_task_lighting_zone_1',
            60,
            $now,
            $lastRunByTaskName,
        ]));
        $this->assertTrue($this->invokePrivateMethod('shouldRunIntervalTask', [
            'laravel_scheduler_task_mist_zone_1',
            60,
            $now,
            $lastRunByTaskName,
        ]));
        $this->assertCount(0, DB::getQueryLog());
    }

    /**
     * @param  array<int, mixed>  $args
     */
    private function invokePrivateMethod(string $method, array $args = []): mixed
    {
        $refMethod = $this->reflection->getMethod($method);
        $refMethod->setAccessible(true);

        return $refMethod->invokeArgs($this->service, $args);
    }
}
