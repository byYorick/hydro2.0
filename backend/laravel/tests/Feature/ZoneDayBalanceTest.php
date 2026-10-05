<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Services\CropDay\DliIntegral;
use App\Services\ZoneAutomationStateService;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Tests\TestCase;

class ZoneDayBalanceTest extends TestCase
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
    private array $sensorIds = [];

    /** @var list<int> */
    private array $sampleIds = [];

    /** @var list<int> */
    private array $phaseIds = [];

    /** @var list<int> */
    private array $cycleIds = [];

    /** @var list<int> */
    private array $revisionIds = [];

    /** @var list<int> */
    private array $recipeIds = [];

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        $this->deleteFixture();
        parent::tearDown();
    }

    public function test_sums_done_irrigation_start_and_cuts_local_midnight(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));

        $zone = $this->makeZone('Europe/Moscow');
        $otherZone = $this->makeZone('Europe/Moscow', $zone->greenhouse);
        $channel = $this->makeChannel($zone, 'pump_main', 2.0);
        $otherChannel = $this->makeChannel($otherZone, 'pump_main', 2.0);

        $this->insertCommand($zone, $channel['node'], $channel['name'], 'DONE', 'irrigation_start', 'irrigation_start', 10000, '2026-10-03 21:00:00');
        $this->insertCommand($zone, $channel['node'], $channel['name'], 'DONE', 'irrigation_start', 'irrigation_start.pump', 20000, '2026-10-04 11:00:00');
        $this->insertCommand($zone, $channel['node'], $channel['name'], 'DONE', 'irrigation_start', 'irrigation_start', null, '2026-10-04 11:30:00');
        $this->insertCommand($zone, $channel['node'], $channel['name'], 'DONE', 'irrigation_start', 'clean_fill_start', 50000, '2026-10-04 10:00:00');
        $this->insertCommand($zone, $channel['node'], $channel['name'], 'DONE', 'irrigation_start', 'solution_fill_start', 50000, '2026-10-04 10:05:00');
        $this->insertCommand($zone, $channel['node'], $channel['name'], 'ERROR', 'irrigation_start', 'irrigation_start', 50000, '2026-10-04 10:10:00');
        $this->insertCommand($zone, $channel['node'], $channel['name'], 'DONE', 'irrigation_start', 'irrigation_start', 100000, '2026-10-03 20:59:59');
        $this->insertCommand($otherZone, $otherChannel['node'], $otherChannel['name'], 'DONE', 'irrigation_start', 'irrigation_start', 100000, '2026-10-04 11:00:00');

        $eventsBefore = $this->zoneEventCount($zone->id);
        $commandsBefore = count($this->commandIds);
        $balance = $this->readBalance($zone);

        $this->assertSame($eventsBefore, $this->zoneEventCount($zone->id));
        $this->assertSame($commandsBefore, (int) DB::table('commands')->whereIn('id', $this->commandIds)->count());
        $this->assertSame('2026-10-04', $balance['local_date']);
        $this->assertFalse($balance['timezone_fallback']);
        $this->assertSame('2026-10-03T21:00:00+00:00', Carbon::parse($balance['window_start'])->utc()->toIso8601String());
        $this->assertSame('2026-10-04T12:00:00+00:00', Carbon::parse($balance['window_end'])->utc()->toIso8601String());
        $this->assertSame(3, $balance['irrigation_commands']);
        $this->assertEqualsWithDelta(30.0, $balance['commanded_sec'], 0.001);
        $this->assertEqualsWithDelta(60.0, $balance['commanded_ml'], 0.001);
        $this->assertSame('ok', $balance['commanded_ml_status']);
    }

    public function test_commanded_ml_null_when_any_channel_has_no_calibration(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));

        $zone = $this->makeZone('Europe/Moscow');
        $calibrated = $this->makeChannel($zone, 'pump_calibrated', 5.0);
        $bare = $this->makeChannel($zone, 'pump_bare', null);

        $this->insertCommand($zone, $calibrated['node'], $calibrated['name'], 'DONE', 'irrigation_start', 'irrigation_start', 10000, '2026-10-04 08:00:00');
        $this->insertCommand($zone, $bare['node'], $bare['name'], 'DONE', 'irrigation_start', 'irrigation_start', 5000, '2026-10-04 09:00:00');

        $balance = $this->readBalance($zone);

        $this->assertSame(2, $balance['irrigation_commands']);
        $this->assertEqualsWithDelta(15.0, $balance['commanded_sec'], 0.001);
        $this->assertNull($balance['commanded_ml']);
        $this->assertSame('calibration_missing', $balance['commanded_ml_status']);
        $this->assertNull($balance['dli_mol']);
        $this->assertSame('not_configured', $balance['dli_status']);
    }

    public function test_dli_mol_is_one_for_ppfd_and_lux_is_not_converted(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $start = Carbon::parse('2026-10-04 00:00:00', 'UTC')->getTimestamp();
        $formula = DliIntegral::integrate([
            ['ts' => $start, 'value' => 100],
            ['ts' => $start + 10000, 'value' => 100],
        ], 10000);
        $this->assertSame(1.0, $formula['dli_mol']);
        $this->assertSame('ok', $formula['status']);

        $zone = $this->makeZone('Europe/Moscow');
        $other = $this->makeZone('Europe/Moscow', $zone->greenhouse);
        $this->bindDliTarget($zone, 5.0);
        $this->bindDliTarget($other, 5.0);
        $ppfd = $this->makeLightSensor($zone, 'ppfd');
        $foreign = $this->makeLightSensor($other, 'ppfd');
        $origin = Carbon::parse('2026-10-04 06:00:00', 'UTC');
        for ($index = 0; $index <= 20; $index++) {
            $this->insertSample($ppfd, $zone->id, $origin->copy()->addSeconds($index * 500), 100);
        }
        $this->insertSample($ppfd, $zone->id, Carbon::parse('2026-10-03 20:00:00', 'UTC'), 9000);
        $this->insertSample($foreign, $other->id, $origin, 9000);

        $luxZone = $this->makeZone('Europe/Moscow');
        $this->bindDliTarget($luxZone, 5.0);
        $lux = $this->makeLightSensor($luxZone, 'lux');
        for ($index = 0; $index <= 20; $index++) {
            $this->insertSample($lux, $luxZone->id, $origin->copy()->addSeconds($index * 500), 100);
        }

        $gapZone = $this->makeZone('Europe/Moscow');
        $this->bindDliTarget($gapZone, 0.1);
        $gap = $this->makeLightSensor($gapZone, 'ppfd');
        $this->insertSample($gap, $gapZone->id, $origin, 100);
        $this->insertSample($gap, $gapZone->id, $origin->copy()->addSeconds(1000), 100);

        $eventsBefore = $this->zoneEventCount($zone->id);
        $alertsBefore = (int) DB::table('alerts')->where('zone_id', $zone->id)->count();
        $balance = $this->readBalance($zone);
        $luxBalance = $this->readBalance($luxZone);
        $gapBalance = $this->readBalance($gapZone);

        $this->assertSame($eventsBefore, $this->zoneEventCount($zone->id));
        $this->assertSame($alertsBefore, (int) DB::table('alerts')->where('zone_id', $zone->id)->count());
        $this->assertEqualsWithDelta(1.0, $balance['dli_mol'], 0.000001);
        $this->assertSame('within_target', $balance['dli_status']);
        $this->assertNull($luxBalance['dli_mol']);
        $this->assertSame('sensor_unavailable', $luxBalance['dli_status']);
        $this->assertNull($gapBalance['dli_mol']);
        $this->assertSame('gap', $gapBalance['dli_status']);
    }

    private function readBalance(Zone $zone): array
    {
        Cache::flush();
        $service = app(ZoneAutomationStateService::class);
        $service->cacheState($zone->id, [
            'zone_id' => $zone->id,
            'state' => 'READY',
            'state_details' => ['failed' => false],
        ]);

        $payload = $service->resolveCachedBootstrap($zone->fresh());
        $this->assertIsArray($payload);

        return $payload['day_balance'];
    }

    private function makeZone(string $timezone, ?Greenhouse $greenhouse = null): Zone
    {
        if ($greenhouse === null) {
            $greenhouse = Greenhouse::factory()->create([
                'timezone' => $timezone,
            ]);
            $this->greenhouseIds[] = (int) $greenhouse->id;
        }

        $zone = Zone::factory()->create([
            'status' => 'online',
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

    private function bindDliTarget(Zone $zone, float $target): void
    {
        $suffix = Str::lower(Str::uuid()->toString());
        $recipeId = (int) DB::table('recipes')->insertGetId([
            'name' => 'g5-dli-'.$suffix,
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
            'name' => 'DLI',
            'dli_target' => $target,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->phaseIds[] = $phaseId;
        DB::table('grow_cycles')->where('id', $cycleId)->update(['current_phase_id' => $phaseId]);
    }

    private function makeLightSensor(Zone $zone, string $unit): int
    {
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'light',
            'status' => 'online',
        ]);
        $this->nodeIds[] = (int) $node->id;
        $this->channelIds[] = (int) DB::table('node_channels')->insertGetId([
            'node_id' => $node->id,
            'channel' => 'light_level',
            'type' => 'SENSOR',
            'metric' => 'LIGHT_INTENSITY',
            'unit' => $unit,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $sensorId = (int) DB::table('sensors')->insertGetId([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'LIGHT_INTENSITY',
            'label' => 'light_level',
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
        $this->sensorIds[] = $sensorId;

        return $sensorId;
    }

    private function insertSample(int $sensorId, int $zoneId, Carbon $ts, float $value): void
    {
        $this->sampleIds[] = (int) DB::table('telemetry_samples')->insertGetId([
            'sensor_id' => $sensorId,
            'zone_id' => $zoneId,
            'ts' => $ts->utc()->format('Y-m-d H:i:s'),
            'value' => $value,
            'quality' => 'GOOD',
            'created_at' => now(),
        ]);
    }

    private function insertCommand(
        Zone $zone,
        DeviceNode $node,
        string $channel,
        string $status,
        string $taskType,
        string $plannerStep,
        ?int $durationMs,
        string $createdAtUtc,
    ): void {
        $createdAt = Carbon::parse($createdAtUtc, 'UTC')->format('Y-m-d H:i:s');
        $suffix = Str::lower(Str::uuid()->toString());

        $taskId = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => $taskType,
            'status' => 'completed',
            'idempotency_key' => 'g2-'.$suffix,
            'scheduled_for' => $createdAt,
            'due_at' => $createdAt,
            'completed_at' => $createdAt,
            'created_at' => $createdAt,
            'updated_at' => $createdAt,
        ]);
        $this->taskIds[] = $taskId;

        $commandId = (int) DB::table('commands')->insertGetId([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'channel' => $channel,
            'cmd' => 'run_pump',
            'status' => $status,
            'cmd_id' => 'g2-'.$suffix,
            'duration_ms' => $durationMs,
            'created_at' => $createdAt,
            'updated_at' => $createdAt,
        ]);
        $this->commandIds[] = $commandId;

        DB::table('ae_commands')->insert([
            'task_id' => $taskId,
            'step_no' => 1,
            'planner_step' => $plannerStep,
            'node_uid' => (string) $node->uid,
            'channel' => $channel,
            'external_id' => (string) $commandId,
            'publish_status' => 'accepted',
            'terminal_status' => $status === 'DONE' ? 'DONE' : 'ERROR',
            'created_at' => $createdAt,
            'updated_at' => $createdAt,
        ]);
    }

    private function zoneEventCount(int $zoneId): int
    {
        if (! DB::getSchemaBuilder()->hasTable('zone_events')) {
            return 0;
        }

        return (int) DB::table('zone_events')->where('zone_id', $zoneId)->count();
    }

    private function deleteFixture(): void
    {
        if ($this->sampleIds !== []) {
            DB::table('telemetry_samples')->whereIn('id', $this->sampleIds)->delete();
        }
        if ($this->sensorIds !== []) {
            DB::table('sensors')->whereIn('id', $this->sensorIds)->delete();
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
        if ($this->calibrationIds !== []) {
            DB::table('pump_calibrations')->whereIn('id', $this->calibrationIds)->delete();
        }
        if ($this->channelIds !== []) {
            DB::table('node_channels')->whereIn('id', $this->channelIds)->delete();
        }
        if ($this->taskIds !== []) {
            DB::table('ae_commands')->whereIn('task_id', $this->taskIds)->delete();
            DB::table('ae_tasks')->whereIn('id', $this->taskIds)->delete();
        }
        if ($this->commandIds !== []) {
            DB::table('commands')->whereIn('id', $this->commandIds)->delete();
        }
        if ($this->nodeIds !== []) {
            DB::table('nodes')->whereIn('id', $this->nodeIds)->delete();
        }
        if ($this->zoneIds !== []) {
            DB::table('zones')->whereIn('id', $this->zoneIds)->delete();
        }
        if ($this->greenhouseIds !== []) {
            DB::table('greenhouses')->whereIn('id', $this->greenhouseIds)->delete();
        }
    }
}
