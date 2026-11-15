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
        User::factory()->create(['role' => 'operator']);
        config(['services.python_bridge.token' => 'node-channel-service-token']);
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

        $response = $this->withHeader('Authorization', 'Bearer node-channel-service-token')
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

    public function test_user_roles_cannot_update_service_config_without_service_token(): void
    {
        $node = DeviceNode::factory()->create();
        $channel = NodeChannel::create([
            'node_id' => $node->id, 'channel' => 'pump_a', 'type' => 'actuator',
            'metric' => 'PUMP', 'config' => ['existing' => true],
        ]);
        foreach (['viewer', 'operator', 'admin'] as $role) {
            $user = User::factory()->create(['role' => $role]);
            $this->actingAs($user, 'sanctum')->patchJson("/api/node-channels/{$channel->id}", [
                'config' => ['existing' => false],
            ])->assertUnauthorized();
            $this->assertSame(['existing' => true], $channel->fresh()->config);
        }
    }
}
