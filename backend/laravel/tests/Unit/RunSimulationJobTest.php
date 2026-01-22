<?php

namespace Tests\Unit;

use App\Jobs\CompleteSimulationJob;
use App\Jobs\RunSimulationJob;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Services\DigitalTwinClient;
use App\Services\NodeSimManagerClient;
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

        $nodeSimManager = Mockery::mock(NodeSimManagerClient::class);
        $nodeSimManager
            ->shouldReceive('startSession')
            ->once()
            ->withArgs(function ($simulation, $sessionId) use ($zone) {
                return $sessionId === 'sim-job-1'
                    && $simulation instanceof ZoneSimulation
                    && $simulation->zone_id === $zone->id;
            });
        $this->app->instance(NodeSimManagerClient::class, $nodeSimManager);

        $client = Mockery::mock(DigitalTwinClient::class);

        $job = new RunSimulationJob($zone->id, [
            'duration_hours' => 24,
            'step_minutes' => 10,
            'scenario' => ['recipe_id' => 1],
            'sim_duration_minutes' => 5,
        ], 'sim-job-1');

        $job->handle($client, $nodeSimManager);

        $simulation = ZoneSimulation::first();
        $this->assertNotNull($simulation);
        $this->assertSame('running', $simulation->status);
        $simulationMeta = $simulation->scenario['simulation'] ?? [];
        $this->assertSame('sim-job-1', $simulationMeta['node_sim_session_id'] ?? null);
        $this->assertSame('pipeline', $simulationMeta['engine'] ?? null);
        $this->assertSame('live', $simulationMeta['mode'] ?? null);

        Queue::assertPushed(CompleteSimulationJob::class);
    }
}
