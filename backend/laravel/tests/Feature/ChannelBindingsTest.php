<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Tests\TestCase;

class ChannelBindingsTest extends TestCase
{
    use RefreshDatabase;

    public function test_operator_can_create_channel_binding_with_node_channel(): void
    {
        Event::fake();

        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $nodeChannel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump1',
        ]);
        $instance = InfrastructureInstance::create([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'Main pump',
            'required' => true,
            'capacity_liters' => null,
            'flow_rate' => null,
            'specs' => null,
        ]);

        $response = $this->actingAs($user)->postJson('/api/channel-bindings', [
            'infrastructure_instance_id' => $instance->id,
            'node_channel_id' => $nodeChannel->id,
            'direction' => 'actuator',
            'role' => 'main_pump',
        ]);

        $response->assertStatus(201);
        $response->assertJsonPath('status', 'ok');
        $this->assertDatabaseHas('channel_bindings', [
            'infrastructure_instance_id' => $instance->id,
            'node_channel_id' => $nodeChannel->id,
            'direction' => 'actuator',
            'role' => 'main_pump',
        ]);
    }
}
