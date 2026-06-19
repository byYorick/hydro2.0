<?php

namespace Tests\Feature\AutomationScheduler;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\LaravelSchedulerActiveTask;
use App\Models\Zone;
use App\Models\ZoneManualSchedule;
use App\Services\AutomationScheduler\ManualScheduleItemBuilder;
use App\Services\AutomationScheduler\ManualScheduleService;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\ScheduleSpecHelper;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ManualScheduleOrchestratorTest extends TestCase
{
    use RefreshDatabase;

    public function test_manual_once_dispatch_marks_schedule_dispatched(): void
    {
        [$zone] = $this->createZoneAndCycle();
        $this->bindEmptyEffectiveTargetsMock();

        $runAt = SchedulerRuntimeHelper::nowUtc()->subSeconds(45);
        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_kind' => 'once',
            'run_at' => $runAt,
            'payload' => ['duration_sec' => 60],
            'enabled' => true,
        ]);

        $items = $this->app->make(ManualScheduleItemBuilder::class)->buildForZone($zone->id);
        $this->assertCount(1, $items);
        $this->assertSame($schedule->id, $items[0]->manualScheduleId);

        $this->seedZoneCursor($zone->id, $runAt->subMinute());

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-irrigation' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '9001',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertSame(1, (int) ($stats['schedules_total'] ?? 0), json_encode($stats, JSON_THROW_ON_ERROR));
        $this->assertGreaterThanOrEqual(1, (int) ($stats['attempted_dispatches'] ?? 0), json_encode($stats, JSON_THROW_ON_ERROR));
        $this->assertGreaterThanOrEqual(1, (int) ($stats['successful_dispatches'] ?? 0), json_encode($stats, JSON_THROW_ON_ERROR));

        $schedule->refresh();
        $this->assertNotNull($schedule->last_dispatched_at);
        $this->assertFalse($schedule->enabled);
    }

    public function test_manual_once_reschedule_dispatches_despite_old_terminal_task(): void
    {
        [$zone] = $this->createZoneAndCycle();
        $this->bindEmptyEffectiveTargetsMock();

        $oldRunAt = SchedulerRuntimeHelper::nowUtc()->subHours(2);
        $newRunAt = SchedulerRuntimeHelper::nowUtc()->subSeconds(20);

        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_kind' => 'once',
            'run_at' => $newRunAt,
            'payload' => ['duration_sec' => 60],
            'enabled' => true,
        ]);

        $scheduleKey = ScheduleItem::makeManualScheduleKey(
            manualScheduleId: (int) $schedule->id,
            zoneId: $zone->id,
            taskType: 'irrigation',
        );

        LaravelSchedulerActiveTask::query()->create([
            'task_id' => '8999',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => $scheduleKey,
            'correlation_id' => 'corr-old-manual',
            'status' => 'completed',
            'accepted_at' => $oldRunAt,
            'terminal_at' => $oldRunAt->addMinute(),
            'details' => ['scheduled_for' => SchedulerRuntimeHelper::toIso($oldRunAt)],
        ]);

        $this->seedZoneCursor($zone->id, $newRunAt->subMinute());

        Http::fake([
            'http://automation-engine:9405/zones/'.$zone->id.'/start-irrigation' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '9002',
                    'zone_id' => $zone->id,
                    'accepted' => true,
                    'runner_state' => 'active',
                    'deduplicated' => false,
                ],
            ], 200),
        ]);

        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertGreaterThanOrEqual(1, (int) ($stats['attempted_dispatches'] ?? 0), json_encode($stats, JSON_THROW_ON_ERROR));
        $this->assertGreaterThanOrEqual(1, (int) ($stats['successful_dispatches'] ?? 0), json_encode($stats, JSON_THROW_ON_ERROR));
        Http::assertSent(fn (Request $request): bool => str_ends_with($request->url(), '/zones/'.$zone->id.'/start-irrigation'));

        $schedule->refresh();
        $this->assertNotNull($schedule->last_dispatched_at);
        $this->assertFalse($schedule->enabled);
    }

    public function test_ae3_ventilation_manual_once_is_not_dispatched_or_consumed(): void
    {
        [$zone] = $this->createZoneAndCycle();
        $this->bindEmptyEffectiveTargetsMock();

        $runAt = SchedulerRuntimeHelper::nowUtc()->subSeconds(30);
        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'ventilation',
            'schedule_kind' => 'once',
            'run_at' => $runAt,
            'payload' => [],
            'enabled' => true,
        ]);

        $this->seedZoneCursor($zone->id, $runAt->subMinute());

        Http::fake();

        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertSame(0, (int) ($stats['successful_dispatches'] ?? 0));
        Http::assertNothingSent();

        $schedule->refresh();
        $this->assertNull($schedule->last_dispatched_at);
        $this->assertTrue($schedule->enabled);
    }

    public function test_rescheduled_once_after_dispatch_can_run_again(): void
    {
        [$zone] = $this->createZoneAndCycle();
        $this->bindEmptyEffectiveTargetsMock();

        $schedule = ZoneManualSchedule::query()->create([
            'zone_id' => $zone->id,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => SchedulerRuntimeHelper::nowUtc()->subHour(),
            'payload' => [],
            'enabled' => false,
        ]);
        $schedule->forceFill(['last_dispatched_at' => SchedulerRuntimeHelper::nowUtc()->subHour()])->save();

        $newRunAt = SchedulerRuntimeHelper::nowUtc()->addHours(2);
        app(ManualScheduleService::class)->update($schedule, [
            'run_at' => $newRunAt->toIso8601String(),
            'enabled' => true,
        ]);

        $schedule->refresh();
        $this->assertNull($schedule->last_dispatched_at);
        $this->assertTrue($schedule->enabled);
        $this->assertTrue(
            ScheduleSpecHelper::parseRunAt($schedule->run_at?->toIso8601String() ?? '')?->equalTo($newRunAt) ?? false,
        );
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

    private function bindEmptyEffectiveTargetsMock(): void
    {
        $mock = Mockery::mock(EffectiveTargetsService::class);
        $mock->shouldReceive('getEffectiveTargetsBatch')
            ->andReturn([]);
        $this->app->instance(EffectiveTargetsService::class, $mock);
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
            'dispatch_parallelism' => 8,
        ];
    }
}
