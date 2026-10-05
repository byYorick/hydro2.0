<?php

namespace Tests\Feature\AutomationScheduler;

use App\Enums\GrowCycleStatus;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class DliLightingCheckDispatchTest extends TestCase
{
    use RefreshDatabase;

    public function test_empty_dli_target_does_not_add_mid_window_tick(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-08-17 10:00:00', 'UTC'));
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->seedZoneCursor($zone->id, CarbonImmutable::parse('2026-08-17 09:00:00', 'UTC'));
        $this->bindTargets($cycle->id, $zone->id, null);

        Http::fake(fn () => Http::response(['status' => 'error'], 500));

        $service = $this->app->make(SchedulerCycleService::class);
        $service->runCycle($this->schedulerConfig(), [$zone->id]);

        Http::assertNotSent(fn (Request $request): bool => str_ends_with($request->url(), '/start-lighting-tick'));
        Carbon::setTestNow();
    }

    public function test_dli_target_mid_tick_bucket_key_is_stable_on_repeat(): void
    {
        $now = CarbonImmutable::parse('2026-08-17 10:00:00', 'UTC');
        Carbon::setTestNow($now);
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->seedZoneCursor($zone->id, CarbonImmutable::parse('2026-08-17 09:00:00', 'UTC'));
        $this->bindTargets($cycle->id, $zone->id, 12.0);

        Http::fake(function (Request $request) use ($zone) {
            if (str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return Http::response([
                    'status' => 'ok',
                    'data' => ['task_id' => '6101', 'zone_id' => $zone->id, 'accepted' => true],
                ], 200);
            }

            return Http::response(['status' => 'error'], 500);
        });

        $service = $this->app->make(SchedulerCycleService::class);
        $service->runCycle($this->schedulerConfig(), [$zone->id]);
        $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $keys = [];
        foreach (Http::recorded() as $record) {
            $request = $record[0] ?? null;
            if (! $request instanceof Request) {
                continue;
            }
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                continue;
            }
            $payload = $request->data();
            $keys[] = (string) ($payload['idempotency_key'] ?? '');
            $this->assertSame('on', $payload['desired_state'] ?? null);
        }

        $scheduleKey = (new ScheduleItem(
            zoneId: $zone->id,
            taskType: 'lighting',
            startTime: '08:00:00',
            endTime: '18:00:00',
        ))->scheduleKey;
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $bucket = SchedulerRuntimeHelper::dliCheckBucket($now, 900);
        $expected = $dispatcher->buildSchedulerCorrelationId(
            $zone->id,
            'lighting',
            SchedulerRuntimeHelper::toIso($bucket),
            $scheduleKey,
        );
        $repeated = $dispatcher->buildSchedulerCorrelationId(
            $zone->id,
            'lighting',
            SchedulerRuntimeHelper::toIso(SchedulerRuntimeHelper::dliCheckBucket($now, 900)),
            $scheduleKey,
        );

        $this->assertSame($expected, $repeated);
        $this->assertNotSame([], $keys);
        $this->assertSame($expected, $keys[0]);
        $this->assertSame([$expected], array_values(array_unique($keys)));
        Carbon::setTestNow();
    }

    public function test_off_boundary_zone_busy_still_does_not_move_cursor_when_dli_target_is_set(): void
    {
        $cursorAt = CarbonImmutable::parse('2026-08-17 14:30:00', 'UTC');
        Carbon::setTestNow(CarbonImmutable::parse('2026-08-17 15:00:00', 'UTC'));
        [$zone, $cycle] = $this->createZoneAndCycle();
        $this->seedZoneCursor($zone->id, $cursorAt);
        $this->bindTargets($cycle->id, $zone->id, 12.0);

        Http::fake(function (Request $request) use ($zone) {
            if (str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return Http::response([
                    'detail' => [
                        'error' => 'start_lighting_tick_zone_busy',
                        'zone_id' => $zone->id,
                    ],
                ], 409);
            }

            return Http::response(['status' => 'error'], 500);
        });

        $service = $this->app->make(SchedulerCycleService::class);
        $stats = $service->runCycle($this->schedulerConfig(), [$zone->id]);

        $this->assertSame(1, (int) ($stats['zones_pending_time_retry'] ?? 0));
        Http::assertSent(function (Request $request) use ($zone): bool {
            if (! str_ends_with($request->url(), '/zones/'.$zone->id.'/start-lighting-tick')) {
                return false;
            }

            return ($request->data()['desired_state'] ?? null) === 'off';
        });
        $cursor = DB::table('laravel_scheduler_zone_cursors')->where('zone_id', $zone->id)->first();
        $this->assertNotNull($cursor);
        $this->assertSame(
            $cursorAt->format('Y-m-d H:i:s'),
            CarbonImmutable::parse((string) $cursor->cursor_at)->utc()->format('Y-m-d H:i:s'),
        );
        Carbon::setTestNow();
    }

    /**
     * @return array{0: Zone, 1: GrowCycle}
     */
    private function createZoneAndCycle(): array
    {
        $greenhouse = Greenhouse::factory()->create(['timezone' => 'Europe/Moscow']);
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
            'greenhouse_id' => $greenhouse->id,
        ]);
        $cycle = GrowCycle::factory()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);
        DB::table('zone_workflow_state')->updateOrInsert(
            ['zone_id' => $zone->id],
            ['workflow_phase' => 'ready', 'updated_at' => now()],
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

    private function bindTargets(int $cycleId, int $zoneId, ?float $dliTarget): void
    {
        $lighting = [
            'start_time' => '08:00:00',
            'photoperiod_hours' => 10,
            'brightness' => 80,
            'brightness_night' => 0,
        ];
        if ($dliTarget !== null) {
            $lighting['dli_target'] = $dliTarget;
        }
        $mock = Mockery::mock(EffectiveTargetsService::class);
        $mock->shouldReceive('getEffectiveTargetsBatch')
            ->andReturnUsing(static fn (array $cycleIds): array => in_array($cycleId, $cycleIds, true)
                ? [$cycleId => ['cycle_id' => $cycleId, 'zone_id' => $zoneId, 'targets' => ['lighting' => $lighting]]]
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
