<?php

namespace Tests\Unit\Console;

use App\Services\AutomationScheduler\ActiveTaskPoller;
use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\LightingScheduleParser;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Mockery;
use ReflectionClass;
use Tests\TestCase;

class AutomationDispatchSchedulesInternalsTest extends TestCase
{
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

    public function test_compute_task_deadlines_applies_due_and_expiry_offsets(): void
    {
        $scheduledFor = CarbonImmutable::parse('2026-02-20 12:00:00', 'UTC');

        [$dueAt, $expiresAt] = $this->invokePrivateMethod(
            'computeTaskDeadlines',
            [$scheduledFor, 15, 120],
        );

        $this->assertSame('2026-02-20T12:00:15Z', $dueAt);
        $this->assertSame('2026-02-20T12:02:00Z', $expiresAt);
    }

    public function test_build_scheduler_correlation_id_is_deterministic_and_zone_scoped(): void
    {
        $scheduleKey = 'zone:3|type:irrigation|time=None|start=None|end=None|interval=60';
        $scheduledFor = '2026-02-20T12:00:00';

        $first = $this->invokePrivateMethod('buildSchedulerCorrelationId', [
            3,
            'irrigation',
            $scheduledFor,
            $scheduleKey,
        ]);
        $second = $this->invokePrivateMethod('buildSchedulerCorrelationId', [
            3,
            'irrigation',
            $scheduledFor,
            $scheduleKey,
        ]);
        $otherZone = $this->invokePrivateMethod('buildSchedulerCorrelationId', [
            4,
            'irrigation',
            $scheduledFor,
            $scheduleKey,
        ]);

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

        $result = $this->invokePrivateMethod('applyCatchupPolicy', [
            $crossings,
            $now,
            'replay_limited',
            2,
        ]);

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

        $result = $this->invokePrivateMethod('applyCatchupPolicy', [
            $crossings,
            $now,
            'skip',
            3,
        ]);

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
