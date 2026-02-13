<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeChannelControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_service_update_config_updates_node_channel_config(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        $response = $this->actingAs($user, 'sanctum')
            ->patchJson("/api/node-channels/{$channel->id}", [
                'config' => [
                    'pump_calibration' => [
                        'ml_per_sec' => 0.91,
                        'duration_sec' => 30,
                        'actual_ml' => 27.3,
                    ],
                ],
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.id', $channel->id);

        $this->assertDatabaseHas('node_channels', [
            'id' => $channel->id,
        ]);
        $this->assertEquals(
            0.91,
            (float) data_get($channel->fresh()->config, 'pump_calibration.ml_per_sec')
        );
    }
}
