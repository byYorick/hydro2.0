<?php

namespace Tests\Feature\AutomationScheduler;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\LaravelSchedulerActiveTask;
use App\Models\Zone;
use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerReliabilityR6Test extends TestCase
{
    use RefreshDatabase;

    public function test_window_interval_dispatches_inside_window_not_only_on_boundary(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-07-07 10:30:00', 'UTC'));
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, [
            'lighting' => [
                'interval_sec' => 1800,
                'start_time' => '08:00:00',
                'photoperiod_hours' => 12,
            ],
        ]);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => '5001',
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
        Http::assertSent(static function (Request $request) use ($zone): bool {
            return $request->method() === 'POST'
                && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick');
        });
        Carbon::setTestNow();
    }

    public function test_window_boundary_schedule_without_interval_dispatches_only_on_crossing(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-07-07 08:00:30', 'UTC'));
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, [
            'lighting' => [
                'start_time' => '08:00:00',
                'photoperiod_hours' => 12,
            ],
        ]);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => '5002',
                        'zone_id' => $zone->id,
                        'accepted' => true,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error'], 500);
        });

        /** @var SchedulerCycleService $service */
        $service = $this->app->make(SchedulerCycleService::class);
        $cfg = $this->schedulerConfig();
        $stats = $service->runCycle($cfg, [$zone->id]);

        $this->assertGreaterThanOrEqual(1, (int) ($stats['successful_dispatches'] ?? 0));

        Http::fake();
        Carbon::setTestNow(CarbonImmutable::parse('2026-07-07 10:00:00', 'UTC'));
        $midWindowStats = $service->runCycle($cfg, [$zone->id]);
        $this->assertSame(0, (int) ($midWindowStats['successful_dispatches'] ?? 0));
        Http::assertNothingSent();
        Carbon::setTestNow();
    }

    public function test_interval_missed_ticks_record_prometheus_counter(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-07-07 12:00:00', 'UTC'));
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, [
            'irrigation' => [
                'interval_sec' => 60,
                'duration_sec' => 10,
            ],
        ]);

        LaravelSchedulerActiveTask::query()->create([
            'task_id' => 'missed-1',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=60',
            'correlation_id' => 'corr-missed-1',
            'status' => 'completed',
            'accepted_at' => CarbonImmutable::parse('2026-07-07 11:56:00', 'UTC'),
            'due_at' => CarbonImmutable::parse('2026-07-07 11:57:00', 'UTC'),
            'expires_at' => CarbonImmutable::parse('2026-07-07 11:58:00', 'UTC'),
            'terminal_at' => CarbonImmutable::parse('2026-07-07 11:56:30', 'UTC'),
            'details' => [],
        ]);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-irrigation')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => '8001',
                        'zone_id' => $zone->id,
                        'accepted' => true,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error'], 500);
        });

        /** @var SchedulerCycleService $service */
        $service = $this->app->make(SchedulerCycleService::class);
        $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertDatabaseHas('laravel_scheduler_missed_windows_totals', [
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
        ]);

        $row = DB::table('laravel_scheduler_missed_windows_totals')
            ->where('zone_id', $zone->id)
            ->where('task_type', 'irrigation')
            ->first();
        $this->assertNotNull($row);
        $this->assertGreaterThanOrEqual(2, (int) ($row->total ?? 0));
        Carbon::setTestNow();
    }

    public function test_dispatch_command_fails_closed_when_scheduler_api_token_missing(): void
    {
        $this->enableSchedulerConfig();
        Config::set('services.automation_engine.scheduler_api_token', '');

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(1);

        $this->assertDatabaseHas('scheduler_logs', [
            'task_name' => SchedulerConstants::CYCLE_LOG_TASK_NAME,
            'status' => 'failed',
        ]);
    }

    public function test_dispatch_command_records_lock_skipped_metric(): void
    {
        $this->enableSchedulerConfig();

        $lock = Mockery::mock(\Illuminate\Contracts\Cache\Lock::class);
        Cache::shouldReceive('lock')
            ->once()
            ->andReturn($lock);
        $lock->shouldReceive('get')->once()->andReturn(false);

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $this->assertDatabaseHas('laravel_scheduler_lock_skipped_totals', [
            'total' => 1,
        ]);
    }

    public function test_irrigation_terminal_dispatch_failure_raises_biz_window_missed_alert(): void
    {
        [$zone, $cycle] = $this->createZoneAndCycle(automationRuntime: 'ae3');
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, [
            'irrigation' => [
                'interval_sec' => 60,
                'duration_sec' => 10,
            ],
        ]);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-irrigation')) {
                return Http::response([
                    'detail' => [
                        'error' => 'start_irrigation_intent_terminal',
                        'zone_id' => $zone->id,
                    ],
                ], 409);
            }

            return Http::response(['status' => 'error'], 500);
        });

        /** @var SchedulerCycleService $service */
        $service = $this->app->make(SchedulerCycleService::class);
        $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'code' => 'biz_irrigation_window_missed',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_scheduler_metrics_endpoint_requires_token_when_configured(): void
    {
        Config::set('services.automation_engine.scheduler_metrics_token', 'metrics-secret');

        $this->get('/api/system/scheduler/metrics')
            ->assertStatus(401);

        $this->withHeader('Authorization', 'Bearer metrics-secret')
            ->get('/api/system/scheduler/metrics')
            ->assertOk();
    }

    /**
     * @return array{0: Zone, 1: GrowCycle}
     */
    private function createZoneAndCycle(string $automationRuntime = 'ae3'): array
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => $automationRuntime,
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

    private function enableSchedulerConfig(): void
    {
        Config::set('services.automation_engine.laravel_scheduler_enabled', true);
        Config::set('services.automation_engine.api_url', 'http://automation-engine:9405');
        Config::set('services.automation_engine.timeout', 2.0);
        Config::set('services.automation_engine.scheduler_api_token', 'test-token');
        Config::set('services.automation_engine.scheduler_dispatch_interval_sec', 60);
        Config::set('services.automation_engine.scheduler_due_grace_sec', 15);
        Config::set('services.automation_engine.scheduler_expires_after_sec', 120);
        Config::set('services.automation_engine.scheduler_active_task_ttl_sec', 180);
        Config::set('services.automation_engine.scheduler_catchup_policy', 'replay_limited');
        Config::set('services.automation_engine.scheduler_cursor_persist_enabled', true);
    }
}
