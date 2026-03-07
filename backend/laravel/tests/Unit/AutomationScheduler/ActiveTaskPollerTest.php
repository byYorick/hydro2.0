<?php

namespace Tests\Unit\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ActiveTaskPoller;
use App\Services\AutomationScheduler\ActiveTaskStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ActiveTaskPollerTest extends TestCase
{
    use RefreshDatabase;

    public function test_is_schedule_busy_uses_reconciled_map_without_extra_queries(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);
        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => 'task-map-1',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=60',
            'correlation_id' => 'corr-map-1',
            'status' => 'accepted',
            'accepted_at' => now(),
            'due_at' => now()->addSeconds(30),
            'expires_at' => now()->addMinutes(5),
            'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $cfg = ['active_task_ttl_sec' => 180];
        $scheduleKey = 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=60';
        $reconciledBusyness = [$scheduleKey => true];

        DB::flushQueryLog();
        DB::enableQueryLog();

        $poller = new ActiveTaskPoller(new ActiveTaskStore);
        $isBusy = $poller->isScheduleBusy(
            scheduleKey: $scheduleKey,
            cfg: $cfg,
            reconciledBusyness: $reconciledBusyness,
            writeLog: static function (string $taskName, string $status, array $details): void {},
        );

        $this->assertTrue($isBusy);
        $this->assertCount(0, DB::getQueryLog());
    }

    public function test_reconcile_pending_active_tasks_returns_schedule_busyness_map(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);
        $intentId = DB::table('zone_automation_intents')->insertGetId([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'payload' => json_encode(['source' => 'test'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'idempotency_key' => 'intent-map-'.$zone->id,
            'status' => 'pending',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $scheduleKey = 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=60';
        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => 'intent-'.$intentId,
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => $scheduleKey,
            'correlation_id' => 'corr-intent-'.$intentId,
            'status' => 'accepted',
            'accepted_at' => CarbonImmutable::now('UTC'),
            'due_at' => CarbonImmutable::now('UTC')->addSeconds(30),
            'expires_at' => CarbonImmutable::now('UTC')->addMinutes(5),
            'details' => json_encode(['task_id' => 'intent-'.$intentId], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $poller = new ActiveTaskPoller(new ActiveTaskStore);
        $busyness = $poller->reconcilePendingActiveTasks(
            cfg: [
                'active_task_poll_batch' => 50,
                'active_task_ttl_sec' => 180,
            ],
            writeLog: static function (string $taskName, string $status, array $details): void {},
        );

        $this->assertArrayHasKey($scheduleKey, $busyness);
        $this->assertTrue($busyness[$scheduleKey]);
    }

    public function test_reconcile_pending_active_tasks_reads_ae3_status_from_canonical_internal_api(): void
    {
        $zone = Zone::factory()->create(['status' => 'online', 'automation_runtime' => 'ae3']);
        $scheduleKey = 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=60';
        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => '321',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => $scheduleKey,
            'correlation_id' => 'corr-ae3-321',
            'status' => 'accepted',
            'accepted_at' => now(),
            'due_at' => now()->addSeconds(30),
            'expires_at' => now()->addMinutes(5),
            'details' => json_encode(['task_id' => '321'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        Http::fake([
            'http://automation-engine:9405/internal/tasks/321' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => 321,
                    'zone_id' => $zone->id,
                    'task_type' => 'cycle_start',
                    'status' => 'completed',
                ],
            ], 200),
        ]);

        $poller = new ActiveTaskPoller(new ActiveTaskStore);
        $busyness = $poller->reconcilePendingActiveTasks(
            cfg: [
                'api_url' => 'http://automation-engine:9405',
                'timeout_sec' => 2.0,
                'scheduler_id' => 'laravel-scheduler',
                'token' => 'test-token',
                'active_task_poll_batch' => 50,
                'active_task_ttl_sec' => 180,
            ],
            writeLog: static function (string $taskName, string $status, array $details): void {},
        );

        $this->assertArrayHasKey($scheduleKey, $busyness);
        $this->assertFalse($busyness[$scheduleKey]);
        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => '321',
            'status' => 'completed',
        ]);
        Http::assertSentCount(1);
    }

    public function test_reconcile_pending_active_tasks_keeps_ae3_task_busy_while_waiting_command(): void
    {
        $zone = Zone::factory()->create(['status' => 'online', 'automation_runtime' => 'ae3']);
        $scheduleKey = 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=60';
        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => '654',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => $scheduleKey,
            'correlation_id' => 'corr-ae3-654',
            'status' => 'accepted',
            'accepted_at' => now(),
            'due_at' => now()->addSeconds(30),
            'expires_at' => now()->addMinutes(5),
            'details' => json_encode(['task_id' => '654'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        Http::fake([
            'http://automation-engine:9405/internal/tasks/654' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => 654,
                    'zone_id' => $zone->id,
                    'task_type' => 'cycle_start',
                    'status' => 'waiting_command',
                ],
            ], 200),
        ]);

        $poller = new ActiveTaskPoller(new ActiveTaskStore);
        $busyness = $poller->reconcilePendingActiveTasks(
            cfg: [
                'api_url' => 'http://automation-engine:9405',
                'timeout_sec' => 2.0,
                'scheduler_id' => 'laravel-scheduler',
                'token' => 'test-token',
                'active_task_poll_batch' => 50,
                'active_task_ttl_sec' => 180,
            ],
            writeLog: static function (string $taskName, string $status, array $details): void {},
        );

        $this->assertArrayHasKey($scheduleKey, $busyness);
        $this->assertTrue($busyness[$scheduleKey]);
        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => '654',
            'status' => 'accepted',
        ]);
    }
}
