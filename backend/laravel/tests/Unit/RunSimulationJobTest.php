<?php

namespace Tests\Unit;

use App\Jobs\RunSimulationJob;
use App\Models\DeviceNode;
use App\Models\GrowCycle;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\DigitalTwinClient;
use App\Services\SimulationOrchestratorService;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Queue;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class RunSimulationJobTest extends TestCase
{
    use RefreshDatabase;

    public function test_live_simulation_starts_node_sim_session(): void
    {
        Queue::fake();

        $zone = Zone::factory()->create(['uid' => 'zn-sim-1']);
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'uid' => 'nd-sim-1',
            'hardware_id' => 'hw-sim-1',
            'type' => 'ph',
        ]);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'ph_sensor',
            'type' => 'SENSOR',
        ]);
        NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'main_pump',
            'type' => 'ACTUATOR',
        ]);

        $simZone = Zone::factory()->create(['greenhouse_id' => $zone->greenhouse_id]);
        $simCycle = GrowCycle::factory()->create(['zone_id' => $simZone->id]);

        $orchestrator = Mockery::mock(SimulationOrchestratorService::class);
        $orchestrator
            ->shouldReceive('createSimulationContext')
            ->once()
            ->with(
                Mockery::on(fn ($zoneArg) => $zoneArg instanceof Zone && $zoneArg->id === $zone->id),
                1,
                ['full_simulation' => false]
            )
            ->andReturn([
                'zone' => $simZone,
                'grow_cycle' => $simCycle,
            ]);
        $this->app->instance(SimulationOrchestratorService::class, $orchestrator);

        $client = Mockery::mock(DigitalTwinClient::class);
        $client
            ->shouldReceive('startLiveSimulation')
            ->once()
            ->andReturn(['simulation_id' => 77]);

        $job = new RunSimulationJob($zone->id, [
            'duration_hours' => 24,
            'step_minutes' => 10,
            'scenario' => ['recipe_id' => 1],
            'sim_duration_minutes' => 5,
        ], 'sim-job-1');

        $job->handle($client, $orchestrator);

        $cached = Cache::get('simulation:sim-job-1');
        $this->assertNotNull($cached);
        $this->assertSame('processing', $cached['status'] ?? null);
        $this->assertSame(77, $cached['simulation_id'] ?? null);
        $this->assertSame($simZone->id, $cached['simulation_zone_id'] ?? null);
        $this->assertSame($simCycle->id, $cached['simulation_grow_cycle_id'] ?? null);

    }
}
