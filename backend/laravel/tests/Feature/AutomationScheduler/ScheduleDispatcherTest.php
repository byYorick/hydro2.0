<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleCycleContext;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
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

        $this->assertFalse($result['ok']);
        $this->assertNull($result['intent_id']);
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
                && str_starts_with((string) ($payload['idempotency_key'] ?? ''), 'sch:z'.$zone->id.':lighting:')
                && ($payload['desired_state'] ?? null) === 'on';
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

        $intent = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($intent);
        $this->assertSame('pending', $intent->status);
        $this->assertSame(0, (int) $intent->retry_count);
    }

    public function test_dispatch_http_error_marks_scheduler_intent_failed_after_max_retries(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-cycle' => Http::response([
                'detail' => 'upstream unavailable',
            ], 500),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-06-29 10:00:00', 'UTC');
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
        $writeLog = function (string $taskName, string $status, array $context) use (&$logs): void {
            $logs[] = compact('taskName', 'status', 'context');
        };

        for ($attempt = 0; $attempt < 3; $attempt++) {
            $result = $dispatcher->dispatch(
                zoneId: $zone->id,
                schedule: $schedule,
                triggerTime: $triggerTime,
                scheduleKey: $schedule->scheduleKey,
                context: $context,
                writeLog: $writeLog,
            );
            $this->assertSame([
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'http_error',
            ], $result);
        }

        $intent = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();

        $this->assertNotNull($intent);
        $this->assertSame('failed', $intent->status);
        $this->assertSame('scheduler_dispatch_http_error', $intent->error_code);
        $this->assertSame(3, (int) $intent->retry_count);
        $this->assertCount(3, $logs);
    }

    public function test_dispatch_connection_error_increments_scheduler_intent_retry_count(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-cycle' => function () {
                throw new \Illuminate\Http\Client\ConnectionException('Connection refused');
            },
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-06-29 11:00:00', 'UTC');
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

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: static function (): void {},
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'connection_error',
        ], $result);

        $intent = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();

        $this->assertNotNull($intent);
        $this->assertSame('pending', $intent->status);
        $this->assertSame(1, (int) $intent->retry_count);
    }

    public function test_dispatch_skips_dispatch_for_manual_control_mode(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
            'control_mode' => 'manual',
        ]);

        Http::fake();

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-06-19 08:00:00', 'UTC');
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
                $zone->id => 'ready',
            ],
            zoneControlModes: [
                $zone->id => 'manual',
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
            'retryable' => false,
            'reason' => 'control_mode_manual',
        ], $result);
        $this->assertDatabaseCount('zone_automation_intents', 0);
        Http::assertNothingSent();
        $this->assertCount(1, $logs);
        $this->assertSame('skipped', $logs[0]['status']);
        $this->assertSame('control_mode_manual', $logs[0]['context']['reason']);
    }

    public function test_dispatch_allows_semi_control_mode(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
            'control_mode' => 'semi',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-cycle' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '7001',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-06-19 08:30:00', 'UTC');
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
            zoneWorkflowPhases: [
                $zone->id => 'ready',
            ],
            zoneControlModes: [
                $zone->id => 'semi',
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
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ], $result);
        Http::assertSentCount(1);
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

    public function test_dispatch_posts_start_solution_change_and_persists_solution_change_task_type(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-solution-change' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '8801',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 09:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'solution_change',
            intervalSec: 10800,
            payload: ['trigger' => 'scheduler'],
        );
        $context = $this->makeDispatchContext($triggerTime, [
            $zone->id => 'ready',
        ]);
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
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-solution-change')) {
                return false;
            }
            $payload = $request->data();

            return ($payload['source'] ?? null) === 'laravel_scheduler'
                && ($payload['trigger'] ?? null) === 'scheduler'
                && str_starts_with((string) ($payload['idempotency_key'] ?? ''), 'sch:z'.$zone->id.':solution_change:');
        });

        $row = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($row);
        $this->assertSame('solution_change', $row->task_type);
        $this->assertSame('SOLUTION_CHANGE_TICK', $row->intent_type);
        $this->assertSame('laravel_scheduler', $row->intent_source);
        $payload = is_string($row->payload)
            ? json_decode($row->payload, true, 512, JSON_THROW_ON_ERROR)
            : (array) $row->payload;
        $this->assertSame('scheduler', $payload['trigger'] ?? null);
    }

    public function test_upsert_scheduler_intent_maps_solution_change_task_type(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 09:15:00', 'UTC');

        $created = $dispatcher->upsertSchedulerIntent(
            zoneId: $zone->id,
            taskType: 'solution_change',
            correlationId: 'sch:z'.$zone->id.':solution_change:upsert-guard',
            triggerTime: $triggerTime,
            payload: ['trigger' => 'periodic_tick'],
        );

        $this->assertTrue($created['ok']);
        $this->assertNotNull($created['intent_id']);

        $row = DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->first();
        $this->assertNotNull($row);
        $this->assertSame('solution_change', $row->task_type);
        $this->assertSame('SOLUTION_CHANGE_TICK', $row->intent_type);
        $payload = is_string($row->payload)
            ? json_decode($row->payload, true, 512, JSON_THROW_ON_ERROR)
            : (array) $row->payload;
        $this->assertSame('periodic_tick', $payload['trigger'] ?? null);
    }

    public function test_dispatch_skips_solution_topup_for_ae3_when_zone_setup_is_pending(): void
    {
        $this->assertSetupPendingSkip('solution_topup');
    }

    public function test_dispatch_skips_solution_change_for_ae3_when_zone_setup_is_pending(): void
    {
        $this->assertSetupPendingSkip('solution_change');
    }

    public function test_dispatch_treats_start_irrigation_setup_pending_as_retryable_backpressure(): void
    {
        $this->assertSetupNotReadyHttpBackpressure(
            taskType: 'irrigation',
            endpoint: '/start-irrigation',
            error: 'start_irrigation_setup_pending',
            extraPayload: ['duration_sec' => 120],
        );
    }

    public function test_dispatch_treats_start_solution_topup_not_ready_as_retryable_backpressure(): void
    {
        $this->assertSetupNotReadyHttpBackpressure(
            taskType: 'solution_topup',
            endpoint: '/start-solution-topup',
            error: 'start_solution_topup_not_ready',
        );
    }

    public function test_dispatch_preserves_solution_change_zone_busy_reason(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-solution-change' => Http::response([
                'detail' => [
                    'error' => 'start_solution_change_zone_busy',
                    'zone_id' => $zone->id,
                    'active_task_id' => 77,
                    'active_task_status' => 'pending',
                ],
            ], 409),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 10:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'solution_change',
            intervalSec: 10800,
        );
        $context = $this->makeDispatchContext($triggerTime, [
            $zone->id => 'ready',
        ]);
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
            'reason' => 'start_solution_change_zone_busy',
        ], $result);

        $intent = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($intent);
        $this->assertSame('pending', $intent->status);
        $this->assertSame(0, (int) $intent->retry_count);
        $this->assertSame('solution_change', $intent->task_type);
    }

    public function test_dispatch_skips_invalid_lighting_desired_state_fail_closed(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake();

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 22:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'lighting',
            startTime: '06:00:00',
            endTime: '22:00:00',
            payload: [
                'desired_state' => 'maybe',
                'brightness' => 80,
            ],
        );
        $context = $this->makeDispatchContext($triggerTime);
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
            'reason' => 'invalid_lighting_desired_state',
        ], $result);
        $this->assertDatabaseCount('zone_automation_intents', 0);
        Http::assertNothingSent();
        $this->assertCount(1, $logs);
        $this->assertSame('skipped', $logs[0]['status']);
        $this->assertSame('invalid_lighting_desired_state', $logs[0]['context']['reason']);
    }

    public function test_dispatch_skips_http_when_idempotency_key_already_terminal(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 12:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'irrigation',
            intervalSec: 1800,
            payload: ['duration_sec' => 60],
        );
        $correlationId = $dispatcher->buildSchedulerCorrelationId(
            zoneId: $zone->id,
            taskType: 'irrigation',
            scheduledFor: SchedulerRuntimeHelper::toIso(
                SchedulerRuntimeHelper::intervalSlotAt(
                    now: $triggerTime,
                    intervalSec: 1800,
                    lastCompletedAt: null,
                )
            ),
            scheduleKey: $schedule->scheduleKey,
        );

        $created = $dispatcher->upsertSchedulerIntent(
            zoneId: $zone->id,
            taskType: 'irrigation',
            correlationId: $correlationId,
            triggerTime: $triggerTime,
            payload: ['duration_sec' => 60],
        );
        $this->assertTrue($created['ok']);
        DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->update([
                'status' => 'completed',
                'completed_at' => $triggerTime,
                'updated_at' => $triggerTime,
            ]);

        Http::fake();
        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $this->makeDispatchContext($triggerTime, [
                $zone->id => 'ready',
            ]),
            writeLog: static function (): void {},
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'intent_upsert_failed',
        ], $result);
        Http::assertNothingSent();
        $this->assertSame(1, DB::table('zone_automation_intents')->where('zone_id', $zone->id)->count());
        $this->assertSame(
            'completed',
            DB::table('zone_automation_intents')->where('id', $created['intent_id'])->value('status'),
        );
    }

    public function test_dispatch_treats_rate_limited_as_retryable_backpressure(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-lighting-tick' => Http::response([
                'detail' => [
                    'error' => 'start_lighting_tick_rate_limited',
                    'zone_id' => $zone->id,
                ],
            ], 429),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 15:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'lighting',
            startTime: '08:00:00',
            endTime: '18:00:00',
            payload: [
                'desired_state' => 'off',
                'catchup_original_trigger_time' => '2026-08-17T15:00:00Z',
            ],
        );

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $this->makeDispatchContext($triggerTime),
            writeLog: static function (): void {},
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'start_lighting_tick_rate_limited',
        ], $result);

        $intent = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($intent);
        $this->assertSame('pending', $intent->status);
        $this->assertSame(0, (int) $intent->retry_count);
    }

    public function test_dispatch_treats_solution_change_zone_not_ready_as_retryable_backpressure(): void
    {
        $this->assertSetupNotReadyHttpBackpressure(
            taskType: 'solution_change',
            endpoint: '/start-solution-change',
            error: 'solution_change_zone_not_ready',
        );
    }

    public function test_interval_irrigation_retries_share_idempotency_key_on_zone_busy(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-irrigation' => Http::response([
                'detail' => [
                    'error' => 'start_irrigation_zone_busy',
                    'zone_id' => $zone->id,
                    'active_task_id' => 44,
                    'active_task_status' => 'pending',
                ],
            ], 409),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'irrigation',
            intervalSec: 1800,
            payload: ['duration_sec' => 90],
        );
        $firstNow = CarbonImmutable::parse('2026-08-17 12:00:10', 'UTC');
        $secondNow = CarbonImmutable::parse('2026-08-17 12:00:40', 'UTC');

        $first = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $firstNow,
            scheduleKey: $schedule->scheduleKey,
            context: $this->makeDispatchContext($firstNow, [
                $zone->id => 'ready',
            ]),
            writeLog: static function (): void {},
        );
        $second = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $secondNow,
            scheduleKey: $schedule->scheduleKey,
            context: $this->makeDispatchContext($secondNow, [
                $zone->id => 'ready',
            ]),
            writeLog: static function (): void {},
        );

        $this->assertSame('start_irrigation_zone_busy', $first['reason']);
        $this->assertSame('start_irrigation_zone_busy', $second['reason']);
        $this->assertTrue($first['retryable']);
        $this->assertTrue($second['retryable']);

        $recorded = Http::recorded(function (\Illuminate\Http\Client\Request $request) use ($zone): bool {
            return str_ends_with($request->url(), '/zones/'.$zone->id.'/start-irrigation');
        });
        $this->assertCount(2, $recorded);
        $keys = $recorded
            ->map(static fn (array $pair): string => (string) ($pair[0]->data()['idempotency_key'] ?? ''))
            ->all();
        $this->assertSame($keys[0], $keys[1]);
        $this->assertNotSame('', $keys[0]);
        $this->assertSame(1, DB::table('zone_automation_intents')->where('zone_id', $zone->id)->count());
    }

    /**
     * @param  array<int, string>  $workflowPhases
     */
    private function makeDispatchContext(CarbonImmutable $triggerTime, array $workflowPhases = []): ScheduleCycleContext
    {
        return new ScheduleCycleContext(
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
            zoneWorkflowPhases: $workflowPhases,
        );
    }

    private function assertSetupPendingSkip(string $taskType): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake();

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 11:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: $taskType,
            intervalSec: 1800,
        );
        $context = $this->makeDispatchContext($triggerTime, [
            $zone->id => 'idle',
        ]);
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
        $this->assertSame($taskType, $logs[0]['context']['task_type']);
    }

    /**
     * @param  array<string, mixed>  $extraPayload
     */
    private function assertSetupNotReadyHttpBackpressure(
        string $taskType,
        string $endpoint,
        string $error,
        array $extraPayload = [],
    ): void {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.$endpoint => Http::response([
                'detail' => [
                    'error' => $error,
                    'zone_id' => $zone->id,
                ],
            ], 409),
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-08-17 12:00:00', 'UTC');
        $schedule = new ScheduleItem(
            zoneId: $zone->id,
            taskType: $taskType,
            intervalSec: 240,
            payload: $extraPayload,
        );
        $context = $this->makeDispatchContext($triggerTime, [
            $zone->id => 'ready',
        ]);

        $result = $dispatcher->dispatch(
            zoneId: $zone->id,
            schedule: $schedule,
            triggerTime: $triggerTime,
            scheduleKey: $schedule->scheduleKey,
            context: $context,
            writeLog: static function (): void {},
        );

        $this->assertSame([
            'dispatched' => false,
            'retryable' => true,
            'reason' => $error,
        ], $result);

        $intent = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($intent);
        $this->assertSame('pending', $intent->status);
        $this->assertSame(0, (int) $intent->retry_count);
    }
}
