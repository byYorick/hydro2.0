<?php

namespace Tests\Unit\Console;

use App\Services\AutomationScheduler\ActiveTaskPoller;
use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use App\Services\AutomationScheduler\SchedulerCycleFinalizer;
use App\Services\AutomationScheduler\ZoneCursorStore;
use Carbon\CarbonImmutable;
use Tests\TestCase;

class AutomationDispatchSchedulesInternalsTest extends TestCase
{
    private ScheduleDispatcher $dispatcher;

    private SchedulerCycleFinalizer $finalizer;

    protected function setUp(): void
    {
        parent::setUp();

        $activeTaskStore = new ActiveTaskStore;
        $zoneCursorStore = new ZoneCursorStore;

        $this->dispatcher = new ScheduleDispatcher(
            activeTaskStore: $activeTaskStore,
            activeTaskPoller: new ActiveTaskPoller($activeTaskStore),
        );
        $this->finalizer = new SchedulerCycleFinalizer(
            zoneCursorStore: $zoneCursorStore,
            activeTaskStore: $activeTaskStore,
        );
    }

    public function test_compute_task_deadlines_applies_due_and_expiry_offsets(): void
    {
        $scheduledFor = CarbonImmutable::parse('2026-02-20 12:00:00', 'UTC');

        [$dueAt, $expiresAt] = $this->dispatcher->computeTaskDeadlines($scheduledFor, 15, 120);

        $this->assertSame('2026-02-20T12:00:15Z', $dueAt);
        $this->assertSame('2026-02-20T12:02:00Z', $expiresAt);
    }

    public function test_build_scheduler_correlation_id_is_deterministic_and_zone_scoped(): void
    {
        $scheduleKey = 'zone:3|type:irrigation|time=None|start=None|end=None|interval=60';
        $scheduledFor = '2026-02-20T12:00:00';

        $first = $this->dispatcher->buildSchedulerCorrelationId(3, 'irrigation', $scheduledFor, $scheduleKey);
        $second = $this->dispatcher->buildSchedulerCorrelationId(3, 'irrigation', $scheduledFor, $scheduleKey);
        $otherZone = $this->dispatcher->buildSchedulerCorrelationId(4, 'irrigation', $scheduledFor, $scheduleKey);

        $this->assertSame($first, $second);
        $this->assertNotSame($first, $otherZone);
        $this->assertMatchesRegularExpression('/^sch:z3:irrigation:[a-f0-9]{20}$/', $first);
    }

    public function test_apply_catchup_policy_replay_limited_keeps_latest_windows(): void
    {
        $crossings = [
            CarbonImmutable::parse('2026-02-20 10:00:00', 'UTC'),
            CarbonImmutable::parse('2026-02-20 11:00:00', 'UTC'),
            CarbonImmutable::parse('2026-02-20 12:00:00', 'UTC'),
        ];
        $now = CarbonImmutable::parse('2026-02-20 12:05:00', 'UTC');

        $result = $this->finalizer->applyCatchupPolicy($crossings, $now, 'replay_limited', 2);

        $this->assertCount(2, $result);
        $this->assertSame('2026-02-20T11:00:00', $result[0]->format('Y-m-d\TH:i:s'));
        $this->assertSame('2026-02-20T12:00:00', $result[1]->format('Y-m-d\TH:i:s'));
    }

    public function test_apply_catchup_policy_skip_uses_current_tick(): void
    {
        $crossings = [
            CarbonImmutable::parse('2026-02-20 11:00:00', 'UTC'),
            CarbonImmutable::parse('2026-02-20 12:00:00', 'UTC'),
        ];
        $now = CarbonImmutable::parse('2026-02-20 12:05:00', 'UTC');

        $result = $this->finalizer->applyCatchupPolicy($crossings, $now, 'skip', 3);

        $this->assertCount(1, $result);
        $this->assertSame('2026-02-20T12:05:00', $result[0]->format('Y-m-d\TH:i:s'));
    }

    public function test_should_run_interval_task_uses_batch_map_without_database_access(): void
    {
        $now = CarbonImmutable::parse('2026-02-20 12:05:00', 'UTC');
        $lastRunByTaskName = [
            'laravel_scheduler_task_irrigation_zone_1' => CarbonImmutable::parse('2026-02-20 12:04:30', 'UTC'),
            'laravel_scheduler_task_lighting_zone_1' => CarbonImmutable::parse('2026-02-20 12:03:00', 'UTC'),
        ];

        $this->assertFalse($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_irrigation_zone_1', 60, $now, $lastRunByTaskName,
        ));
        $this->assertTrue($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_lighting_zone_1', 60, $now, $lastRunByTaskName,
        ));
        $this->assertTrue($this->finalizer->shouldRunIntervalTask(
            'laravel_scheduler_task_mist_zone_1', 60, $now, $lastRunByTaskName,
        ));
    }
}
