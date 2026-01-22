<?php

namespace Tests\Unit;

use App\Jobs\StopSimulationNodesJob;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Services\PythonBridgeService;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class StopSimulationNodesJobTest extends TestCase
{
    use RefreshDatabase;

    public function test_stop_simulation_nodes_sends_stop_commands_for_actuators(): void
    {
        $zone = Zone::factory()->create();
        $simulation = ZoneSimulation::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'running',
            'scenario' => [
                'recipe_id' => 1,
                'simulation' => [
                    'real_started_at' => now()->toIso8601String(),
                    'sim_started_at' => now()->toIso8601String(),
                    'real_duration_minutes' => 10,
                    'time_scale' => 12,
                ],
            ],
        ]);

        $nodeOnline = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        NodeChannel::create([
            'node_id' => $nodeOnline->id,
            'channel' => 'pump_main',
            'type' => 'ACTUATOR',
            'config' => ['actuator_type' => 'PUMP'],
        ]);
        NodeChannel::create([
            'node_id' => $nodeOnline->id,
            'channel' => 'fan_pwm',
            'type' => 'ACTUATOR',
            'config' => ['actuator_type' => 'PWM'],
        ]);

        $nodeOffline = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'offline',
        ]);
        NodeChannel::create([
            'node_id' => $nodeOffline->id,
            'channel' => 'pump_off',
            'type' => 'ACTUATOR',
            'config' => ['actuator_type' => 'PUMP'],
        ]);

        $otherZone = Zone::factory()->create();
        $otherNode = DeviceNode::factory()->create([
            'zone_id' => $otherZone->id,
            'status' => 'online',
        ]);
        NodeChannel::create([
            'node_id' => $otherNode->id,
            'channel' => 'pump_other',
            'type' => 'ACTUATOR',
            'config' => ['actuator_type' => 'PUMP'],
        ]);

        $seen = [];
        $mock = Mockery::mock(PythonBridgeService::class);
        $mock->shouldReceive('sendNodeCommand')
            ->twice()
            ->andReturnUsing(function ($node, $payload) use (&$seen) {
                $seen[] = [$node->uid, $payload];
                return 'cmd-test';
            });
        $this->app->instance(PythonBridgeService::class, $mock);

        $job = new StopSimulationNodesJob($zone->id, $simulation->id, 'sim-job');
        $job->handle($mock);

        $this->assertCount(2, $seen);
        $payloadByChannel = [];
        foreach ($seen as $entry) {
            $payloadByChannel[$entry[1]['channel']] = $entry[1];
        }

        $this->assertSame('set_relay', $payloadByChannel['pump_main']['type']);
        $this->assertSame(['state' => false], $payloadByChannel['pump_main']['params']);
        $this->assertSame('set_pwm', $payloadByChannel['fan_pwm']['type']);
        $this->assertSame(['value' => 0], $payloadByChannel['fan_pwm']['params']);
    }

    public function test_stop_simulation_nodes_requires_simulation_meta(): void
    {
        $zone = Zone::factory()->create();
        $simulation = ZoneSimulation::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'running',
            'scenario' => [
                'recipe_id' => 1,
            ],
        ]);

        $nodeOnline = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        NodeChannel::create([
            'node_id' => $nodeOnline->id,
            'channel' => 'pump_main',
            'type' => 'ACTUATOR',
            'config' => ['actuator_type' => 'PUMP'],
        ]);

        $mock = Mockery::mock(PythonBridgeService::class);
        $mock->shouldReceive('sendNodeCommand')->never();
        $this->app->instance(PythonBridgeService::class, $mock);

        $job = new StopSimulationNodesJob($zone->id, $simulation->id, 'sim-job');
        $job->handle($mock);
    }
}
