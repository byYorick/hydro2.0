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
}
