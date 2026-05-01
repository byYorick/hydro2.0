<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleCycleContext;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ScheduleDispatcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_upsert_scheduler_intent_does_not_mutate_terminal_intent(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-03-12 12:00:00', 'UTC');
        $correlationId = 'sch:z'.$zone->id.':irrigation:test-guard';

        $created = $dispatcher->upsertSchedulerIntent(
            zoneId: $zone->id,
            taskType: 'irrigation',
            correlationId: $correlationId,
            triggerTime: $triggerTime,
        );

        $this->assertTrue($created['ok']);
        $this->assertNotNull($created['intent_id']);

        DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->update([
                'status' => 'completed',
                'payload' => json_encode([
                    'source' => 'laravel_scheduler',
                    'workflow' => 'cycle_start',
                    'marker' => 'terminal',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'not_before' => $triggerTime,
                'completed_at' => $triggerTime,
                'updated_at' => $triggerTime,
            ]);

        $before = DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->first();

        $this->assertNotNull($before);

        $result = $dispatcher->upsertSchedulerIntent(
            zoneId: $zone->id,
            taskType: 'irrigation',
            correlationId: $correlationId,
            triggerTime: $triggerTime->addMinutes(5),
        );

        $after = DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->first();

        $this->assertTrue($result['ok']);
        $this->assertNotNull($after);
        $this->assertSame('completed', $after->status);
        $this->assertSame($before->updated_at, $after->updated_at);
        $this->assertSame($before->not_before, $after->not_before);
        $this->assertSame(
            json_decode((string) $before->payload, true, 512, JSON_THROW_ON_ERROR),
            json_decode((string) $after->payload, true, 512, JSON_THROW_ON_ERROR),
        );
    }

    public function test_dispatch_skips_non_irrigation_task_for_ae3_runtime(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake();

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-03-14 07:30:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'ventilation',
            intervalSec: 60,
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
        $logs = [];

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: function (string $taskName, string $status, array $context) use (&$logs): void {
                $logs[] = compact('taskName', 'status', 'context');
            },
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => false,
            'reason' => 'ae3_task_type_not_supported',
        ], $result);
        $this->assertDatabaseCount('zone_automation_intents', 0);
        Http::assertNothingSent();
        $this->assertCount(1, $logs);
        $this->assertSame('skipped', $logs[0]['status']);
        $this->assertSame('ae3_task_type_not_supported', $logs[0]['context']['reason']);
    }

    public function test_dispatch_posts_start_lighting_tick_for_ae3_lighting_task(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-lighting-tick' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '5001',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-04-04 08:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'lighting',
            intervalSec: 3600,
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
        $logs = [];

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: function (string $taskName, string $status, array $context) use (&$logs): void {
                $logs[] = compact('taskName', 'status', 'context');
            },
        );

        $this->assertSame([
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ], $result);

        Http::assertSent(function (\Illuminate\Http\Client\Request $request) use ($zone): bool {
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return false;
            }
            $payload = $request->data();

            return ($payload['source'] ?? null) === 'laravel_scheduler'
                && str_starts_with((string) ($payload['idempotency_key'] ?? ''), 'sch:z'.$zone->id.':lighting:');
        });

        $row = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($row);
        $this->assertSame('lighting_tick', $row->task_type);
        $this->assertSame('lighting_tick', $row->topology);
        $this->assertSame('LIGHTING_TICK', $row->intent_type);
        $this->assertSame('laravel_scheduler', $row->intent_source);
    }

    public function test_dispatch_posts_start_cycle_for_ae3_diagnostics_task(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-cycle' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '5002',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-04-05 08:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'diagnostics',
            intervalSec: 1800,
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
        $logs = [];

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: function (string $taskName, string $status, array $context) use (&$logs): void {
                $logs[] = compact('taskName', 'status', 'context');
            },
        );

        $this->assertSame([
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ], $result);

        Http::assertSent(function (\Illuminate\Http\Client\Request $request) use ($zone): bool {
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-cycle')) {
                return false;
            }
            $payload = $request->data();

            return ($payload['source'] ?? null) === 'laravel_scheduler'
                && str_starts_with((string) ($payload['idempotency_key'] ?? ''), 'sch:z'.$zone->id.':diagnostics:');
        });

        $row = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($row);
        $this->assertSame('cycle_start', $row->task_type);
        $this->assertSame('DIAGNOSTICS_TICK', $row->intent_type);
        $this->assertSame('laravel_scheduler', $row->intent_source);
        $this->assertNull($row->payload);
    }

    public function test_dispatch_batch_processes_multiple_jobs_in_parallel_pool_path(): void
    {
        $zoneA = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);
        $zoneB = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zoneA->id.'/start-cycle' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '6101',
                    'zone_id' => $zoneA->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
            'http://automation-engine:9405/zones/'.$zoneB->id.'/start-cycle' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '6102',
                    'zone_id' => $zoneB->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-04-05 10:00:00', 'UTC');
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

        $scheduleA = new ScheduleItem(zoneId: $zoneA->id, taskType: 'diagnostics', intervalSec: 1800);
        $scheduleB = new ScheduleItem(zoneId: $zoneB->id, taskType: 'diagnostics', intervalSec: 1800);
        $logs = [];

        $results = $dispatcher->dispatchBatch(
            jobs: [
                [
                    'zoneId' => $zoneA->id,
                    'schedule' => $scheduleA,
                    'triggerTime' => $triggerTime,
                    'scheduleKey' => $scheduleA->scheduleKey,
                ],
                [
                    'zoneId' => $zoneB->id,
                    'schedule' => $scheduleB,
                    'triggerTime' => $triggerTime,
                    'scheduleKey' => $scheduleB->scheduleKey,
                ],
            ],
            context: $context,
            writeLog: function (string $taskName, string $status, array $context) use (&$logs): void {
                $logs[] = compact('taskName', 'status', 'context');
            },
        );

        $this->assertCount(2, $results);
        $this->assertSame('accepted', $results[0]['reason']);
        $this->assertSame('accepted', $results[1]['reason']);
        $this->assertTrue($results[0]['dispatched']);
        $this->assertTrue($results[1]['dispatched']);
        Http::assertSentCount(2);
        $this->assertNotEmpty($logs);
    }

    public function test_dispatch_preserves_zone_busy_reason_for_backpressure_metrics(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-cycle' => Http::response([
                'detail' => [
                    'error' => 'start_cycle_zone_busy',
                    'zone_id' => $zone->id,
                    'active_task_id' => 42,
                    'active_task_status' => 'pending',
                ],
            ], 409),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-04-13 18:28:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'diagnostics',
            intervalSec: 240,
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
        $logs = [];

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: function (string $taskName, string $status, array $context) use (&$logs): void {
                $logs[] = compact('taskName', 'status', 'context');
            },
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'start_cycle_zone_busy',
        ], $result);
        $this->assertNotEmpty($logs);
        $this->assertSame('failed', $logs[0]['status']);
        $this->assertSame('start_cycle_zone_busy', $logs[0]['context']['error']);
        $this->assertSame(409, $logs[0]['context']['status_code']);
    }

    public function test_dispatch_skips_irrigation_for_ae3_when_zone_setup_is_pending(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake();

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-04-13 18:28:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'irrigation',
            intervalSec: 240,
            payload: ['duration_sec' => 120],
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
            zoneWorkflowPhases: [
                $zone->id => 'idle',
            ],
        );
        $logs = [];

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: function (string $taskName, string $status, array $context) use (&$logs): void {
                $logs[] = compact('taskName', 'status', 'context');
            },
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'zone_setup_pending',
        ], $result);
        $this->assertDatabaseCount('zone_automation_intents', 0);
        Http::assertNothingSent();
        $this->assertCount(1, $logs);
        $this->assertSame('skipped', $logs[0]['status']);
        $this->assertSame('zone_setup_pending', $logs[0]['context']['reason']);
        $this->assertSame('idle', $logs[0]['context']['workflow_phase']);
    }
}
