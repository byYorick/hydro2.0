<?php

namespace Tests\Feature\AutomationScheduler;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleCycleContext;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class LightingDesiredStateDispatchTest extends TestCase
{
    use RefreshDatabase;

    public function test_window_exit_dispatches_lighting_tick_with_desired_state_off(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-07-07 22:00:30', 'UTC'));
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->seedZoneCursor($zone->id, CarbonImmutable::parse('2026-07-07 21:30:00', 'UTC'));
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, [
            'lighting' => [
                'start_time' => '06:00:00',
                'photoperiod_hours' => 16,
                'brightness' => 80,
                'brightness_night' => 0,
            ],
        ]);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => '5101',
                        'zone_id' => $zone->id,
                        'accepted' => true,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error'], 500);
        });

        /** @var SchedulerCycleService $service */
        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertGreaterThanOrEqual(1, (int) ($stats['successful_dispatches'] ?? 0));
        Http::assertSent(function (Request $request) use ($zone): bool {
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return false;
            }
            $payload = $request->data();

            return ($payload['desired_state'] ?? null) === 'off'
                && ($payload['brightness'] ?? null) === 0;
        });
        Carbon::setTestNow();
    }

    public function test_dispatcher_forwards_desired_state_and_brightness_in_start_lighting_tick_payload(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-lighting-tick' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '5102',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-07-07 22:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'lighting',
            startTime: '06:00:00',
            endTime: '22:00:00',
            payload: [
                'desired_state' => 'off',
                'brightness' => 75,
                'brightness_night' => 5,
            ],
        );
        $context = new ScheduleCycleContext(
            cfg: [
                'timeout_sec' => 2.0,
                'api_url' => 'http://automation-engine:9405',
                'due_grace_sec' => 15,
                'expires_after_sec' => 600,
                'active_task_ttl_sec' => 600,
            ],
            headers: [
                'Accept' => 'application/json',
                'Authorization' => 'Bearer dev-token-12345',
                'X-Trace-Id' => 'test-trace-id',
            ],
            traceId: 'test-trace-id',
            cycleNow: $triggerTime,
            lastRunByTaskName: [],
            reconciledBusyness: [],
            zoneWorkflowPhases: [],
        );

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: static function (): void {},
        );

        $this->assertSame([
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ], $result);

        Http::assertSent(function (Request $request) use ($zone): bool {
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return false;
            }
            $payload = $request->data();

            return ($payload['source'] ?? null) === 'laravel_scheduler'
                && ($payload['desired_state'] ?? null) === 'off'
                && ($payload['brightness'] ?? null) === 5;
        });
    }

    public function test_dispatcher_defaults_desired_state_on_for_interval_lighting_without_window_transition(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-lighting-tick' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '5103',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-07-07 10:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'lighting',
            intervalSec: 1800,
            payload: ['brightness' => 60],
        );
        $context = new ScheduleCycleContext(
            cfg: [
                'timeout_sec' => 2.0,
                'api_url' => 'http://automation-engine:9405',
                'due_grace_sec' => 15,
                'expires_after_sec' => 600,
                'active_task_ttl_sec' => 600,
            ],
            headers: [
                'Accept' => 'application/json',
                'Authorization' => 'Bearer dev-token-12345',
                'X-Trace-Id' => 'test-trace-id',
            ],
            traceId: 'test-trace-id',
            cycleNow: $triggerTime,
            lastRunByTaskName: [],
            reconciledBusyness: [],
            zoneWorkflowPhases: [],
        );

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: static function (): void {},
        );

        $this->assertTrue($result['dispatched']);
        Http::assertSent(function (Request $request) use ($zone): bool {
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return false;
            }
            $payload = $request->data();

            return ($payload['desired_state'] ?? null) === 'on'
                && ($payload['brightness'] ?? null) === 60;
        });
    }

    /**
     * @return array{0: Zone, 1: GrowCycle}
     */
    private function createZoneAndCycle(): array
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        $cycle = GrowCycle::factory()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        DB::table('zone_workflow_state')->updateOrInsert(
            ['zone_id' => $zone->id],
            [
                'workflow_phase' => 'ready',
                'updated_at' => now(),
            ],
        );

        return [$zone, $cycle];
    }

    private function seedZoneCursor(int $zoneId, CarbonImmutable $cursorAt): void
    {
        DB::table('laravel_scheduler_zone_cursors')->updateOrInsert(
            ['zone_id' => $zoneId],
            [
                'cursor_at' => $cursorAt,
                'catchup_policy' => 'replay_limited',
                'metadata' => json_encode(['source' => 'test'], JSON_THROW_ON_ERROR),
                'created_at' => now(),
                'updated_at' => now(),
            ],
        );
    }

    /**
     * @param  array<string, mixed>  $targets
     */
    private function bindEffectiveTargetsMock(int $cycleId, int $zoneId, array $targets): void
    {
        $targetsPayload = [
            'cycle_id' => $cycleId,
            'zone_id' => $zoneId,
            'targets' => $targets,
        ];

        $mock = Mockery::mock(EffectiveTargetsService::class);
        $mock->shouldReceive('getEffectiveTargetsBatch')
            ->andReturnUsing(static fn (array $cycleIds): array => in_array($cycleId, $cycleIds, true)
                ? [$cycleId => $targetsPayload]
                : []);

        $this->app->instance(EffectiveTargetsService::class, $mock);
    }

    /**
     * @return array<string, mixed>
     */
    private function schedulerConfig(): array
    {
        return [
            'api_url' => 'http://automation-engine:9405',
            'timeout_sec' => 2.0,
            'scheduler_id' => 'laravel-scheduler',
            'scheduler_version' => '3.0.0',
            'protocol_version' => '2.0',
            'token' => 'test-token',
            'due_grace_sec' => 15,
            'expires_after_sec' => 120,
            'catchup_policy' => 'replay_limited',
            'catchup_max_windows' => 3,
            'catchup_rate_limit_per_cycle' => 20,
            'dispatch_interval_sec' => 60,
            'dispatch_parallelism' => 8,
            'active_task_ttl_sec' => 180,
            'active_task_retention_days' => 60,
            'active_task_cleanup_batch' => 500,
            'active_task_poll_batch' => 500,
            'cursor_persist_enabled' => true,
        ];
    }
}
