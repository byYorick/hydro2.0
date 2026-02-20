<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\LaravelSchedulerActiveTask;
use App\Models\Zone;
use App\Services\EffectiveTargetsService;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationDispatchSchedulesCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_command_skips_when_scheduler_disabled(): void
    {
        Config::set('services.automation_engine.laravel_scheduler_enabled', false);

        $this->artisan('automation:dispatch-schedules')
            ->expectsOutput('AUTOMATION_LARAVEL_SCHEDULER_ENABLED=0, dispatch skipped.')
            ->assertExitCode(0);
    }

    public function test_command_dispatches_and_persists_durable_state(): void
    {
        $this->enableSchedulerConfig();
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, 1);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/scheduler/bootstrap')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'bootstrap_status' => 'ready',
                        'lease_id' => 'lease-test-1',
                    ],
                ], 200);
            }

            if ($request->method() === 'POST' && str_ends_with($request->url(), '/scheduler/task')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => 'st-accepted-1',
                        'zone_id' => $zone->id,
                        'task_type' => 'irrigation',
                        'status' => 'accepted',
                        'is_duplicate' => false,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error', 'message' => 'unexpected request'], 500);
        });

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => 'st-accepted-1',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'status' => 'accepted',
        ]);
        $this->assertDatabaseHas('laravel_scheduler_zone_cursors', [
            'zone_id' => $zone->id,
            'catchup_policy' => 'replay_limited',
        ]);

        $task = LaravelSchedulerActiveTask::query()
            ->where('task_id', 'st-accepted-1')
            ->first();
        $this->assertNotNull($task);
        $this->assertNotNull($task->due_at);
        $this->assertNotNull($task->expires_at);
        $this->assertArrayHasKey('schedule_key', $task->details ?? []);

        Http::assertSent(function (Request $request) use ($zone): bool {
            if (! ($request->method() === 'POST' && str_ends_with($request->url(), '/scheduler/task'))) {
                return false;
            }

            $payload = $request->data();
            $correlationId = (string) ($payload['correlation_id'] ?? '');
            $taskPayload = is_array($payload['payload'] ?? null) ? $payload['payload'] : [];
            $scheduleKey = (string) ($taskPayload['schedule_key'] ?? '');

            return (int) ($payload['zone_id'] ?? 0) === $zone->id
                && (string) ($payload['task_type'] ?? '') === 'irrigation'
                && str_starts_with($correlationId, 'sch:z'.$zone->id.':irrigation:')
                && isset($payload['due_at'], $payload['expires_at'])
                && str_contains($scheduleKey, 'zone:'.$zone->id.'|type:irrigation');
        });
    }

    public function test_command_recovery_reconciles_persisted_active_task_before_next_dispatch(): void
    {
        $this->enableSchedulerConfig();
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, 2);

        $postCalls = 0;
        $pollCalls = 0;

        Http::fake(function (Request $request) use ($zone, &$postCalls, &$pollCalls) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/scheduler/bootstrap')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'bootstrap_status' => 'ready',
                        'lease_id' => 'lease-recovery',
                    ],
                ], 200);
            }

            if ($request->method() === 'POST' && str_ends_with($request->url(), '/scheduler/task')) {
                $postCalls++;
                $taskId = $postCalls === 1 ? 'st-recovery-old' : 'st-recovery-new';

                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => $taskId,
                        'zone_id' => $zone->id,
                        'task_type' => 'irrigation',
                        'status' => 'accepted',
                    ],
                ], 200);
            }

            if ($request->method() === 'GET' && str_ends_with($request->url(), '/scheduler/task/st-recovery-old')) {
                $pollCalls++;

                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => 'st-recovery-old',
                        'zone_id' => $zone->id,
                        'task_type' => 'irrigation',
                        'status' => 'completed',
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error', 'message' => 'unexpected request'], 500);
        });

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => 'st-recovery-old',
            'status' => 'accepted',
        ]);

        Cache::flush();

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $this->assertSame(2, $postCalls);
        $this->assertSame(1, $pollCalls);

        $oldTask = LaravelSchedulerActiveTask::query()
            ->where('task_id', 'st-recovery-old')
            ->first();
        $this->assertNotNull($oldTask);
        $this->assertSame('completed', $oldTask->status);
        $this->assertNotNull($oldTask->terminal_at);
        $this->assertSame(
            'automation_engine_status_poll',
            (string) (($oldTask->details ?? [])['terminal_source'] ?? '')
        );

        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => 'st-recovery-new',
            'zone_id' => $zone->id,
            'status' => 'accepted',
        ]);
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

    /**
     * @return array{0: Zone, 1: GrowCycle}
     */
    private function createZoneAndCycle(): array
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
        ]);

        $cycle = GrowCycle::factory()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        return [$zone, $cycle];
    }

    private function bindEffectiveTargetsMock(int $cycleId, int $zoneId, int $times): void
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
            ->times($times)
            ->andReturnUsing(static fn (array $cycleIds): array => in_array($cycleId, $cycleIds, true)
                ? [$cycleId => $targetsPayload]
                : []);

        $this->app->instance(EffectiveTargetsService::class, $mock);
    }
}
