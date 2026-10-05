<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\CropDay\SolutionRefreshRecommendation;
use App\Services\EffectiveTargetsService;
use App\Services\ZoneAutomationStateService;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use Mockery;
use Tests\TestCase;

class SolutionRefreshRecommendationTest extends TestCase
{
    /** @var list<int> */
    private array $greenhouseIds = [];

    /** @var list<int> */
    private array $zoneIds = [];

    /** @var list<int> */
    private array $nodeIds = [];

    /** @var list<int> */
    private array $channelIds = [];

    /** @var list<int> */
    private array $calibrationIds = [];

    /** @var list<int> */
    private array $taskIds = [];

    /** @var list<int> */
    private array $commandIds = [];

    /** @var list<int> */
    private array $phaseIds = [];

    /** @var list<int> */
    private array $cycleIds = [];

    /** @var list<int> */
    private array $revisionIds = [];

    /** @var list<int> */
    private array $recipeIds = [];

    private ?int $schedulerLogFloor = null;

    protected function setUp(): void
    {
        parent::setUp();
        Cache::forget('crop_day.solution_refresh.hourly_scan_at');
        Cache::forget('crop_day.solution_refresh.considered_zone_ids');
        Cache::forever(SolutionRefreshRecommendation::METRIC_CACHE_KEY, 0);
        $this->schedulerLogFloor = (int) (DB::table('scheduler_logs')->max('id') ?? 0);
    }

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        $this->deleteFixture();
        parent::tearDown();
    }

    public function test_age_over_threshold_creates_one_event(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $zone = $this->makeZone();
        $this->bindPhase($zone, ['solution_max_age_days' => 7]);
        $this->insertReadyTransition($zone, '2026-09-26 12:00:00');
        $this->bindTargets($zone, []);

        $this->runScheduler([$zone->id]);

        $this->assertSame(1, $this->recommendationCount($zone->id));
        $this->assertSame(1, $this->alertCount($zone->id));
        $this->assertSame(0, $this->solutionChangeIntentCount($zone->id));
        $this->assertSame(1, (int) Cache::get(SolutionRefreshRecommendation::METRIC_CACHE_KEY));
    }

    public function test_repeat_after_an_hour_does_not_create_a_second_event(): void
    {
        $now = Carbon::parse('2026-10-04 12:00:00', 'UTC');
        Carbon::setTestNow($now);
        $zone = $this->makeZone();
        $this->bindPhase($zone, ['solution_max_age_days' => 7]);
        $this->insertReadyTransition($zone, '2026-09-26 12:00:00');
        $this->bindTargets($zone, []);

        $this->runScheduler([$zone->id]);
        Carbon::setTestNow($now->copy()->addHour());
        $this->runScheduler([$zone->id]);

        $this->assertSame(1, $this->recommendationCount($zone->id));
        $this->assertSame(1, $this->alertCount($zone->id));
        $this->assertSame(0, $this->solutionChangeIntentCount($zone->id));
        $this->assertSame(1, (int) Cache::get(SolutionRefreshRecommendation::METRIC_CACHE_KEY));
    }

    public function test_below_threshold_creates_no_event(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $young = $this->makeZone();
        $this->bindPhase($young, ['solution_max_age_days' => 7]);
        $this->insertReadyTransition($young, '2026-10-01 12:00:00');

        $empty = $this->makeZone();
        $this->bindPhase($empty, []);
        $this->insertReadyTransition($empty, '2026-09-01 12:00:00');

        $replaced = $this->makeZone();
        $this->bindPhase($replaced, ['solution_max_age_days' => 7]);
        $this->insertReadyTransition($replaced, '2026-09-01 12:00:00');
        $this->insertCompletedSolutionChange($replaced, '2026-10-03 12:00:00');

        $shortTopup = $this->makeZone();
        $this->bindPhase($shortTopup, ['solution_refresh_after_topup_ml' => 100]);
        $this->insertReadyTransition($shortTopup, '2026-10-02 12:00:00');
        $channel = $this->makeChannel($shortTopup, 'pump_topup', 1.0);
        $this->insertTopup($shortTopup, $channel['node'], $channel['name'], 'DONE', 5000, '2026-10-03 12:00:00');

        $uncalibrated = $this->makeZone();
        $this->bindPhase($uncalibrated, ['solution_refresh_after_topup_ml' => 10]);
        $this->insertReadyTransition($uncalibrated, '2026-10-02 12:00:00');
        $bare = $this->makeChannel($uncalibrated, 'pump_bare', null);
        $this->insertTopup($uncalibrated, $bare['node'], $bare['name'], 'DONE', 60000, '2026-10-03 12:00:00');

        $this->bindTargetsForZones([
            $young->id => [],
            $empty->id => [],
            $replaced->id => [],
            $shortTopup->id => [],
            $uncalibrated->id => [],
        ]);
        $this->runScheduler([
            $young->id,
            $empty->id,
            $replaced->id,
            $shortTopup->id,
            $uncalibrated->id,
        ]);

        foreach ([$young, $empty, $replaced, $shortTopup, $uncalibrated] as $zone) {
            $this->assertSame(0, $this->recommendationCount($zone->id), 'zone '.$zone->id);
            $this->assertSame(0, $this->solutionChangeIntentCount($zone->id), 'zone '.$zone->id);
        }
        $this->assertSame(0, (int) Cache::get(SolutionRefreshRecommendation::METRIC_CACHE_KEY));
    }

    public function test_topup_over_threshold_creates_one_event_without_solution_change_intent(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $zone = $this->makeZone();
        $this->bindPhase($zone, ['solution_refresh_after_topup_ml' => 10]);
        $this->insertReadyTransition($zone, '2026-10-02 12:00:00');
        $channel = $this->makeChannel($zone, 'pump_topup', 2.0);
        $this->insertTopup($zone, $channel['node'], $channel['name'], 'DONE', 10000, '2026-10-03 12:00:00');
        $this->bindTargets($zone, []);

        $this->runScheduler([$zone->id]);

        $this->assertSame(1, $this->recommendationCount($zone->id));
        $this->assertSame(1, $this->alertCount($zone->id));
        $this->assertSame(0, $this->solutionChangeIntentCount($zone->id));
    }

    public function test_irrigation_intent_writes_event_before_automation_engine(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $zone = $this->makeZone();
        DB::table('zone_workflow_state')->updateOrInsert(
            ['zone_id' => $zone->id],
            ['workflow_phase' => 'ready', 'updated_at' => now()],
        );
        $this->bindPhase($zone, ['solution_max_age_days' => 7]);
        $this->insertReadyTransition($zone, '2026-09-26 12:00:00');
        $this->bindTargets($zone, [
            'irrigation' => ['interval_sec' => 3600],
        ]);

        $eventExistedBeforeAe = false;
        Http::fake(function (Request $request) use ($zone, &$eventExistedBeforeAe) {
            if (str_ends_with($request->url(), '/zones/'.$zone->id.'/start-irrigation')) {
                $eventExistedBeforeAe = $this->recommendationCount($zone->id) === 1;

                return Http::response([
                    'status' => 'ok',
                    'data' => ['task_id' => '6106', 'zone_id' => $zone->id, 'accepted' => true],
                ], 200);
            }

            return Http::response(['status' => 'error'], 500);
        });

        $this->runScheduler([$zone->id]);

        $this->assertTrue($eventExistedBeforeAe);
        $this->assertSame(1, $this->recommendationCount($zone->id));
        $this->assertSame(1, $this->alertCount($zone->id));
        $this->assertSame(0, $this->solutionChangeIntentCount($zone->id));
        Http::assertNotSent(fn (Request $request): bool => str_contains($request->url(), '/start-solution-change'));
    }

    public function test_day_balance_read_does_not_increase_events(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $zone = $this->makeZone();
        $this->bindPhase($zone, ['solution_max_age_days' => 7]);
        $this->insertReadyTransition($zone, '2026-09-26 12:00:00');
        $this->bindTargets($zone, []);
        $this->runScheduler([$zone->id]);

        $eventsBefore = $this->zoneEventCount($zone->id);
        $recommendationsBefore = $this->recommendationCount($zone->id);
        $this->assertSame(1, $recommendationsBefore);

        Cache::flush();
        $service = app(ZoneAutomationStateService::class);
        $service->cacheState($zone->id, [
            'zone_id' => $zone->id,
            'state' => 'READY',
            'state_details' => ['failed' => false],
        ]);
        $payload = $service->resolveCachedBootstrap($zone->fresh());

        $this->assertIsArray($payload);
        $this->assertArrayHasKey('day_balance', $payload);
        $this->assertSame($eventsBefore, $this->zoneEventCount($zone->id));
        $this->assertSame($recommendationsBefore, $this->recommendationCount($zone->id));
        $this->assertSame(0, $this->solutionChangeIntentCount($zone->id));
    }

    /**
     * @param  list<int>  $zoneIds
     */
    private function runScheduler(array $zoneIds): void
    {
        app(SchedulerCycleService::class)->runCycle($this->schedulerConfig(), $zoneIds);
    }

    /**
     * @param  array<string, mixed>  $targets
     */
    private function bindTargets(Zone $zone, array $targets): void
    {
        $this->bindTargetsForZones([$zone->id => $targets]);
    }

    /**
     * @param  array<int, array<string, mixed>>  $targetsByZone
     */
    private function bindTargetsForZones(array $targetsByZone): void
    {
        $cycles = DB::table('grow_cycles')
            ->whereIn('zone_id', array_keys($targetsByZone))
            ->pluck('zone_id', 'id');
        $mock = Mockery::mock(EffectiveTargetsService::class);
        $mock->shouldReceive('getEffectiveTargetsBatch')
            ->andReturnUsing(function (array $cycleIds) use ($cycles, $targetsByZone): array {
                $payload = [];
                foreach ($cycleIds as $cycleId) {
                    $zoneId = (int) ($cycles[$cycleId] ?? 0);
                    if ($zoneId <= 0 || ! array_key_exists($zoneId, $targetsByZone)) {
                        continue;
                    }
                    $payload[(int) $cycleId] = [
                        'cycle_id' => (int) $cycleId,
                        'zone_id' => $zoneId,
                        'targets' => $targetsByZone[$zoneId],
                    ];
                }

                return $payload;
            });
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

    /**
     * @param  array<string, mixed>  $extensions
     */
    private function bindPhase(Zone $zone, array $extensions): void
    {
        $suffix = Str::lower(Str::uuid()->toString());
        $recipeId = (int) DB::table('recipes')->insertGetId([
            'name' => 'g6-refresh-'.$suffix,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->recipeIds[] = $recipeId;
        $revisionId = (int) DB::table('recipe_revisions')->insertGetId([
            'recipe_id' => $recipeId,
            'revision_number' => 1,
            'status' => 'DRAFT',
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->revisionIds[] = $revisionId;
        $cycleId = (int) DB::table('grow_cycles')->insertGetId([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revisionId,
            'status' => 'RUNNING',
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->cycleIds[] = $cycleId;
        $phaseId = (int) DB::table('grow_cycle_phases')->insertGetId([
            'grow_cycle_id' => $cycleId,
            'phase_index' => 0,
            'name' => 'G6',
            'extensions' => json_encode($extensions, JSON_THROW_ON_ERROR),
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->phaseIds[] = $phaseId;
        DB::table('grow_cycles')->where('id', $cycleId)->update(['current_phase_id' => $phaseId]);
    }

    private function makeZone(): Zone
    {
        $greenhouse = Greenhouse::factory()->create([
            'timezone' => 'Europe/Moscow',
        ]);
        $this->greenhouseIds[] = (int) $greenhouse->id;
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
            'control_mode' => 'auto',
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->zoneIds[] = (int) $zone->id;

        return $zone->fresh();
    }

    /**
     * @return array{node: DeviceNode, name: string}
     */
    private function makeChannel(Zone $zone, string $channel, ?float $mlPerSec): array
    {
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'irrig',
            'status' => 'online',
        ]);
        $this->nodeIds[] = (int) $node->id;
        $channelId = (int) DB::table('node_channels')->insertGetId([
            'node_id' => $node->id,
            'channel' => $channel,
            'type' => 'ACTUATOR',
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->channelIds[] = $channelId;
        if ($mlPerSec !== null) {
            $this->calibrationIds[] = (int) DB::table('pump_calibrations')->insertGetId([
                'node_channel_id' => $channelId,
                'ml_per_sec' => $mlPerSec,
                'is_active' => true,
                'valid_from' => '2026-01-01 00:00:00',
                'valid_to' => null,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }

        return ['node' => $node, 'name' => $channel];
    }

    private function insertReadyTransition(Zone $zone, string $atUtc): void
    {
        $at = Carbon::parse($atUtc, 'UTC')->format('Y-m-d H:i:s');
        $taskId = $this->insertTask($zone, 'cycle_start', 'completed', $at);
        DB::table('ae_stage_transitions')->insert([
            'task_id' => $taskId,
            'from_stage' => 'prepare_recirculation_check',
            'to_stage' => 'complete_ready',
            'workflow_phase' => 'ready',
            'triggered_at' => $at,
            'created_at' => $at,
        ]);
    }

    private function insertCompletedSolutionChange(Zone $zone, string $atUtc): void
    {
        $at = Carbon::parse($atUtc, 'UTC')->format('Y-m-d H:i:s');
        $this->insertTask($zone, 'solution_change', 'completed', $at);
    }

    private function insertTask(Zone $zone, string $taskType, string $status, string $at): int
    {
        $taskId = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => $taskType,
            'status' => $status,
            'idempotency_key' => 'g6-'.Str::lower(Str::uuid()->toString()),
            'scheduled_for' => $at,
            'due_at' => $at,
            'completed_at' => $status === 'completed' ? $at : null,
            'created_at' => $at,
            'updated_at' => $at,
        ]);
        $this->taskIds[] = $taskId;

        return $taskId;
    }

    private function insertTopup(
        Zone $zone,
        DeviceNode $node,
        string $channel,
        string $status,
        int $durationMs,
        string $createdAtUtc,
    ): void {
        $createdAt = Carbon::parse($createdAtUtc, 'UTC')->format('Y-m-d H:i:s');
        $taskId = $this->insertTask($zone, 'solution_topup', 'completed', $createdAt);
        $commandId = (int) DB::table('commands')->insertGetId([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'channel' => $channel,
            'cmd' => 'run_pump',
            'status' => $status,
            'cmd_id' => 'g6-'.Str::lower(Str::uuid()->toString()),
            'duration_ms' => $durationMs,
            'created_at' => $createdAt,
            'updated_at' => $createdAt,
        ]);
        $this->commandIds[] = $commandId;
        DB::table('ae_commands')->insert([
            'task_id' => $taskId,
            'step_no' => 1,
            'planner_step' => 'solution_topup_start',
            'node_uid' => (string) $node->uid,
            'channel' => $channel,
            'external_id' => (string) $commandId,
            'publish_status' => 'accepted',
            'terminal_status' => 'DONE',
            'created_at' => $createdAt,
            'updated_at' => $createdAt,
        ]);
    }

    private function recommendationCount(int $zoneId): int
    {
        return (int) DB::table('zone_events')
            ->where('zone_id', $zoneId)
            ->where('type', SolutionRefreshRecommendation::EVENT_TYPE)
            ->count();
    }

    private function alertCount(int $zoneId): int
    {
        return (int) DB::table('alerts')
            ->where('zone_id', $zoneId)
            ->where('code', SolutionRefreshRecommendation::ALERT_CODE)
            ->count();
    }

    private function solutionChangeIntentCount(int $zoneId): int
    {
        return (int) DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->where('task_type', 'solution_change')
            ->count();
    }

    private function zoneEventCount(int $zoneId): int
    {
        return (int) DB::table('zone_events')->where('zone_id', $zoneId)->count();
    }

    private function deleteFixture(): void
    {
        if ($this->zoneIds !== []) {
            DB::table('alerts')->whereIn('zone_id', $this->zoneIds)->delete();
            DB::table('zone_events')->whereIn('zone_id', $this->zoneIds)->delete();
            DB::table('zone_automation_intents')->whereIn('zone_id', $this->zoneIds)->delete();
            DB::table('laravel_scheduler_active_tasks')->whereIn('zone_id', $this->zoneIds)->delete();
            DB::table('laravel_scheduler_zone_cursors')->whereIn('zone_id', $this->zoneIds)->delete();
            DB::table('zone_workflow_state')->whereIn('zone_id', $this->zoneIds)->delete();
        }
        if ($this->taskIds !== []) {
            DB::table('ae_commands')->whereIn('task_id', $this->taskIds)->delete();
            DB::table('ae_stage_transitions')->whereIn('task_id', $this->taskIds)->delete();
            DB::table('ae_tasks')->whereIn('id', $this->taskIds)->delete();
        }
        if ($this->commandIds !== []) {
            DB::table('commands')->whereIn('id', $this->commandIds)->delete();
        }
        if ($this->calibrationIds !== []) {
            DB::table('pump_calibrations')->whereIn('id', $this->calibrationIds)->delete();
        }
        if ($this->channelIds !== []) {
            DB::table('node_channels')->whereIn('id', $this->channelIds)->delete();
        }
        if ($this->nodeIds !== []) {
            DB::table('nodes')->whereIn('id', $this->nodeIds)->delete();
        }
        if ($this->cycleIds !== []) {
            DB::table('grow_cycles')->whereIn('id', $this->cycleIds)->update(['current_phase_id' => null]);
        }
        if ($this->phaseIds !== []) {
            DB::table('grow_cycle_phases')->whereIn('id', $this->phaseIds)->delete();
        }
        if ($this->cycleIds !== []) {
            DB::table('grow_cycles')->whereIn('id', $this->cycleIds)->delete();
        }
        if ($this->revisionIds !== []) {
            DB::table('recipe_revisions')->whereIn('id', $this->revisionIds)->delete();
        }
        if ($this->recipeIds !== []) {
            DB::table('recipes')->whereIn('id', $this->recipeIds)->delete();
        }
        if ($this->zoneIds !== []) {
            DB::table('zones')->whereIn('id', $this->zoneIds)->delete();
        }
        if ($this->greenhouseIds !== []) {
            DB::table('greenhouses')->whereIn('id', $this->greenhouseIds)->delete();
        }
        if ($this->schedulerLogFloor !== null) {
            DB::table('scheduler_logs')->where('id', '>', $this->schedulerLogFloor)->delete();
        }
    }
}
