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
use Illuminate\Support\Facades\DB;
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
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => 'st-accepted-1',
                        'zone_id' => $zone->id,
                        'accepted' => true,
                        'runner_state' => 'active',
                        'deduplicated' => false,
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
        $this->assertDatabaseCount('zone_automation_intents', 1);
        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'status' => 'pending',
        ]);
        $intentRow = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($intentRow);
        $intentPayloadRaw = $intentRow->payload ?? null;
        $intentPayload = is_string($intentPayloadRaw)
            ? json_decode($intentPayloadRaw, true, 512, JSON_THROW_ON_ERROR)
            : (is_array($intentPayloadRaw) ? $intentPayloadRaw : []);
        $this->assertIsArray($intentPayload);
        $this->assertSame('laravel_scheduler', $intentPayload['source'] ?? null);
        $this->assertSame('diagnostics', $intentPayload['task_type'] ?? null);
        $this->assertSame('cycle_start', $intentPayload['workflow'] ?? null);
        $this->assertArrayNotHasKey('task_payload', $intentPayload);
        $this->assertArrayNotHasKey('schedule_payload', $intentPayload);

        $task = LaravelSchedulerActiveTask::query()
            ->where('task_id', 'st-accepted-1')
            ->first();
        $this->assertNotNull($task);
        $this->assertNotNull($task->due_at);
        $this->assertNotNull($task->expires_at);
        $this->assertArrayHasKey('schedule_key', $task->details ?? []);

        Http::assertSent(function (Request $request) use ($zone): bool {
            if (! ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle'))) {
                return false;
            }

            $payload = $request->data();
            $idempotencyKey = (string) ($payload['idempotency_key'] ?? '');

            return (string) ($payload['source'] ?? '') === 'laravel_scheduler'
                && str_starts_with($idempotencyKey, 'sch:z'.$zone->id.':irrigation:');
        });
    }

    public function test_command_recovery_reconciles_persisted_active_task_before_next_dispatch(): void
    {
        $this->enableSchedulerConfig();
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, 2);

        $postCalls = 0;
        Http::fake(function (Request $request) use ($zone, &$postCalls) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                $postCalls++;
                $taskId = $postCalls === 1 ? 'st-recovery-old' : 'st-recovery-new';

                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'task_id' => $taskId,
                        'zone_id' => $zone->id,
                        'accepted' => true,
                        'runner_state' => 'active',
                        'deduplicated' => false,
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
        $this->assertDatabaseCount('zone_automation_intents', 1);

        Cache::flush();
        $this->travel(130)->seconds();

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $this->assertSame(2, $postCalls);

        $oldTask = LaravelSchedulerActiveTask::query()
            ->where('task_id', 'st-recovery-old')
            ->first();
        $this->assertNotNull($oldTask);
        $this->assertSame('timeout', $oldTask->status);
        $this->assertNotNull($oldTask->terminal_at);
        $this->assertSame('laravel_dispatcher_local_expiry', $oldTask->details['terminal_source'] ?? null);

        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => 'st-recovery-new',
            'zone_id' => $zone->id,
            'status' => 'accepted',
        ]);
        $this->assertDatabaseCount('zone_automation_intents', 2);
    }

    public function test_command_marks_task_terminal_when_intent_completed(): void
    {
        $this->enableSchedulerConfig();
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, 2);

        $postCalls = 0;
        Http::fake(function (Request $request) use ($zone, &$postCalls) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                $postCalls++;

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

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $firstTask = LaravelSchedulerActiveTask::query()->orderBy('id')->first();
        $this->assertNotNull($firstTask);
        $firstTaskId = (string) $firstTask->task_id;
        $this->assertMatchesRegularExpression('/^intent-\d+$/', $firstTaskId);

        $intentId = (int) str_replace('intent-', '', $firstTaskId);
        DB::table('zone_automation_intents')
            ->where('id', $intentId)
            ->update([
                'status' => 'completed',
                'completed_at' => now(),
                'updated_at' => now(),
            ]);

        Cache::flush();
        $this->travel(61)->seconds();

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $this->assertSame(2, $postCalls);
        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => $firstTaskId,
            'status' => 'completed',
        ]);
        $completedTask = LaravelSchedulerActiveTask::query()
            ->where('task_id', $firstTaskId)
            ->first();
        $this->assertNotNull($completedTask);
        $this->assertNotNull($completedTask->terminal_at);
    }

    public function test_command_uses_task_status_from_start_cycle_payload_even_if_accepted_false(): void
    {
        $this->enableSchedulerConfig();
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->bindEffectiveTargetsMock($cycle->id, $zone->id, 1);

        Http::fake(function (Request $request) use ($zone) {
            if ($request->method() === 'POST' && str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => [
                        'zone_id' => $zone->id,
                        'accepted' => false,
                        'runner_state' => 'terminal',
                        'task_status' => 'completed',
                        'deduplicated' => true,
                    ],
                ], 200);
            }

            return Http::response(['status' => 'error', 'message' => 'unexpected request'], 500);
        });

        $this->artisan('automation:dispatch-schedules')
            ->assertExitCode(0);

        $task = LaravelSchedulerActiveTask::query()
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();

        $this->assertNotNull($task);
        $this->assertMatchesRegularExpression('/^intent-\d+$/', (string) $task->task_id);
        $this->assertSame('completed', $task->status);
        $this->assertNotNull($task->terminal_at);
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
