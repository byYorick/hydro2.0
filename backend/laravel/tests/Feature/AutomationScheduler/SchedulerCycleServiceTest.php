<?php

namespace Tests\Feature\AutomationScheduler;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\SchedulerLog;
use App\Models\Zone;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\EffectiveTargetsService;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerCycleServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_run_cycle_dispatches_and_persists_state(): void
    {
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => 'svc-cycle-task-1',
                        'zone_id' => $zone->id,
                        'accepted' => true,
                        'runner_state' => 'active',
                        'deduplicated' => false,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error', 'message' => 'unexpected request'], 500);
        });

        /** @var SchedulerCycleService $service */
        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertSame(1, (int) ($stats['zones_total'] ?? 0));
        $this->assertGreaterThanOrEqual(1, (int) ($stats['attempted_dispatches'] ?? 0));
        $this->assertGreaterThanOrEqual(1, (int) ($stats['successful_dispatches'] ?? 0));

        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => 'svc-cycle-task-1',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'status' => 'accepted',
        ]);
        $this->assertDatabaseHas('laravel_scheduler_zone_cursors', [
            'zone_id' => $zone->id,
            'catchup_policy' => 'replay_limited',
        ]);
        $this->assertDatabaseHas('scheduler_logs', [
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'accepted',
        ]);
        $this->assertDatabaseHas('scheduler_logs', [
            'task_name' => 'laravel_scheduler_cycle',
            'status' => 'completed',
        ]);
        $this->assertDatabaseHas('scheduler_logs', [
            'task_name' => 'laravel_scheduler_metrics',
            'status' => 'metric',
        ]);

        $metricsLogs = SchedulerLog::query()
            ->where('task_name', 'laravel_scheduler_metrics')
            ->where('status', 'metric')
            ->get();
        $metrics = $metricsLogs
            ->map(static fn (SchedulerLog $log): string => (string) (($log->details ?? [])['metric'] ?? ''))
            ->filter()
            ->values()
            ->all();
        $this->assertContains('laravel_scheduler_dispatches_total', $metrics);
        $this->assertContains('laravel_scheduler_cycle_duration_seconds', $metrics);
        $this->assertContains('laravel_scheduler_active_tasks_count', $metrics);
    }

    public function test_run_cycle_fails_closed_for_ae3_when_start_cycle_response_has_no_canonical_task_id(): void
    {
        [$zone, $cycle] = $this->createZoneAndCycle(automationRuntime: 'ae3');
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'zone_id' => $zone->id,
                        'accepted' => true,
                        'runner_state' => 'active',
                        'deduplicated' => false,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error', 'message' => 'unexpected request'], 500);
        });

        /** @var SchedulerCycleService $service */
        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertSame(1, (int) ($stats['zones_total'] ?? 0));
        $this->assertGreaterThanOrEqual(1, (int) ($stats['attempted_dispatches'] ?? 0));
        $this->assertSame(0, (int) ($stats['successful_dispatches'] ?? 0));
        $this->assertDatabaseMissing('laravel_scheduler_active_tasks', [
            'zone_id' => $zone->id,
        ]);

        $taskLog = SchedulerLog::query()
            ->where('task_name', 'laravel_scheduler_task_irrigation_zone_'.$zone->id)
            ->latest('id')
            ->first();

        $this->assertNotNull($taskLog);
        $this->assertSame('failed', $taskLog->status);
        $this->assertSame('ae3_task_id_missing', ($taskLog->details ?? [])['error'] ?? null);
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
            'active_task_ttl_sec' => 180,
            'active_task_retention_days' => 60,
            'active_task_cleanup_batch' => 500,
            'active_task_poll_batch' => 500,
            'cursor_persist_enabled' => true,
        ];
    }

    /**
     * @return array{0: Zone, 1: GrowCycle}
     */
    private function createZoneAndCycle(string $automationRuntime = 'ae2'): array
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

        return [$zone, $cycle];
    }

    private function bindEffectiveTargetsMock(int $cycleId, int $zoneId): void
    {
        $targetsPayload = [
            'cycle_id' => $cycleId,
            'zone_id' => $zoneId,
            'targets' => [
                'irrigation' => [
                    'interval_sec' => 60,
                    'duration_sec' => 10,
                ],
            ],
        ];

        $mock = Mockery::mock(EffectiveTargetsService::class);
        $mock->shouldReceive('getEffectiveTargetsBatch')
            ->once()
            ->andReturnUsing(static fn (array $cycleIds): array => in_array($cycleId, $cycleIds, true)
                ? [$cycleId => $targetsPayload]
                : []);

        $this->app->instance(EffectiveTargetsService::class, $mock);
    }
}
