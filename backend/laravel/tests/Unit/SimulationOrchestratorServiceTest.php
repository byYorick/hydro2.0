<?php

namespace Tests\Unit;

use App\Enums\GrowCycleStatus;
use App\Models\AutomationEffectiveBundle;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\RecipeRevision;
use App\Services\GrowCycleService;
use App\Services\SimulationOrchestratorService;
use Illuminate\Support\Facades\DB;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SimulationOrchestratorServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_full_simulation_marks_zone_running_and_enables_controls(): void
    {
        $sourceZone = Zone::factory()->create([
            'status' => 'online',
            'water_state' => 'NORMAL_RECIRC',
            'capabilities' => [
                'ph_control' => false,
                'ec_control' => false,
                'climate_control' => false,
                'light_control' => false,
                'irrigation_control' => false,
            ],
        ]);

        $service = app(SimulationOrchestratorService::class);
        $context = $service->createSimulationContext($sourceZone, null, ['full_simulation' => true]);

        $simZone = $context['zone'];
        $simCycle = $context['grow_cycle'];

        $this->assertSame('RUNNING', $simZone->status);
        $this->assertTrue($simZone->capabilities['ph_control'] ?? false);
        $this->assertTrue($simZone->capabilities['ec_control'] ?? false);
        $this->assertTrue($simZone->capabilities['climate_control'] ?? false);
        $this->assertTrue($simZone->capabilities['light_control'] ?? false);
        $this->assertTrue($simZone->capabilities['irrigation_control'] ?? false);

        $nodes = DeviceNode::query()->where('zone_id', $simZone->id)->get();
        $this->assertNotEmpty($nodes);
        $this->assertSame(
            $nodes->count(),
            $nodes->where('status', 'online')->count()
        );
        $this->assertEqualsCanonicalizing(['ec', 'irrig', 'ph'], $nodes->pluck('type')->unique()->values()->all());
        $this->assertSame('irrig', $context['node']?->type);

        $irrigNode = $nodes->firstWhere('type', 'irrig');
        $phNode = $nodes->firstWhere('type', 'ph');
        $ecNode = $nodes->firstWhere('type', 'ec');
        $this->assertNotNull($irrigNode);
        $this->assertNotNull($phNode);
        $this->assertNotNull($ecNode);

        $irrigChannels = NodeChannel::query()
            ->where('node_id', $irrigNode->id)
            ->pluck('channel')
            ->all();
        $this->assertContains('valve_clean_fill', $irrigChannels);
        $this->assertContains('valve_solution_fill', $irrigChannels);
        $this->assertContains('valve_solution_supply', $irrigChannels);
        $this->assertContains('valve_irrigation', $irrigChannels);
        $this->assertContains('pump_main', $irrigChannels);
        $this->assertContains('level_clean_max', $irrigChannels);
        $this->assertContains('level_solution_max', $irrigChannels);

        $phChannels = NodeChannel::query()
            ->where('node_id', $phNode->id)
            ->pluck('channel')
            ->all();
        $this->assertContains('system', $phChannels);
        $this->assertContains('ph_sensor', $phChannels);
        $this->assertContains('pump_acid', $phChannels);
        $this->assertContains('pump_base', $phChannels);

        $ecChannels = NodeChannel::query()
            ->where('node_id', $ecNode->id)
            ->pluck('channel')
            ->all();
        $this->assertContains('system', $ecChannels);
        $this->assertContains('ec_sensor', $ecChannels);
        $this->assertContains('pump_a', $ecChannels);
        $this->assertContains('pump_d', $ecChannels);
        $this->assertDatabaseHas('automation_effective_bundles', [
            'scope_type' => 'zone',
            'scope_id' => $simZone->id,
            'status' => 'valid',
        ]);
        $this->assertDatabaseHas('automation_effective_bundles', [
            'scope_type' => 'grow_cycle',
            'scope_id' => $simCycle->id,
            'status' => 'valid',
        ]);
        $zoneBundle = AutomationEffectiveBundle::query()
            ->where('scope_type', 'zone')
            ->where('scope_id', $simZone->id)
            ->first();
        $this->assertNotNull($zoneBundle?->bundle_revision);
        $this->assertNotEmpty(data_get($zoneBundle?->config, 'zone.logic_profile.active_profile.command_plans.plans.diagnostics.steps'));
    }

    public function test_simulation_grow_cycle_starts_after_outer_transaction_commits(): void
    {
        $sourceZone = Zone::factory()->create([
            'status' => 'online',
            'water_state' => 'NORMAL_RECIRC',
        ]);

        $createTransactionLevel = null;
        $startTransactionLevel = null;
        $growCycleService = Mockery::mock(GrowCycleService::class);
        $growCycleService
            ->shouldReceive('createCycle')
            ->once()
            ->ordered()
            ->andReturnUsing(function (Zone $simZone, RecipeRevision $revision, int $plantId, array $data) use (&$createTransactionLevel) {
                $createTransactionLevel = DB::transactionLevel();
                $this->assertGreaterThan(0, $createTransactionLevel);
                $this->assertFalse((bool) ($data['start_immediately'] ?? true));

                return GrowCycle::factory()->create([
                    'greenhouse_id' => $simZone->greenhouse_id,
                    'zone_id' => $simZone->id,
                    'plant_id' => $plantId,
                    'recipe_id' => $revision->recipe_id,
                    'recipe_revision_id' => $revision->id,
                    'status' => GrowCycleStatus::PLANNED,
                ])->fresh();
            });
        $growCycleService
            ->shouldReceive('syncCycleConfigDocuments')
            ->once()
            ->ordered()
            ->with(Mockery::type(GrowCycle::class), [], null);
        $growCycleService
            ->shouldReceive('startCycle')
            ->once()
            ->ordered()
            ->andReturnUsing(function (GrowCycle $cycle) use (&$startTransactionLevel) {
                $startTransactionLevel = DB::transactionLevel();
                $this->assertSame(GrowCycleStatus::PLANNED, $cycle->status);

                $cycle->update([
                    'status' => GrowCycleStatus::RUNNING,
                    'started_at' => now(),
                    'recipe_started_at' => now(),
                    'phase_started_at' => now(),
                    'planting_at' => now(),
                ]);

                return $cycle->fresh();
            });

        $service = new SimulationOrchestratorService($growCycleService);
        $context = $service->createSimulationContext($sourceZone, null, ['full_simulation' => true]);

        $this->assertNotNull($createTransactionLevel);
        $this->assertNotNull($startTransactionLevel);
        $this->assertLessThan($createTransactionLevel, $startTransactionLevel);
        $this->assertSame(GrowCycleStatus::RUNNING, $context['grow_cycle']->status);
    }

    public function test_simulation_context_deduplicates_duplicate_runtime_node_types(): void
    {
        $sourceZone = Zone::factory()->create([
            'status' => 'online',
            'water_state' => 'NORMAL_RECIRC',
            'capabilities' => [
                'ph_control' => true,
                'ec_control' => true,
                'irrigation_control' => true,
            ],
        ]);

        $legacyPhNode = DeviceNode::factory()->create([
            'zone_id' => $sourceZone->id,
            'type' => 'ph',
            'status' => 'online',
            'validated' => true,
        ]);
        NodeChannel::create([
            'node_id' => $legacyPhNode->id,
            'channel' => 'ph_sensor',
            'type' => 'SENSOR',
            'metric' => 'PH',
        ]);

        $runtimePhNode = DeviceNode::factory()->create([
            'zone_id' => $sourceZone->id,
            'type' => 'ph',
            'status' => 'online',
            'validated' => true,
        ]);
        foreach (['system', 'ph_sensor', 'pump_acid', 'pump_base'] as $channel) {
            NodeChannel::create([
                'node_id' => $runtimePhNode->id,
                'channel' => $channel,
                'type' => $channel === 'ph_sensor' ? 'SENSOR' : 'ACTUATOR',
                'metric' => $channel === 'ph_sensor' ? 'PH' : 'PUMP',
            ]);
        }

        $irrigNode = DeviceNode::factory()->create([
            'zone_id' => $sourceZone->id,
            'type' => 'irrig',
            'status' => 'online',
            'validated' => true,
        ]);
        foreach (['pump_main', 'valve_clean_fill', 'valve_solution_fill', 'valve_solution_supply', 'valve_irrigation'] as $channel) {
            NodeChannel::create([
                'node_id' => $irrigNode->id,
                'channel' => $channel,
                'type' => 'ACTUATOR',
                'metric' => 'RELAY',
            ]);
        }

        $ecNode = DeviceNode::factory()->create([
            'zone_id' => $sourceZone->id,
            'type' => 'ec',
            'status' => 'online',
            'validated' => true,
        ]);
        foreach (['system', 'ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d'] as $channel) {
            NodeChannel::create([
                'node_id' => $ecNode->id,
                'channel' => $channel,
                'type' => $channel === 'ec_sensor' ? 'SENSOR' : 'ACTUATOR',
                'metric' => $channel === 'ec_sensor' ? 'EC' : 'PUMP',
            ]);
        }

        $service = app(SimulationOrchestratorService::class);
        $context = $service->createSimulationContext($sourceZone, null, ['full_simulation' => true]);

        $simZone = $context['zone'];
        $simNodes = DeviceNode::query()
            ->where('zone_id', $simZone->id)
            ->orderBy('id')
            ->get();

        $this->assertCount(3, $simNodes);
        $this->assertSame(1, $simNodes->where('type', 'ph')->count());

        $simPhNode = $simNodes->firstWhere('type', 'ph');
        $this->assertNotNull($simPhNode);
        $this->assertSame(
            1,
            NodeChannel::query()
                ->where('node_id', $simPhNode->id)
                ->where('channel', 'system')
                ->count()
        );
    }
}
